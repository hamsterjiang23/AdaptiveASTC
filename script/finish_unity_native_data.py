"""Prepare and audit native data after frozen upstream jobs complete."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--check-once", action="store_true")
    args = parser.parse_args()
    result = UnityNativeDataPipeline(Path(__file__).resolve().parents[1], args.config).run(
        follow=not args.check_once
    )
    print({key: result[key] for key in ["status", "expected_counts", "wall_seconds"]}, flush=True)


if __name__ == "__main__":
    main()
