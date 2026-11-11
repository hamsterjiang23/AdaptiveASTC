"""Prepare native patch shards from a frozen published candidate-batch snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.patch_batches import UnityPatchBatchPreparation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityPatchBatchPreparation(Path(__file__).resolve().parents[1], args.config).run()
    print(
        {
            key: result[key]
            for key in ["status", "coverage", "counts", "patch_counts", "wall_seconds"]
        }
    )


if __name__ == "__main__":
    main()
