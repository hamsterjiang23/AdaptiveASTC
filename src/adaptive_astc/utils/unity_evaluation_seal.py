"""Atomically bind native inference to one model and decision contract per cohort."""

from __future__ import annotations

import copy
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A

T = TypeVar("T")


class UnityEvaluationSeal:
    """A persistent cohort lock and append-only attempt record, including failed forwards.

    The caller audits capture/model provenance and supplies all execution file bindings.
    This class freezes that contract; it does not certify data isolation or model quality.
    """

    def __init__(self, registry: Path, identity: JsonDict) -> None:
        self.registry = registry.resolve()
        self.identity = copy.deepcopy(identity)
        required = {
            "schema",
            "split",
            "cohort_fingerprint",
            "model",
            "inputs_fingerprint",
            "policies_fingerprint",
            "decision",
            "runtime",
            "files_sha256",
        }
        if set(identity) != required or identity["schema"] != "unity_native_inference_v1":
            raise ValueError("Native inference seal requires the complete known schema")
        if identity["split"] not in {"validation", "confirmation"}:
            raise ValueError("Native inference seal needs an explicit evaluation split")
        for key in ["cohort_fingerprint", "inputs_fingerprint", "policies_fingerprint"]:
            value = identity[key]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("Seal fingerprints must be lowercase SHA-256 values")
        if (
            not identity["model"]
            or not identity["decision"]
            or not identity["runtime"]
            or not identity["files_sha256"]
        ):
            raise ValueError("Model, decision, runtime and execution files must be bound")
        self.fingerprint = A.fingerprint(self.identity)
        # Independent of a trial output directory: renaming a run cannot reopen this cohort.
        self.path = self.registry / identity["cohort_fingerprint"] / "seal.json"
        self.record: JsonDict | None = None
        self.verify_files()

    def verify_files(self) -> None:
        if A.fingerprint(self.identity) != self.fingerprint:
            raise ValueError("In-memory native inference contract changed")
        for name, digest in self.identity["files_sha256"].items():
            path = Path(name)
            if not path.is_absolute():
                raise ValueError("Native seal execution files must use absolute paths")
            if digest is None:
                if path.exists():
                    raise ValueError("An absent bound native input appeared")
            elif A.sha256_file(path) != digest:
                raise ValueError(f"Native sealed file changed: {path}")

    def acquire(self) -> JsonDict:
        self.verify_files()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        proposed = {
            "identity": self.identity,
            "fingerprint": self.fingerprint,
            "created_utc": datetime.now(UTC).isoformat(),
            "schema": "unity_native_seal_v1",
        }
        temporary = self.path.parent / f".{uuid.uuid4().hex}.json"
        try:
            A.write_json(temporary, proposed)
            try:
                # Publish complete bytes without replacing another process's winning seal.
                os.link(temporary, self.path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
        record = A.read_json(self.path)
        if (
            set(record) != {"identity", "fingerprint", "created_utc", "schema"}
            or record["schema"] != "unity_native_seal_v1"
            or record["identity"] != self.identity
            or record["fingerprint"] != self.fingerprint
        ):
            raise ValueError("This cohort is already sealed to another inference contract")
        self.record = record
        self.verify()
        return copy.deepcopy(record)

    def verify(self) -> None:
        self.verify_files()
        if self.record is None or A.read_json(self.path) != self.record:
            raise ValueError("Native inference seal is missing or changed")

    def forward(self, operation: Callable[[], T]) -> T:
        """Record an attempt before user code runs; failure never erases the cohort lock."""
        self.verify()
        path = self.path.parent / "attempts" / f"{uuid.uuid4().hex}.json"
        state: JsonDict = {
            "status": "started",
            "started_utc": datetime.now(UTC).isoformat(),
            "seal_fingerprint": self.fingerprint,
            "split": self.identity["split"],
            "test_opened": self.identity["split"] == "confirmation",
            "scope": "An inference operation was attempted; not a successful evaluation claim",
        }
        A.write_json(path, state)
        try:
            result = operation()
            self.verify()
            state["status"] = "passed"
            return result
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["ended_utc"] = datetime.now(UTC).isoformat()
            A.write_json(path, state)
