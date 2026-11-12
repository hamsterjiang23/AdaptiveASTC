"""Refit native image heads on frozen encodings with sampled or complete patch bags."""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import torch
from torch import Tensor
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader, Subset, TensorDataset

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_quality_loss import (
    UnityImageTargets,
    UnityQualityLoss,
    UnityQualityLossConfig,
)
from adaptive_astc.training.unity_quality_trainer import UnityQualityTrainer
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from script.audit_unity_normalization import UnityNormalizationAudit


@dataclass
class NativeFeatureCache:
    rows: list[JsonDict]
    features: Tensor
    valid_pixels: Tensor
    metadata: Tensor
    patch_indexes: list[Tensor]
    channel_mse: np.ndarray
    targets: dict[str, Tensor]

    def predict(
        self,
        model: UnityQualityRegressor,
        image_indexes: Tensor,
        views: int = 0,
        generator: torch.Generator | None = None,
    ) -> dict[str, Tensor]:
        device = self.features.device
        chosen = []
        for image_index in image_indexes.tolist():
            available = self.patch_indexes[image_index]
            if views:
                draws = torch.randint(len(available), (views,), generator=generator)
                available = available[draws]
            chosen.append(available)
        patch_indexes = torch.cat(chosen).to(device)
        image_ids = torch.arange(len(chosen)).repeat_interleave(
            torch.tensor([len(indexes) for indexes in chosen])
        )
        return model.predict_images(
            self.features[patch_indexes],
            self.valid_pixels[patch_indexes],
            image_ids.to(device),
            self.metadata[image_indexes.to(device)],
        )

    @classmethod
    def prepare(
        cls,
        dataset: UnityPatchDataset,
        image_indexes: list[int],
        model: UnityQualityRegressor,
        batch_size: int,
        device: torch.device,
        output: Path,
        name: str,
    ) -> tuple[NativeFeatureCache, dict[str, str]]:
        image_lookup = np.full(len(dataset.rows), -1, dtype=np.int64)
        image_lookup[image_indexes] = np.arange(len(image_indexes))
        source_patches = np.flatnonzero(image_lookup[dataset.image_ids] >= 0)
        patch_lookup = np.full(len(dataset), -1, dtype=np.int64)
        patch_lookup[source_patches] = np.arange(len(source_patches))
        features = np.empty((len(source_patches), 512), dtype=np.float32)
        logs = np.empty((len(source_patches), 20, 4), dtype=np.float64)
        model.eval()
        with torch.inference_mode():
            for batch in DataLoader(
                Subset(dataset, source_patches.tolist()), batch_size=batch_size, num_workers=0
            ):
                with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                    encoded = model.encode(
                        batch["rgba"].to(device),
                        batch["valid_mask"].to(device),
                        batch["metadata"].to(device),
                    )
                positions = patch_lookup[batch["patch_index"].numpy()]
                features[positions] = encoded["features"].float().cpu().numpy()
                logs[positions] = encoded["channel_log_mse"].float().cpu().numpy()
        ids = image_lookup[dataset.image_ids[source_patches]]
        pixels = dataset.pixel_counts[source_patches]
        counts = np.bincount(ids, minlength=len(image_indexes))
        ordered = np.argsort(ids, kind="stable")
        patches = [
            torch.from_numpy(indexes) for indexes in np.split(ordered, np.cumsum(counts)[:-1])
        ]
        rows = [dataset.rows[index] for index in image_indexes]
        paths = [output / f"{name}-features.npy", output / f"{name}-indexes.npz"]
        np.save(paths[0], features)
        np.savez_compressed(
            paths[1],
            source_images=np.asarray(image_indexes, dtype=np.int64),
            source_patches=source_patches,
            image_ids=ids,
            valid_pixels=pixels,
        )
        return cls(
            rows,
            torch.from_numpy(features).to(device),
            torch.from_numpy(pixels).to(device),
            torch.from_numpy(dataset.input_metadata[image_indexes]).to(device),
            patches,
            UnityQualityPrediction.aggregate_mse(logs, pixels, ids, len(rows)),
            {key: value.to(device) for key, value in UnityImageTargets.build(rows).items()},
        ), {str(path): A.sha256_file(path) for path in paths}


class UnityImageHeadRefit:
    @staticmethod
    def loss_config(config: JsonDict, initial_settings: JsonDict) -> UnityQualityLossConfig:
        weights = UnityQualityLossConfig(
            **{
                name: config.get(name, initial_settings[name])
                for name in ("zero_weight", "ssim_weight", "angle_weight")
            }
        )
        weights.validate()
        if weights.zero_weight + weights.ssim_weight + weights.angle_weight == 0:
            raise ValueError("Image-head refitting requires a positive supervision weight")
        return weights

    @staticmethod
    def image_losses(
        outputs: dict[str, Tensor], targets: dict[str, Tensor], settings: JsonDict
    ) -> dict[str, Tensor]:
        logits, quality = outputs["channel_zero_logits"], outputs["image_quality"]
        active = targets["channel_active"][:, None, :].expand_as(logits)
        mask = targets["quality_active"][:, None, :].expand_as(quality)
        zero = torch.nn.functional.binary_cross_entropy_with_logits(
            logits[active].float(), targets["channel_zero"][active]
        )
        ssim = UnityQualityLoss.masked_huber(
            quality[:, :, :1], targets["image_quality"][:, :, :1], mask[:, :, :1], 1
        )
        angle = UnityQualityLoss.masked_huber(
            quality[:, :, 1:], targets["image_quality"][:, :, 1:], mask[:, :, 1:], 1
        )
        total = (
            settings["zero_weight"] * zero
            + settings["ssim_weight"] * ssim
            + settings["angle_weight"] * angle
        )
        if not torch.isfinite(total):
            raise ValueError("Nonfinite native image-head supervision")
        return {"total": total, "zero": zero, "ssim": ssim, "angle": angle}

    @staticmethod
    def evaluate(
        cache: NativeFeatureCache,
        model: UnityQualityRegressor,
        trainer: UnityQualityTrainer,
    ) -> tuple[JsonDict, dict[str, np.ndarray], list[JsonDict]]:
        started = time.perf_counter()
        model.eval()
        with torch.inference_mode():
            with torch.autocast("cuda", dtype=torch.float16):
                outputs = cache.predict(model, torch.arange(len(cache.rows)))
            quality = outputs["image_quality"].cpu().numpy().astype(np.float64)
            probability = (
                torch.sigmoid(outputs["channel_zero_logits"]).cpu().numpy().astype(np.float64)
            )
        zero = probability >= trainer.config.zero_probability_threshold
        metrics, decisions = UnityQualityPrediction.score(
            cache.rows,
            [trainer.resolver.policy_for(row) for row in cache.rows],
            cache.channel_mse,
            zero,
            quality,
        )
        metrics["seconds"] = time.perf_counter() - started
        return (
            metrics,
            {
                "channel_mse": cache.channel_mse,
                "channel_zero": zero,
                "zero_probability": probability,
                "image_quality": quality,
            },
            decisions,
        )

    @classmethod
    def run(cls, config_path: Path) -> JsonDict:
        root = Path(__file__).resolve().parents[1]
        config_path = config_path.resolve()
        config_sha256 = A.sha256_file(config_path)
        config = A.read_json(config_path)
        if (
            type(config["smoke"]) is not bool
            or type(config["epochs"]) is not int
            or config["epochs"] < 1
            or type(config["patches_per_image"]) is not int
            or config["patches_per_image"] not in (0, 4)
            or not math.isfinite(config["learning_rate"])
            or config["learning_rate"] <= 0
        ):
            raise ValueError(
                "Require explicit smoke, epoch budget, 0/all or4 views, and positive lr"
            )
        output, report = Path(config["output"]).resolve(), Path(config["report"]).resolve()
        if not output.is_relative_to(root / "experiment report/.local") or report.is_relative_to(
            output
        ):
            raise ValueError("Require private head-stage artifacts and an external report")
        if output.exists() or report.exists():
            raise FileExistsError("Use a new native image-head refit identity")
        training_path = Path(config["training_report"]).resolve()
        if A.sha256_file(training_path) != config["training_report_sha256"]:
            raise ValueError("Initial native training report changed")
        initial = A.read_json(training_path)
        initial_settings = initial["config"]
        loss_config = cls.loss_config(config, initial_settings)
        if (
            initial["status"] != "completed"
            or initial["test_opened"] is not False
            or initial_settings["smoke"] is not False
            or initial_settings["train_image_indices"]
            or initial["training_updates"] <= 0
            or initial_settings["train_images"] != 10000
            or initial_settings["validation_images"] != 1000
            or initial["checkpoint_audit"]["status"] != "passed"
            or initial["checkpoint_audit"]["test_opened"] is not False
            or initial["checkpoint_audit"]["metrics"]["count"] != 1000
            or initial["checkpoint_audit"]["selected_artifacts_sha256"]
            != initial["best_artifacts_sha256"]
            or initial["checkpoint_audit"]["checkpoint_sha256"] != initial["checkpoint_sha256"]
            or initial["best_artifacts_sha256"]["best.pt"] != initial["checkpoint_sha256"]
        ):
            raise ValueError("Require complete full native training and selected-weight replay")
        archive = (
            Path(config["training_source_archive"])
            if config.get("training_source_archive")
            else None
        )
        binding_settings = {"source_files_sha256": initial_settings["source_sha256"]}
        source_binding = PatchNormalizationAudit.bind_training_sources(
            binding_settings, root, archive
        )
        initial_output = Path(initial_settings["output"])
        UnityQualityTrainer.verify_artifacts(initial_output, initial["best_artifacts_sha256"])
        training_config_path = UnityNormalizationAudit.training_config_path(initial_settings)
        corpus = Path(initial_settings["corpus"])
        execution_paths = {Path(name) for name in initial_settings["source_sha256"]}
        execution_paths.update(
            {
                Path(__file__).resolve(),
                config_path,
                training_path,
                root / "script/audit_unity_normalization.py",
                root / "src/adaptive_astc/evaluation/patch_normalization.py",
                root / "src/adaptive_astc/utils/artifacts.py",
            }
        )
        sources = {str(path): A.sha256_file(path) for path in execution_paths}
        sources.update(
            {
                str(config_path): config_sha256,
                str(training_path): config["training_report_sha256"],
                str(corpus / "corpus.json"): initial_settings["corpus_sha256"],
            }
        )
        UnityNormalizationAudit.verify_sources(sources)
        trainer = UnityQualityTrainer(training_config_path, root)
        if (
            trainer.config.corpus != Path(initial_settings["corpus"]).resolve()
            or trainer.config.corpus_sha256 != initial_settings["corpus_sha256"]
            or trainer.config.zero_probability_threshold
            != initial_settings["zero_probability_threshold"]
        ):
            raise ValueError("Initial native trainer input configuration differs from the model")
        trainer.config = replace(
            trainer.config, output=output, report=report, smoke=config["smoke"]
        )
        device = ExperimentRuntime.configure(initial_settings["seed"])
        if device.type != "cuda":
            raise RuntimeError("Native image-head refitting requires CUDA")
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as handle:
            handle.write('{"status":"preparing"}\n')
        started = time.perf_counter()
        state: JsonDict = {"status": "preparing", "training_updates": 0, "test_opened": False}
        try:
            datasets = {
                split: UnityPatchDataset(
                    corpus, split, expected_sha256=initial_settings["corpus_sha256"]
                )
                for split in ("train", "validation")
            }
            if len(datasets["train"].rows) != 10000 or len(datasets["validation"].rows) != 1000:
                raise ValueError("Require the frozen full development corpus")
            if datasets["train"].fingerprint != initial_settings["corpus_fingerprint"]:
                raise ValueError("Initial native corpus fingerprint changed")
            checkpoint = torch.load(
                initial_output / "best.pt", map_location="cpu", weights_only=False
            )
            if A.fingerprint(checkpoint["config"]) != A.fingerprint(initial_settings):
                raise ValueError("Initial checkpoint settings differ from its training report")
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            for parameter in model.parameters():
                parameter.requires_grad_(False)
            model.image_head.requires_grad_(True)
            train_images = list(range(32 if config["smoke"] else 10000))
            train, train_files = NativeFeatureCache.prepare(
                datasets["train"],
                train_images,
                model,
                trainer.config.validation_batch_size,
                device,
                output,
                "train",
            )
            validation, validation_files = NativeFeatureCache.prepare(
                datasets["validation"],
                list(range(1000)),
                model,
                trainer.config.validation_batch_size,
                device,
                output,
                "validation",
            )
            baseline, predictions, decisions = cls.evaluate(validation, model, trainer)
            UnityNormalizationAudit.verify_predictions(
                predictions, initial_output / "best-validation.npz"
            )
            if decisions != A.read_json(initial_output / "best-decisions.json")["rows"]:
                raise ValueError("Cached native baseline decisions did not replay")
            sources.update({**train_files, **validation_files})
            UnityNormalizationAudit.verify_sources(sources)
            settings = {
                **initial_settings,
                "output": str(output),
                "report": str(report),
                "smoke": config["smoke"],
                "train_image_indices": train_images if config["smoke"] else [],
                "epochs": config["epochs"],
                "learning_rate": config["learning_rate"],
                "warmup_epochs": 0,
                "patience": 0,
                "learning_rate_schedule": "Constant during the image-head stage",
                "ema_decay": 0.0,
                "ema": False,
                "selection_metric": "accuracy",
                "group_image_cap": 0,
                "normal_image_repeats": 1,
                "train_epoch_image_draws": len(train.rows),
                "zero_weight": loss_config.zero_weight,
                "ssim_weight": loss_config.ssim_weight,
                "angle_weight": loss_config.angle_weight,
                "source_sha256": sources,
                "training_config_path": str(training_config_path),
                "train_images": len(train.rows),
                "validation_images": 1000,
                "stage": "Frozen encoder image-head refit",
                "head_patch_views": config["patches_per_image"],
                "patches_per_image": config["patches_per_image"],
                "image_target_scope": "Full-image targets with frozen native patch encodings",
                "initial_training_report": str(training_path),
                "initial_training_report_sha256": config["training_report_sha256"],
                "trainable_parameters": sum(
                    p.numel() for p in model.parameters() if p.requires_grad
                ),
                "sampling": (
                    "Each selected image once per epoch; independent fixed-seed patch generator"
                ),
                "selection": "Validation footprint Top1 then color near-threshold RMSE",
            }
            A.write_json(output / "config.json", settings)
            state.update(
                status="running",
                config=settings,
                baseline=baseline,
                initial_training_updates=initial["training_updates"],
                training_source_binding=source_binding,
                history=[],
                preparation_seconds=time.perf_counter() - started,
            )
            optimizer = torch.optim.AdamW(
                model.image_head.parameters(),
                lr=config["learning_rate"],
                weight_decay=initial_settings["weight_decay"],
            )
            scaler = GradScaler("cuda")
            updates = 0

            def track_update(
                optimizer: torch.optim.Optimizer,
                args: tuple[object, ...],
                kwargs: dict[str, object],
            ) -> None:
                nonlocal updates
                updates += 1
                state["training_updates"] = updates

            hook = optimizer.register_step_post_hook(track_update)
            loader = DataLoader(
                TensorDataset(torch.arange(len(train.rows))),
                batch_size=initial_settings["image_batch_size"],
                shuffle=True,
                generator=torch.Generator().manual_seed(initial_settings["seed"]),
            )
            patch_generator = torch.Generator().manual_seed(initial_settings["seed"] + 1)
            best_key = (math.inf, math.inf)
            torch.cuda.reset_peak_memory_stats()
            try:
                for epoch in range(config["epochs"]):
                    epoch_started = time.perf_counter()
                    model.eval()
                    totals = dict.fromkeys(["total", "zero", "ssim", "angle"], 0.0)
                    attempts, before = 0, updates
                    for (indexes,) in loader:
                        optimizer.zero_grad(set_to_none=True)
                        with torch.autocast("cuda", dtype=torch.float16):
                            outputs = train.predict(
                                model, indexes, config["patches_per_image"], patch_generator
                            )
                        targets = {
                            name: values[indexes.to(device)]
                            for name, values in train.targets.items()
                        }
                        losses = cls.image_losses(outputs, targets, settings)
                        scaler.scale(losses["total"]).backward()
                        scaler.unscale_(optimizer)
                        torch.nn.utils.clip_grad_norm_(model.image_head.parameters(), 5.0)
                        scaler.step(optimizer)
                        scaler.update()
                        for name in totals:
                            totals[name] += float(losses[name].detach()) * len(indexes)
                        attempts += 1
                    torch.cuda.synchronize()
                    training_seconds = time.perf_counter() - epoch_started
                    if updates == before:
                        raise RuntimeError("Native head epoch applied no optimizer updates")
                    metrics, predictions, decisions = cls.evaluate(validation, model, trainer)
                    state["history"].append(
                        {
                            "epoch": epoch + 1,
                            "loss": {k: v / len(train.rows) for k, v in totals.items()},
                            "validation": metrics,
                            "images_seen": len(train.rows),
                            "step_attempts": attempts,
                            "optimizer_updates": updates - before,
                            "amp_skipped_steps": attempts - (updates - before),
                            "training_seconds": training_seconds,
                        }
                    )
                    saved = {
                        "model": model.state_dict(),
                        "optimizer": optimizer.state_dict(),
                        "scaler": scaler.state_dict(),
                        "config": settings,
                        "epoch": epoch + 1,
                        "history": state["history"],
                        "selected_variant": "image_head_refit",
                    }
                    torch.save(saved, output / "last.pt")
                    key = UnityQualityTrainer.selection_key(metrics)
                    if key < best_key:
                        best_key = key
                        torch.save(saved, output / "best.pt")
                        np.savez_compressed(
                            output / "best-validation.npz",
                            channel_mse=predictions["channel_mse"],
                            channel_zero=predictions["channel_zero"],
                            zero_probability=predictions["zero_probability"],
                            image_quality=predictions["image_quality"],
                        )
                        A.write_json(
                            output / "best-decisions.json", {"rows": decisions, "metrics": metrics}
                        )
                        state["best_artifacts_sha256"] = {
                            name: A.sha256_file(output / name)
                            for name in ("best.pt", "best-validation.npz", "best-decisions.json")
                        }
                    state.update(
                        best_validation_accuracy=-best_key[0],
                        wall_seconds=time.perf_counter() - started,
                        peak_vram_bytes=torch.cuda.max_memory_allocated(),
                    )
                    A.write_json(report, state)
                    print(
                        {"epoch": epoch + 1, "updates": updates, "accuracy": metrics["accuracy"]},
                        flush=True,
                    )
            finally:
                hook.remove()
            best = torch.load(output / "best.pt", map_location="cpu", weights_only=False)
            for name, tensor in best["model"].items():
                if not name.startswith("image_head.") and not torch.equal(
                    tensor, checkpoint["model"][name]
                ):
                    raise ValueError("Frozen encoder, channel head or buffers changed")
            UnityQualityTrainer.verify_input_files(
                datasets["train"].rows + datasets["validation"].rows
            )
            UnityQualityTrainer.verify_artifacts(initial_output, initial["best_artifacts_sha256"])
            UnityNormalizationAudit.verify_sources(sources)
            if source_binding != PatchNormalizationAudit.bind_training_sources(
                binding_settings, root, archive
            ):
                raise ValueError("Initial native training source archive changed")
            audit = trainer.audit_best(
                datasets["validation"], device, state["best_artifacts_sha256"]
            )
            UnityNormalizationAudit.verify_sources(sources)
            state.update(
                status="passed_smoke" if config["smoke"] else "completed",
                checkpoint_audit=audit,
                checkpoint_sha256=state["best_artifacts_sha256"]["best.pt"],
                encoder_and_channel_head_unchanged=True,
                stop_reason="epoch_budget",
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
            A.write_json(output / "history.json", state)
        return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    UnityImageHeadRefit.run(args.config)


if __name__ == "__main__":
    main()
