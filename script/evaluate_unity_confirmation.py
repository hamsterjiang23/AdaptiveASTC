"""Run a frozen model once as a decision procedure on all reserved confirmation images."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.confirmation_evaluation import UnityConfirmationEvaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityConfirmationEvaluation(Path(__file__).resolve().parents[1], args.config).run()
    print({key: result[key] for key in ["status", "summary", "accuracy90_met", "wall_seconds"]})


if __name__ == "__main__":
    main()
