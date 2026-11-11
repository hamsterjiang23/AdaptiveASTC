"""Run V1 regularized/ordinal classification controls without opening test data."""

import argparse
from pathlib import Path

from adaptive_astc.training.classification_control import (
    ClassificationControlConfig,
    ClassificationControlTrainer,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--initialization", choices=["scratch", "pretrained"], default="pretrained")
    parser.add_argument(
        "--loss", choices=["cross_entropy", "ordered_cumulative"], default="cross_entropy"
    )
    parser.add_argument("--smoothing", type=float, default=0.1)
    parser.add_argument("--learning-rate", type=float, default=0.003)
    parser.add_argument("--weight-decay", type=float, default=0.0005)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--scheduler-t-max", type=int, default=30)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--train-limit", type=int, default=0)
    parser.add_argument("--validation-limit", type=int, default=0)
    result = ClassificationControlTrainer(
        ClassificationControlConfig(**vars(parser.parse_args()))
    ).fit()
    print({key: value for key, value in result.items() if key != "history"}, flush=True)


if __name__ == "__main__":
    main()
