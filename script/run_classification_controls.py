"""Run a frozen, serial CUDA classification-control suite with per-trial records."""

import argparse
import time
from pathlib import Path

import torch

from adaptive_astc.training.classification_control import (
    ClassificationControlConfig,
    ClassificationControlTrainer,
)
from adaptive_astc.utils.artifacts import ArtifactStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    suite = ArtifactStore.read_json(args.config)
    output = Path(suite["summary"])
    if output.exists():
        raise FileExistsError("Use a new suite identity; individual trial reports remain retained")
    started = time.perf_counter()
    state = {
        "status": "running",
        "config_sha256": ArtifactStore.sha256_file(args.config),
        "trials": [],
        "test_opened": False,
    }
    ArtifactStore.write_json(output, state)
    try:
        for trial in suite["trials"]:
            options = dict(trial["config"])
            for name in ["source", "output", "report"]:
                options[name] = Path(options[name])
            config = ClassificationControlConfig(**options)
            state["current_trial"] = trial["name"]
            ArtifactStore.write_json(output, state)
            result = ClassificationControlTrainer(config).fit()
            state["trials"].append(
                {
                    "name": trial["name"],
                    "report": str(config.report),
                    "status": result["status"],
                    "best_validation_accuracy": result["best_validation_accuracy"],
                    "best_validation_nll": result["best_validation_nll"],
                    "completed_epochs": len(result["history"]),
                    "wall_seconds": result["wall_seconds"],
                    "report_sha256": ArtifactStore.sha256_file(config.report),
                }
            )
            ArtifactStore.write_json(output, state)
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
    print(state, flush=True)


if __name__ == "__main__":
    main()
