"""Freeze development rating strata or build model-bound V5 review packets."""

import argparse
from pathlib import Path

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_dense_review import UnityDenseReview
from adaptive_astc.evaluation.unity_dense_screening import UnityDenseScreening
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "experiment report/unity-accuracy90-20261111"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", type=Path, required=True)
    parser.add_argument("--freeze-partition", action="store_true")
    parser.add_argument("--training-run", type=Path)
    parser.add_argument("--step-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    archive = UnityTileArchive(HANDOFF / "unity-v2-data-inputs.json")
    review = UnityDenseReview(archive)
    if args.freeze_partition:
        if args.partition.exists():
            raise FileExistsError("Preserve the frozen V5 human rating partitions")
        partition = review.partition()
        A.write_json(args.partition, partition)
        print(f"Froze development strata {partition['counts']}")
        return
    if any(value is None for value in (args.training_run, args.step_report, args.output)):
        parser.error("Packet generation requires a training run, step report and output")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "experiment report/.local/unity-v5-20261119"):
        parser.error("Keep V5 packet images under its private experiment directory")
    partition = A.read_json(args.partition)
    run_path = args.training_run / "report.json"
    run = A.read_json(run_path)
    if (
        run["status"] != "passed"
        or run["test_opened"] is not False
        or not run["checkpoint_reloaded"]
    ):
        raise ValueError("Review generation requires a reloaded development checkpoint")
    dense = archive.read_bound_json(
        args.training_run / "best-validation.json", run["best_validation_sha256"], dict
    )
    step = A.read_json(args.step_report)
    if (
        step["status"] != "passed"
        or step["test_opened"] is not False
        or step["development_corpus_sha256"] != archive.sha256
        or step["candidate"] != [8, "fastest"]
    ):
        raise ValueError("Step baseline is outside the frozen review scope")
    screening = UnityDenseScreening(
        archive, HANDOFF / "unity-development-corpus11000-v2-interface.json"
    )
    packets = review.packet(output, screening, partition, dense["images"], step["rows"])
    A.write_json(
        output / "manifest.json",
        {
            "status": "awaiting_human_ratings",
            "training_stage": run["stage"],
            "partition_sha256": A.sha256_file(args.partition),
            "training_report_sha256": A.sha256_file(run_path),
            "validation_sha256": run["best_validation_sha256"],
            "step_report_sha256": A.sha256_file(args.step_report),
            "strata": packets,
            "confirmation_opened": False,
        },
    )
    ratings = sum(len(group["rows"]) for group in packets.values())
    print(f"Prepared paired images for {ratings} ratings")


if __name__ == "__main__":
    main()
