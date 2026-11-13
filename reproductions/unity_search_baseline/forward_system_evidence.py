"""Admit a frozen validation-qualified system while retaining original training evidence."""

from __future__ import annotations

import math
import sys
from importlib.metadata import version
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal
from reproductions.unity_search_baseline.confirmation_evidence import UnityConfirmationEvidence


class UnityForwardSystemEvidence(UnityConfirmationEvidence):
    def __init__(self, root: Path, system: JsonDict) -> None:
        super().__init__(root)
        self.system = system
        self.replay_archive: Path | None = None
        self.admission: JsonDict = {}

    @staticmethod
    def validate_system(freeze: JsonDict, runtime: JsonDict, training: JsonDict) -> JsonDict:
        identity = freeze["identity"]
        decision = identity["decision"]
        metrics = runtime["summary"]["forward"]["validation_metrics"]
        accuracy = metrics["accuracy"]
        if (
            freeze["status"] != "passed_validation_only_freeze"
            or freeze["validation_images"] != 1000
            or freeze["test_opened"] is not False
            or freeze["training_updates"] != 0
            or identity["split"] != "validation"
            or identity["model"]["name"] != "imagenet-resnet34-head-sampled4"
            or identity["model"]["checkpoint_sha256"] != training["checkpoint_sha256"]
            or identity["model"]["config_fingerprint"] != A.fingerprint(training["config"])
            or identity["model"]["selected_epoch"] != training["checkpoint_audit"]["epoch"]
            or training["config"].get("backbone_name") != "resnet34"
            or training["config"].get("image_pooling") != "mean"
            or training["config"].get("head_patch_views") != 4
            or identity["runtime"]["inference_images"] != 1000
            or identity["runtime"]["inference_patches"] != runtime["input_parity_patches"]
            or identity["runtime"]["validation_batch_size"] != 16
            or training["config"]["validation_batch_size"] != 16
            or decision["variant"] != "B1_candidate_idx"
            or decision["prediction_mode"] != "raw"
            or decision["start"] != "predicted_candidate_index"
            or decision["direction"] != "canonical20_forward"
            or decision["encoding_budget"] is not None
            or decision["normal_native_search"] is not False
            or decision["reuse_selected_encoded_result"] is not True
            or any(
                decision[name] != 0.0
                for name in [
                    "quality_margin_psnr_db",
                    "quality_margin_ms_ssim_db",
                    "quality_margin_normal_degrees",
                ]
            )
            or decision["zero_probability_threshold"] != 0.5
            or decision["zero_probability_threshold"]
            != training["config"]["zero_probability_threshold"]
            or runtime["status"] != "passed"
            or runtime["test_opened"] is not False
            or runtime["training_updates"] != 0
            or runtime["model_parameters_and_buffers_unchanged"] is not True
            or runtime["checkpoint_sha256"] != training["checkpoint_sha256"]
            or runtime["config"]["variant"] != decision["variant"]
            or runtime["config"]["prediction_mode"] != decision["prediction_mode"]
            or runtime["config"]["smoke"] is not False
            or runtime["inference_images"] != 1000
            or runtime["encoded_images"] != 1000
            or metrics["images"] != 1000
            or not math.isfinite(accuracy)
            or not 0.90 <= accuracy <= 1.0
            or freeze["validation_system_accuracy"] != accuracy
            or freeze["validation_pure_model_accuracy"]
            != training["checkpoint_audit"]["metrics"]["accuracy"]
        ):
            raise ValueError(
                "Require the frozen raw ResNet34 forward system and real validation1000 Top-1 >=90%"
            )
        measurements = runtime["measurements"]
        if len(measurements) != 4:
            raise ValueError(
                "System admission requires one warmup and three completed paired repeats"
            )
        for index, record in enumerate(measurements):
            forward = record["arms"]["forward"]
            audit = forward["query_audit"]
            if (
                record["repetition"] != index
                or record["warmup"] is not (index == 0)
                or set(record["arms"]) != {"forward", "fixed8"}
                or any(arm["status"] != "passed" for arm in record["arms"].values())
                or forward["validation_metrics"] != metrics
                or forward["timings"]["inference_images"] != 1000
                or forward["timings"]["encoded_images"] != 1000
                or forward["timings"]["prediction_passes"] != 1
                or forward["timings"]["encoding_calls"] != metrics["candidates_measured"]["total"]
                or audit["actual_queried_candidates_verified"]
                != forward["timings"]["encoding_calls"]
                or any(
                    audit[name] is not True
                    for name in [
                        "starting_choices_exact",
                        "forward_choices_and_query_order_exact",
                        "all_query_payloads_pixels_and_native_quality_match",
                    ]
                )
                or set(audit["fresh_prediction_max_abs_difference"])
                != {"channel_mse", "channel_zero", "zero_probability", "image_quality"}
                or any(
                    value != 0 for value in audit["fresh_prediction_max_abs_difference"].values()
                )
            ):
                raise ValueError("Real paired validation coverage or query/output audit differs")
        return metrics

    def training_stage(self, item: JsonDict, ancestors: set[Path]) -> JsonDict:
        """Retain launched archive identities and use a separate archive for source replay."""
        report_path = Path(item["report"]["path"]).resolve()
        if report_path in ancestors:
            raise ValueError("Cyclic initial training evidence")
        ancestors = ancestors | {report_path}
        config_path = self.bind(Path(item["config"]["path"]), item["config"]["sha256"])
        launched = self.read(config_path)
        training = self.bound(item["report"])
        self.validate_training(training, require_accuracy=False)
        settings = training["config"]
        stage = settings.get("stage")
        if stage not in (None, "Frozen encoder image-head refit"):
            raise ValueError("Unsupported native training stage")
        self.job(
            item["job"],
            "script/refit_unity_image_head.py" if stage else "script/train_unity_quality.py",
            config_path,
        )
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
            original_archive = compared.pop("training_source_archive", None)
            identities = [
                Path(value).resolve() if value else None
                for value in [
                    original_archive,
                    training["training_source_binding"]["archive"],
                    initial_item.get("training_source_archive"),
                ]
            ]
            if len(set(identities)) != 1:
                raise ValueError("Original head-stage and initial source archive identities differ")
            compared["initial_training_report"] = compared.pop("training_report")
            compared["initial_training_report_sha256"] = compared.pop("training_report_sha256")
            compared["head_patch_views"] = compared["patches_per_image"]
            initial = self.training_stage(initial_item, ancestors)
            if (
                training["initial_training_updates"] != initial["training_updates"]
                or any(
                    settings[key] != initial["config"][key]
                    for key in ["corpus", "corpus_sha256", "corpus_fingerprint"]
                )
                or settings.get("image_pooling", "mean_max")
                != initial["config"].get("image_pooling", "mean_max")
                or settings.get("backbone_name", "resnet18")
                != initial["config"].get("backbone_name", "resnet18")
                or {
                    str((self.root / row["relative_path"]).resolve()): row["training_sha256"]
                    for row in training["training_source_binding"]["sources"]
                }
                != initial["config"]["source_sha256"]
            ):
                raise ValueError("Head stage changed initial model lineage or development corpus")
        if Path(launched["report"]).resolve() != report_path or any(
            A.fingerprint(settings.get(key)) != A.fingerprint(value)
            for key, value in compared.items()
        ):
            raise ValueError("Training report differs from its completed job configuration")
        replay = PatchNormalizationAudit.bind_training_sources(
            {"source_files_sha256": settings["source_sha256"]}, self.root, self.replay_archive
        )
        for source in replay["sources"]:
            self.bind(Path(source["verified_source"]), source["training_sha256"])
        for epoch in training.get("history", []):
            if "image_sampling" in epoch:
                self.bind(Path(epoch["image_sampling"]["path"]), epoch["image_sampling"]["sha256"])
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
            raise ValueError("Require complete native train10000/validation1000")
        self.corpus = corpus
        return training

    def model(self, item: JsonDict) -> JsonDict:
        freeze = self.bound(self.system["validation_freeze"])
        identity = freeze["identity"]
        if identity["split"] != "validation":
            raise ValueError("System admission requires a development-only freeze")
        runtime_versions = {
            name: version(name) for name in ["torch", "torchvision", "numpy", "pillow"]
        }
        if (
            identity["runtime"]["packages"] != runtime_versions
            or identity["runtime"]["python"] != sys.version
        ):
            raise ValueError("Runtime versions differ from the frozen development system")
        seal_path = self.bind(Path(freeze["seal_path"]), freeze["seal_sha256"])
        seal = self.read(seal_path)
        if (
            seal["identity"] != identity
            or seal["fingerprint"] != A.fingerprint(identity)
            or seal["fingerprint"] != freeze["seal_fingerprint"]
        ):
            raise ValueError("Validation system seal changed")
        UnityEvaluationSeal(seal_path.parents[1], identity).verify_files()
        for name, digest in identity["files_sha256"].items():
            self.bind(Path(name), digest)
        manifest = self.bind(
            Path(self.system["source_replay_manifest"]["path"]),
            self.system["source_replay_manifest"]["sha256"],
        )
        self.replay_archive = manifest.parent
        runtime = self.bound(self.system["validation_runtime_report"])
        runtime_path = str(Path(self.system["validation_runtime_report"]["path"]).resolve())
        if (
            identity["files_sha256"].get(runtime_path)
            != self.system["validation_runtime_report"]["sha256"]
        ):
            raise ValueError("Runtime evidence differs from the frozen system")
        training = self.training_stage(item, set())
        metrics = self.validate_system(freeze, runtime, training)
        for record in runtime["measurements"]:
            for arm, result in record["arms"].items():
                folder = Path(runtime["config"]["output"]) / f"{record['repetition']:02d}-{arm}"
                for name, digest in result["audit"]["outputs_sha256"].items():
                    path = (folder / name).resolve()
                    if not path.is_relative_to(folder.resolve()):
                        raise ValueError("Validation artifact path escapes its output directory")
                    self.bind(path, digest)
        self.admission = {
            "evaluation_object": "frozen_prediction_forward_search_system",
            "validation_images": 1000,
            "accuracy": metrics["accuracy"],
            "model_accuracy": training["checkpoint_audit"]["metrics"]["accuracy"],
            "metrics": metrics,
            "development_seal_fingerprint": freeze["seal_fingerprint"],
            "source_replay_archive": str(self.replay_archive),
            "historical_training_archive_identity_preserved": True,
        }
        self.verify()
        return training
