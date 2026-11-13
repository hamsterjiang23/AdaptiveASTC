"""Prepare or explicitly execute the frozen forward system on the approved revised cohort."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.revised_forward_confirmation import (
    UnityRevisedForwardConfirmationEvaluation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--execute-confirmation", action="store_true")
    args = parser.parse_args()
    evaluation = UnityRevisedForwardConfirmationEvaluation(
        Path(__file__).resolve().parents[1], args.config
    )
    result = evaluation.prepare() if args.prepare_only else evaluation.run()
    print({key: result[key] for key in ["status", "test_opened", "training_updates"]})


if __name__ == "__main__":
    main()
