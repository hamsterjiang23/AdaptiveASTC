"""Run V3 development experiments through the serial audited job runner."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psutil

from adaptive_astc.utils.artifacts import ArtifactStore as A


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Read the current suite status")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    private = root / "experiment report/.local/unity-v3-20261113"
    progress = root / "experiment report/unity-v3-20261113/progress.json"
    if args.status:
        print(json.dumps(A.read_json(progress) if progress.exists() else {"status": "not_started"}))
        return
    if progress.exists():
        previous = A.read_json(progress)
        if previous["status"] == "completed_development":
            print(
                json.dumps(
                    {
                        "status": previous["status"],
                        "summary": previous["summary"],
                        "test_opened": previous["test_opened"],
                    }
                )
            )
            return
    receipt = private / "jobs/development-suite-v1/receipt.json"
    if receipt.exists():
        existing = A.read_json(receipt)
        if existing["status"] == "running" and psutil.pid_exists(existing.get("child_pid", -1)):
            raise RuntimeError("The V3 suite is running; use --status to inspect it")
    private.mkdir(parents=True, exist_ok=True)
    lock = private / "suite.lock"
    if lock.exists():
        owner = A.read_json(lock)
        if psutil.pid_exists(owner["pid"]):
            raise RuntimeError("Another V3 suite owns the execution lock")
        lock.unlink()
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid()}, stream)
    try:
        from reproductions.unity_search_baseline.v3_suite import UnityV3Suite

        result = UnityV3Suite(root).run()
        print(json.dumps({"status": result["status"], "test_opened": result["test_opened"]}))
    finally:
        lock.unlink()


if __name__ == "__main__":
    main()
