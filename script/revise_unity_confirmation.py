"""Create a versioned V2-eligible confirmation reservation from its original reserves."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.confirmation_revision import UnityConfirmationRevision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    result = UnityConfirmationRevision(Path(__file__).resolve().parents[1], args.config).revise()
    print(
        {
            key: result[key]
            for key in ["status", "replaced_primary", "primary_images", "wall_seconds"]
        }
    )


if __name__ == "__main__":
    main()
