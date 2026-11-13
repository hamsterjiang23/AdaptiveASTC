"""Bind an approved revised cohort to the frozen forward-system confirmation protocol."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.capture_policy import UnityCapturePolicyBinding
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture as C
from reproductions.unity_search_baseline.confirmation_near_revision import (
    UnityConfirmationNearRevision as R,
)
from reproductions.unity_search_baseline.confirmation_revision_pixels import (
    UnityConfirmationRevisionPixelAudit as Q,
)
from reproductions.unity_search_baseline.forward_system_evidence import UnityForwardSystemEvidence
from reproductions.unity_search_baseline.near_duplicates import UnityNearDuplicateAudit as N
from reproductions.unity_search_baseline.pixel_audit_pipeline import UnityPixelAuditPipeline as I
from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit as P


class UnityRevisedConfirmationEvidence(UnityForwardSystemEvidence):
    def __init__(self, root: Path, system: JsonDict) -> None:
        super().__init__(root, system)
        self.revised: JsonDict = {}
        self.captured: JsonDict = {}
        self.input_fingerprint = ""

    @staticmethod
    def validate_capture_execution(
        data: JsonDict,
        config: JsonDict,
        capture: JsonDict,
        guard: JsonDict,
        expected_guard_sha256: str,
    ) -> None:
        if (
            capture["status"] != "passed"
            or capture["captured_images"] != 2000
            or capture["model_forward_calls"] != 0
            or capture["training_updates"] != 0
            or capture["test_opened"] is not False
            or capture["config_sha256"] != data["capture_config"]["sha256"]
            or capture["sources_sha256"] != config["sources_sha256"]
            or "reproductions/unity_search_baseline/policy.py" not in capture["sources_sha256"]
            or guard["status"] != "passed"
            or guard["test_opened"] is not False
            or guard["config_sha256"] != data["capture_config"]["sha256"]
            or guard["guard_sha256"] != expected_guard_sha256
            or any(
                guard[key] != 0
                for key in [
                    "model_forward_calls",
                    "training_updates",
                    "blocked_model_import_attempts",
                    "blocked_model_file_access_attempts",
                ]
            )
        ):
            raise ValueError("Revised capture execution chain changed")

    def read(self, path: Path, digest: str | None = None) -> JsonDict:
        path = path.resolve()
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if (digest is not None and actual != digest) or (
            str(path) in self.files and self.files[str(path)] != actual
        ):
            raise ValueError("Revised confirmation evidence changed")
        self.files[str(path)] = actual
        return json.loads(raw.decode("utf-8-sig"))

    def data_stage(self, stage: JsonDict, script: str, archive: JsonDict) -> None:
        job, receipt, guard = [self.bound(stage[name]) for name in ["job", "receipt", "guard"]]
        exact = script.endswith("audit_unity_confirmation_revision_pixels.py")
        name = (
            "run_confirmation_pixel_guarded_v3.py"
            if exact
            else "run_confirmation_data_guarded_v3.py"
        )
        runner = self.root / "experiment report/.local/unity-v2-20261112" / name
        runner_key = str(runner.relative_to(self.root)).replace("\\", "/")
        self.bind(runner, archive["files"][runner_key]["sha256"])
        expected = [sys.executable, "-X", "utf8", "-u", str(runner)]
        if not exact:
            expected.extend(["--script", str(self.root / script)])
        expected.extend(
            [
                "--config",
                stage["config"]["path"],
                "--guard-report",
                stage["guard"]["path"],
            ]
        )
        counters = ["model_forward_calls", "training_updates", "blocked_model_file_access_attempts"]
        counters.extend(
            ["model_initializations", "optimizer_initializations", "cuda_initializations"]
            if exact
            else ["blocked_model_import_attempts"]
        )
        if (
            job["command"] != expected
            or receipt["command"] != expected
            or receipt["status"] != "passed"
            or receipt["process_exit_code"] != 0
            or receipt["config_sha256"] != stage["job"]["sha256"]
            or guard["status"] != "passed"
            or guard["test_opened"] is not False
            or guard["config_sha256"] != stage["config"]["sha256"]
            or guard["guard_sha256"] != archive["files"][runner_key]["sha256"]
            or any(guard[name] != 0 for name in counters)
        ):
            raise ValueError("Revised data stage lacks successful zero-model execution evidence")
        if not exact and guard["script_sha256"] != A.sha256_file(self.root / script):
            raise ValueError("Near audit entry point differs from its execution receipt")

    def pixel_audit(self, item: JsonDict) -> tuple[I, JsonDict]:
        data = self.bound(item["revised_cohort"])
        archive = self.bound(data["source_archive"])
        if (
            data["schema"] != "unity_confirmation_revised_cohort_v3"
            or data["status"] != "passed_scope_revision_native_capture_and_full_pixel_reaudit"
            or data["counts"] != self.EXPECTED
            or data["model_forward_calls"] != 0
            or data["training_updates"] != 0
            or data["test_opened"] is not False
            or data["selection_uses_predictions_or_quality"] is not False
            or data["formal_confirmation_model_evaluations"] != 0
        ):
            raise ValueError("Require completed approved data preparation before confirmation")
        corpus = data["development_corpus"]
        if not self.corpus or (
            self.files.get(str(Path(corpus["path"]).resolve())) != corpus["sha256"]
        ):
            raise ValueError("Bind the frozen development model before revised pixel evidence")
        self.bind(Path(corpus["path"]), corpus["sha256"])
        revision = self.bound(data["reservation_report"])
        reservation = self.read(Path(revision["manifest"]), revision["manifest_sha256"])
        proposal = self.bound(data["identity_review"])
        capture_config = self.bound(data["capture_config"])
        capture = self.bound(data["capture_report"])
        captured = self.bound(data["capture_manifest"])
        capture_guard = self.bound(data["capture_guard"])
        guard_key = "experiment report/.local/unity-v2-20261112/run_confirmation_data_guarded_v3.py"
        self.validate_capture_execution(
            data, capture_config, capture, capture_guard, archive["files"][guard_key]["sha256"]
        )
        if (
            revision["status"] != "reserved"
            or revision["scope_revision_authorized"] is not True
            or revision["identity_review"] != data["identity_review"]
            or captured["model_forward_calls"] != 0
            or captured["training_updates"] != 0
            or captured["test_opened"] is not False
            or capture["manifest_sha256"] != data["capture_manifest"]["sha256"]
            or captured["reservation_manifest_sha256"] != revision["manifest_sha256"]
        ):
            raise ValueError("Revised native capture belongs to a different approved reservation")
        for manifest in [reservation, captured]:
            unsigned = {key: value for key, value in manifest.items() if key != "fingerprint"}
            if manifest["fingerprint"] != A.fingerprint(unsigned):
                raise ValueError("Revised cohort manifest fingerprint changed")
        for name, digest in capture["inputs_sha256"].items():
            self.bind(Path(name), digest)
        for name, digest in capture["sources_sha256"].items():
            self.bind(self.root / name, digest)
        capture_script = Path(capture_guard["script"])
        script_key = str(capture_script.relative_to(self.root)).replace("\\", "/")
        if capture_guard["script_sha256"] != archive["files"][script_key]["sha256"]:
            raise ValueError("Revised capture producer differs from the audited source archive")
        exact_item, near_item = data["exact"], data["near"]
        self.data_stage(exact_item, "script/audit_unity_confirmation_revision_pixels.py", archive)
        self.data_stage(near_item, "script/audit_unity_near_duplicates.py", archive)
        exact_config, exact = self.bound(exact_item["config"]), self.bound(exact_item["report"])
        near_config, near = self.bound(near_item["config"]), self.bound(near_item["report"])
        if (
            exact_config["confirmation_reservation"] != data["reservation_report"]
            or exact_config["confirmation_capture"] != data["capture_report"]
            or exact_config["identity_review"] != data["identity_review"]
            or exact_config["sources_sha256"] != Q.execution_sources(self.root)
            or near_config["sources_sha256"] != N.execution_sources(self.root)
            or near_config["pixel_identity_report"] != exact_item["report"]
            or near_config["runtime"] != N.runtime()
            or near_config["rgba_rmse_8bit"] != 2.0
            or near_config["cell_grid"] != 8
            or near_config["max_candidate_pairs"] != 100000
            or exact["native_confirmation_input_images"] != 2000
        ):
            raise ValueError("Revised exact/near audit contracts differ from the approved inputs")
        for stage, config, report in [
            (exact_item, exact_config, exact),
            (near_item, near_config, near),
        ]:
            if (
                report["status"] != "passed"
                or report["counts"] != self.EXPECTED
                or config["expected_counts"] != self.EXPECTED
                or report["config_sha256"] != stage["config"]["sha256"]
                or report["sources_sha256"] != config["sources_sha256"]
                or report["model_forward_calls"] != 0
                or report["training_updates"] != 0
                or report["test_opened"] is not False
                or report["splits_modified"] is not False
            ):
                raise ValueError("Revised audit coverage, identity or execution scope changed")
            for name, digest in report["inputs_sha256"].items():
                self.bind(Path(name), digest)
            for name, digest in config["sources_sha256"].items():
                self.bind(self.root / name, digest)
        exact_rows = self.read(Path(exact["details"]), exact["details_sha256"])
        near_rows = self.read(Path(near["details"]), near["details_sha256"])
        audit = Q(self.root, Path(exact_item["config"]["path"]))
        old, added = [audit.audited_rows(key) for key in ["original_pixels", "replacement_pixels"]]
        expected_rows = R.select_pixels(old, added, reservation["primary"], proposal)
        near_fields = [
            "path",
            "source_split",
            "reference",
            "reference_sha256",
            "width",
            "height",
            "rgba_identity",
            "rgba_sha256",
            "observed_options",
        ]
        if exact_rows["rows"] != expected_rows or near_rows["rows"] != [
            {key: row[key] for key in near_fields} for row in expected_rows
        ]:
            raise ValueError("Exact/near pixels changed approved membership or original order")
        for field, name in [("rgba_identity", "rgba"), ("rgb_identity", "rgb_only")]:
            if P.group_duplicates(expected_rows, field)[1] != exact[name]:
                raise ValueError("Revised duplicate summaries differ from native identities")
        if any(self.overlaps(exact_rows, near_rows).values()):
            raise ValueError("Revised confirmation overlaps development pixels")
        by_path = {(row["source_split"], row["path"].casefold()): row for row in expected_rows}
        if len(by_path) != 13000:
            raise ValueError("Revised pixel identities are duplicated or incomplete")
        for split, textures in self.corpus["splits"].items():
            for texture in textures:
                row = by_path[(split, texture["path"].casefold())]
                if row["reference_sha256"] != texture["reference_sha256"] or (
                    row["callback_rgba_sha256"] != texture["actual_options"]["rgba_sha256"]
                ):
                    raise ValueError("Revised pixels changed frozen development inputs")
        pngs = self.read(Path(exact["native_png_bindings"]), exact["native_png_bindings_sha256"])
        if pngs != {
            str(Path(row["reference"]).resolve()): row["reference_sha256"] for row in expected_rows
        }:
            raise ValueError("Revised native PNG bindings differ from complete pixels")
        for name, digest in pngs.items():
            self.bind(Path(name), digest)
        pipeline_path = self.bind(
            Path(item["registry_pipeline"]["path"]), item["registry_pipeline"]["sha256"]
        )
        pipeline = I(self.root, pipeline_path)
        if pipeline.confirmation is None or (
            pipeline.confirmation.smoke.reservation["manifest_sha256"]
            != revision["prior"]["manifest"]["sha256"]
        ):
            raise ValueError("Revised cohort changed the shared original reservation identity")
        for name, digest in pipeline.inputs.items():
            self.bind(Path(name), digest)
        self.revised, self.captured = data, captured
        self.input_fingerprint = exact["native_confirmation_input_fingerprint"]
        self.verify()
        return pipeline, exact_rows

    def captures(self, pipeline: I, pixels: JsonDict) -> tuple[list[JsonDict], list[int]]:
        if not self.revised or pipeline.confirmation is None:
            raise ValueError("Complete revised pixel evidence must be bound first")
        rows = self.captured["splits"]["confirmation"]
        origins = self.captured["origins"]
        indices = []
        self.policies = []
        sources: list[list[JsonDict]] = []
        references: list[list[JsonDict]] = []
        options: list[list[JsonDict]] = []
        imports: list[list[JsonDict]] = []
        for inventory in self.captured["batches"]:
            binding = inventory["binding"]
            config = self.bind(Path(binding["config"]), binding["config_sha256"])
            capture = C(self.root, config)
            capture.validate()
            capture.baseline.verify_protocol()
            native = self.read(Path(binding["report"]), binding["report_sha256"])
            phase = self.read(
                capture.baseline.run_dir / "batch-receipt.json", binding["phase_receipt_sha256"]
            )
            restored = self.read(
                capture.baseline.run_dir / "managed-hook/receipt.json",
                binding["managed_restoration_sha256"],
            )
            reference = self.read(
                capture.baseline.run_dir / "references/normalized-batch/receipt.json",
                binding["reference_receipt_sha256"],
            )
            if (
                native["status"] != "passed"
                or native["images"] != len(capture.rows)
                or phase["status"] != "passed"
                or phase["process_exit_code"] != 0
                or phase["metadata_restore_conflicts"]
                or restored != native["managed_source_restoration"]
                or restored["status"] != "restored"
                or restored["original_sha256"] != restored["restored_sha256"]
            ):
                raise ValueError("Revised capture lost complete native execution or restoration")
            policy = UnityCapturePolicyBinding(
                capture.baseline,
                "batch",
                reference_sha256=binding["reference_receipt_sha256"],
                phase_sha256=binding["phase_receipt_sha256"],
            )
            for name, digest in policy.inputs.items():
                if name in self.files and self.files[name] != digest:
                    raise ValueError("Conflicting revised native policy sources")
                self.files[name] = digest
            self.policies.append(policy)
            sources.append(capture.rows)
            references.append(reference["rows"])
            options.append(native["options_audit"]["rows"])
            imported_path = self.bind(capture.baseline.run_dir / "batch-imports.jsonl")
            imports.append(capture.baseline._read_lines(imported_path))
        seen: set[tuple[int, int]] = set()
        for row, origin in zip(rows, origins, strict=True):
            index = origin["batch_inventory_index"]
            position = origin["capture_index"]
            if (
                type(index) is not int
                or not 0 <= index < len(self.policies)
                or type(position) is not int
                or not 0 <= position < len(sources[index])
            ):
                raise ValueError("Revised native origin index is outside its source batch")
            identity = (index, position)
            inventory = self.captured["batches"][index]
            if (
                row["path"] != origin["path"]
                or identity in seen
                or position not in inventory["used_capture_indices"]
                or row["capture_index"] != position
                or Path(row["capture_directory"]).resolve()
                != self.policies[index].baseline.run_dir / "references/normalized-batch"
            ):
                raise ValueError("Revised native origin mapping changed")
            self.validate_native_row(
                row,
                sources[index][position],
                references[index][position],
                options[index][position],
                imports[index][position],
            )
            seen.add(identity)
            indices.append(index)
        if len(rows) != 2000 or seen != {
            (index, position)
            for index, batch in enumerate(self.captured["batches"])
            for position in batch["used_capture_indices"]
        }:
            raise ValueError("Revised native origins lack complete unique coverage")
        confirmation_pixels = [
            row for row in pixels["rows"] if row["source_split"] == "confirmation"
        ]
        for native, pixel in zip(rows, confirmation_pixels, strict=True):
            if native["path"] != pixel["path"] or (
                native["reference_sha256"] != pixel["reference_sha256"]
                or native["actual_options"]["rgba_sha256"] != pixel["callback_rgba_sha256"]
            ):
                raise ValueError("Revised confirmation capture differs from complete pixel audit")
        self.verify()
        return rows, indices

    @staticmethod
    def validate_native_row(
        row: JsonDict, source: JsonDict, reference: JsonDict, actual: JsonDict, imported: JsonDict
    ) -> None:
        if (
            row["path"] != source["path"]
            or row["source_md4"] != source["fileHash"]
            or row["source_sha256"] != source["source_sha256"]
            or row["meta_sha256"] != source["meta_sha256"]
            or row["path"] != reference["path"]
            or row["source_split"] != "confirmation"
            or reference["source_split"] != "confirmation"
            or row["reference_sha256"] != reference["artifacts_sha256"]["original.png"]
            or (row["width"], row["height"]) != (reference["width"], reference["height"])
            or row["selection"] != reference["selection"]
            or row["actual_options"] != actual
            or row["import_metadata"] != imported
        ):
            raise ValueError("Revised native row differs from its original source receipts")
