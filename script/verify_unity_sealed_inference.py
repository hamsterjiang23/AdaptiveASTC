"""Validate a sealed native model on the two previously observed validation images."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.sealed_inference import UnitySealedInferenceSmoke


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnitySealedInferenceSmoke(Path(__file__).resolve().parents[1], args.config).run()
    print(
        {
            key: result[key]
            for key in ["status", "images", "patches", "choices_match", "wall_seconds"]
        }
    )


if __name__ == "__main__":
    main()
