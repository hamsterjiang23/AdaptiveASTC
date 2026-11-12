"""Collect all reserved confirmation images serially after a successful native smoke."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.confirmation_series import UnityConfirmationSeries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    series = UnityConfirmationSeries(Path(__file__).resolve().parents[1], args.config)
    result = series.validate() if args.validate_only else series.run()
    print({key: result[key] for key in ["status", "source_split", "test_opened"]})


if __name__ == "__main__":
    main()
