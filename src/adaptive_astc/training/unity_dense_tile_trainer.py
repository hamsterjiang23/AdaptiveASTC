"""Train and independently reload the frozen-encoder V5 dense head."""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_dense_tile_dataset import (
    UnityDenseImageSampler,
    UnityDenseTileDataset,
)
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_dense_tile_metrics import UnityDenseTileMetrics
from adaptive_astc.models.unity_dense_tile import UnityDenseTileRegressor
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A


@dataclass(frozen=True)
class UnityDenseTrainConfig:
    stage: str
    corpus: Path
    corpus_sha256: str
    parent: Path
    parent_sha256: str
    output: Path
    epochs: int = 5
    batch_size: int = 16
    learning_rate: float = 3e-4
    seed: int = 20261119
    loss_cap_db: float | None = None


class UnityDenseTileTrainer:
    SOURCES = (
        "script/train_unity_dense_tiles.py",
        "src/adaptive_astc/models/unity_quality.py",
        "src/adaptive_astc/models/unity_dense_tile.py",
        "src/adaptive_astc/data/unity_dense_tile_dataset.py",
        "src/adaptive_astc/evaluation/unity_dense_tile_metrics.py",
        "src/adaptive_astc/training/unity_dense_tile_trainer.py",
    )

    def __init__(self, archive: UnityTileArchive, config: UnityDenseTrainConfig) -> None:
        self.config = config
        if (
            config.stage not in ("smoke", "aligned-smoke", "prototype", "full")
            or config.epochs < 1
            or config.batch_size < 1
            or not 0 < config.learning_rate < 1
            or (config.loss_cap_db is not None and not 32 < config.loss_cap_db < 100)
        ):
            raise ValueError("Invalid frozen V5 training configuration")
        manifest = archive.read_bound_json(config.corpus, config.corpus_sha256, dict)
        contract = A.read_json(config.corpus.with_name("config.json"))
        selection = contract.pop("selection")
        counts = {split: len(records) for split, records in manifest["splits"].items()}
        if (
            manifest["status"] != "passed"
            or manifest["test_opened"] is not False
            or set(counts) != {"train", "validation"}
            or manifest["counts"] != counts
            or contract["development_corpus_sha256"] != archive.sha256
            or A.fingerprint(contract) != manifest["binding"]
            or selection
            != {split: [r["index"] for r in rows] for split, rows in manifest["splits"].items()}
        ):
            raise ValueError("V5 label corpus or development binding changed")
        if config.stage == "full" and (
            manifest["coverage"] != "complete" or counts != {"train": 10000, "validation": 1000}
        ):
            raise ValueError("Full V5 training requires all development labels")
        if config.stage in ("smoke", "aligned-smoke"):
            manifest["splits"] = {split: rows[:4] for split, rows in manifest["splits"].items()}
        size = 240 if config.stage in ("full", "aligned-smoke") else 128
        self.train_dataset = UnityDenseTileDataset(
            archive, config.corpus.parent, "train", manifest, size
        )
        self.validation_dataset = UnityDenseTileDataset(
            archive, config.corpus.parent, "validation", manifest, size
        )

    @classmethod
    def source_hashes(cls) -> dict[str, str]:
        root = Path(__file__).resolve().parents[3]
        return {name: A.sha256_file(root / name) for name in cls.SOURCES}

    @staticmethod
    def validation_key(metrics: JsonDict) -> tuple[float, float]:
        display = metrics["views"]["display"]
        scores = [
            display["bad_share_mae"][str(y)]["content"] for y in UnityDenseTileMetrics.THRESHOLDS
        ]
        return (
            float(np.mean(scores)) if all(score is not None for score in scores) else math.inf,
            display["log_mse_rmse"],
        )

    @staticmethod
    def model_hash(model: nn.Module) -> str:
        digest = hashlib.sha256()
        for name, value in sorted(model.state_dict().items()):
            digest.update(name.encode("utf-8"))
            digest.update(value.cpu().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes())
        return digest.hexdigest()

    def build_model(self, device: torch.device) -> UnityDenseTileRegressor:
        if A.sha256_file(self.config.parent) != self.config.parent_sha256:
            raise ValueError("V3 parent checkpoint identity changed")
        checkpoint = torch.load(self.config.parent, map_location="cpu", weights_only=True)
        if checkpoint["config"]["backbone_name"] != "resnet34":
            raise ValueError("Expected the frozen V3 ResNet-34 checkpoint")
        parent = UnityQualityRegressor.from_checkpoint(checkpoint, device)
        return UnityDenseTileRegressor(parent).to(device)

    @staticmethod
    def loss(
        predicted: Tensor, reference: Tensor, pixels: Tensor, cap_db: float | None = None
    ) -> Tensor:
        weights = pixels[..., None, None].float()
        if cap_db is not None:
            floor = -cap_db / 10
            censored = reference <= floor
            reference = reference.clamp_min(floor)
            predicted = torch.where(censored, predicted.clamp_min(floor), predicted)
        error = nn.functional.huber_loss(predicted, reference, reduction="none", delta=0.1)
        return (error * weights).sum() / (weights.sum() * predicted.shape[-2] * predicted.shape[-1])

    @staticmethod
    @torch.inference_mode()
    def evaluate(
        model: UnityDenseTileRegressor,
        loader: DataLoader[dict[str, Tensor]],
        dataset: UnityDenseTileDataset,
        device: torch.device,
    ) -> UnityDenseTileMetrics:
        model.eval()
        metrics = UnityDenseTileMetrics()
        current: int | None = None
        predicted: np.ndarray | None = None
        for batch in loader:
            outputs = model(*(batch[key].to(device) for key in ("rgba", "valid_mask", "metadata")))
            for tile_patch, img, origin in zip(
                outputs.cpu().numpy(),
                batch["image"].tolist(),
                batch["origin"].tolist(),
                strict=True,
            ):
                if img != current:
                    if current is not None and predicted is not None:
                        metrics.add(
                            predicted, dataset.load(current)[2], dataset.rows[current]["index"]
                        )
                    current = img
                    shape = dataset.load(current)[2].squared_errors.shape
                    predicted = np.full(shape, np.nan, dtype=np.float32)
                if predicted is None:
                    raise ValueError("Missing dense validation image accumulator")
                y, x = origin
                h = min(tile_patch.shape[0], predicted.shape[1] - y)
                w = min(tile_patch.shape[1], predicted.shape[2] - x)
                view = predicted[:, y : y + h, x : x + w, :]
                if not np.isnan(view).all():
                    raise ValueError("Duplicate validation patch predictions")
                view[:] = tile_patch[:h, :w].transpose(2, 0, 1, 3)
        if current is not None and predicted is not None:
            metrics.add(predicted, dataset.load(current)[2], dataset.rows[current]["index"])
        if [row["index"] for row in metrics.values] != [row["index"] for row in dataset.rows]:
            raise ValueError("Dense validation image coverage changed")
        return metrics

    def run(self) -> JsonDict:
        config = self.config
        config.output.mkdir(parents=True, exist_ok=False)
        started = time.perf_counter()
        state: JsonDict = {
            "status": "starting",
            "stage": config.stage,
            "training_updates": 0,
            "parent_sha256": config.parent_sha256,
            "corpus_sha256": config.corpus_sha256,
            "source_sha256": self.source_hashes(),
            "test_opened": False,
            "history": [],
        }
        report = config.output / "report.json"
        A.write_json(report, state)
        try:
            self.fit(state, report)
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state

    def fit(self, state: JsonDict, report: Path) -> None:
        config = self.config
        if not torch.cuda.is_available():
            raise RuntimeError("V5 native-model training requires CUDA")
        device = torch.device("cuda")
        torch.manual_seed(config.seed)
        torch.backends.cudnn.benchmark = False
        torch.cuda.reset_peak_memory_stats()
        model = self.build_model(device)
        base_before = self.model_hash(model.native)
        optimizer = torch.optim.AdamW(model.tile_head.parameters(), lr=config.learning_rate)
        train = DataLoader(
            self.train_dataset,
            batch_size=config.batch_size,
            sampler=UnityDenseImageSampler(self.train_dataset, config.seed),
        )
        validation = DataLoader(self.validation_dataset, batch_size=config.batch_size)
        state.update(
            status="training",
            counts={
                "train": len(self.train_dataset.rows),
                "validation": len(self.validation_dataset.rows),
            },
            patch_counts={
                "train": len(self.train_dataset),
                "validation": len(self.validation_dataset),
            },
            batch_size=config.batch_size,
            seed=config.seed,
            epochs=config.epochs,
            learning_rate=config.learning_rate,
            loss_cap_db=config.loss_cap_db,
        )
        best = (math.inf, math.inf)
        for epoch in range(1, config.epochs + 1):
            model.train()
            training_loss = []
            for batch in train:
                optimizer.zero_grad(set_to_none=True)
                outputs = model(
                    *(batch[key].to(device) for key in ("rgba", "valid_mask", "metadata"))
                )
                loss = self.loss(
                    outputs,
                    batch["log_mse"].to(device),
                    batch["pixels"].to(device),
                    config.loss_cap_db,
                )
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite V5 training loss")
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    model.tile_head.parameters(), 1.0, error_if_nonfinite=True
                )
                optimizer.step()
                training_loss.append(float(loss.detach()))
                state["training_updates"] += 1
            validation_result = self.evaluate(model, validation, self.validation_dataset, device)
            metrics = validation_result.summarize()
            key = self.validation_key(metrics)
            state["history"].append(
                {
                    "epoch": epoch,
                    "mean_training_batch_huber": float(np.mean(training_loss)),
                    "validation": metrics,
                }
            )
            if key < best:
                best = key
                self.save_best(model, epoch, validation_result, state)
            A.write_json(report, state)
            print(f"epoch {epoch} completed; display log-MSE RMSE {key[1]:.4f}", flush=True)
        if base_before != self.model_hash(model.native):
            raise ValueError("Frozen V3 parameters or buffers changed during V5 training")
        del model, optimizer
        # Rebuild the parent from disk and reload the best head to audit the published artifact.
        checkpoint_path = config.output / "best-head.pt"
        validation_path = config.output / "best-validation.json"
        if (
            A.sha256_file(checkpoint_path) != state["best_checkpoint_sha256"]
            or A.sha256_file(validation_path) != state["best_validation_sha256"]
        ):
            raise ValueError("Best V5 checkpoint or prediction archive changed before reload")
        fresh = self.build_model(device)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        if (
            checkpoint["epoch"] != state["best_epoch"]
            or checkpoint["parent_sha256"] != config.parent_sha256
            or checkpoint["corpus_sha256"] != config.corpus_sha256
        ):
            raise ValueError("Best V5 checkpoint metadata disagrees with the frozen run")
        fresh.load_state_dict(checkpoint["model"], strict=True)
        reloaded = self.evaluate(fresh, validation, self.validation_dataset, device)
        reference = A.read_json(validation_path)
        if reloaded.summarize() != reference["summary"] or reloaded.values != reference["images"]:
            raise ValueError("Reloaded V5 predictions disagree with best validation checkpoint")
        base_after = self.model_hash(fresh.native)
        if base_before != base_after:
            raise ValueError("Frozen V3 parameters or buffers changed during V5 training")
        if A.sha256_file(config.corpus) != config.corpus_sha256:
            raise ValueError("V5 training corpus changed during training")
        if self.source_hashes() != state["source_sha256"]:
            raise ValueError("V5 training source changed during training")
        state.update(
            status="passed",
            checkpoint_reloaded=True,
            native_state_sha256=base_after,
            frozen_native_parameters_and_buffers_unchanged=True,
            peak_cuda_memory_bytes=torch.cuda.max_memory_allocated(),
        )

    def save_best(
        self,
        model: UnityDenseTileRegressor,
        epoch: int,
        metrics: UnityDenseTileMetrics,
        state: JsonDict,
    ) -> None:
        output = self.config.output
        path = output / "best-head.pt"
        temporary = path.with_suffix(".tmp")
        torch.save(
            {
                "model": model.state_dict(),
                "epoch": epoch,
                "parent_sha256": self.config.parent_sha256,
                "corpus_sha256": self.config.corpus_sha256,
            },
            temporary,
        )
        temporary.replace(path)
        validation = output / "best-validation.json"
        A.write_json(validation, {"summary": metrics.summarize(), "images": metrics.values})
        state.update(
            best_epoch=epoch,
            best_checkpoint_sha256=A.sha256_file(path),
            best_validation_sha256=A.sha256_file(validation),
        )
