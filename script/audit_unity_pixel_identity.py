"""Check exact native pixel duplicates in explicitly frozen completed archives."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    result = UnityPixelIdentityAudit(args.config).run()
    print({key: result[key] for key in ["status", "counts", "rgba", "rgb_only", "wall_seconds"]})


if __name__ == "__main__":
    main()
