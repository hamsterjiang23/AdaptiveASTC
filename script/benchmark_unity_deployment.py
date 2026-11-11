"""Measure paired fresh CUDA prediction-to-ASTC and fixed8 deployment paths."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.deployment_benchmark import UnityDeploymentBenchmark


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityDeploymentBenchmark(Path(__file__).resolve().parents[1], args.config).run()
    print({key: result[key] for key in ["status", "summary", "active_seconds"]}, flush=True)


if __name__ == "__main__":
    main()
