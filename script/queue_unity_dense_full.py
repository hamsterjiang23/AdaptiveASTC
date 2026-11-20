"""Start full V5 frozen training once the bound complete label job exits successfully."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import psutil

from adaptive_astc.training.unity_dense_tile_trainer import UnityDenseTileTrainer
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiment report/.local/unity-v5-20261119"


def wait_for_labels(config: Path, digest: str, corpus: Path) -> None:
    if A.sha256_file(config) != digest:
        raise ValueError("Full V5 label dependency configuration changed")
    command = A.read_json(config)["command"]
    if (
        len(command) < 5
        or Path(command[-4]).name != "prepare_unity_tile_labels.py"
        or command[-3] != "--output"
        or Path(command[-2]).resolve() != corpus.parent
        or command[-1] != "--full"
    ):
        raise ValueError("Dependency must materialize the complete V5 label corpus")
    path = config.with_name("receipt.json")
    receipt = A.read_json(path)
    print(f"Waiting for label job {receipt.get('child_pid')}", flush=True)
    while True:
        receipt = A.read_json(path)
        if receipt["config_sha256"] != digest:
            raise ValueError("Receipt is bound to a different label job")
        if receipt["status"] == "passed" and receipt["process_exit_code"] == 0:
            return
        if receipt["status"] != "running":
            raise RuntimeError(f"Bound V5 label job ended with {receipt['status']}")
        if not psutil.pid_exists(receipt["process_id"]):
            # Let a receipt replacement that raced with the PID check become visible.
            receipt = A.read_json(path)
            if receipt["status"] != "running":
                continue
            raise RuntimeError("The bound label broker disappeared without a terminal receipt")
        time.sleep(15)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-job", type=Path, required=True)
    parser.add_argument("--label-job-sha256", required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus, output = args.corpus.resolve(), args.output.resolve()
    if any(not path.is_relative_to(RAW) for path in (corpus, output, args.label_job.resolve())):
        parser.error("Use V5 local inputs and outputs")
    if corpus.name != "corpus.json" or output.exists():
        raise ValueError("Expected a canonical corpus and a fresh full-training identity")
    sources = UnityDenseTileTrainer.source_hashes()
    wait_for_labels(args.label_job.resolve(), args.label_job_sha256, corpus)
    if UnityDenseTileTrainer.source_hashes() != sources:
        raise ValueError("Full training implementation changed while waiting")
    manifest = A.read_json(corpus)
    if (
        manifest["status"] != "passed"
        or manifest["coverage"] != "complete"
        or manifest["counts"] != {"train": 10000, "validation": 1000}
        or manifest["test_opened"] is not False
    ):
        raise ValueError("V5 full label dependency did not publish the complete development corpus")
    info = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
        text=True,
    )
    free_mib, use_percent = map(int, info.splitlines()[0].split(","))
    if free_mib < 4096 or use_percent > 80 or psutil.virtual_memory().available < 8 * 2**30:
        raise RuntimeError("GPU or RAM headroom unavailable for full dense training")
    print(f"Complete label corpus verified; CUDA memory free {free_mib} MiB", flush=True)
    subprocess.run(
        [
            sys.executable,
            "-u",
            str(ROOT / "script/train_unity_dense_tiles.py"),
            "--stage",
            "full",
            "--corpus",
            str(corpus),
            "--corpus-sha256",
            A.sha256_file(corpus),
            "--output",
            str(output),
            "--batch-size",
            "16",
            "--loss-cap-db",
            "45",
            "--epochs",
            "5",
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
