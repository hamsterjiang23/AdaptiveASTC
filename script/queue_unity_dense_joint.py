"""Run full V5 joint training and best-native replay after the bound frozen job."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import psutil

from adaptive_astc.training.unity_dense_joint_trainer import UnityDenseJointTrainer
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiment report/.local/unity-v5-20261119"


def wait_for_frozen(job: Path, expected_sha: str, output: Path) -> None:
    if A.sha256_file(job) != expected_sha:
        raise ValueError("Frozen V5 dependency configuration changed")
    cmd = A.read_json(job)["command"]
    if (
        len(cmd) < 5
        or Path(cmd[2]).name != "queue_unity_dense_full.py"
        or cmd[-2] != "--output"
        or Path(cmd[-1]).resolve() != output
    ):
        raise ValueError("Dependency must publish the complete frozen V5 checkpoint")
    receipt_path = job.with_name("receipt.json")
    print(f"Waiting for frozen V5 job {A.read_json(receipt_path).get('child_pid')}", flush=True)
    while True:
        receipt = A.read_json(receipt_path)
        if receipt["config_sha256"] != expected_sha:
            raise ValueError("Receipt belongs to a different V5 frozen job")
        if receipt["status"] == "passed" and receipt["process_exit_code"] == 0:
            return
        if receipt["status"] != "running":
            raise RuntimeError(f"Frozen V5 job ended with {receipt['status']}")
        if not psutil.pid_exists(receipt["process_id"]):
            if A.read_json(receipt_path)["status"] != "running":
                continue
            raise RuntimeError("Frozen V5 job disappeared without a terminal receipt")
        time.sleep(15)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-job", type=Path, required=True)
    parser.add_argument("--frozen-job-sha256", required=True)
    parser.add_argument("--frozen-run", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-replay", type=Path, required=True)
    args = parser.parse_args()
    job, frozen, corpus, output, replay = (
        path.resolve()
        for path in (args.frozen_job, args.frozen_run, args.corpus, args.output, args.native_replay)
    )
    if any(not path.is_relative_to(RAW) for path in (job, frozen, corpus, output, replay)):
        parser.error("Use V5 local inputs and outputs")
    if output.exists() or replay.exists() or output == replay:
        raise ValueError("Choose fresh separate identities for joint training and replay")
    script = ROOT / "script/check_unity_dense_native_regression.py"
    sources = UnityDenseJointTrainer.source_hashes()
    replay_source_sha = A.sha256_file(script)
    wait_for_frozen(job, args.frozen_job_sha256, frozen)
    if (
        UnityDenseJointTrainer.source_hashes() != sources
        or A.sha256_file(script) != replay_source_sha
    ):
        raise ValueError("Joint V5 implementation changed while waiting")
    report_path = frozen / "report.json"
    report = A.read_json(report_path)
    corpus_sha = A.sha256_file(corpus)
    if (
        report["status"] != "passed"
        or report["stage"] != "full"
        or not report["checkpoint_reloaded"]
        or report["corpus_sha256"] != corpus_sha
        or report["counts"] != {"train": 10000, "validation": 1000}
        or report["test_opened"] is not False
    ):
        raise ValueError("Expected the reloaded full frozen V5 result on this exact corpus")
    info = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
        text=True,
    )
    free_mib, use_percent = map(int, info.splitlines()[0].split(","))
    if free_mib < 5120 or use_percent > 80 or psutil.virtual_memory().available < 8 * 2**30:
        raise RuntimeError("GPU or RAM headroom unavailable for full joint V5")
    print(f"Frozen checkpoint verified; CUDA memory free {free_mib} MiB", flush=True)
    subprocess.run(
        [
            sys.executable,
            "-u",
            str(ROOT / "script/train_unity_dense_joint.py"),
            "--stage",
            "full",
            "--corpus",
            str(corpus),
            "--corpus-sha256",
            corpus_sha,
            "--frozen-run",
            str(frozen),
            "--frozen-report-sha256",
            A.sha256_file(report_path),
            "--output",
            str(output),
            "--batch-size",
            "8",
            "--epochs",
            "3",
        ],
        cwd=ROOT,
        check=True,
    )
    joint = A.read_json(output / "report.json")
    checkpoint = output / "best-native.pt"
    if (
        joint["status"] != "passed"
        or A.sha256_file(checkpoint) != joint["best_native_checkpoint_sha256"]
    ):
        raise ValueError("Full joint V5 job did not publish a verified native checkpoint")
    subprocess.run(
        [
            sys.executable,
            "-u",
            str(script),
            "--native-checkpoint",
            str(checkpoint),
            "--native-checkpoint-sha256",
            joint["best_native_checkpoint_sha256"],
            "--output",
            str(replay),
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
