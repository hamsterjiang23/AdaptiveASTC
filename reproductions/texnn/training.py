"""Train the published TexNN layer sizes on native block labels with resumable state."""

from __future__ import annotations

import math
import shutil
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, Dataset

from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.checkpoints import CheckpointStore
from adaptive_astc.utils.environment import RunEnvironment
from reproductions.texnn.corpus import TexNNBlockCorpus
from reproductions.texnn.models import TexNNClassifier


class TexNNBlockDataset(Dataset[tuple[Tensor, Tensor]]):
    def __init__(
        self,
        directory: Path,
        network: Literal["pnn", "demnn"],
        split: Literal["train", "validation"],
    ) -> None:
        self.rgb = np.load(directory / "rgb.npy", mmap_mode="r", allow_pickle=False)
        self.endpoints = np.load(directory / "endpoints.npy", mmap_mode="r", allow_pickle=False)
        self.targets = np.load(directory / f"{network}.npy", mmap_mode="r", allow_pickle=False)
        self.indices = np.load(directory / f"{split}.npy", mmap_mode="r", allow_pickle=False)
        self.network: Literal["pnn", "demnn"] = network

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        row = int(self.indices[index])
        features = np.array(self.rgb[row], dtype=np.float32, copy=True)
        if self.network == "demnn":
            features = np.concatenate((features, self.endpoints[row]))
        return torch.from_numpy(features), torch.tensor(int(self.targets[row]), dtype=torch.long)


class TexNNTrainer:
    def __init__(
        self,
        prepared: Path,
        output: Path,
        network: Literal["pnn", "demnn"],
        *,
        epochs: int = 100,
        batch_size: int = 128,
        learning_rate: float = 1e-4,
        patience: int = 8,
        seed: int = 20261111,
        device: str = "cuda",
        resume: bool = False,
    ) -> None:
        if network not in {"pnn", "demnn"}:
            raise ValueError("Unsupported TexNN network")
        if epochs < 1 or batch_size < 1 or patience < 0:
            raise ValueError("Invalid TexNN training duration or batch size")
        if not math.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("Learning rate must be positive and finite")
        self.prepared = prepared.resolve()
        self.output = output.resolve()
        self.network: Literal["pnn", "demnn"] = network
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.patience = patience
        self.seed = seed
        self.device = torch.device(device)
        self.resume = resume

    @staticmethod
    def epoch(
        model: TexNNClassifier,
        batches: DataLoader,
        device: torch.device,
        optimizer: torch.optim.Optimizer | None,
        valid_classes: int,
    ) -> dict[str, float | int]:
        started = time.perf_counter()
        model.train(optimizer is not None)
        loss_sum = 0.0
        samples = 0
        correct = 0
        correct10 = 0
        masked_correct = 0
        masked_correct10 = 0
        with torch.set_grad_enabled(optimizer is not None):
            for features, targets in batches:
                features, targets = features.to(device), targets.to(device)
                if optimizer is not None:
                    optimizer.zero_grad(set_to_none=True)
                logits = model(features)
                loss = nn.functional.cross_entropy(logits, targets)
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite TexNN training or validation loss")
                if optimizer is not None:
                    loss.backward()
                    optimizer.step()
                count = targets.numel()
                samples += count
                loss_sum += float(loss.item()) * count
                predictions = logits.detach().topk(10, dim=1).indices
                correct += int((predictions[:, 0] == targets).sum().item())
                correct10 += int((predictions == targets[:, None]).any(dim=1).sum().item())
                masked = (
                    logits.detach()[:, :valid_classes].topk(min(10, valid_classes), dim=1).indices
                )
                masked_correct += int((masked[:, 0] == targets).sum().item())
                masked_correct10 += int((masked == targets[:, None]).any(dim=1).sum().item())
        return {
            "samples": samples,
            "loss": loss_sum / samples,
            "accuracy1": correct / samples,
            "accuracy10": correct10 / samples,
            "masked_accuracy1": masked_correct / samples,
            "masked_accuracy10": masked_correct10 / samples,
            "seconds": time.perf_counter() - started,
        }

    def train(self) -> dict[str, Any]:
        attempt_started = time.perf_counter()
        manifest = TexNNBlockCorpus.validate(self.prepared)
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable for TexNN training")
        self.output.mkdir(parents=True, exist_ok=self.resume)
        model_config: dict[str, Any] = {
            "dropout": 0.6,
            "activation": "relu",
            "initialization_std": 0.01,
        }
        signature = {
            "network": self.network,
            "seed": self.seed,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "optimizer": "Adam",
            "patience": self.patience,
            "model_config": model_config,
            "architecture_sha256": ArtifactStore.sha256_file(
                Path(__file__).with_name("architectures.json")
            ),
        }
        torch.manual_seed(self.seed)
        torch.set_num_threads(1)
        generator = torch.Generator().manual_seed(self.seed)
        model = TexNNClassifier(
            (manifest["size"], manifest["size"]), self.network, **model_config
        ).to(self.device)
        optimizer = torch.optim.Adam(model.parameters(), lr=self.learning_rate)
        train = DataLoader(
            TexNNBlockDataset(self.prepared, self.network, "train"),
            batch_size=self.batch_size,
            shuffle=True,
            generator=generator,
            num_workers=0,
            pin_memory=self.device.type == "cuda",
        )
        validation = DataLoader(
            TexNNBlockDataset(self.prepared, self.network, "validation"),
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=0,
            pin_memory=self.device.type == "cuda",
        )
        history: list[dict[str, Any]] = []
        best_loss = float("inf")
        best_epoch = 0
        stale = 0
        start_epoch = 0
        previous_seconds: float | None = 0.0
        if self.resume:
            state = torch.load(self.output / "last.pt", map_location=self.device, weights_only=True)
            CheckpointStore.validate_resume(state, manifest, self.network, self.output, signature)
            model.load_state_dict(state["model"], strict=True)
            optimizer.load_state_dict(state["optimizer"])
            torch.set_rng_state(state["torch_rng"].cpu())
            generator.set_state(state["loader_rng"].cpu())
            if self.device.type == "cuda" and state["cuda_rng"]:
                torch.cuda.set_rng_state_all([value.cpu() for value in state["cuda_rng"]])
            start_epoch = state["epoch"]
            previous_seconds = state.get("total_training_seconds")
            history = state["history"]
            best_loss, best_epoch, stale = state["best_loss"], state["best_epoch"], state["stale"]
            names = ["best.pt", "last.pt", "config.json", "history.json", "training_complete.json"]
            previous = {
                name: ArtifactStore.sha256_file(self.output / name)
                for name in names
                if (self.output / name).exists()
            }
            archive = self.output / "history" / ArtifactStore.fingerprint(previous)
            archive.mkdir(parents=True, exist_ok=True)
            for name in previous:
                original = self.output / name
                target = archive / name
                if not target.exists():
                    shutil.copy2(original, target)
                if ArtifactStore.sha256_file(original) != ArtifactStore.sha256_file(target):
                    raise ValueError("Previous TexNN training archive differs from its source")
        config = {
            **signature,
            "epochs": self.epochs,
            "patience": self.patience,
            "device": str(self.device),
            "data_fingerprint": manifest["fingerprint"],
            "size": manifest["size"],
            "environment": RunEnvironment.capture(),
            "torch_version": str(torch.__version__),
        }
        ArtifactStore.write_json(self.output / "config.json", config)
        started = time.perf_counter()
        valid_classes = len(
            manifest["partitions"] if self.network == "pnn" else manifest["joint_labels"]
        )
        for epoch in range(start_epoch + 1, self.epochs + 1):
            metrics: dict[str, Any] = {
                "epoch": epoch,
                "train": self.epoch(model, train, self.device, optimizer, valid_classes),
                "validation": self.epoch(model, validation, self.device, None, valid_classes),
            }
            history.append(metrics)
            improved = metrics["validation"]["loss"] < best_loss
            if improved:
                best_loss, best_epoch, stale = metrics["validation"]["loss"], epoch, 0
            else:
                stale += 1
            packet = {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "epoch": epoch,
                "initialization": self.network,
                "data_fingerprint": manifest["fingerprint"],
                "optimization_config": signature,
                "model_config": model_config,
                "network": self.network,
                "size": manifest["size"],
                "feature_protocol": manifest["feature_protocol"],
                "history": history,
                "best_loss": best_loss,
                "best_epoch": best_epoch,
                "stale": stale,
                "torch_rng": torch.get_rng_state(),
                "loader_rng": generator.get_state(),
                "cuda_rng": torch.cuda.get_rng_state_all() if self.device.type == "cuda" else [],
                "total_training_seconds": None
                if previous_seconds is None
                else previous_seconds + time.perf_counter() - started,
            }
            if improved:
                CheckpointStore.save(self.output / "best.pt", packet)
            CheckpointStore.save(self.output / "last.pt", packet)
            ArtifactStore.write_json(self.output / "history.json", {"epochs": history})
            print(
                f"TexNN {manifest['size']}x{manifest['size']} {self.network} epoch={epoch} "
                f"loss={metrics['validation']['loss']:.5f} "
                f"accuracy10={metrics['validation']['accuracy10']:.4f}",
                flush=True,
            )
            if self.patience > 0 and stale >= self.patience:
                break
        receipt = {
            "status": "passed",
            "completed_epochs": history[-1]["epoch"],
            "best_epoch": best_epoch,
            "best_validation_loss": best_loss,
            "early_stopped": self.patience > 0 and stale >= self.patience,
            "wall_seconds": time.perf_counter() - started,
            "total_training_seconds": None
            if previous_seconds is None
            else previous_seconds + time.perf_counter() - started,
            "prior_training_seconds_known": previous_seconds is not None,
            "attempt_total_seconds": time.perf_counter() - attempt_started,
            "config": config,
            "best_sha256": ArtifactStore.sha256_file(self.output / "best.pt"),
            "last_sha256": ArtifactStore.sha256_file(self.output / "last.pt"),
        }
        ArtifactStore.write_json(self.output / "training_complete.json", receipt)
        return receipt
