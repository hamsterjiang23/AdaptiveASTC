"""Measure real validation forward search and a paired fixed8 baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.forward_benchmark import UnityForwardSearchBenchmark


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = UnityForwardSearchBenchmark(root, args.config).run()
    print({"status": result["status"], "training_updates": result["training_updates"]})


if __name__ == "__main__":
    main()
