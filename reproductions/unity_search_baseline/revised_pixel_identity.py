"""Re-audit pixels for an approved development revision and frozen confirmation cohort."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit as I


class UnityRevisedPixelIdentityAudit:
    """Apply only the approved membership change, then recompute all native identities."""

    def __init__(self, root: Path, path: Path) -> None:
        self.root, self.path = root.resolve(), path.resolve()
        raw = self.path.read_bytes()
        self.config = json.loads(raw)
        self.sha = hashlib.sha256(raw).hexdigest()
        self.inputs: dict[str, str] = {str(self.path): self.sha}
        self.pngs: dict[str, str] = {}
        self.output = Path(self.config["output"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        local = self.root / "experiment report/.local"
        if (
            not self.output.is_relative_to(local)
            or not self.report.is_relative_to(self.root / "experiment report")
            or self.report.is_relative_to(local)
        ):
            raise ValueError("Require a new local output and a distinct public report")
        self.verify()

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/revised_pixel_identity.py",
            "reproductions/unity_search_baseline/pixel_identity.py",
            "src/adaptive_astc/utils/artifacts.py",
            "script/audit_unity_revised_pixels.py",
            "pyproject.toml",
            "uv.lock",
        ]
        return {name: A.sha256_file(root / name) for name in names}

    def verify(self) -> None:
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Revised pixel audit execution sources changed")
        for name, digest in (self.inputs | self.pngs).items():
            if A.sha256_file(Path(name)) != digest:
                raise ValueError(f"Revised pixel audit evidence changed: {name}")

    def bound(self, binding: JsonDict) -> JsonDict:
        path = Path(binding["path"]).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != binding["sha256"] or (
            str(path) in self.inputs and self.inputs[str(path)] != digest
        ):
            raise ValueError("Frozen revision evidence changed")
        self.inputs[str(path)] = digest
        return json.loads(raw)

    def audited_rows(self, key: str) -> list[JsonDict]:
        report = self.bound(self.config[key])
        if report["status"] != "passed" or report["splits_modified"] is not False:
            raise ValueError("Require completed immutable original pixel audit reports")
        for name, digest in report["inputs_sha256"].items():
            self.bound({"path": name, "sha256": digest})
        details = self.bound({"path": report["details"], "sha256": report["details_sha256"]})
        rows = details["rows"]
        if dict(Counter(row["source_split"] for row in rows)) != report["counts"]:
            raise ValueError("Original pixel audit coverage differs from its details")
        for identity, summary in [("rgba_identity", "rgba"), ("rgb_identity", "rgb_only")]:
            if I.group_duplicates(rows, identity)[1] != report[summary]:
                raise ValueError("Original duplicate summaries do not match their identities")
        return rows

    @staticmethod
    def select(
        old: list[JsonDict], added: list[JsonDict], reservation: JsonDict, corpus: JsonDict
    ) -> list[JsonDict]:
        def key(row: JsonDict) -> str:
            return row["path"].replace("\\", "/").casefold()

        def unique(rows: list[JsonDict]) -> dict[str, JsonDict]:
            result = {key(row): row for row in rows}
            if len(result) != len(rows):
                raise ValueError("Duplicate asset identity in pixel audit")
            return result

        old_map, added_map = unique(old), unique(added)
        changes = reservation["replacements"]
        removed = {item["old_path"].replace("\\", "/").casefold() for item in changes}
        expected_new = {item["new_path"].replace("\\", "/").casefold() for item in changes}
        if len(removed) != len(changes) or len(expected_new) != len(changes):
            raise ValueError("Approved replacement mapping is not one-to-one")
        if set(added_map) != expected_new or set(added_map) & set(old_map):
            raise ValueError("Measured replacements differ from approved new identities")
        if not removed <= set(old_map):
            raise ValueError("Approved removed identities are absent from original pixels")
        for change in changes:
            before = old_map[change["old_path"].replace("\\", "/").casefold()]
            after = added_map[change["new_path"].replace("\\", "/").casefold()]
            if before["source_split"] != change["split"] or (
                after["source_split"] != change["split"]
            ):
                raise ValueError("Replacement changes a split or confirmation membership")
            if change["split"] not in {"train", "validation"}:
                raise ValueError("Only development replacements are approved")
        available = {name: row for name, row in old_map.items() if name not in removed}
        available.update(added_map)
        result = []
        for split in ["train", "validation"]:
            for sample in corpus["splits"][split]:
                row = available.pop(key(sample))
                if row["source_split"] != split or (
                    row["reference_sha256"] != sample["reference_sha256"]
                    or Path(row["reference"]).resolve() != Path(sample["reference"]).resolve()
                    or row["callback_rgba_sha256"] != sample["actual_options"]["rgba_sha256"]
                ):
                    raise ValueError("Final corpus pixel origin differs from capture audit")
                result.append(row)
        confirmation = [row for row in old if row["source_split"] == "confirmation"]
        if set(available) != {key(row) for row in confirmation}:
            raise ValueError("Unapproved development membership change")
        result.extend(confirmation)
        return result

    def run(self) -> JsonDict:
        started = time.perf_counter()
        if self.output.exists() or self.report.exists():
            raise FileExistsError("Use new revision audit output/report identities")
        revision = self.bound(self.config["corpus_revision_report"])
        corpus = self.bound(self.config["corpus"])
        reservation = self.bound(self.config["reservation"])
        if revision["status"] != "passed" or (
            revision["corpus_sha256"] != self.config["corpus"]["sha256"]
            or Path(revision["corpus"]).resolve() != Path(self.config["corpus"]["path"]).resolve()
            or reservation["status"] != "reserved"
        ):
            raise ValueError("Require the completed approved revised corpus")
        revision_config = corpus["config"]["revision"]
        if revision_config["reservation"] != self.config["reservation"]:
            raise ValueError("Corpus and pixel audit use different approvals")
        if (
            A.fingerprint(corpus["config"]) != corpus["binding"]
            or A.fingerprint({"binding": corpus["binding"], "splits": corpus["splits"]})
            != corpus["fingerprint"]
        ):
            raise ValueError("Revised corpus fingerprint differs")
        old, added = [self.audited_rows(key) for key in ["original_pixels", "replacement_pixels"]]
        rows = self.select(old, added, reservation, corpus)
        counts = dict(Counter(row["source_split"] for row in rows))
        if counts != self.config["expected_counts"] or any(
            counts[split] != reservation["counts"][split] for split in ["train", "validation"]
        ):
            raise ValueError("Final revised pixel coverage differs")
        self.output.mkdir(parents=True, exist_ok=False)
        self.report.parent.mkdir(parents=True, exist_ok=True)
        state: JsonDict = {
            "status": "running",
            "config_sha256": self.sha,
            "sources_sha256": self.config["sources_sha256"],
            "coverage": "approved_revised_native_cohort",
            "scope": "Exact dimensions + RGBA8; RGB-only diagnostic; near audit separate",
            "splits_modified": False,
            "cohort_revision_applied_before_audit": True,
            "training_updates": 0,
            "test_opened": False,
            "independent_test_isolation_proven": False,
        }
        with self.report.open("x", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
        try:
            for row in rows:
                path = Path(row["reference"]).resolve()
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if digest != row["reference_sha256"]:
                    raise ValueError("Native reference PNG changed since original pixel audit")
                self.pngs[str(path)] = digest
                pixels = I.pixel_identity(raw, row["width"], row["height"])
                if any(row[key] != value for key, value in pixels.items()):
                    raise ValueError("Native pixels differ from frozen capture identities")
            rgba_groups, rgba_summary = I.group_duplicates(rows, "rgba_identity")
            rgb_groups, rgb_summary = I.group_duplicates(rows, "rgb_identity")
            self.verify()
            details = self.output / "pixel-identities.json"
            A.write_json(
                details, {"rows": rows, "rgba_groups": rgba_groups, "rgb_groups": rgb_groups}
            )
            png_bindings = self.output / "png-bindings.json"
            A.write_json(png_bindings, self.pngs)
            state.update(
                status="passed",
                counts=counts,
                rgba=rgba_summary,
                rgb_only=rgb_summary,
                constant_rgba_images=sum(row["constant_rgba"] for row in rows),
                details=str(details),
                details_sha256=A.sha256_file(details),
                inputs_sha256=self.inputs,
                native_png_bindings=str(png_bindings),
                native_png_bindings_sha256=A.sha256_file(png_bindings),
                replacement_counts=reservation["replacement_counts"],
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(self.report, state)
        return state
