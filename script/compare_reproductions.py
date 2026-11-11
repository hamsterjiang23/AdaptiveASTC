"""Publish a scoped shared64 comparison after the measured GDC training diagnostic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reproductions.common.comparison import ReproductionComparison  # noqa: E402
from reproductions.common.reference_comparison import ReferenceComparison  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdc-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unity-reference", action="store_true")
    args = parser.parse_args()
    comparison = ReferenceComparison(ROOT) if args.unity_reference else ReproductionComparison(ROOT)
    result = comparison.write(args.gdc_report, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
