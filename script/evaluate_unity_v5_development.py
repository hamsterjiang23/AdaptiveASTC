"""Evaluate the complete frozen and jointly fine-tuned V5 development runs."""

import argparse
from pathlib import Path

from adaptive_astc.evaluation.unity_v5_development import UnityV5Development

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-corpus", required=True, type=Path)
    parser.add_argument("--frozen-run", required=True, type=Path)
    parser.add_argument("--joint-run", required=True, type=Path)
    parser.add_argument("--joint-native-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = UnityV5Development(ROOT).run(
        args.label_corpus, args.frozen_run, args.joint_run, args.joint_native_report, args.output
    )
    print(
        f"V5 development evaluation complete; selected for review: {result['selected_for_review']}"
    )


if __name__ == "__main__":
    main()
