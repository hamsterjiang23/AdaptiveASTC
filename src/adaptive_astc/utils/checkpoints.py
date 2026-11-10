"""Atomic checkpoint persistence and training completion checks."""

import math
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
    def validate_resume(
        state: JsonDict,
        manifest: JsonDict,
        initialization: str,
        output: Path,
        optimization_signature: JsonDict,
    ) -> None:
        if state["data_fingerprint"] != manifest["fingerprint"]:
            raise ValueError("Checkpoint belongs to a different dataset")
        if state["initialization"] != initialization:
            raise ValueError("Checkpoint initialization differs")
        saved_config = state.get("optimization_config")
        if saved_config is None:
            previous_config = ArtifactStore.read_json(output / "config.json")
            saved_config = {
                key: previous_config[key]
                for key in ("seed", "effective_batch", "optimizer", "scheduler")
            }
        if saved_config != optimization_signature:
            raise ValueError("Resume optimization configuration differs from checkpoint")

    @staticmethod
    def require_completed(run_dir: Path, initialization: str, manifest: JsonDict) -> None:
        complete = ArtifactStore.read_json(run_dir / initialization / "training_complete.json")
        history = ArtifactStore.read_json(run_dir / initialization / "history.json")["epochs"]
        effective_batch = int(complete["config"].get("effective_batch", 64))
        expected_steps = math.ceil(10000 / effective_batch)
        if not manifest["smoke"] and (
            complete["completed_epochs"] != 30
            or complete["config"]["max_steps"] != 0
            or len(history) != 30
            or any(
                item["train"]["samples"] != 10000 or item["train"]["steps"] != expected_steps
                for item in history
            )
        ):
            raise ValueError("Formal calibration/test requires 30 complete 10000-image epochs")
