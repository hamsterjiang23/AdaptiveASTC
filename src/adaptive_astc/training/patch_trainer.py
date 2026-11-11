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
from torch.utils.data import DataLoader, WeightedRandomSampler

from adaptive_astc.config import CLASSES, JsonDict
from adaptive_astc.data.patch_dataset import NativePatchDataset
from adaptive_astc.data.patch_targets import PatchErrorGrid
from adaptive_astc.evaluation.metrics import ClassificationMetrics
from adaptive_astc.models.patch_regressor import ASTCPatchRegressor
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

    def validate(self) -> None:
        if min(self.epochs, self.batch_size, self.patches_per_image) < 1:
            raise ValueError("Epoch, batch and sampling budget must be positive")
        if self.initialization not in {"scratch", "pretrained"}:
            raise ValueError("Unsupported initialization")
        if self.workers < 0 or self.max_steps < 0 or self.warmup_epochs < 0:
            raise ValueError("Workers, step limit and warmup must be nonnegative")
        if not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("Learning rate must be finite and positive")
        if not math.isfinite(self.weight_decay) or self.weight_decay < 0:
            raise ValueError("Weight decay must be finite and nonnegative")


class PatchTrainer:
    def __init__(self, config: PatchTrainConfig) -> None:
        config.validate()
        self.config = config

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
        model = ASTCPatchRegressor(config.initialization, config.remove_maxpool).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
        )
        scaler = GradScaler("cuda")
        generator = torch.Generator().manual_seed(config.seed)
        sampler = WeightedRandomSampler(
            train.image_balanced_weights().tolist(),
            len(train.rows) * config.patches_per_image,
            replacement=True,
            generator=generator,
        )
        batches = DataLoader(
            train,
            batch_size=config.batch_size,
            sampler=sampler,
            num_workers=config.workers,
            pin_memory=True,
            persistent_workers=config.workers > 0,
        )
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
                "sampling": "equal expected image weight; uniform patch within image; replacement",
                "targets_clipped": False,
                "augmentations": [],
                "ema": False,
                "selection": "validation exact footprint accuracy at margin0, "
                "then near-threshold RMSE",
                "scope": "source RGB GDC development; no test access; no Unity production claim",
                "source_files_sha256": {
                    str(path): ArtifactStore.sha256_file(path)
                    for path in [
                        Path(__file__),
                        Path(__file__).parents[1] / "models/patch_regressor.py",
                        Path(__file__).parents[1] / "data/patch_dataset.py",
                    ]
                },
            }
        )
        ArtifactStore.write_json(config.output / "config.json", settings)
        history: list[JsonDict] = []
        best_key = (math.inf, math.inf)
        applied_updates = 0

        def track_update(
            optimizer: torch.optim.Optimizer, args: tuple[object, ...], kwargs: dict[str, object]
        ) -> None:
            nonlocal applied_updates
            applied_updates += 1

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
                before_updates = applied_updates
                for images, targets, _ in batches:
                    images, targets = images.to(device), targets.to(device)
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast("cuda", dtype=torch.float16):
                        prediction = model(images)
                    weights = 1 + 2 * torch.exp(-torch.abs(-10 * targets - 35) / 3)
                    losses = nn.functional.huber_loss(
                        prediction.float(), targets, delta=0.1, reduction="none"
                    )
                    loss = (losses * weights).mean()
                    if not torch.isfinite(loss):
                        raise ValueError("Non-finite regression loss")
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                    scaler.step(optimizer)
                    scaler.update()
                    loss_sum += float(loss.detach()) * len(images)
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
                updates = applied_updates - before_updates
                row = {
                    "epoch": epoch + 1,
                    "train_loss": loss_sum / samples,
                    "samples": samples,
                    "step_attempts": attempts,
                    "optimizer_updates": updates,
                    "amp_skipped_steps": attempts - updates,
                    "learning_rate": optimizer.param_groups[0]["lr"],
                    "training_seconds": training_seconds,
                    "validation": metrics,
                    "seconds": time.perf_counter() - epoch_started,
                }
                if updates == 0:
                    raise RuntimeError("No optimizer update applied; trial is incomplete")
                history.append(row)
                key = (-metrics["accuracy"], metrics["near_threshold_rmse_db"])
                checkpoint = {
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "scaler": scaler.state_dict(),
                    "config": settings,
                    "history": history,
                    "epoch": epoch + 1,
                }
                temporary = config.output / "last.tmp"
                torch.save(checkpoint, temporary)
                temporary.replace(config.output / "last.pt")
                if key < best_key:
                    best_key = key
                    torch.save(checkpoint, config.output / "best.pt")
                    np.savez_compressed(
                        config.output / "best-validation.npz",
                        psnr=predicted_psnr,
                        labels=np.array([item["class_id"] for item in validation.rows]),
                    )
                result = {
                    "status": "running",
                    "config": settings,
                    "history": history,
                    "best_validation_accuracy": -best_key[0],
                    "wall_seconds": time.perf_counter() - started,
                    "peak_vram_bytes": torch.cuda.max_memory_allocated(),
                    "test_opened": False,
                }
                ArtifactStore.write_json(config.output / "history.json", result)
                ArtifactStore.write_json(config.report, result)
                print(row, flush=True)
        finally:
            hook.remove()
        result["status"] = "passed_smoke" if config.max_steps else "completed"
        result["checkpoint_sha256"] = ArtifactStore.sha256_file(config.output / "best.pt")
        result["wall_seconds"] = time.perf_counter() - started
        ArtifactStore.write_json(config.output / "history.json", result)
        ArtifactStore.write_json(config.output / "progress.json", result)
        ArtifactStore.write_json(config.report, result)
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
        psnr = -10 * np.log10(np.maximum(mse, 1e-10))
        truth_mse = np.array([row["full_squared_errors"] for row in dataset.rows], dtype=np.float64)
        truth_mse /= np.array([row["pixel_count"] for row in dataset.rows])[:, None] * 3 * 255**2
        truth_psnr = -10 * np.log10(np.maximum(truth_mse, 1e-10))
        labels = np.array([row["class_id"] for row in dataset.rows])
        chosen = PatchErrorGrid.choose(psnr)
        # Hard decisions have no classification NLL. Reuse only confusion/recall metrics.
        logits = torch.nn.functional.one_hot(torch.from_numpy(chosen), 4).float()
        all_metrics = ClassificationMetrics.compute(logits, torch.from_numpy(labels))
        metrics = {
            key: all_metrics[key]
            for key in [
                "count",
                "accuracy",
                "macro_f1",
                "balanced_accuracy",
                "confusion_matrix",
                "per_class",
            ]
        }
        near = np.abs(truth_psnr - 35) <= 3
        near_rmse = (
            float(np.sqrt(np.square(psnr[near] - truth_psnr[near]).mean())) if near.any() else 0.0
        )
        quality_pass = truth_psnr[np.arange(len(chosen)), chosen] > 35
        payload = np.array([row["payload_bytes"] for row in dataset.rows])
        metrics.update(
            {
                "near_threshold_rmse_db": near_rmse,
                "near_threshold_candidate_count": int(near.sum()),
                "quality_pass_rate": float(quality_pass.mean()),
                "payload_bytes": int(payload[np.arange(len(chosen)), chosen].sum()),
                "fixed8_payload_bytes": int(payload[:, 1].sum()),
                "seconds": time.perf_counter() - started,
                "margins": [
                    {
                        "margin_db": margin,
                        "accuracy": float((PatchErrorGrid.choose(psnr, margin) == labels).mean()),
                    }
                    for margin in [0.0, 0.25, 0.5, 0.75, 1.0]
                ],
                "classes": list(CLASSES),
            }
        )
        return metrics, psnr
