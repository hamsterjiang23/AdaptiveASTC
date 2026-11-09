"""ResNet-18 fine-tuning, checkpoint recovery, and sealed inference."""

import gc
import math
import os
import random
import time
from collections.abc import Sized
from pathlib import Path
from typing import cast

import numpy as np
import psutil
import torch
import torchvision
from torch import Tensor, nn
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader, Dataset
from torch.version import cuda as cuda_version
from torchvision.models import ResNet18_Weights, resnet18

from adaptive_astc.common import (
    CLASSES,
    SEED,
    JsonDict,
    environment,
    read_json,
    sha256_file,
    write_json,
)
from adaptive_astc.metrics import fit_temperature, probability_metrics


class TextureDataset(Dataset[tuple[Tensor, int]]):
    def __init__(self, run_dir: Path, rows: list[JsonDict]) -> None:
        self.run_dir = run_dir
        self.rows = rows
        self.mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[Tensor, int]:
        row = self.rows[index]
        pixels = np.load(self.run_dir / row["cache"], allow_pickle=False)
        tensor = torch.from_numpy(pixels).permute(2, 0, 1).float().div_(255)
        return (tensor - self.mean) / self.std, int(row["class_id"])


def configure(seed: int = SEED) -> torch.device:
    os.environ.setdefault("TORCH_HOME", str(Path(".cache/torch").resolve()))
    torch.hub.set_dir(str(Path(".cache/torch/hub").resolve()))
    torch.set_num_threads(4)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def make_model(initialization: str, pretrained: bool = True) -> nn.Module:
    weights = (
        ResNet18_Weights.IMAGENET1K_V1 if initialization == "pretrained" and pretrained else None
    )
    model = resnet18(weights=weights)
    model.fc = nn.Linear(model.fc.in_features, len(CLASSES))
    return model


def loader(
    run_dir: Path,
    rows: list[JsonDict],
    batch_size: int,
    workers: int,
    shuffle: bool = False,
    seed: int = SEED,
) -> DataLoader:
    generator = torch.Generator().manual_seed(seed)
    return DataLoader(
        TextureDataset(run_dir, rows),
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=workers,
        pin_memory=torch.cuda.is_available(),
        generator=generator,
        persistent_workers=False,
    )


@torch.inference_mode()
def infer(model: nn.Module, batches: DataLoader, device: torch.device) -> tuple[Tensor, Tensor]:
    model.eval()
    scores: list[Tensor] = []
    targets: list[Tensor] = []
    for images, labels in batches:
        with torch.autocast(
            device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"
        ):
            output = model(images.to(device, non_blocking=True))
        scores.append(output.float().cpu())
        targets.append(labels.cpu())
    logits, truth = torch.cat(scores), torch.cat(targets)
    if not torch.isfinite(logits).all():
        raise ValueError("Non-finite inference logits")
    return logits, truth


def save_checkpoint(path: Path, state: JsonDict) -> None:
    temporary = path.with_suffix(".tmp")
    torch.save(state, temporary)
    temporary.replace(path)


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
        images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)
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


def train(
    run_dir: Path,
    report_dir: Path,
    initialization: str,
    epochs: int = 30,
    micro_batch: int = 64,
    workers: int = 2,
    resume: bool = False,
    max_steps: int = 0,
) -> JsonDict:
    device = configure()
    if (run_dir / "test_seal.json").exists():
        raise ValueError("Test already opened; train a new run instead")
    if device.type != "cuda":
        raise RuntimeError("The planned local run requires a CUDA GPU")
    manifest = read_json(run_dir / "manifest.json")
    output = run_dir / initialization
    output.mkdir(parents=True, exist_ok=True)
    last_path, best_path = output / "last.pt", output / "best.pt"
    if last_path.exists() and not resume:
        raise ValueError("Existing training state requires --resume or a new run directory")
    model = make_model(initialization, pretrained=not resume).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9, weight_decay=0.0001)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=30, eta_min=0)
    scaler = GradScaler("cuda")
    history: list[JsonDict] = []
    best_key = (math.inf, math.inf, math.inf)
    start_epoch = 0
    if resume:
        state = torch.load(last_path, map_location=device, weights_only=False)
        if state["data_fingerprint"] != manifest["fingerprint"]:
            raise ValueError("Checkpoint belongs to a different dataset")
        if state["initialization"] != initialization:
            raise ValueError("Checkpoint initialization differs")
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        scaler.load_state_dict(state["scaler"])
        history, start_epoch = state["history"], int(state["epoch"])
        best_key = tuple(state["best_key"])
        random.setstate(state["python_rng"])
        np.random.set_state(state["numpy_rng"])
        torch.set_rng_state(state["torch_rng"].cpu())
        torch.cuda.set_rng_state_all([item.cpu() for item in state["cuda_rng"]])
    validation = loader(run_dir, manifest["splits"]["validation"], 64, workers)
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
            "sha256": sha256_file(Path(".cache/torch/hub/checkpoints/resnet18-f37072fd.pth")),
        }
        if initialization == "pretrained"
        else None,
        "initialization": initialization,
        "data_fingerprint": manifest["fingerprint"],
        "epochs_target": epochs,
        "seed": SEED,
        "effective_batch": 64,
        "micro_batch": micro_batch,
        "workers": workers,
        "max_steps": max_steps,
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "cuda_runtime": cuda_version,
        "gpu": torch.cuda.get_device_name(),
        "environment": environment(),
        "source_code_sha256": sha256_file(Path(__file__)),
    }
    write_json(output / "config.json", config)
    for epoch in range(start_epoch, epochs):
        batches = loader(
            run_dir, manifest["splits"]["train"], micro_batch, workers, True, SEED + epoch
        )
        epoch_started = time.perf_counter()
        training = train_epoch(model, batches, device, optimizer, scaler, micro_batch, max_steps)
        logits, truth = infer(model, validation, device)
        metrics = probability_metrics(logits, truth)
        learning_rate = optimizer.param_groups[0]["lr"]
        scheduler.step()
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
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "scaler": scaler.state_dict(),
            "epoch": epoch + 1,
            "best_key": best_key,
            "history": history,
            "data_fingerprint": manifest["fingerprint"],
            "initialization": initialization,
            "python_rng": random.getstate(),
            "numpy_rng": np.random.get_state(),
            "torch_rng": torch.get_rng_state(),
            "cuda_rng": torch.cuda.get_rng_state_all(),
        }
        if improved:
            save_checkpoint(best_path, state)
        save_checkpoint(last_path, state)
        write_json(output / "history.json", {"epochs": history})
        write_json(
            report_dir / f"{initialization}_training.json", {"config": config, "epochs": history}
        )
        print(
            f"{initialization} epoch={epoch + 1}/{epochs} train_loss={training['loss']:.5f} "
            f"val_nll={metrics['nll']:.5f} val_acc={metrics['accuracy']:.4f} "
            f"seconds={record['epoch_seconds']:.1f}",
            flush=True,
        )
    result = {"completed_epochs": len(history), "best_epoch": best_key[2], "config": config}
    write_json(output / "training_complete.json", result)
    del model, optimizer, scaler
    gc.collect()
    torch.cuda.empty_cache()
    return result


def checkpoint_inference(
    run_dir: Path, initialization: str, split: str, workers: int
) -> tuple[Tensor, Tensor, JsonDict]:
    device = configure()
    manifest = read_json(run_dir / "manifest.json")
    checkpoint = run_dir / initialization / "best.pt"
    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if state["data_fingerprint"] != manifest["fingerprint"]:
        raise ValueError("Checkpoint and manifest differ")
    model = make_model(initialization, pretrained=False).to(device)
    model.load_state_dict(state["model"])
    batches = loader(run_dir, manifest["splits"][split], 64, workers)
    started = time.perf_counter()
    logits, labels = infer(model, batches, device)
    information = {
        "split": split,
        "checkpoint_sha256": sha256_file(checkpoint),
        "checkpoint_epoch": state["epoch"],
        "data_fingerprint": manifest["fingerprint"],
        "seconds": time.perf_counter() - started,
    }
    save_checkpoint(
        run_dir / initialization / f"{split}_logits.pt",
        {"logits": logits, "labels": labels, "information": information},
    )
    del model
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return logits, labels, information


def require_completed_training(run_dir: Path, initialization: str, manifest: JsonDict) -> None:
    complete = read_json(run_dir / initialization / "training_complete.json")
    history = read_json(run_dir / initialization / "history.json")["epochs"]
    if not manifest["smoke"] and (
        complete["completed_epochs"] != 30
        or complete["config"]["max_steps"] != 0
        or len(history) != 30
        or any(
            item["train"]["samples"] != 10000 or item["train"]["steps"] != 157 for item in history
        )
    ):
        raise ValueError("Formal calibration/test requires 30 complete 10000-image epochs")


def calibrate(run_dir: Path, report_dir: Path, initialization: str, workers: int = 2) -> JsonDict:
    if (run_dir / "test_seal.json").exists():
        raise ValueError("Test already opened; calibration is frozen")
    require_completed_training(run_dir, initialization, read_json(run_dir / "manifest.json"))
    logits, labels, information = checkpoint_inference(
        run_dir, initialization, "calibration", workers
    )
    fitted = fit_temperature(logits, labels)
    result = {
        **fitted,
        **information,
        "initialization": initialization,
        "scope": "calibration_fit_metrics_only",
    }
    write_json(run_dir / initialization / "temperature.json", result)
    write_json(report_dir / f"{initialization}_calibration.json", result)
    print(
        f"calibrated {initialization} T={result['temperature']:.6f} status={result['status']}",
        flush=True,
    )
    return result


def evaluate(run_dir: Path, report_dir: Path, workers: int = 2) -> JsonDict:
    manifest = read_json(run_dir / "manifest.json")
    seal_path = run_dir / "test_seal.json"
    arms = ("pretrained", "scratch")
    locked: JsonDict = {"data_fingerprint": manifest["fingerprint"], "arms": {}}
    for arm in arms:
        require_completed_training(run_dir, arm, manifest)
        temperature = read_json(run_dir / arm / "temperature.json")
        if temperature["data_fingerprint"] != manifest["fingerprint"]:
            raise ValueError("Temperature belongs to a different dataset")
        checkpoint_hash = sha256_file(run_dir / arm / "best.pt")
        if temperature["checkpoint_sha256"] != checkpoint_hash:
            raise ValueError("Calibration checkpoint changed")
        locked["arms"][arm] = {
            "checkpoint_sha256": checkpoint_hash,
            "temperature_sha256": sha256_file(run_dir / arm / "temperature.json"),
        }
    if seal_path.exists() and read_json(seal_path) != locked:
        raise ValueError("The locked models/temperatures changed after test opening")
    write_json(seal_path, locked)
    results: JsonDict = {"data_fingerprint": manifest["fingerprint"], "arms": {}}
    for arm in arms:
        logits_path = run_dir / arm / "test_logits.pt"
        if logits_path.exists():
            packet = torch.load(logits_path, map_location="cpu", weights_only=True)
            logits, labels, information = packet["logits"], packet["labels"], packet["information"]
            if information["checkpoint_sha256"] != locked["arms"][arm]["checkpoint_sha256"]:
                raise ValueError("Cached inference checkpoint mismatch")
        else:
            logits, labels, information = checkpoint_inference(run_dir, arm, "test", workers)
        fitted = read_json(run_dir / arm / "temperature.json")
        temperature = float(fitted["temperature"])
        if not torch.equal(logits.argmax(dim=1), (logits.double() / temperature).argmax(dim=1)):
            raise ValueError("Temperature scaling changed argmax")
        results["arms"][arm] = {
            "raw": probability_metrics(logits, labels),
            "calibrated": probability_metrics(logits, labels, temperature),
            "temperature": temperature,
            "argmax_unchanged": True,
            "inference": information,
        }
        np.savez_compressed(
            run_dir / arm / "test_predictions.npz",
            logits=logits.numpy(),
            labels=labels.numpy(),
            raw_probabilities=logits.double().softmax(dim=1).numpy(),
            calibrated_probabilities=(logits.double() / temperature).softmax(dim=1).numpy(),
        )
    train_labels = [row["class_id"] for row in manifest["splits"]["train"]]
    majority = int(np.bincount(train_labels, minlength=4).argmax())
    test_labels = torch.tensor([row["class_id"] for row in manifest["splits"]["test"]])
    results["majority_baseline"] = {
        "class": CLASSES[majority],
        "accuracy": float((test_labels == majority).double().mean()),
    }
    write_json(report_dir / "metrics.json", results)
    return results
