"""Atomic checkpoint persistence and training completion checks."""

from pathlib import Path

import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore


class CheckpointStore:
    """Persist packets and guard formal calibration/test admission."""

    @staticmethod
    def save(path: Path, state: JsonDict) -> None:
        temporary = path.with_suffix(".tmp")
        torch.save(state, temporary)
        temporary.replace(path)

    @staticmethod
    def require_completed(run_dir: Path, initialization: str, manifest: JsonDict) -> None:
        complete = ArtifactStore.read_json(run_dir / initialization / "training_complete.json")
        history = ArtifactStore.read_json(run_dir / initialization / "history.json")["epochs"]
        if not manifest["smoke"] and (
            complete["completed_epochs"] != 30
            or complete["config"]["max_steps"] != 0
            or len(history) != 30
            or any(
                item["train"]["samples"] != 10000 or item["train"]["steps"] != 157
                for item in history
            )
        ):
            raise ValueError("Formal calibration/test requires 30 complete 10000-image epochs")
