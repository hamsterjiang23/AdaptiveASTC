"""CUDA patch regression with image-level validation and auditable checkpoints."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.amp.grad_scaler import GradScaler
from torch.optim.swa_utils import AveragedModel, get_ema_multi_avg_fn
from torch.utils.data import DataLoader, WeightedRandomSampler

from adaptive_astc.config import JsonDict
from adaptive_astc.data.patch_bags import ImagePatchBatchSampler
from adaptive_astc.data.patch_dataset import NativePatchDataset
from adaptive_astc.data.patch_sampling import PatchSampling
from adaptive_astc.evaluation.patch_metrics import PatchRegressionMetrics
from adaptive_astc.models.patch_regressor import ASTCPatchRegressor
from adaptive_astc.training.patch_loss import PatchRegressionLoss
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.runtime import ExperimentRuntime


@dataclass(frozen=True)
class PatchTrainConfig:
    corpus: Path
    output: Path
    report: Path
    initialization: str = "scratch"
    epochs: int = 15
    batch_size: int = 32
    patches_per_image: int = 4
    learning_rate: float = 0.001
    weight_decay: float = 0.05
    warmup_epochs: int = 2
    workers: int = 2
    seed: int = 20261111
    max_steps: int = 0
    remove_maxpool: bool = True
    monotone: bool = False
    ema_decay: float = 0.0
    patience: int = 0
    group_image_cap: int = 0
    bag_size: int = 1
    aggregate_loss_weight: float = 0.0

    def validate(self) -> None:
        if min(self.epochs, self.batch_size, self.patches_per_image) < 1:
            raise ValueError("Epoch, batch and sampling budget must be positive")
        if type(self.group_image_cap) is not int or self.group_image_cap < 0:
            raise ValueError("Asset group image cap must be a nonnegative integer")
        if self.initialization not in {"scratch", "pretrained"}:
            raise ValueError("Unsupported initialization")
        if self.workers < 0 or self.max_steps < 0 or self.warmup_epochs < 0:
            raise ValueError("Workers, step limit and warmup must be nonnegative")
        if not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("Learning rate must be finite and positive")
        if not math.isfinite(self.weight_decay) or self.weight_decay < 0:
            raise ValueError("Weight decay must be finite and nonnegative")
        if not 0 <= self.ema_decay < 1 or self.patience < 0:
            raise ValueError("EMA decay must be in [0,1), patience nonnegative")
        PatchRegressionLoss(self.bag_size, self.aggregate_loss_weight)
        if self.batch_size % self.bag_size:
            raise ValueError("Batch size must contain complete patch bags")


class PatchTrainer:
    def __init__(self, config: PatchTrainConfig) -> None:
        config.validate()
        self.config = config

    def training_batches(self, train: NativePatchDataset) -> DataLoader:
        config = self.config
        generator = torch.Generator().manual_seed(config.seed)
        count = len(train.rows) * config.patches_per_image
        if config.bag_size > 1:
            return DataLoader(
                train,
                batch_sampler=ImagePatchBatchSampler(
                    train.rows,
                    train.image_ids,
                    batch_size=config.batch_size,
                    bag_size=config.bag_size,
                    num_samples=count,
                    generator=generator,
                    group_image_cap=config.group_image_cap,
                ),
                num_workers=config.workers,
                pin_memory=True,
                persistent_workers=config.workers > 0,
            )
        return DataLoader(
            train,
            batch_size=config.batch_size,
            sampler=WeightedRandomSampler(
                PatchSampling.weights(train.rows, train.image_ids, config.group_image_cap).tolist(),
                count,
                replacement=True,
                generator=generator,
            ),
            num_workers=config.workers,
            pin_memory=True,
            persistent_workers=config.workers > 0,
        )

    def fit(self) -> JsonDict:
        config = self.config
        device = ExperimentRuntime.configure(config.seed)
        if device.type != "cuda":
            raise RuntimeError("Patch training requires CUDA")
        if config.output.exists() and any(config.output.iterdir()):
            raise FileExistsError("Use a fresh training identity; partial trials remain archived")
        config.output.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        train = NativePatchDataset(config.corpus, "train")
        validation = NativePatchDataset(config.corpus, "validation")
        if train.fingerprint != validation.fingerprint:
            raise ValueError("Training and validation corpus identities differ")
        model = ASTCPatchRegressor(
            config.initialization, config.remove_maxpool, config.monotone
        ).to(device)
        ema = (
            AveragedModel(
                model,
                device=device,
                multi_avg_fn=get_ema_multi_avg_fn(config.ema_decay),
                use_buffers=True,
            )
            if config.ema_decay
            else None
        )
        optimizer = torch.optim.AdamW(
            model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
        )
        scaler = GradScaler("cuda")
        batches = self.training_batches(train)
        criterion = PatchRegressionLoss(config.bag_size, config.aggregate_loss_weight)
        validation_batches = DataLoader(
            validation,
            batch_size=config.batch_size,
            num_workers=config.workers,
            pin_memory=True,
            persistent_workers=config.workers > 0,
        )
        settings = {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        }
        settings.update(
            {
                "corpus_fingerprint": train.fingerprint,
                "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
                "gpu": torch.cuda.get_device_name(),
                "torch": torch.__version__,
                "loss": "Huber log10(MSE+1e-10), delta0.1=1dB; "
                "threshold weight 1+2exp(-distance/3dB)",
                "sampling": (
                    f"image weight min(1,{config.group_image_cap}/asset_group_images); "
                    "uniform patch within image; replacement"
                    if config.group_image_cap
                    else "equal expected image weight; uniform patch within image; replacement"
                ),
                "targets_clipped": False,
                "patch_bag": {
                    "size": config.bag_size,
                    "aggregate_loss_weight": config.aggregate_loss_weight,
                    "sampling": "same-image patches with replacement"
                    if config.bag_size > 1
                    else "independent patch draws",
                    "target_scope": "sampled bag, not full image",
                    "aggregation": "valid-pixel-weighted MSE, inference clipping and epsilon",
                },
                "augmentations": [],
                "ema": "parameters and buffers after each applied optimizer update"
                if ema
                else False,
                "selection": "validation exact footprint accuracy at margin0, "
                "then near-threshold RMSE",
                "scope": "source RGB GDC development; no test access; no Unity production claim",
                "source_files_sha256": {
                    str(path): ArtifactStore.sha256_file(path)
                    for path in [
                        Path(__file__),
                        Path(__file__).parents[1] / "models/patch_regressor.py",
                        Path(__file__).parents[1] / "data/patch_dataset.py",
                        Path(__file__).parents[1] / "data/patch_sampling.py",
                        Path(__file__).parents[1] / "data/patch_bags.py",
                        Path(__file__).with_name("patch_loss.py"),
                        Path(__file__).parents[1] / "evaluation/patch_metrics.py",
                        Path(__file__).parents[1] / "data/patch_targets.py",
                    ]
                },
            }
        )
        ArtifactStore.write_json(config.output / "config.json", settings)
        history: list[JsonDict] = []
        best_key = (math.inf, math.inf)
        best_rmse = math.inf
        stale_epochs = 0
        stop_reason = "epoch_budget"
        applied_updates = 0

        def track_update(
            optimizer: torch.optim.Optimizer, args: tuple[object, ...], kwargs: dict[str, object]
        ) -> None:
            nonlocal applied_updates
            applied_updates += 1
            if ema is not None:
                ema.update_parameters(model)

        hook = optimizer.register_step_post_hook(track_update)
        torch.cuda.reset_peak_memory_stats()
        try:
            for epoch in range(config.epochs):
                epoch_started = time.perf_counter()
                warmup = min(config.warmup_epochs, config.epochs)
                factor = (
                    (epoch + 1) / warmup
                    if epoch < warmup
                    else 0.5
                    * (1 + math.cos(math.pi * (epoch - warmup) / max(1, config.epochs - warmup)))
                )
                for group in optimizer.param_groups:
                    group["lr"] = config.learning_rate * factor
                model.train()
                samples, attempts, loss_sum = 0, 0, 0.0
                patch_loss_sum, aggregate_loss_sum = 0.0, 0.0
                before_updates = applied_updates
                for images, targets, indexes in batches:
                    images, targets = images.to(device), targets.to(device)
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast("cuda", dtype=torch.float16):
                        prediction = model(images)
                    loss, patch_loss, aggregate_loss = criterion(
                        prediction,
                        targets,
                        torch.from_numpy(train.pixel_counts[indexes.numpy()]).to(device),
                        torch.from_numpy(train.image_ids[indexes.numpy()]),
                    )
                    if not torch.isfinite(loss):
                        raise ValueError("Non-finite regression loss")
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                    scaler.step(optimizer)
                    scaler.update()
                    loss_sum += float(loss.detach()) * len(images)
                    patch_loss_sum += float(patch_loss.detach()) * len(images)
                    aggregate_loss_sum += float(aggregate_loss.detach()) * len(images)
                    samples += len(images)
                    attempts += 1
                    if attempts % 25 == 0:
                        ArtifactStore.write_json(
                            config.output / "progress.json",
                            {
                                "epoch": epoch + 1,
                                "batches": attempts,
                                "samples": samples,
                                "optimizer_updates": applied_updates,
                                "wall_seconds": time.perf_counter() - started,
                            },
                        )
                    if config.max_steps and attempts >= config.max_steps:
                        break
                torch.cuda.synchronize()
                training_seconds = time.perf_counter() - epoch_started
                metrics, predicted_psnr = self.evaluate(
                    model, validation_batches, validation, device
                )
                variants: dict[str, tuple[nn.Module, JsonDict, np.ndarray]] = {
                    "raw": (model, metrics, predicted_psnr)
                }
                if ema is not None:
                    ema_metrics, ema_psnr = self.evaluate(
                        ema, validation_batches, validation, device
                    )
                    variants["ema"] = (ema.module, ema_metrics, ema_psnr)
                updates = applied_updates - before_updates
                row = {
                    "epoch": epoch + 1,
                    "train_loss": loss_sum / samples,
                    "train_patch_loss": patch_loss_sum / samples,
                    "train_aggregate_loss": aggregate_loss_sum / samples,
                    "samples": samples,
                    "step_attempts": attempts,
                    "optimizer_updates": updates,
                    "amp_skipped_steps": attempts - updates,
                    "learning_rate": optimizer.param_groups[0]["lr"],
                    "training_seconds": training_seconds,
                    "validation": metrics,
                    "validation_variants": {name: value[1] for name, value in variants.items()},
                    "ema_updates": int(ema.n_averaged) if ema is not None else 0,
                    "seconds": time.perf_counter() - epoch_started,
                }
                if updates == 0:
                    raise RuntimeError("No optimizer update applied; trial is incomplete")
                history.append(row)
                winner = min(
                    variants,
                    key=lambda name: (
                        -variants[name][1]["accuracy"],
                        self.rmse_key(variants[name][1]),
                    ),
                )
                eval_model, winner_metrics, winner_psnr = variants[winner]
                key = (-winner_metrics["accuracy"], self.rmse_key(winner_metrics))
                checkpoint = {
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "scaler": scaler.state_dict(),
                    "config": settings,
                    "history": history,
                    "epoch": epoch + 1,
                    "ema": ema.state_dict() if ema is not None else None,
                }
                temporary = config.output / "last.tmp"
                torch.save(checkpoint, temporary)
                temporary.replace(config.output / "last.pt")
                if key < best_key:
                    best_key = key
                    torch.save(
                        {
                            **checkpoint,
                            "model": eval_model.state_dict(),
                            "selected_variant": winner,
                        },
                        config.output / "best.pt",
                    )
                    np.savez_compressed(
                        config.output / "best-validation.npz",
                        psnr=winner_psnr,
                        labels=np.array([item["class_id"] for item in validation.rows]),
                    )
                rmse_winner = min(variants, key=lambda name: self.rmse_key(variants[name][1]))
                epoch_rmse = variants[rmse_winner][1]["near_threshold_rmse_db"]
                if epoch_rmse is None:
                    pass
                elif epoch_rmse < best_rmse:
                    best_rmse, stale_epochs = epoch_rmse, 0
                    torch.save(
                        {
                            **checkpoint,
                            "model": variants[rmse_winner][0].state_dict(),
                            "selected_variant": rmse_winner,
                        },
                        config.output / "best_rmse.pt",
                    )
                else:
                    stale_epochs += 1
                result = {
                    "status": "running",
                    "config": settings,
                    "history": history,
                    "best_validation_accuracy": -best_key[0],
                    "best_near_threshold_rmse_db": best_rmse if math.isfinite(best_rmse) else None,
                    "wall_seconds": time.perf_counter() - started,
                    "peak_vram_bytes": torch.cuda.max_memory_allocated(),
                    "test_opened": False,
                }
                ArtifactStore.write_json(config.output / "history.json", result)
                ArtifactStore.write_json(config.report, result)
                print(row, flush=True)
                if config.patience and epoch >= warmup and stale_epochs >= config.patience:
                    stop_reason = "near_threshold_rmse_patience"
                    break
        finally:
            hook.remove()
        result["status"] = "passed_smoke" if config.max_steps else "completed"
        result["stop_reason"] = stop_reason
        result["checkpoint_sha256"] = ArtifactStore.sha256_file(config.output / "best.pt")
        result["wall_seconds"] = time.perf_counter() - started
        ArtifactStore.write_json(config.output / "history.json", result)
        ArtifactStore.write_json(config.output / "progress.json", result)
        ArtifactStore.write_json(config.report, result)
        return result

    @staticmethod
    def rmse_key(metrics: JsonDict) -> float:
        value = metrics["near_threshold_rmse_db"]
        return math.inf if value is None else float(value)

    @staticmethod
    def audit_best(output: Path, report: Path) -> JsonDict:
        history = ArtifactStore.read_json(output / "history.json")
        if history["status"] not in {"completed", "passed_smoke"}:
            raise ValueError("Checkpoint audit requires a finished trial")
        checkpoint_path = output / "best.pt"
        checkpoint_sha = ArtifactStore.sha256_file(checkpoint_path)
        if checkpoint_sha != history["checkpoint_sha256"]:
            raise ValueError("Selected checkpoint changed")
        settings = history["config"]
        device = ExperimentRuntime.configure(settings["seed"])
        if device.type != "cuda":
            raise RuntimeError("Checkpoint prediction audit requires CUDA")
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        if checkpoint["config"] != settings:
            raise ValueError("Checkpoint configuration differs from the final report")
        validation = NativePatchDataset(Path(settings["corpus"]), "validation")
        if validation.fingerprint != settings["corpus_fingerprint"]:
            raise ValueError("Checkpoint corpus changed")
        model = ASTCPatchRegressor("scratch", settings["remove_maxpool"], settings["monotone"]).to(
            device
        )
        model.load_state_dict(checkpoint["model"], strict=True)
        batches = DataLoader(validation, batch_size=settings["batch_size"], num_workers=0)
        metrics, psnr = PatchTrainer.evaluate(model, batches, validation, device)
        with np.load(output / "best-validation.npz", allow_pickle=False) as saved:
            np.testing.assert_allclose(psnr, saved["psnr"], rtol=0, atol=1e-5)
            np.testing.assert_array_equal(
                saved["labels"], np.array([row["class_id"] for row in validation.rows])
            )
        if metrics["accuracy"] != history["best_validation_accuracy"]:
            raise ValueError("Reloaded checkpoint does not reproduce selected accuracy")
        result = {
            "status": "passed",
            "checkpoint_sha256": checkpoint_sha,
            "predictions_sha256": ArtifactStore.sha256_file(output / "best-validation.npz"),
            "selected_variant": checkpoint["selected_variant"],
            "selected_epoch": checkpoint["epoch"],
            "metrics": metrics,
            "fp32_parameter_bytes": sum(p.numel() * p.element_size() for p in model.parameters()),
            "prediction_tolerance_db": 1e-5,
            "test_opened": False,
        }
        ArtifactStore.write_json(report, result)
        return result

    @staticmethod
    def evaluate(
        model: nn.Module, batches: DataLoader, dataset: NativePatchDataset, device: torch.device
    ) -> tuple[JsonDict, np.ndarray]:
        started = time.perf_counter()
        model.eval()
        prediction = np.empty_like(dataset.mse)
        with torch.inference_mode():
            for images, _, indexes in batches:
                with torch.autocast("cuda", dtype=torch.float16):
                    values = model(images.to(device, non_blocking=True))
                prediction[indexes.numpy()] = values.float().cpu().numpy()
        mse = dataset.aggregate(prediction)
        metrics, psnr = PatchRegressionMetrics.compute(mse, dataset.rows)
        metrics["seconds"] = time.perf_counter() - started
        return metrics, psnr
