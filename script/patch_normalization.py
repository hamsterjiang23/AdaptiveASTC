"""Compare frozen raw/EMA patch weights before and after train-only BN recalibration."""

import argparse
from pathlib import Path

from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--calibration-batches", type=int, default=128)
    parser.add_argument(
        "--training-source-archive",
        type=Path,
        help="Verified repository-relative snapshot when the original training sources changed",
    )
    args = parser.parse_args()
    result = PatchNormalizationAudit.run(**vars(args))
    print({"status": result["status"], "wall_seconds": result["wall_seconds"]}, flush=True)


if __name__ == "__main__":
    main()
