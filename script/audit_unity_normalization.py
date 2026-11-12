"""Audit native Unity checkpoints with train-only BatchNorm re-estimation."""

from __future__ import annotations

import argparse
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_image_bags import UnityImageBags
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_quality_trainer import UnityQualityTrainer
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime


class UnityNormalizationAudit:
    @staticmethod
    def training_config_path(settings: JsonDict) -> Path:
        explicit = settings.get("training_config_path")
        candidates = [Path(name) for name in settings["source_sha256"] if name.endswith(".json")]
        if explicit is None and len(candidates) != 1:
            raise ValueError("Require the original native trainer configuration path")
        path = Path(explicit).resolve() if explicit is not None else candidates[0]
        expected = settings["source_sha256"].get(str(path))
        if expected is None or A.sha256_file(path) != expected:
            raise ValueError("Original native training configuration changed or is unbound")
        return path

    @staticmethod
    def verify_sources(sources: dict[str, str]) -> None:
        for name, digest in sources.items():
            if A.sha256_file(Path(name)) != digest:
                raise ValueError(f"Native normalization source changed: {name}")

    @staticmethod
    def calibration_inputs(batch: dict[str, Tensor]) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        count, views = batch["rgba"].shape[:2]
        return (
            batch["rgba"].flatten(0, 1),
            batch["valid_mask"].flatten(0, 1),
            torch.arange(count).repeat_interleave(views),
            batch["metadata"],
        )

    @staticmethod
    def verify_predictions(actual: dict[str, np.ndarray], saved_path: Path) -> None:
        with np.load(saved_path, allow_pickle=False) as saved:
            for key, value in actual.items():
                if value.dtype == np.bool_:
                    np.testing.assert_array_equal(value, saved[key])
                else:
                    np.testing.assert_allclose(value, saved[key], rtol=0, atol=1e-5)

    @classmethod
    def run(cls, config_path: Path) -> JsonDict:
        started = time.perf_counter()
        root = Path(__file__).resolve().parents[1]
        config_path = config_path.resolve()
        config_sha256 = A.sha256_file(config_path)
        config = A.read_json(config_path)
        output, report = Path(config["output"]).resolve(), Path(config["report"]).resolve()
        if (
            not output.is_relative_to(root / "experiment report/.local")
            or report.is_relative_to(output)
            or type(config["smoke"]) is not bool
        ):
            raise ValueError(
                "Require private artifacts, an external report and explicit smoke flag"
            )
        if output.exists() or report.exists():
            raise FileExistsError("Use a new native normalization identity")
        training_path = Path(config["training_report"]).resolve()
        if A.sha256_file(training_path) != config["training_report_sha256"]:
            raise ValueError("Frozen native training report changed")
        training = A.read_json(training_path)
        settings, audit = training["config"], training["checkpoint_audit"]
        if (
            training["status"] != "completed"
            or training["test_opened"] is not False
            or settings["smoke"] is not False
            or settings["train_image_indices"]
            or audit["status"] != "passed"
            or audit["metrics"]["count"] != 1000
            or audit["selected_artifacts_sha256"] != training["best_artifacts_sha256"]
        ):
            raise ValueError("Require completed full native training and its selected-weight audit")
        archive = (
            Path(config["training_source_archive"])
            if config.get("training_source_archive")
            else None
        )
        binding_settings = {"source_files_sha256": settings["source_sha256"]}
        binding = PatchNormalizationAudit.bind_training_sources(binding_settings, root, archive)
        training_output = Path(settings["output"])
        UnityQualityTrainer.verify_artifacts(training_output, training["best_artifacts_sha256"])
        trainer = UnityQualityTrainer(UnityNormalizationAudit.training_config_path(settings), root)
        if (
            trainer.config.corpus != Path(settings["corpus"]).resolve()
            or trainer.config.corpus_sha256 != settings["corpus_sha256"]
            or trainer.config.zero_probability_threshold != settings["zero_probability_threshold"]
        ):
            raise ValueError("Native trainer configuration differs from the selected model inputs")
        device = ExperimentRuntime.configure(settings["seed"])
        if device.type != "cuda":
            raise RuntimeError("Native normalization diagnosis requires CUDA")
        corpus = Path(settings["corpus"])
        train = UnityPatchDataset(corpus, "train", expected_sha256=settings["corpus_sha256"])
        validation = UnityPatchDataset(
            corpus, "validation", expected_sha256=settings["corpus_sha256"]
        )
        if (
            len(train.rows) != 10000
            or len(validation.rows) != 1000
            or train.fingerprint != settings["corpus_fingerprint"]
        ):
            raise ValueError("Require the frozen full development corpus")
        checkpoint = torch.load(training_output / "best.pt", map_location="cpu", weights_only=False)
        if (
            A.fingerprint(checkpoint["config"]) != A.fingerprint(settings)
            or checkpoint["epoch"] != audit["epoch"]
        ):
            raise ValueError("Selected checkpoint differs from completed training")
        model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
        execution_paths = {
            Path(__file__).resolve(),
            config_path,
            training_path,
            corpus / "corpus.json",
        }
        execution_paths.update(Path(name) for name in settings["source_sha256"])
        execution_paths.update(
            root / name
            for name in [
                "src/adaptive_astc/evaluation/patch_normalization.py",
                "src/adaptive_astc/utils/artifacts.py",
            ]
        )
        sources = {str(path): A.sha256_file(path) for path in execution_paths}
        sources.update(
            {
                str(config_path): config_sha256,
                str(training_path): config["training_report_sha256"],
                str(corpus / "corpus.json"): settings["corpus_sha256"],
            }
        )
        cls.verify_sources(sources)
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as handle:
            handle.write('{"status":"running"}\n')
        state: JsonDict = {
            "status": "running",
            "config": config,
            "training_source_binding": binding,
            "execution_sources_sha256": sources,
            "source_checkpoint_sha256": training["best_artifacts_sha256"]["best.pt"],
            "optimizer_updates": 0,
            "test_opened": False,
            "sampling": "Each train image once, uniform within-image patches with replacement",
            "scope": "Selected native weights, train-only BN statistics, development validation",
            "confirmation_deployment_integrated": False,
        }
        try:
            before, predictions, decisions = trainer.evaluate(model, validation, device)
            cls.verify_predictions(predictions, training_output / "best-validation.npz")
            if decisions != A.read_json(training_output / "best-decisions.json")["rows"]:
                raise ValueError("Original selected-weight decisions did not replay")
            state["before_metrics"] = before
            image_indices = list(range(32 if config["smoke"] else len(train.rows)))
            views = trainer.config.patches_per_image
            bags = UnityImageBags(train, image_indices, views)
            loader = DataLoader(bags, batch_size=settings["image_batch_size"], num_workers=0)
            draws: list[np.ndarray] = []

            def batches() -> Iterator[tuple[Tensor, Tensor, Tensor, Tensor]]:
                for batch, _ in loader:
                    draws.append(batch["patch_index"].numpy().copy())
                    yield cls.calibration_inputs(batch)

            calibration_started = time.perf_counter()
            count = PatchNormalizationAudit.recalibrate(model, batches(), device)
            torch.cuda.synchronize()
            state["calibration_seconds"] = time.perf_counter() - calibration_started
            expected_count = len(image_indices) * views
            if count != expected_count:
                raise ValueError("Native calibration patch coverage mismatch")
            for name, parameter in model.named_parameters():
                if not torch.equal(parameter.detach().cpu(), checkpoint["model"][name]):
                    raise ValueError("Native BN re-estimation changed learned parameters")
            after, predictions, decisions = trainer.evaluate(model, validation, device)
            np.save(output / "train-patch-indexes.npy", np.concatenate(draws))
            torch.save(
                {"model": model.state_dict(), "config": settings, "postprocessing": state["scope"]},
                output / "recalibrated.pt",
            )
            np.savez_compressed(
                output / "recalibrated-validation.npz",
                channel_mse=predictions["channel_mse"],
                channel_zero=predictions["channel_zero"],
                zero_probability=predictions["zero_probability"],
                image_quality=predictions["image_quality"],
            )
            A.write_json(
                output / "recalibrated-decisions.json", {"rows": decisions, "metrics": after}
            )
            fresh = UnityQualityRegressor.from_checkpoint(
                torch.load(output / "recalibrated.pt", map_location="cpu", weights_only=False),
                device,
            )
            _, reloaded, reloaded_decisions = trainer.evaluate(fresh, validation, device)
            cls.verify_predictions(reloaded, output / "recalibrated-validation.npz")
            if reloaded_decisions != decisions:
                raise ValueError("Re-estimated checkpoint decisions did not replay")
            UnityQualityTrainer.verify_input_files(train.rows + validation.rows)
            UnityQualityTrainer.verify_artifacts(training_output, training["best_artifacts_sha256"])
            cls.verify_sources(sources)
            if binding != PatchNormalizationAudit.bind_training_sources(
                binding_settings, root, archive
            ):
                raise ValueError("Native training source archive changed")
            state.update(
                status="passed_smoke" if config["smoke"] else "passed",
                after_metrics=after,
                calibration_images=len(image_indices),
                calibration_patch_views=views,
                calibration_patches=count,
                parameters_unchanged=True,
                checkpoint_reload="passed",
                artifacts_sha256={
                    name: A.sha256_file(output / name)
                    for name in [
                        "train-patch-indexes.npy",
                        "recalibrated.pt",
                        "recalibrated-validation.npz",
                        "recalibrated-decisions.json",
                    ]
                },
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    UnityNormalizationAudit.run(args.config)


if __name__ == "__main__":
    main()
