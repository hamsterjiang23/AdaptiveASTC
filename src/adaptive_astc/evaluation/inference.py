"""Model inference and checkpoint-bound prediction artifacts."""

import gc
import time
from pathlib import Path

import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.dataset import TextureDataModule
from adaptive_astc.models import ASTCClassifier
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.checkpoints import CheckpointStore
from adaptive_astc.utils.runtime import ExperimentRuntime


class Predictor:
    """Bind checkpoint inference to a prepared run and worker policy."""

    def __init__(self, run_dir: Path, workers: int = 2) -> None:
        self.run_dir = run_dir
        self.workers = workers

    @staticmethod
    @torch.inference_mode()
    def predict(
        model: nn.Module, batches: DataLoader, device: torch.device
    ) -> tuple[Tensor, Tensor]:
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

    def from_checkpoint(self, initialization: str, split: str) -> tuple[Tensor, Tensor, JsonDict]:
        device = ExperimentRuntime.configure()
        manifest = ArtifactStore.read_json(self.run_dir / "manifest.json")
        checkpoint = self.run_dir / initialization / "best.pt"
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        if state["data_fingerprint"] != manifest["fingerprint"]:
            raise ValueError("Checkpoint and manifest differ")
        model = ASTCClassifier(initialization, pretrained=False).to(device)
        model.load_state_dict(state["model"])
        batches = TextureDataModule(self.run_dir, self.workers).loader(
            manifest["splits"][split], 64
        )
        started = time.perf_counter()
        logits, labels = self.predict(model, batches, device)
        information = {
            "split": split,
            "checkpoint_sha256": ArtifactStore.sha256_file(checkpoint),
            "checkpoint_epoch": state["epoch"],
            "data_fingerprint": manifest["fingerprint"],
            "seconds": time.perf_counter() - started,
        }
        CheckpointStore.save(
            self.run_dir / initialization / f"{split}_logits.pt",
            {"logits": logits, "labels": labels, "information": information},
        )
        del model
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()
        return logits, labels, information
