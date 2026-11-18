"""Run the independent V4 development experiment stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.v4_experiment import UnityV4Experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["offline", "benchmark"], default="offline")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--attempt", default="v3")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = root / "experiment report/unity-v4-20261117/progress.json"
    if args.status:
        result = A.read_json(report) if report.exists() else {"status": "implementation"}
    elif args.stage == "offline":
        result = UnityV4Experiment(root).offline()
    else:
        from reproductions.unity_search_baseline.v4_benchmark import UnityV4Benchmark

        result = UnityV4Benchmark(root, smoke=args.smoke, attempt=args.attempt).run()
    print(
        json.dumps(
            {key: result[key] for key in ["status", "images", "wall_seconds"] if key in result}
        )
    )


if __name__ == "__main__":
    main()
