"""ResNet optimization, validation selection, and resumable training."""

import gc
import math
import random
import time
from collections.abc import Sized
from pathlib import Path
from typing import cast

import numpy as np
import psutil
import torch
import torchvision
from torch import nn
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader
from torch.version import cuda as cuda_version
from torchvision.models import ResNet18_Weights

from adaptive_astc.config import SEED, JsonDict
from adaptive_astc.data.dataset import TextureDataModule
from adaptive_astc.evaluation.inference import Predictor
from adaptive_astc.evaluation.metrics import ClassificationMetrics
from adaptive_astc.models import ASTCClassifier
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.checkpoints import CheckpointStore
from adaptive_astc.utils.environment import RunEnvironment
from adaptive_astc.utils.runtime import ExperimentRuntime


class Trainer:
    """Own the model, optimizer, scheduler, scaler, and run configuration."""

    def __init__(
        self,
        run_dir: Path,
        report_dir: Path,
        initialization: str,
        epochs: int = 30,
        micro_batch: int = 64,
        workers: int = 2,
        resume: bool = False,
        max_steps: int = 0,
    ) -> None:
        self.run_dir = run_dir
        self.report_dir = report_dir
        self.initialization = initialization
        self.epochs = epochs
        self.micro_batch = micro_batch
        self.workers = workers
        self.resume = resume
        self.max_steps = max_steps
        self.data = TextureDataModule(run_dir, workers)

    @staticmethod
    def train_epoch(
        model: nn.Module,
        batches: DataLoader,
        device: torch.device,
        optimizer: torch.optim.Optimizer,
        scaler: GradScaler,
        micro_batch: int,
        max_steps: int,
    ) -> JsonDict:
        model.train()
        optimizer.zero_grad(set_to_none=True)
        accumulation = 64 // micro_batch
        total_samples = len(cast(Sized, batches.dataset))
        loss_sum = 0.0
        samples = 0
        steps = 0
        started = time.perf_counter()
        for batch_index, (images, labels) in enumerate(batches):
            group_start = (batch_index // accumulation) * 64
            group_samples = min(64, total_samples - group_start)
            images, labels = (
                images.to(device, non_blocking=True),
                labels.to(device, non_blocking=True),
            )
            with torch.autocast(
                device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"
            ):
                logits = model(images)
                summed_loss = nn.functional.cross_entropy(logits, labels, reduction="sum")
                loss = summed_loss / group_samples
            if not torch.isfinite(loss):
                raise ValueError("Non-finite training loss")
            scaler.scale(loss).backward()
            loss_sum += float(summed_loss.detach())
            samples += len(labels)
            if (batch_index + 1) % accumulation == 0 or batch_index + 1 == len(batches):
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                steps += 1
                if max_steps and steps >= max_steps:
                    break
        if device.type == "cuda":
            torch.cuda.synchronize()
        return {
            "loss": loss_sum / samples,
            "samples": samples,
            "steps": steps,
            "seconds": time.perf_counter() - started,
        }

    def fit(self) -> JsonDict:
        self.device = ExperimentRuntime.configure()
        if (self.run_dir / "test_seal.json").exists():
            raise ValueError("Test already opened; train a new run instead")
        if self.device.type != "cuda":
            raise RuntimeError("The planned local run requires a CUDA GPU")
        self.manifest = ArtifactStore.read_json(self.run_dir / "manifest.json")
        output = self.run_dir / self.initialization
        output.mkdir(parents=True, exist_ok=True)
        last_path, best_path = output / "last.pt", output / "best.pt"
        if last_path.exists() and not self.resume:
            raise ValueError("Existing training state requires --resume or a new run directory")
        self.model = ASTCClassifier(self.initialization, pretrained=not self.resume).to(self.device)
        self.optimizer = torch.optim.SGD(
            self.model.parameters(), lr=0.01, momentum=0.9, weight_decay=0.0001
        )
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=30, eta_min=0
        )
        self.scaler = GradScaler("cuda")
        history: list[JsonDict] = []
        best_key = (math.inf, math.inf, math.inf)
        start_epoch = 0
        if self.resume:
            state = torch.load(last_path, map_location=self.device, weights_only=False)
            if state["data_fingerprint"] != self.manifest["fingerprint"]:
                raise ValueError("Checkpoint belongs to a different dataset")
            if state["initialization"] != self.initialization:
                raise ValueError("Checkpoint initialization differs")
            self.model.load_state_dict(state["model"])
            self.optimizer.load_state_dict(state["optimizer"])
            self.scheduler.load_state_dict(state["scheduler"])
            self.scaler.load_state_dict(state["scaler"])
            history, start_epoch = state["history"], int(state["epoch"])
            best_key = tuple(state["best_key"])
            random.setstate(state["python_rng"])
            np.random.set_state(state["numpy_rng"])
            torch.set_rng_state(state["torch_rng"].cpu())
            torch.cuda.set_rng_state_all([item.cpu() for item in state["cuda_rng"]])
        validation = self.data.loader(self.manifest["splits"]["validation"], 64)
        torch.cuda.reset_peak_memory_stats()
        config = {
            "architecture": "resnet18",
            "input": "RGB224_bilinear_ImageNet_normalization",
            "optimizer": {"name": "SGD", "lr": 0.01, "momentum": 0.9, "weight_decay": 0.0001},
            "scheduler": {"name": "CosineAnnealingLR", "T_max": 30, "eta_min": 0},
            "loss": "unweighted_cross_entropy",
            "amp": "fp16",
            "pretrained_weights": {
                "url": ResNet18_Weights.IMAGENET1K_V1.url,
                "sha256": ArtifactStore.sha256_file(
                    Path(".cache/torch/hub/checkpoints/resnet18-f37072fd.pth")
                ),
            }
            if self.initialization == "pretrained"
            else None,
            "initialization": self.initialization,
            "data_fingerprint": self.manifest["fingerprint"],
            "epochs_target": self.epochs,
            "seed": SEED,
            "effective_batch": 64,
            "micro_batch": self.micro_batch,
            "workers": self.workers,
            "max_steps": self.max_steps,
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "cuda_runtime": cuda_version,
            "gpu": torch.cuda.get_device_name(),
            "environment": RunEnvironment.capture(),
            "source_code_sha256": ArtifactStore.sha256_file(Path(__file__)),
            "source_files_sha256": {
                path.relative_to(
                    Path(__file__).resolve().parents[1]
                ).as_posix(): ArtifactStore.sha256_file(path)
                for path in sorted(Path(__file__).resolve().parents[1].rglob("*.py"))
            },
        }
        ArtifactStore.write_json(output / "config.json", config)
        for epoch in range(start_epoch, self.epochs):
            batches = self.data.loader(
                self.manifest["splits"]["train"], self.micro_batch, True, SEED + epoch
            )
            epoch_started = time.perf_counter()
            training = self.train_epoch(
                self.model,
                batches,
                self.device,
                self.optimizer,
                self.scaler,
                self.micro_batch,
                self.max_steps,
            )
            logits, truth = Predictor.predict(self.model, validation, self.device)
            metrics = ClassificationMetrics.compute(logits, truth)
            learning_rate = self.optimizer.param_groups[0]["lr"]
            self.scheduler.step()
            record = {
                "epoch": epoch + 1,
                "train": training,
                "validation": metrics,
                "lr": learning_rate,
                "epoch_seconds": time.perf_counter() - epoch_started,
                "peak_vram_mib": torch.cuda.max_memory_allocated() / 1024**2,
                "rss_mib": psutil.Process().memory_info().rss / 1024**2,
            }
            history.append(record)
            key = (metrics["nll"], -metrics["accuracy"], epoch + 1)
            improved = key < best_key
            if improved:
                best_key = key
            state = {
                "model": self.model.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "scheduler": self.scheduler.state_dict(),
                "scaler": self.scaler.state_dict(),
                "epoch": epoch + 1,
                "best_key": best_key,
                "history": history,
                "data_fingerprint": self.manifest["fingerprint"],
                "initialization": self.initialization,
                "python_rng": random.getstate(),
                "numpy_rng": np.random.get_state(),
                "torch_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state_all(),
            }
            if improved:
                CheckpointStore.save(best_path, state)
            CheckpointStore.save(last_path, state)
            ArtifactStore.write_json(output / "history.json", {"epochs": history})
            ArtifactStore.write_json(
                self.report_dir / f"{self.initialization}_training.json",
                {"config": config, "epochs": history},
            )
            print(
                f"{self.initialization} epoch={epoch + 1}/{self.epochs} "
                f"train_loss={training['loss']:.5f} "
                f"val_nll={metrics['nll']:.5f} val_acc={metrics['accuracy']:.4f} "
                f"seconds={record['epoch_seconds']:.1f}",
                flush=True,
            )
        result = {"completed_epochs": len(history), "best_epoch": best_key[2], "config": config}
        ArtifactStore.write_json(output / "training_complete.json", result)
        del self.model, self.optimizer, self.scheduler, self.scaler
        gc.collect()
        torch.cuda.empty_cache()
        return result
