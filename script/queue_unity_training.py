"""Wait for bound CUDA/data jobs, then run native smoke and complete-corpus training."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.training_queue import UnityTrainingQueue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityTrainingQueue(Path(__file__).resolve().parents[1], args.config).run()
    print({key: result[key] for key in ["status", "stages", "wall_seconds"]}, flush=True)


if __name__ == "__main__":
    main()
