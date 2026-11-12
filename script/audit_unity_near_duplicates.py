"""Screen frozen native RGBA images for aligned same-resolution near duplicates."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.near_duplicates import UnityNearDuplicateAudit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityNearDuplicateAudit(Path(__file__).resolve().parents[1], args.config).run()
    print({key: result[key] for key in ["status", "counts", "near_identity_pairs", "wall_seconds"]})


if __name__ == "__main__":
    main()
