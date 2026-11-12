"""Bind the trained model and all reserved confirmation inputs before model evaluation."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.capture_policy import UnityCapturePolicyBinding
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture as C
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P
from reproductions.unity_search_baseline.pixel_audit_pipeline import UnityPixelAuditPipeline as I


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
    def validate_training(training: JsonDict) -> None:
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
        if not 0.90 <= audit["metrics"]["accuracy"] <= 1.0:
            raise ValueError("Selected model has not reached90% on the development validation set")

    def model(self, item: JsonDict) -> JsonDict:
        config_path = self.bind(Path(item["config"]["path"]), item["config"]["sha256"])
        self.job(item["job"], "script/train_unity_quality.py", config_path)
        launched = self.read(config_path)
        training = self.bound(item["report"])
        self.validate_training(training)
        settings = training["config"]
        if Path(launched["report"]).resolve() != Path(item["report"]["path"]).resolve() or any(
            A.fingerprint(settings.get(key)) != A.fingerprint(value)
            for key, value in launched.items()
        ):
            raise ValueError("Training report differs from the completed job configuration")
        for name, digest in settings["source_sha256"].items():
            self.bind(Path(name), digest)
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
        for stage in report["stages"]:
            summary = self.bound(stage)
            if summary["status"] != "passed" or summary["counts"] != self.EXPECTED:
                raise ValueError("Pixel audit stage lacks complete coverage")
            for name, digest in summary["inputs_sha256"].items():
                self.bind(Path(name), digest)
            details[stage["kind"]] = self.read(Path(summary["details"]), summary["details_sha256"])
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
