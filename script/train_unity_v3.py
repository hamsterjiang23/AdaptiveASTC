"""Train a paired V3 full model or frozen-encoder image head, then audit its checkpoint."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("full", "head"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    from adaptive_astc.training.unity_v3_head import UnityV3HeadTrainer
    from adaptive_astc.training.unity_v3_trainer import UnityV3Trainer

    trainer_type = UnityV3Trainer if args.stage == "full" else UnityV3HeadTrainer
    trainer = trainer_type(args.config, Path(__file__).resolve().parents[1])
    result = trainer.run()
    print({key: result[key] for key in ("status", "training_updates", "wall_seconds")}, flush=True)


if __name__ == "__main__":
    main()
