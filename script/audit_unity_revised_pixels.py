"""Audit native pixels after the explicitly approved development scope revision."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.revised_pixel_identity import (
    UnityRevisedPixelIdentityAudit,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityRevisedPixelIdentityAudit(Path.cwd(), args.config).run()
    print({key: result[key] for key in ["status", "counts", "replacement_counts"]})


if __name__ == "__main__":
    main()
