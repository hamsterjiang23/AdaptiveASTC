"""Measure native input-only CUDA inference after configured training dependencies finish."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.inference_benchmark import UnityInferenceBenchmark


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityInferenceBenchmark(Path(__file__).resolve().parents[1], args.config).run()
    print(
        {
            key: result[key]
            for key in ["status", "median_preprocess_inference_decision_seconds", "wall_seconds"]
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
