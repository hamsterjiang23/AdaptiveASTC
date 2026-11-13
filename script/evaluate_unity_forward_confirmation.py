"""Prepare development admission or execute an explicitly authorized forward confirmation."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.forward_confirmation import (
    UnityForwardConfirmationEvaluation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--execute-confirmation", action="store_true")
    args = parser.parse_args()
    runner = UnityForwardConfirmationEvaluation(Path(__file__).resolve().parents[1], args.config)
    result = runner.prepare() if args.prepare_only else runner.run()
    print({"status": result["status"], "test_opened": result["test_opened"]}, flush=True)


if __name__ == "__main__":
    main()
