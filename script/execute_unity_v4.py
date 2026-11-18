"""Execute V4 smoke, complete native benchmarks, reporting and protocol preparation."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.v4_benchmark import UnityV4Benchmark
from reproductions.unity_search_baseline.v4_experiment import UnityV4Experiment
from reproductions.unity_search_baseline.v4_report import UnityV4Report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--attempt", default="v3")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    public = root / "experiment report/unity-v4-20261117"
    if args.status:
        print(A.read_json(public / "progress.json"))
        return
    if not (public / "offline.json").exists():
        UnityV4Experiment(root).offline()
    smoke_path = public / f"smoke32-{args.attempt}" / "result.json"
    if not smoke_path.exists():
        UnityV4Benchmark(root, smoke=True, attempt=args.attempt).run()
    smoke = A.read_json(smoke_path)
    if smoke["status"] != "passed" or smoke["images"] != 32:
        raise ValueError("The fixed 32-image native smoke must pass")
    by_mode = {(r["case"]["name"], r["scope"], r["mode"]): r for r in smoke["measurements"]}
    for scope in ["files", "pixels_ready"]:
        for mode in ["batch", "single"]:
            if (
                by_mode[("v3_baseline", scope, mode)]["astc_sha256"]
                != by_mode[("remove_lookahead", scope, mode)]["astc_sha256"]
            ):
                raise ValueError("Lookahead removal must preserve ASTC bytes in every input mode")
    UnityV4Benchmark(root, smoke=False, attempt=args.attempt).run()
    summary = UnityV4Report(root, args.attempt).build()
    print({"status": summary["status"], "recommendations": summary["recommendations"]})


if __name__ == "__main__":
    main()
