"""Bind an effective Unity policy directly to its completed original capture phase."""

from __future__ import annotations

import time
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture as C
from reproductions.unity_search_baseline.policy import UnitySearchPolicy


class UnityCapturePolicyBinding:
    """Resolve rules without supplemental candidate files or changing capture split identity."""

    def __init__(
        self,
        baseline: UnitySearchBaseline,
        phase: str,
        *,
        reference_sha256: str,
        phase_sha256: str,
    ) -> None:
        if phase not in {"probe", "batch", "smoke1", "smoke2", "smoke3", "full"}:
            raise ValueError("Unknown original capture phase")
        if baseline.source_split not in {"train", "validation", "confirmation"}:
            raise ValueError("Native capture split must remain explicit")
        self.baseline, self.phase = baseline, phase
        self.inputs: dict[str, str | None] = {}
        run = baseline.run_dir
        reference_path = run / "references" / f"normalized-{phase}" / "receipt.json"
        reference = A.read_json(self.bind(reference_path, reference_sha256))
        receipt = A.read_json(self.bind(run / f"{phase}-receipt.json", phase_sha256))
        if (
            reference["status"] != "passed"
            or receipt["status"] != "passed"
            or receipt["process_exit_code"] != 0
            or receipt["metadata_restore_conflicts"]
        ):
            raise ValueError("Policy requires completed successful original capture")
        config = A.read_json(self.bind(run / f"{phase}-config.json"))
        identity = A.read_json(self.bind(run / "identity.json"))
        self.bind(run / "protocol-lock.json")
        self.bind(run / f"{phase}-launch.json")
        self.bind(baseline.manifest)
        self.bind(run / f"{phase}-native.jsonl")
        assembly = run / f"{phase}-assembly.json"
        self.watch_optional(assembly)
        if assembly.exists():
            cache_path = run / f"{phase}-parameters.jsonl"
        else:
            cache_path = (
                baseline.project / config["cacheDirectory"] / "parameter_cache_detail.jsonl"
            ).resolve()
            if not cache_path.is_relative_to((baseline.project / "ASTC_Cache").resolve()):
                raise ValueError("Native policy cache escapes the original project cache")
        self.watch_optional(cache_path)
        self.watch_optional(cache_path.with_suffix(".json"))
        if not cache_path.is_file() and not cache_path.with_suffix(".json").is_file():
            raise ValueError("Original native policy cache is missing")
        provenance = baseline.audit(phase)
        if provenance != reference["capture_provenance"] or provenance != receipt["provenance"]:
            raise ValueError("Policy audit differs from the original captured provenance")
        if assembly.exists():
            bundle = A.read_json(assembly)
            for entry in bundle["inputs"]:
                self.bind(Path(entry["path"]), entry["sha256"])
            for name, digest in bundle["outputs"].items():
                if Path(name).name != name:
                    raise ValueError("Recovery output must remain within the capture run")
                self.bind(run / name, digest)
        self.bind(baseline.editor, str(provenance["editor_sha256"]))
        for name, digest in identity["encoder_dlls"].items():
            self.bind(baseline.project / "Assets/Editor/Astc/Plugins" / name, digest)
        cache = baseline.read_parameter_cache(cache_path)
        tables = [r["tableConfig"] for r in cache if r.get("_kind") == "astc_cache_table_config"]
        if len(tables) != 1:
            raise ValueError("Original capture requires exactly one effective policy table")
        self.policy = UnitySearchPolicy(tables[0])
        self.effective_fingerprint = A.fingerprint(self.policy.table)
        expected = [baseline._asset_key(r["path"]) for r in config["assets"]]
        rows = reference["rows"]
        records = [r for r in cache if "filePath" in r]
        choices = {baseline._asset_key(r["filePath"]): r for r in records}
        native_rows = baseline._read_lines(run / f"{phase}-native.jsonl")
        native = {baseline._asset_key(r["asset"]): r for r in native_rows}
        if (
            not expected
            or len(set(expected)) != len(expected)
            or reference["images"] != len(expected)
            or len(rows) != len(expected)
            or [baseline._asset_key(r["path"]) for r in rows] != expected
            or len(records) != len(expected)
            or set(choices) != set(expected)
            or len(native_rows) != len(expected)
            or set(native) != set(expected)
        ):
            raise ValueError("Original policy/reference/native coverage or order differs")
        for row, key in zip(rows, expected, strict=True):
            cached, selected = choices[key], native[key]
            if (
                row.get("source_split", "train") != baseline.source_split
                or row["selection"] != selected
                or cached["fileHash"].lower() != row["source_md4"].lower()
                or (cached["blockSize"], cached["qualityLevel"])
                != (selected["block_size"], selected["preset"])
                or cached.get("rdo") is not False
                or selected["search_executed"] is not True
                or selected["cache_hit"] is not False
            ):
                raise ValueError("Original source split, hash or search selection differs")
        self.binding = {
            "capture_run": str(run),
            "phase": phase,
            "source_split": baseline.source_split,
            "reference_receipt_sha256": reference_sha256,
            "phase_receipt_sha256": phase_sha256,
            "images": len(rows),
            "legacy_train_rows_without_split": sum("source_split" not in row for row in rows),
            "cache_path": str(cache_path),
            "native_table": tables[0],
            "policy_table": dict(self.policy.table),
            "effective_policy_fingerprint": self.effective_fingerprint,
            "policy_fingerprint": A.fingerprint(tables[0]),
            "provenance": provenance,
            "inputs_sha256": self.inputs,
            "scope": "Original policy binding only; no candidate replay or model evaluation",
        }
        self.verify()

    def bind(self, path: Path, expected: str | None = None) -> Path:
        path = path.resolve()
        digest = A.sha256_file(path)
        if expected is not None and digest != expected:
            raise ValueError(f"Bound capture policy input changed: {path}")
        if str(path) in self.inputs and self.inputs[str(path)] != digest:
            raise ValueError("Capture policy input changed during binding")
        self.inputs[str(path)] = digest
        return path

    def watch_optional(self, path: Path) -> None:
        if path.exists():
            self.bind(path)
        else:
            self.inputs[str(path.resolve())] = None

    def verify(self) -> None:
        if A.fingerprint(self.policy.table) != self.effective_fingerprint:
            raise ValueError("Bound effective policy changed")
        for name, digest in self.inputs.items():
            path = Path(name)
            if digest is None:
                if path.exists():
                    raise ValueError("An absent capture cache/assembly appeared after binding")
            elif A.sha256_file(path) != digest:
                raise ValueError(f"Bound capture policy input changed: {path}")


class UnityCapturePolicyAudit:
    """Read-only entry for both explicit development and reserved confirmation captures."""

    def __init__(self, root: Path, path: Path) -> None:
        self.root, self.path = root.resolve(), path.resolve()
        self.config_sha = A.sha256_file(self.path)
        self.config = A.read_json(self.path)

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/capture_policy.py",
            "reproductions/unity_search_baseline/policy.py",
            "script/audit_unity_capture_policy.py",
        ]
        return C.execution_sources(root) | {name: A.sha256_file(root / name) for name in names}

    def verify(self) -> None:
        if A.sha256_file(self.path) != self.config_sha:
            raise ValueError("Capture policy audit configuration changed")
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Capture policy audit execution sources changed")
        if not self.config["captures"]:
            raise ValueError("Capture policy audit requires at least one completed capture")
        for entry in self.config["captures"]:
            if A.sha256_file(Path(entry["config"])) != entry["config_sha256"]:
                raise ValueError("Capture configuration changed")

    def baseline(self, entry: JsonDict) -> UnitySearchBaseline:
        path = Path(entry["config"])
        if entry["kind"] == "confirmation":
            capture = C(self.root, path)
            capture.validate()
            return capture.baseline
        if entry["kind"] != "development":
            raise ValueError("Explicit development or confirmation capture kind required")
        config = A.read_json(path)
        return UnitySearchBaseline(
            self.root,
            Path(config["project"]),
            Path(config["editor"]),
            Path(config["manifest"]),
            run_id=config["run_id"],
            capture_references=True,
            source_split=config.get("source_split", "train"),
            capture_paths=config.get("capture_paths"),
        )

    def run(self) -> JsonDict:
        self.verify()
        report = Path(self.config["report"]).resolve()
        public = self.root / "experiment report"
        if not report.is_relative_to(public) or report.is_relative_to(public / ".local"):
            raise ValueError("Capture policy report must be public")
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        started = time.perf_counter()
        state: JsonDict = {
            "status": "running",
            "config_sha256": self.config_sha,
            "bindings": [],
            "source_files_sha256": self.config["sources_sha256"],
            "test_opened": False,
            "model_forward_calls": 0,
            "training_updates": 0,
            "scope": "Original capture policy provenance; no quality replay or inference",
        }
        try:
            completed: list[UnityCapturePolicyBinding] = []
            for entry in self.config["captures"]:
                binding = UnityCapturePolicyBinding(
                    self.baseline(entry),
                    entry["phase"],
                    reference_sha256=entry["reference_receipt_sha256"],
                    phase_sha256=entry["phase_receipt_sha256"],
                )
                state["bindings"].append(binding.binding)
                completed.append(binding)
                A.write_json(report, state)
            self.verify()
            for binding in completed:
                binding.verify()
            state["status"] = "passed"
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state
