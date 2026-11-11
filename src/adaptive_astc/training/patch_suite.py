"""Serial, independently identified native-patch CUDA experiments."""

from __future__ import annotations

import gc
import time
from pathlib import Path

import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.training.patch_trainer import PatchTrainConfig, PatchTrainer
from adaptive_astc.utils.artifacts import ArtifactStore


class PatchExperimentSuite:
    def __init__(self, config: Path) -> None:
        self.config = config

    def run(self) -> JsonDict:
        suite = ArtifactStore.read_json(self.config)
        output = Path(suite["summary"])
        if output.exists():
            raise FileExistsError("Use a new suite identity; previous trials remain archived")
        if not suite["trials"]:
            raise ValueError("The suite requires at least one trial")
        started = time.perf_counter()
        state = {
            "status": "running",
            "config_sha256": ArtifactStore.sha256_file(self.config),
            "trials": [],
            "current_trial": None,
            "test_opened": False,
        }
        ArtifactStore.write_json(output, state)
        try:
            for trial in suite["trials"]:
                options = dict(trial["config"])
                for name in ["corpus", "output", "report"]:
                    options[name] = Path(options[name])
                config = PatchTrainConfig(**options)
                state["current_trial"] = trial["name"]
                ArtifactStore.write_json(output, state)
                result = PatchTrainer(config).fit()
                audit_report = config.report.with_name(f"{config.report.stem}-audit.json")
                audit = PatchTrainer.audit_best(config.output, audit_report)
                state["trials"].append(
                    {
                        "name": trial["name"],
                        "report": str(config.report),
                        "status": result["status"],
                        "best_validation_accuracy": result["best_validation_accuracy"],
                        "best_near_threshold_rmse_db": result["best_near_threshold_rmse_db"],
                        "completed_epochs": len(result["history"]),
                        "wall_seconds": result["wall_seconds"],
                        "report_sha256": ArtifactStore.sha256_file(config.report),
                        "checkpoint_audit": str(audit_report),
                        "checkpoint_audit_status": audit["status"],
                        "checkpoint_audit_sha256": ArtifactStore.sha256_file(audit_report),
                    }
                )
                ArtifactStore.write_json(output, state)
                gc.collect()
                torch.cuda.empty_cache()
        except BaseException as error:
            state["status"] = (
                "interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "failed"
            )
            state["error"] = repr(error)
            state["wall_seconds"] = time.perf_counter() - started
            ArtifactStore.write_json(output, state)
            raise
        state["status"] = "completed"
        state["current_trial"] = None
        state["wall_seconds"] = time.perf_counter() - started
        ArtifactStore.write_json(output, state)
        return state
