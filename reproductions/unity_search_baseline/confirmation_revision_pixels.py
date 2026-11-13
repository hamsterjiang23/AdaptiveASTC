"""Recompute complete native pixel identities after an approved confirmation revision."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_near_revision import (
    UnityConfirmationNearRevision as R,
)
from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit as I
from reproductions.unity_search_baseline.revised_pixel_identity import (
    UnityRevisedPixelIdentityAudit,
)


class UnityConfirmationRevisionPixelAudit(UnityRevisedPixelIdentityAudit):
    """Keep all development pixels and validate the revised complete confirmation input."""

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/confirmation_revision_pixels.py",
            "reproductions/unity_search_baseline/confirmation_near_revision.py",
            "src/adaptive_astc/data/unity_capture_input.py",
            "src/adaptive_astc/data/unity_inference.py",
            "src/adaptive_astc/evaluation/unity_quality.py",
            "script/audit_unity_confirmation_revision_pixels.py",
        ]
        return UnityRevisedPixelIdentityAudit.execution_sources(root) | {
            name: A.sha256_file(root / name) for name in names
        }

    def run(self) -> JsonDict:
        started = time.perf_counter()
        if self.output.exists() or self.report.exists():
            raise FileExistsError("Use a new confirmation pixel audit identity")
        revision = self.bound(self.config["confirmation_reservation"])
        primary = self.bound({"path": revision["manifest"], "sha256": revision["manifest_sha256"]})
        unsigned = {key: value for key, value in primary.items() if key != "fingerprint"}
        proposal = self.bound(self.config["identity_review"])
        capture_report = self.bound(self.config["confirmation_capture"])
        captured = self.bound({
            "path": capture_report["manifest"], "sha256": capture_report["manifest_sha256"],
        })
        capture_unsigned = {key: value for key, value in captured.items() if key != "fingerprint"}
        if (
            revision["status"] != "reserved"
            or revision["scope_revision_authorized"] is not True
            or revision["model_forward_calls"] != 0
            or revision["training_updates"] != 0
            or revision["test_opened"] is not False
            or primary["fingerprint"] != A.fingerprint(unsigned)
            or revision["identity_review"] != self.config["identity_review"]
            or capture_report["status"] != "passed"
            or capture_report["model_forward_calls"] != 0
            or capture_report["training_updates"] != 0
            or capture_report["test_opened"] is not False
            or capture_report["captured_images"] != len(primary["primary"])
            or captured["status"] != "passed"
            or captured["fingerprint"] != A.fingerprint(capture_unsigned)
            or captured["reservation_manifest_sha256"] != revision["manifest_sha256"]
            or captured["test_opened"] is not False
            or captured["model_forward_calls"] != 0
            or captured["training_updates"] != 0
        ):
            raise ValueError("Revised reservation and complete native capture disagree")
        for name, digest in capture_report["inputs_sha256"].items():
            self.bound({"path": name, "sha256": digest})
        old, added = [self.audited_rows(name) for name in ["original_pixels", "replacement_pixels"]]
        rows = R.select_pixels(old, added, primary["primary"], proposal)
        counts = dict(Counter(row["source_split"] for row in rows))
        if counts != self.config["expected_counts"]:
            raise ValueError("Revised native pixel coverage differs from frozen counts")
        confirmation = [row for row in rows if row["source_split"] == "confirmation"]
        capture_rows = captured["splits"]["confirmation"]
        for source, pixel, native in zip(
            primary["primary"], confirmation, capture_rows, strict=True
        ):
            if (
                source["path"] != pixel["path"]
                or source["path"] != native["path"]
                or native["source_md4"] != source["fileHash"]
                or native["source_sha256"] != source["source_sha256"]
                or native["meta_sha256"] != source["meta_sha256"]
                or Path(native["reference_png"]).resolve() != Path(pixel["reference"]).resolve()
                or native["reference_sha256"] != pixel["reference_sha256"]
                or native["actual_options"]["rgba_sha256"] != pixel["callback_rgba_sha256"]
                or (native["width"], native["height"]) != (pixel["width"], pixel["height"])
                or (native["selection"]["block_size"], native["selection"]["preset"])
                != (pixel["selected_block_size"], pixel["selected_preset"])
            ):
                raise ValueError("Revised capture reference identities differ from pixel rows")
            observed = {
                key: native["actual_options"][key]
                for key in [
                    "need_alpha", "profile", "normal_pack", "channel",
                    "srgb_importer", "texture_type_importer",
                ]
            }
            if pixel["observed_options"] != observed:
                raise ValueError("Revised pixel native options differ from original capture")
        self.output.mkdir(parents=True, exist_ok=False)
        self.report.parent.mkdir(parents=True, exist_ok=True)
        state: JsonDict = {
            "status": "running", "config_sha256": self.sha,
            "sources_sha256": self.config["sources_sha256"],
            "coverage": "approved_revised_confirmation_native_cohort",
            "scope": "Exact dimensions plus RGBA8 and native input validation, near audit separate",
            "cohort_revision_applied_before_audit": True,
            "splits_modified": False, "model_forward_calls": 0,
            "training_updates": 0, "actual_encoding_calls": 0, "test_opened": False,
            "independent_test_isolation_proven": False,
        }
        with self.report.open("x", encoding="utf-8") as output:
            json.dump(state, output, ensure_ascii=False, indent=2)
        try:
            for index, row in enumerate(rows):
                path = Path(row["reference"]).resolve()
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if digest != row["reference_sha256"]:
                    raise ValueError("Native reference bytes changed")
                self.pngs[str(path)] = digest
                actual = I.pixel_identity(raw, row["width"], row["height"])
                if any(row[key] != value for key, value in actual.items()):
                    raise ValueError("Recomputed native pixels differ from frozen capture")
                if (index + 1) % 1000 == 0:
                    print(f"Recomputed native pixel identities {index + 1}/{len(rows)}", flush=True)
            adapter = UnityCaptureInputAdapter(capture_rows, "confirmation")
            rgba_groups, rgba_summary = I.group_duplicates(rows, "rgba_identity")
            rgb_groups, rgb_summary = I.group_duplicates(rows, "rgb_identity")
            self.verify()
            details = self.output / "pixel-identities.json"
            A.write_json(details, {
                "rows": rows, "rgba_groups": rgba_groups, "rgb_groups": rgb_groups,
            })
            pngs = self.output / "png-bindings.json"
            A.write_json(pngs, self.pngs)
            state.update(
                status="passed", counts=counts, rgba=rgba_summary, rgb_only=rgb_summary,
                details=str(details), details_sha256=A.sha256_file(details),
                native_png_bindings=str(pngs), native_png_bindings_sha256=A.sha256_file(pngs),
                inputs_sha256=self.inputs,
                constant_rgba_images=sum(row["constant_rgba"] for row in rows),
                replacement_counts={"confirmation": len(proposal["proposed_replacements"])},
                native_confirmation_input_images=len(adapter.bindings),
                native_confirmation_input_fingerprint=adapter.fingerprint,
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(self.report, state)
        return state
