"""Train native Unity quality heads on CUDA and audit the selected checkpoint."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptive_astc.training.unity_quality_trainer import UnityQualityTrainer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityQualityTrainer(args.config, Path(__file__).resolve().parents[1]).run()
    print({k: result[k] for k in ["status", "training_updates", "wall_seconds"]}, flush=True)


if __name__ == "__main__":
    main()
