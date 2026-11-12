"""Bind original Unity capture policies without supplemental candidate data."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.capture_policy import UnityCapturePolicyAudit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityCapturePolicyAudit(Path(__file__).resolve().parents[1], args.config).run()
    print({key: result[key] for key in ["status", "test_opened", "wall_seconds"]})


if __name__ == "__main__":
    main()
