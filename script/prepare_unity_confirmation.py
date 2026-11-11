"""Reserve independent source identities without opening native test labels or predictions."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.confirmation import UnityConfirmationCohort


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    result = UnityConfirmationCohort(Path(__file__).resolve().parents[1], args.config).reserve()
    print({k: result[k] for k in ["status", "primary_images", "reserve_images", "wall_seconds"]})
    if result["status"] != "reserved":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
