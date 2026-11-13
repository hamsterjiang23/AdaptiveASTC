"""Recompute all native pixels for a frozen, approved revised confirmation cohort."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.confirmation_revision_pixels import (
    UnityConfirmationRevisionPixelAudit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    audit = UnityConfirmationRevisionPixelAudit(Path(__file__).resolve().parents[1], args.config)
    result = audit.run()
    print({key: result[key] for key in ["status", "counts", "rgba", "wall_seconds"]})


if __name__ == "__main__":
    main()
