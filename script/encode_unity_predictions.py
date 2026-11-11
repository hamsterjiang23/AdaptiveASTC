"""Encode saved native validation predictions and a fixed8 control, then audit quality."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityFinalEncoding(Path(__file__).resolve().parents[1], args.config).run()
    print(
        {key: result[key] for key in ["status", "validation_images", "summary", "wall_seconds"]},
        flush=True,
    )


if __name__ == "__main__":
    main()
