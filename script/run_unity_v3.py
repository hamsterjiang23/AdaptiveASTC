"""Run isolated Unity V3 development stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reproductions.unity_search_baseline.v3_experiment import UnityV3Experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["offline", "smoke-corpus", "benchmark"], required=True)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    tool = UnityV3Experiment(Path(__file__).resolve().parents[1])
    if args.stage == "offline":
        result = tool.offline()
    elif args.stage == "smoke-corpus":
        result = {"status": "passed", "corpus": str(tool.prepare_smoke_corpus())}
    else:
        from reproductions.unity_search_baseline.v3_benchmark import UnityV3Benchmark

        if args.config is None:
            parser.error("--config required for benchmark")
        result = UnityV3Benchmark(tool.root, args.config).run()
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key in ["status", "images", "wall_seconds", "corpus"]
            }
        )
    )


if __name__ == "__main__":
    main()
