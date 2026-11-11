"""Verify the native model-to-policy interface on frozen development patch targets."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.prediction_audit import UnityPredictionAudit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityPredictionAudit(Path(__file__).resolve().parents[1], args.config).run()
    print({key: result[key] for key in ["status", "training_updates", "wall_seconds"]}, flush=True)


if __name__ == "__main__":
    main()
