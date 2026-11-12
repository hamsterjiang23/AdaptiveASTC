"""Bind the trained model and all reserved confirmation inputs before model evaluation."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.capture_policy import UnityCapturePolicyBinding
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture as C
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P
from reproductions.unity_search_baseline.near_duplicates import UnityNearDuplicateAudit as N
from reproductions.unity_search_baseline.pixel_audit_pipeline import UnityPixelAuditPipeline as I
from reproductions.unity_search_baseline.revised_pixel_identity import (
    UnityRevisedPixelIdentityAudit as R,
)


class UnityConfirmationEvidence:
    """Read-only preconditions, with no model construction, inference or cohort filtering."""

    EXPECTED = {"train": 10000, "validation": 1000, "confirmation": 2000}

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.files: dict[str, str | None] = {}
        self.policies: list[UnityCapturePolicyBinding] = []
        self.corpus: JsonDict = {}

    def bind(self, path: Path, digest: str | None = None) -> Path:
        path = path.resolve()
        actual = A.sha256_file(path)
        if (digest is not None and actual != digest) or (
            str(path) in self.files and self.files[str(path)] != actual
        ):
            raise ValueError(f"Confirmation evidence changed: {path}")
        self.files[str(path)] = actual
        return path

    def read(self, path: Path, digest: str | None = None) -> JsonDict:
        return A.read_json(self.bind(path, digest))

    def bound(self, item: JsonDict) -> JsonDict:
        return self.read(Path(item["path"]), item["sha256"])

    def verify(self) -> None:
        for name, digest in self.files.items():
            if digest is None:
                if Path(name).exists():
                    raise ValueError("Previously absent confirmation evidence appeared")
            else:
                self.bind(Path(name), digest)
        for policy in self.policies:
            policy.verify()

    def job(self, item: JsonDict, script: str, config_path: Path) -> None:
        path = self.bind(Path(item["job_config"]), item["sha256"])
        command = self.read(path).get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(value, str) for value in command)
        ):
            raise ValueError("Completed job does not execute the bound configuration")
        arguments = command[1:]
        if arguments[:2] == ["-X", "utf8"]:
            arguments = arguments[2:]
        if (
            len(arguments) != 4
            or arguments[0] != "-u"
            or arguments[2] != "--config"
            or Path(command[0]).resolve() != Path(sys.executable).resolve()
            or (self.root / arguments[1]).resolve() != (self.root / script).resolve()
            or (self.root / arguments[3]).resolve() != config_path.resolve()
        ):
            raise ValueError("Completed job does not execute the bound configuration")
        observed = P.dependency_status(item)
        if observed["status"] != "passed":
            raise ValueError("Confirmation evaluation requires completed upstream jobs")
        self.bind(path.with_name("receipt.json"), observed["receipt_sha256"])

    @staticmethod
    def validate_training(training: JsonDict, *, require_accuracy: bool = True) -> None:
        settings, audit = training["config"], training["checkpoint_audit"]
        expected = training["best_artifacts_sha256"]
        if (
            training["status"] != "completed"
            or training["test_opened"] is not False
            or training["training_updates"] <= 0
            or settings["smoke"] is not False
            or settings["train_image_indices"]
            or audit["status"] != "passed"
            or audit["test_opened"] is not False
            or audit["metrics"]["count"] != 1000
            or set(expected) != {"best.pt", "best-validation.npz", "best-decisions.json"}
            or audit["selected_artifacts_sha256"] != expected
            or audit["checkpoint_sha256"] != training["checkpoint_sha256"]
            or expected["best.pt"] != training["checkpoint_sha256"]
            or audit["predictions_sha256"] != expected["best-validation.npz"]
        ):
            raise ValueError("Require formal native training and its selected-checkpoint audit")
        # Keep the confirmation cohort out of iterative model selection.
        accuracy = audit["metrics"]["accuracy"]
        if not 0 <= accuracy <= 1.0 or (require_accuracy and accuracy < 0.90):
            raise ValueError("Selected model has not reached90% on the development validation set")
        if (
            settings.get("group_image_cap", 0) or settings.get("normal_image_repeats", 1) != 1
        ) and (
            not training.get("history")
            or any(not epoch.get("image_sampling") for epoch in training["history"])
        ):
            raise ValueError("Native sampling controls require complete observed-order receipts")

    def model(self, item: JsonDict) -> JsonDict:
        return self._model(item, require_accuracy=True, ancestors=set())

    def _model(self, item: JsonDict, *, require_accuracy: bool, ancestors: set[Path]) -> JsonDict:
        report_path = Path(item["report"]["path"]).resolve()
        if report_path in ancestors:
            raise ValueError("Cyclic initial training evidence")
        ancestors = ancestors | {report_path}
        config_path = self.bind(Path(item["config"]["path"]), item["config"]["sha256"])
        launched = self.read(config_path)
        training = self.bound(item["report"])
        self.validate_training(training, require_accuracy=require_accuracy)
        settings = training["config"]
        stage = settings.get("stage")
        if stage not in (None, "Frozen encoder image-head refit"):
            raise ValueError("Unsupported native training stage")
        script = "script/refit_unity_image_head.py" if stage else "script/train_unity_quality.py"
        self.job(item["job"], script, config_path)
        compared = dict(launched)
        if stage:
            initial_item = item["initial_training"]
            if (
                training["encoder_and_channel_head_unchanged"] is not True
                or settings["head_patch_views"] not in (0, 4)
                or settings.get("selection_metric", "accuracy") != "accuracy"
                or Path(settings["initial_training_report"]).resolve()
                != Path(initial_item["report"]["path"]).resolve()
                or settings["initial_training_report_sha256"] != initial_item["report"]["sha256"]
            ):
                raise ValueError("Head-stage evidence differs from its initial native training")
            archive = compared.pop("training_source_archive", None)
            recorded_archive = training["training_source_binding"]["archive"]
            initial_archive = initial_item.get("training_source_archive")
            archives = [
                Path(p).resolve() if p else None
                for p in (archive, recorded_archive, initial_archive)
            ]
            if len(set(archives)) != 1:
                raise ValueError("Head stage and initial training require the same source archive")
            compared["initial_training_report"] = compared.pop("training_report")
            compared["initial_training_report_sha256"] = compared.pop("training_report_sha256")
            compared["head_patch_views"] = compared["patches_per_image"]
            initial = self._model(initial_item, require_accuracy=False, ancestors=ancestors)
            if (
                training["initial_training_updates"] != initial["training_updates"]
                or any(
                    settings[key] != initial["config"][key]
                    for key in ("corpus", "corpus_sha256", "corpus_fingerprint")
                )
                or settings.get("image_pooling", "mean_max")
                != initial["config"].get("image_pooling", "mean_max")
                or {
                    str((self.root / row["relative_path"]).resolve()): row["training_sha256"]
                    for row in training["training_source_binding"]["sources"]
                }
                != initial["config"]["source_sha256"]
            ):
                raise ValueError("Head stage changed its initial training or development corpus")
        if Path(launched["report"]).resolve() != report_path or any(
            A.fingerprint(settings.get(key)) != A.fingerprint(value)
            for key, value in compared.items()
        ):
            raise ValueError("Training report differs from the completed job configuration")
        source_binding = PatchNormalizationAudit.bind_training_sources(
            {"source_files_sha256": settings["source_sha256"]},
            self.root,
            Path(item["training_source_archive"]) if item.get("training_source_archive") else None,
        )
        for source in source_binding["sources"]:
            self.bind(Path(source["verified_source"]), source["training_sha256"])
        for epoch in training.get("history", []):
            if "image_sampling" in epoch:
                receipt = epoch["image_sampling"]
                self.bind(Path(receipt["path"]), receipt["sha256"])
        run = Path(settings["output"])
        for name, digest in training["best_artifacts_sha256"].items():
            self.bind(run / name, digest)
        if (
            self.read(run / "config.json") != settings
            or self.read(run / "checkpoint-audit.json") != training["checkpoint_audit"]
        ):
            raise ValueError("Selected checkpoint evidence changed")
        corpus = self.read(Path(settings["corpus"]) / "corpus.json", settings["corpus_sha256"])
        if (
            corpus["status"] != "passed"
            or corpus["test_opened"] is not False
            or corpus["counts"] != {"train": 10000, "validation": 1000}
            or {split: len(rows) for split, rows in corpus["splits"].items()} != corpus["counts"]
        ):
            raise ValueError("Selected model did not use the complete native development corpus")
        self.corpus = corpus
        return training

    @staticmethod
    def overlaps(exact: JsonDict, near: JsonDict) -> JsonDict:
        rows = exact["rows"]
        fields = (
            "path",
            "source_split",
            "reference",
            "reference_sha256",
            "width",
            "height",
            "rgba_identity",
            "rgba_sha256",
            "observed_options",
        )
        if near["rows"] != [{field: row[field] for field in fields} for row in rows]:
            raise ValueError("Exact and near-pixel audits refer to different rows")

        def crosses(indices: list[int]) -> bool:
            splits = {rows[i]["source_split"] for i in indices}
            return "confirmation" in splits and bool(splits & {"train", "validation"})

        exact_hits = [group for group in exact["rgba_groups"] if crosses(group["row_indices"])]
        near_hits = [
            pair
            for pair in near["near_pairs"]
            if crosses(pair["left_row_indices"] + pair["right_row_indices"])
        ]
        return {
            "exact_confirmation_overlap_groups": len(exact_hits),
            "near_confirmation_overlap_pairs": len(near_hits),
        }

    def revised_pixels(self, item: JsonDict, original: JsonDict) -> dict[str, JsonDict]:
        exact_item, near_item = item["exact"], item["near"]
        path = self.bind(Path(exact_item["config"]["path"]), exact_item["config"]["sha256"])
        audit = R(self.root, path)
        config = audit.config
        self.job(exact_item["job"], "script/audit_unity_revised_pixels.py", path)
        report = self.bound(exact_item["report"])
        revision = audit.bound(config["corpus_revision_report"])
        corpus = audit.bound(config["corpus"])
        reservation = audit.bound(config["reservation"])
        if (
            report["status"] != "passed"
            or report["counts"] != self.EXPECTED
            or config["expected_counts"] != self.EXPECTED
            or report["config_sha256"] != exact_item["config"]["sha256"]
            or audit.report != Path(exact_item["report"]["path"]).resolve()
            or report["sources_sha256"] != config["sources_sha256"]
            or report["coverage"] != "approved_revised_native_cohort"
            or report["cohort_revision_applied_before_audit"] is not True
            or report["test_opened"] is not False
            or report["splits_modified"] is not False
            or report["training_updates"] != 0
            or config["original_pixels"] != original
            or corpus != self.corpus
            or revision["status"] != "passed"
            or revision["corpus_sha256"] != config["corpus"]["sha256"]
            or Path(revision["corpus"]).resolve() != Path(config["corpus"]["path"]).resolve()
            or reservation["status"] != "reserved"
            or corpus["config"]["revision"]["reservation"] != config["reservation"]
            or A.fingerprint(corpus["config"]) != corpus["binding"]
            or A.fingerprint({"binding": corpus["binding"], "splits": corpus["splits"]})
            != corpus["fingerprint"]
        ):
            raise ValueError("Revised pixels differ from the approved complete development corpus")
        old, added = [audit.audited_rows(key) for key in ("original_pixels", "replacement_pixels")]
        expected = R.select(old, added, reservation, corpus)
        exact = self.read(Path(report["details"]), report["details_sha256"])
        if (
            exact["rows"] != expected
            or report["replacement_counts"] != reservation["replacement_counts"]
            or report["inputs_sha256"] != audit.inputs
        ):
            raise ValueError("Revised pixels changed approved positions or confirmation membership")
        for name, digest in audit.inputs.items():
            self.bind(Path(name), digest)
        for name, digest in config["sources_sha256"].items():
            self.bind(self.root / name, digest)
        pngs = self.read(Path(report["native_png_bindings"]), report["native_png_bindings_sha256"])
        if pngs != {
            str(Path(row["reference"]).resolve()): row["reference_sha256"] for row in expected
        }:
            raise ValueError("Revised native PNG bindings differ from the audited rows")
        near_path = self.bind(Path(near_item["config"]["path"]), near_item["config"]["sha256"])
        self.job(near_item["job"], "script/audit_unity_near_duplicates.py", near_path)
        near_config, near_report = self.read(near_path), self.bound(near_item["report"])
        if (
            near_report["status"] != "passed"
            or near_report["counts"] != self.EXPECTED
            or near_config["expected_counts"] != self.EXPECTED
            or Path(near_config["report"]).resolve() != Path(near_item["report"]["path"]).resolve()
            or near_report["config_sha256"] != near_item["config"]["sha256"]
            or near_config["pixel_identity_report"] != exact_item["report"]
            or near_config["sources_sha256"] != N.execution_sources(self.root)
            or near_report["sources_sha256"] != near_config["sources_sha256"]
            or near_report["rgba_rmse_8bit"] != 2.0
            or near_config["rgba_rmse_8bit"] != 2.0
            or near_report["test_opened"] is not False
            or near_report["splits_modified"] is not False
            or near_report["model_forward_calls"] != 0
            or near_report["training_updates"] != 0
        ):
            raise ValueError("Revised near-pixel audit differs from the complete exact audit")
        for name, digest in near_report["inputs_sha256"].items():
            self.bind(Path(name), digest)
        for name, digest in near_config["sources_sha256"].items():
            self.bind(self.root / name, digest)
        return {
            "exact": exact,
            "near": self.read(Path(near_report["details"]), near_report["details_sha256"]),
        }

    def pixel_audit(self, item: JsonDict) -> tuple[I, JsonDict]:
        config = self.bound(item["config"])
        path = Path(item["config"]["path"])
        self.job(item["job"], "script/queue_unity_pixel_audit.py", path)
        report = self.bound(item["report"])
        if (
            config["mode"] != "confirmation_complete"
            or Path(config["report"]).resolve() != Path(item["report"]["path"]).resolve()
            or report["config_sha256"] != item["config"]["sha256"]
            or report["status"] != "passed"
            or report["counts"] != self.EXPECTED
            or report["expected_counts"] != self.EXPECTED
            or report["sources_sha256"] != I.execution_sources(self.root)
            or report["test_opened"] is not False
            or report["splits_modified"] is not False
            or report["model_forward_calls"] != 0
            or report["training_updates"] != 0
            or [stage["kind"] for stage in report["stages"]] != ["exact", "near"]
        ):
            raise ValueError("Full original pixel audit must finish before confirmation inference")
        for name, digest in report["inputs_sha256"].items():
            self.bind(Path(name), digest)
        details = {}
        original_exact = {}
        for stage in report["stages"]:
            summary = self.bound(stage)
            if summary["status"] != "passed" or summary["counts"] != self.EXPECTED:
                raise ValueError("Pixel audit stage lacks complete coverage")
            for name, digest in summary["inputs_sha256"].items():
                self.bind(Path(name), digest)
            details[stage["kind"]] = self.read(Path(summary["details"]), summary["details_sha256"])
            if stage["kind"] == "exact":
                original_exact = {"path": stage["path"], "sha256": stage["sha256"]}
        if "revised_development" in item:
            details = self.revised_pixels(item["revised_development"], original_exact)
        overlap = self.overlaps(details["exact"], details["near"])
        if any(overlap.values()):
            raise ValueError(
                f"Confirmation overlaps development pixels; retain the cohort: {overlap}"
            )
        rows = details["exact"]["rows"]
        if dict(Counter(row["source_split"] for row in rows)) != self.EXPECTED:
            raise ValueError("Pixel detail coverage differs from the full audit")
        lookup = {(row["source_split"], row["path"].casefold()): row for row in rows}
        if len(lookup) != len(rows):
            raise ValueError("Duplicate asset identities in pixel audit")
        for split, textures in self.corpus["splits"].items():
            for texture in textures:
                pixel = lookup[(split, texture["path"].casefold())]
                if (
                    pixel["reference_sha256"] != texture["reference_sha256"]
                    or pixel["callback_rgba_sha256"] != texture["actual_options"]["rgba_sha256"]
                    or (pixel["selected_block_size"], pixel["selected_preset"])
                    != (
                        texture["original_selection"]["block_size"],
                        texture["original_selection"]["preset"],
                    )
                ):
                    raise ValueError(
                        "Pixel audit differs from the selected model's training corpus"
                    )
        for row in rows:
            self.bind(Path(row["reference"]), row["reference_sha256"])
        return I(self.root, path), details["exact"]

    def captures(self, pipeline: I, pixels: JsonDict) -> tuple[list[JsonDict], list[int]]:
        series = pipeline.confirmation
        if series is None:
            raise ValueError("Reserved confirmation series is missing")
        series.validate()
        report = self.read(series.report)
        if (
            report["status"] != "passed"
            or report["captured_images"] != 2000
            or report["coverage"] != "complete"
        ):
            raise ValueError("Reserved confirmation capture is incomplete")
        manifest = self.read(Path(report["manifest"]), report["manifest_sha256"])
        rows, indices, bindings = [], [], []
        for recorded, (start, count) in zip(
            report["batches"], [(0, 2), *series.ranges()], strict=True
        ):
            path = self.bind(Path(recorded["config"]), recorded["config_sha256"])
            capture = C(self.root, path)
            if (capture.config["start"], capture.config["images"]) != (start, count):
                raise ValueError("Confirmation order differs from reserved ranges")
            I.require_archive(capture.baseline.run_dir, "batch")
            batch, actual = series.audit_batch(capture)
            if actual != recorded:
                raise ValueError("Confirmation batch no longer matches its manifest")
            policy = UnityCapturePolicyBinding(
                capture.baseline,
                "batch",
                reference_sha256=recorded["reference_receipt_sha256"],
                phase_sha256=recorded["phase_receipt_sha256"],
            )
            for name, digest in policy.inputs.items():
                if name in self.files and self.files[name] != digest:
                    raise ValueError("Conflicting original policy evidence")
                self.files[name] = digest
            indices.extend([len(self.policies)] * len(batch))
            self.policies.append(policy)
            rows.extend(batch)
            bindings.append(actual)
        if (
            manifest["splits"] != {"confirmation": rows}
            or manifest["batches"] != bindings
            or len(rows) != 2000
            or [row["path"] for row in rows] != [row["path"] for row in series.rows]
            or manifest["reservation_manifest_sha256"]
            != series.smoke.reservation["manifest_sha256"]
        ):
            raise ValueError(
                "Confirmation membership differs from the entire reserved primary cohort"
            )
        by_path = {
            row["path"].casefold(): row
            for row in pixels["rows"]
            if row["source_split"] == "confirmation"
        }
        for row in rows:
            pixel = by_path[row["path"].casefold()]
            if (
                pixel["reference_sha256"] != row["reference_sha256"]
                or pixel["callback_rgba_sha256"] != row["actual_options"]["rgba_sha256"]
                or (pixel["selected_block_size"], pixel["selected_preset"])
                != (row["selection"]["block_size"], row["selection"]["preset"])
            ):
                raise ValueError("Confirmation pixel audit and original capture disagree")
        # Input projection validates callback pixels and import metadata before sealing.
        UnityCaptureInputAdapter(rows, "confirmation")
        self.verify()
        return rows, indices
