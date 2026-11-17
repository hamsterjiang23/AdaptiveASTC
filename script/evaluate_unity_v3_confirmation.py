"""Prepare, smoke-test or execute the frozen V3 independent confirmation protocol."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.v3_confirmation import UnityV3Confirmation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--phase", choices=["prepare", "smoke", "run"], required=True)
    args = parser.parse_args()
    evaluation = UnityV3Confirmation(Path(__file__).resolve().parents[1], args.config)
    if args.phase == "prepare":
        result = evaluation.prepare_inputs()
    elif args.phase == "smoke":
        evaluation.load_inputs(True)
        result = evaluation.evaluate(True)
    else:
        result = evaluation.run_confirmation()
    print({key: result.get(key) for key in ["status", "images", "test_opened", "accuracy90_met"]})


if __name__ == "__main__":
    main()
