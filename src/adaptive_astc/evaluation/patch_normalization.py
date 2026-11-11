"""Diagnose frozen patch checkpoints with train-only BatchNorm recalibration."""

from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, WeightedRandomSampler

from adaptive_astc.config import JsonDict
from adaptive_astc.data.patch_dataset import NativePatchDataset
from adaptive_astc.models.patch_regressor import ASTCPatchRegressor
from adaptive_astc.training.patch_trainer import PatchTrainer
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.runtime import ExperimentRuntime


class PatchNormalizationAudit:
    @staticmethod
    def baseline_matches(measured: JsonDict, recorded: JsonDict) -> bool:
        actual, expected = (
            measured["near_threshold_rmse_db"],
            recorded["near_threshold_rmse_db"],
        )
        rmse_matches = (actual is None and expected is None) or (
            actual is not None
            and expected is not None
            and np.isfinite(actual)
            and np.isfinite(expected)
            and np.isclose(actual, expected, rtol=0, atol=1e-5)
        )
        return bool(measured["accuracy"] == recorded["accuracy"] and rmse_matches)

    @staticmethod
    def recalibrate(model: nn.Module, images: Iterable[Tensor], device: torch.device) -> int:
        modes = {module: module.training for module in model.modules()}
        layers = [module for module in model.modules() if isinstance(module, nn.BatchNorm2d)]
        if not layers:
            raise ValueError("BatchNorm2d layers required")
        momentum = {module: module.momentum for module in layers}
        model.eval()
        for module in layers:
            module.reset_running_stats()
            module.momentum = None
            module.train()
        count = 0
        try:
            with torch.no_grad():
                for batch in images:
                    with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                        model(batch.to(device, non_blocking=True))
                    count += len(batch)
            if count == 0:
                raise ValueError("No training images for normalization")
        finally:
            for module, value in momentum.items():
                module.momentum = value
            for module, training in modes.items():
                module.training = training
        return count

    @staticmethod
    def run(training: Path, output: Path, report: Path, calibration_batches: int = 128) -> JsonDict:
        if calibration_batches < 1:
            raise ValueError("Positive calibration batch budget required")
        if output.exists() or report.exists():
            raise FileExistsError("Use a new normalization audit identity")
        history_path = training / "history.json"
        history = ArtifactStore.read_json(history_path)
        if history["status"] not in {"completed", "passed_smoke"} or history["test_opened"]:
            raise ValueError("Require a completed development training run")
        settings = history["config"]
        for name, expected in settings["source_files_sha256"].items():
            if ArtifactStore.sha256_file(Path(name)) != expected:
                raise ValueError("Training implementation changed before normalization audit")
        checkpoint_path = training / "last.pt"
        checkpoint_sha = ArtifactStore.sha256_file(checkpoint_path)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        if (
            checkpoint["config"] != settings
            or checkpoint["history"] != history["history"]
            or checkpoint["epoch"] != history["history"][-1]["epoch"]
            or not checkpoint["ema"]
        ):
            raise ValueError("Last checkpoint differs from completed EMA training history")
        device = ExperimentRuntime.configure(settings["seed"])
        if device.type != "cuda":
            raise RuntimeError("Normalization diagnosis requires CUDA")
        started = time.perf_counter()
        train = NativePatchDataset(Path(settings["corpus"]), "train")
        validation = NativePatchDataset(Path(settings["corpus"]), "validation")
        if train.fingerprint != settings["corpus_fingerprint"] or (
            validation.fingerprint != train.fingerprint
        ):
            raise ValueError("Training/validation corpus changed")
        batch_size = settings["batch_size"]
        sampled = list(
            WeightedRandomSampler(
                train.image_balanced_weights().tolist(),
                batch_size * calibration_batches,
                replacement=True,
                generator=torch.Generator().manual_seed(settings["seed"]),
            )
        )
        train_batches = DataLoader(
            train, batch_size=batch_size, sampler=sampled, num_workers=0, pin_memory=True
        )
        validation_batches = DataLoader(
            validation, batch_size=batch_size, num_workers=0, pin_memory=True
        )
        output.mkdir(parents=True)
        np.save(output / "train-patch-indexes.npy", np.array(sampled, dtype=np.int64))
        state: JsonDict = {
            "status": "running",
            "scope": "Frozen last-epoch weights; train-only BN statistics; development validation",
            "training": str(training),
            "history_sha256": ArtifactStore.sha256_file(history_path),
            "checkpoint_sha256": checkpoint_sha,
            "epoch": checkpoint["epoch"],
            "source_sha256": ArtifactStore.sha256_file(Path(__file__)),
            "corpus_fingerprint": train.fingerprint,
            "calibration_batches": calibration_batches,
            "calibration_patches": len(sampled),
            "unique_training_images": len(np.unique(train.image_ids[sampled])),
            "calibration_indexes_sha256": ArtifactStore.sha256_file(
                output / "train-patch-indexes.npy"
            ),
            "optimizer_updates": 0,
            "test_opened": False,
            "rows": [],
        }
        try:
            for variant in ["raw", "ema"]:
                weights = (
                    checkpoint["model"]
                    if variant == "raw"
                    else {
                        key.removeprefix("module."): value
                        for key, value in checkpoint["ema"].items()
                        if key.startswith("module.")
                    }
                )
                model = ASTCPatchRegressor(
                    "scratch", settings["remove_maxpool"], settings["monotone"]
                ).to(device)
                model.load_state_dict(weights, strict=True)
                for recalibrated in [False, True]:
                    calibration_seconds = 0.0
                    if recalibrated:
                        calibration_started = time.perf_counter()
                        count = PatchNormalizationAudit.recalibrate(
                            model, (batch[0] for batch in train_batches), device
                        )
                        torch.cuda.synchronize()
                        calibration_seconds = time.perf_counter() - calibration_started
                        if count != len(sampled):
                            raise ValueError("Training calibration budget mismatch")
                    for name, parameter in model.named_parameters():
                        if not torch.equal(parameter.detach().cpu(), weights[name]):
                            raise ValueError("Normalization diagnosis changed learned parameters")
                    metrics, psnr = PatchTrainer.evaluate(
                        model, validation_batches, validation, device
                    )
                    if not recalibrated:
                        recorded = history["history"][-1]["validation_variants"][variant]
                        if not PatchNormalizationAudit.baseline_matches(metrics, recorded):
                            raise ValueError("Baseline reload differs from recorded last epoch")
                    name = f"{variant}-{'recalibrated' if recalibrated else 'original'}"
                    torch.save(
                        {"model": model.state_dict(), "config": settings}, output / f"{name}.pt"
                    )
                    np.savez_compressed(output / f"{name}.npz", psnr=psnr)
                    state["rows"].append(
                        {
                            "name": name,
                            "parameters_unchanged": True,
                            "calibration_seconds": calibration_seconds,
                            "metrics": metrics,
                            "weights_sha256": ArtifactStore.sha256_file(output / f"{name}.pt"),
                            "predictions_sha256": ArtifactStore.sha256_file(output / f"{name}.npz"),
                        }
                    )
                    ArtifactStore.write_json(output / "receipt.json", state)
            if ArtifactStore.sha256_file(checkpoint_path) != checkpoint_sha:
                raise ValueError("Original checkpoint changed during diagnosis")
            state["status"] = "passed"
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            ArtifactStore.write_json(output / "receipt.json", state)
            ArtifactStore.write_json(report, state)
        return state
