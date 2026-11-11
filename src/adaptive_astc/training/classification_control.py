"""Validation-selected fixed-capacity GDC classification controls for V1."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch.amp.grad_scaler import GradScaler

from adaptive_astc.config import JsonDict, TrainConfig
from adaptive_astc.data.dataset import TextureDataModule
from adaptive_astc.data.development import MeasuredDevelopmentData
from adaptive_astc.evaluation.inference import Predictor
from adaptive_astc.evaluation.metrics import ClassificationMetrics
from adaptive_astc.models.ordinal import ASTCOrdinalClassifier, ClassificationObjective
from adaptive_astc.models.resnet import ASTCClassifier
from adaptive_astc.training.trainer import Trainer
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.checkpoints import CheckpointStore
from adaptive_astc.utils.runtime import ExperimentRuntime


@dataclass(frozen=True)
class ClassificationControlConfig:
    source: Path
    output: Path
    report: Path
    initialization: str = "pretrained"
    loss: str = "cross_entropy"
    smoothing: float = 0.1
    learning_rate: float = 0.003
    weight_decay: float = 0.0005
    epochs: int = 15
    patience: int = 5
    batch_size: int = 64
    workers: int = 2
    seed: int = 20261109
    scheduler_t_max: int = 30
    max_steps: int = 0
    train_limit: int = 0
    validation_limit: int = 0

    def validate(self) -> None:
        TrainConfig(
            initialization=self.initialization,  # pyright: ignore[reportArgumentType]
            epochs=self.epochs,
            micro_batch=self.batch_size,
            workers=self.workers,
            learning_rate=self.learning_rate,
            weight_decay=self.weight_decay,
            scheduler_t_max=self.scheduler_t_max,
            max_steps=self.max_steps,
            seed=self.seed,
        )
        if self.patience < 1 or min(self.train_limit, self.validation_limit) < 0:
            raise ValueError("Positive patience and nonnegative data limits required")
        ClassificationObjective(self.loss, self.smoothing)


class ClassificationControlTrainer:
    def __init__(self, config: ClassificationControlConfig) -> None:
        config.validate()
        self.config = config

    def fit(self) -> JsonDict:
        config = self.config
        if config.output.exists() and any(config.output.iterdir()):
            raise FileExistsError("Use a new control identity; partial trials remain recorded")
        device = ExperimentRuntime.configure(config.seed)
        if device.type != "cuda":
            raise RuntimeError("Classification controls require CUDA")
        started = time.perf_counter()
        manifest = MeasuredDevelopmentData(config.source).load(
            config.train_limit, config.validation_limit
        )
        config.output.mkdir(parents=True, exist_ok=True)
        ArtifactStore.write_json(config.output / "manifest.json", manifest)
        data = TextureDataModule(config.source, config.workers)
        validation = data.loader(manifest["splits"]["validation"], 64)
        train_rows = manifest["splits"]["train"]
        probe_indexes = np.linspace(0, len(train_rows) - 1, min(512, len(train_rows)), dtype=int)
        probe = data.loader([train_rows[int(i)] for i in probe_indexes], 64)
        model = (
            ASTCOrdinalClassifier(config.initialization)
            if config.loss == "ordered_cumulative"
            else ASTCClassifier(config.initialization)
        )
        model = model.to(device)
        criterion = ClassificationObjective(config.loss, config.smoothing).to(device)
        optimizer = torch.optim.SGD(
            model.parameters(),
            lr=config.learning_rate,
            momentum=0.9,
            weight_decay=config.weight_decay,
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, config.scheduler_t_max)
        scaler = GradScaler("cuda")
        settings = {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        }
        settings.update(
            {
                "data_fingerprint": manifest["fingerprint"],
                "input": "frozen RGB224 bilinear",
                "effective_batch": 64,
                "optimizer": "SGD momentum0.9",
                "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
                "gpu": torch.cuda.get_device_name(),
                "augmentations": [],
                "selection": "save best_accuracy and best_nll; "
                "early stop on validation NLL patience",
                "ordinal_variant": "shared scalar score, "
                "explicitly ordered softplus threshold gaps; "
                "sum of three cumulative binary losses; class probability argmax decision"
                if config.loss == "ordered_cumulative"
                else None,
                "scope": "GDC source RGB train/validation development; no test access",
                "source_files_sha256": {
                    str(path): ArtifactStore.sha256_file(path)
                    for path in [
                        Path(__file__),
                        Path(__file__).with_name("trainer.py"),
                        Path(__file__).parents[1] / "models/ordinal.py",
                        Path(__file__).parents[1] / "data/development.py",
                    ]
                },
            }
        )
        ArtifactStore.write_json(config.output / "config.json", settings)
        history: list[JsonDict] = []
        best_nll, best_accuracy = math.inf, -1.0
        stale_epochs = 0
        stop_reason = "epoch_budget"
        torch.cuda.reset_peak_memory_stats()
        for epoch in range(config.epochs):
            epoch_started = time.perf_counter()
            learning_rate = optimizer.param_groups[0]["lr"]
            train = Trainer.train_epoch(
                model,
                data.loader(train_rows, config.batch_size, shuffle=True, seed=config.seed + epoch),
                device,
                optimizer,
                scaler,
                config.batch_size,
                config.max_steps,
                64,
                criterion,
            )
            logits, labels = Predictor.predict(model, validation, device)
            metrics = ClassificationMetrics.compute(logits, labels)
            train_logits, train_labels = Predictor.predict(model, probe, device)
            probe_metrics = ClassificationMetrics.compute(train_logits, train_labels)
            row = {
                "epoch": epoch + 1,
                "train": train,
                "validation": metrics,
                "train_eval_probe": probe_metrics,
                "learning_rate": learning_rate,
                "seconds": time.perf_counter() - epoch_started,
            }
            if train["optimizer_updates"] == 0:
                raise RuntimeError("No optimizer updates applied; control is incomplete")
            history.append(row)
            scheduler.step()
            packet = {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
                "scaler": scaler.state_dict(),
                "config": settings,
                "epoch": epoch + 1,
                "history": history,
            }
            CheckpointStore.save(config.output / "last.pt", packet)
            if metrics["accuracy"] > best_accuracy:
                best_accuracy = metrics["accuracy"]
                CheckpointStore.save(config.output / "best_accuracy.pt", packet)
                CheckpointStore.save(
                    config.output / "best_accuracy_predictions.pt",
                    {
                        "logits": logits,
                        "labels": labels,
                        "data_fingerprint": manifest["fingerprint"],
                        "checkpoint_sha256": ArtifactStore.sha256_file(
                            config.output / "best_accuracy.pt"
                        ),
                    },
                )
            if metrics["nll"] < best_nll:
                best_nll, stale_epochs = metrics["nll"], 0
                CheckpointStore.save(config.output / "best_nll.pt", packet)
            else:
                stale_epochs += 1
            result = {
                "status": "running",
                "config": settings,
                "history": history,
                "best_validation_accuracy": best_accuracy,
                "best_validation_nll": best_nll,
                "wall_seconds": time.perf_counter() - started,
                "peak_vram_bytes": torch.cuda.max_memory_allocated(),
                "test_opened": False,
            }
            ArtifactStore.write_json(config.output / "history.json", result)
            ArtifactStore.write_json(config.report, result)
            print(
                {
                    "epoch": epoch + 1,
                    "train_accuracy": train["accuracy"],
                    "validation_accuracy": metrics["accuracy"],
                    "validation_nll": metrics["nll"],
                    "train_probe_accuracy": probe_metrics["accuracy"],
                    "seconds": row["seconds"],
                },
                flush=True,
            )
            if stale_epochs >= config.patience:
                stop_reason = "validation_nll_patience"
                break
        result.update(
            {
                "status": "passed_smoke"
                if config.max_steps or config.train_limit or config.validation_limit
                else "completed",
                "stop_reason": stop_reason,
                "wall_seconds": time.perf_counter() - started,
                "checkpoint_sha256": ArtifactStore.sha256_file(config.output / "best_accuracy.pt"),
            }
        )
        ArtifactStore.write_json(config.output / "history.json", result)
        ArtifactStore.write_json(config.report, result)
        return result
