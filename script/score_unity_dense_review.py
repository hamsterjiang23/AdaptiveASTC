"""Compare calibrated step scores or score the human review of a frozen V5 run."""

import argparse
import hashlib
from pathlib import Path

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_dense_review import UnityDenseReview
from adaptive_astc.evaluation.unity_dense_review_scoring import UnityDenseReviewScoring as Score
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("step", "calibration", "holdout"), required=True)
    parser.add_argument("--training-run", type=Path, required=True)
    parser.add_argument("--partition", type=Path, required=True)
    parser.add_argument("--step-report", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--calibration-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "experiment report/.local/unity-v5-20261119"):
        parser.error("Keep V5 scoring results in its private experiment directory")
    if output.exists():
        raise FileExistsError("Preserve the prior V5 scoring result")
    handoff = ROOT / "experiment report/unity-accuracy90-20261111/unity-v2-data-inputs.json"
    archive = UnityTileArchive(handoff)
    partition = A.read_json(args.partition)
    if partition != UnityDenseReview(archive).partition():
        raise ValueError("Review partition marker did not match the frozen development groups")
    run = A.read_json(args.training_run / "report.json")
    if (
        run["status"] != "passed"
        or run["test_opened"] is not False
        or not run["checkpoint_reloaded"]
    ):
        raise ValueError("Expected a reloaded development-only dense run")
    validation_sha = run["best_validation_sha256"]
    dense = archive.read_bound_json(
        args.training_run / "best-validation.json", validation_sha, dict
    )
    binding = {
        "validation_sha256": validation_sha,
        "partition_sha256": A.sha256_file(args.partition),
    }
    candidate = archive.GRID.index((8, "fastest"))
    if args.phase == "step":
        if args.step_report is None:
            parser.error("Step comparison requires a baseline report")
        step = A.read_json(args.step_report)
        if (
            step["status"] != "passed"
            or step["test_opened"] is not False
            or step["development_corpus_sha256"] != archive.sha256
            or step["candidate"] != [8, "fastest"]
            or step["color_coverage"] != "complete"
        ):
            raise ValueError("Expected the matching full native color step baseline")
        result = Score.step_baseline(dense["images"], step["rows"], partition, candidate)
        result["step_sha256"] = A.sha256_file(args.step_report)
    else:
        if args.packet is None or args.ratings is None:
            parser.error("Human scoring requires a model-bound packet and completed rating CSV")
        packet = A.read_json(args.packet / "manifest.json")
        if (
            any(packet[key] != value for key, value in binding.items())
            or packet["training_stage"] != "full"
        ):
            raise ValueError("Formal human scoring requires the matching full model review packet")
        stratum = packet["strata"][args.phase]
        allowed = {row["index"] for row in partition["strata"][args.phase]}
        if not {row["index"] for row in stratum["rows"]}.issubset(allowed):
            raise ValueError("Model packet includes images outside this evaluation partition")
        binding["packet_sha256"] = A.sha256_file(args.packet / "manifest.json")
        directory = args.packet / args.phase
        for image in stratum["rows"]:
            for filename, digest in image["display_sha256"].items():
                if A.sha256_file(directory / "pairs" / filename) != digest:
                    raise ValueError("A paired review image changed after the packet was frozen")
        if args.phase == "calibration":
            ratings_content = args.ratings.read_bytes()
            ratings = Score.read_ratings(ratings_content, stratum)
            result = Score.select_rule(dense["images"], ratings, candidate)
        else:
            if args.calibration is None or args.calibration_sha256 is None:
                parser.error("Bind the prior calibration result before scoring holdout labels")
            selection = archive.read_bound_json(args.calibration, args.calibration_sha256, dict)
            if (
                selection["status"] != "passed"
                or selection["phase"] != "calibration"
                or selection["binding"] != binding
            ):
                raise ValueError("Calibration result belongs to a different packet")
            rule = selection["frozen_rule"]
            ratings_content = args.ratings.read_bytes()
            ratings = Score.read_ratings(ratings_content, stratum)
            result = {
                "frozen_rule": rule,
                "result": Score.apply_rule(dense["images"], ratings, rule, candidate),
                "calibration_sha256": args.calibration_sha256,
            }
        result.update(
            ratings_sha256=hashlib.sha256(ratings_content).hexdigest(),
            queues=Score.queue_quality(stratum, ratings),
        )
    A.write_json(
        output,
        {
            "status": "passed",
            "phase": args.phase,
            "training_stage": run["stage"],
            "binding": binding,
            "confirmation_opened": False,
            **result,
        },
    )
    print(f"Completed V5 {args.phase} scoring")


if __name__ == "__main__":
    main()
