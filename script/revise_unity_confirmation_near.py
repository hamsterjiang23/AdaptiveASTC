"""Apply a frozen, explicitly approved confirmation near-identity replacement proposal."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.confirmation_near_revision import (
    UnityConfirmationNearRevision,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    revision = UnityConfirmationNearRevision(Path(__file__).resolve().parents[1], args.config)
    result = revision.revise()
    print({key: result[key] for key in ["status", "replaced_primary", "reserve_images"]})


if __name__ == "__main__":
    main()
