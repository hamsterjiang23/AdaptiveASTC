"""Freeze the V5 model, review rule and reserved source cohort for future confirmation."""

import argparse
from pathlib import Path

import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.models.unity_dense_tile import UnityDenseTileRegressor
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_dense_tile_trainer import UnityDenseTileTrainer
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "experiment report/unity-v5-20261119"
RAW = ROOT / "experiment report/.local/unity-v5-20261119"


def checked(record: JsonDict) -> Path:
    path = ROOT / record["path"]
    if A.sha256_file(path) != record["sha256"]:
        raise ValueError(f"V5 confirmation prerequisite digest changed: {path}")
    return path


def check_ratings(evaluation: JsonDict, calibration: Path, holdout: Path) -> JsonDict:
    selected = evaluation["models"][evaluation["selected_for_review"]]
    manifest = checked(evaluation["review_manifest"])
    binding = {
        "validation_sha256": selected["validation"]["sha256"],
        "packet_sha256": evaluation["review_manifest"]["sha256"],
        "partition_sha256": A.read_json(manifest)["partition_sha256"],
    }
    selection = A.read_json(calibration)
    measured = A.read_json(holdout)
    if (
        selection["status"] != "passed"
        or measured["status"] != "passed"
        or selection["phase"] != "calibration"
        or measured["phase"] != "holdout"
        or selection["binding"] != binding
        or measured["binding"] != binding
        or measured["calibration_sha256"] != A.sha256_file(calibration)
        or selection["frozen_rule"] != measured["frozen_rule"]
        or selection["confirmation_opened"]
        or measured["confirmation_opened"]
    ):
        raise ValueError(
            "Independent protocol requires the frozen calibration and completed holdout"
        )
    return selection["frozen_rule"]


def freeze(
    evaluation_path: Path,
    calibration: Path,
    holdout: Path,
    calibration_ratings: Path,
    holdout_ratings: Path,
    output: Path,
) -> None:
    if output.exists():
        raise FileExistsError("Preserve existing V5 confirmation protocol identity")
    evaluation = A.read_json(evaluation_path)
    if evaluation["status"] != "awaiting_human_ratings" or evaluation["confirmation_opened"]:
        raise ValueError("Expected the frozen V5 development evaluation")
    rule = check_ratings(evaluation, calibration, holdout)
    rating_inputs = {
        name: {"path": str(ratings.resolve()), "sha256": A.read_json(receipt)["ratings_sha256"]}
        for name, ratings, receipt in (
            ("calibration", calibration_ratings, calibration),
            ("holdout", holdout_ratings, holdout),
        )
    }
    for record in rating_inputs.values():
        checked(record)
    assets = A.read_json(PUBLIC / "confirmation-protocol-preparation.json")
    reservation = A.read_json(checked(assets["reservation"]))
    isolation = A.read_json(checked(assets["source_isolation"]))
    manifest = checked({"path": reservation["manifest"], "sha256": reservation["manifest_sha256"]})
    if (
        reservation["status"] != "reserved"
        or reservation["test_opened"]
        or isolation["status"] != "passed"
        or isolation["confirmation_opened"]
        or isolation["path_group_and_source_md4_overlaps"] != 0
        or isolation["manifest_sha256"] != reservation["manifest_sha256"]
    ):
        raise ValueError("Reserved sources have not passed historical identity isolation")
    chosen = evaluation["models"][evaluation["selected_for_review"]]
    path = checked(chosen["checkpoint"])
    training = A.read_json(checked(chosen["model_report"]))
    v3 = A.read_json(ROOT / "experiment report/unity-v3-20261113/progress.json")["recommendation"]
    parent_path = checked({"path": v3["checkpoint"], "sha256": v3["checkpoint_sha256"]})
    device = torch.device("cpu")
    parent = UnityQualityRegressor.from_checkpoint(
        torch.load(parent_path, map_location=device, weights_only=True), device
    )
    model = UnityDenseTileRegressor(parent)
    dense = torch.load(path, map_location=device, weights_only=True)
    if (
        dense["parent_sha256"] != v3["checkpoint_sha256"]
        or dense["corpus_sha256"] != training["corpus_sha256"]
        or dense["epoch"] != training["best_epoch"]
    ):
        raise ValueError("Full V5 checkpoint provenance changed")
    model.load_state_dict(dense["model"], strict=True)
    model_state_sha256 = UnityDenseTileTrainer.model_hash(model)
    prior_binding = A.read_json(PUBLIC / "confirmation-model-binding.json")
    native_checkpoint = prior_binding["native_checkpoint"]
    checked(native_checkpoint)
    if (
        checked(prior_binding["development_evaluation"]).resolve() != evaluation_path.resolve()
        or checked(prior_binding["checkpoint"]).resolve() != path.resolve()
        or prior_binding["model_state_sha256"] != model_state_sha256
        or prior_binding["selected_variant"] != evaluation["selected_for_review"]
    ):
        raise ValueError("V5 confirmation model differs from the pre-review binding")
    matrix_path = ROOT / "experiment plan/V5/matrix.json"
    matrix = A.read_json(matrix_path)
    sources = (
        "script/freeze_unity_v5_confirmation.py",
        "script/predict_unity_dense_tiles.py",
        "script/score_unity_dense_review.py",
        "src/adaptive_astc/models/unity_dense_tile.py",
        "src/adaptive_astc/models/unity_quality.py",
        "src/adaptive_astc/data/unity_dense_tile_dataset.py",
        "src/adaptive_astc/data/unity_tile_errors.py",
        "src/adaptive_astc/evaluation/unity_dense_review_scoring.py",
        "src/adaptive_astc/evaluation/unity_dense_tile_inference.py",
        "src/adaptive_astc/evaluation/unity_dense_native_regression.py",
        "reproductions/unity_search_baseline/v3_policy.py",
    )
    A.write_json(
        output,
        {
            "schema": "unity-v5-pre-execution-confirmation-v1",
            "status": "model_rule_and_source_cohort_frozen_pending_native_capture",
            "confirmation_execution_authorized": False,
            "confirmation_opened": False,
            "model": chosen["checkpoint"],
            "native_v3_parent_sha256": v3["checkpoint_sha256"],
            "model_state_sha256": model_state_sha256,
            "native_policy_model": native_checkpoint,
            "variant": evaluation["selected_for_review"],
            "numeric_gate_status": evaluation["numeric_gate_status"],
            "training_report": chosen["model_report"],
            "source_manifest": {"path": str(manifest), "sha256": reservation["manifest_sha256"]},
            "source_isolation": assets["source_isolation"],
            "screening_rule": rule,
            "screening_candidate": [8, "fastest"],
            "analysis_grid": matrix["tile"],
            "canonical_candidates": matrix["candidate_set"],
            "development_evaluation_sha256": A.sha256_file(evaluation_path),
            "human_calibration_sha256": A.sha256_file(calibration),
            "human_holdout_sha256": A.sha256_file(holdout),
            "human_rating_inputs": rating_inputs,
            "source_sha256": {name: A.sha256_file(ROOT / name) for name in sources},
            "planned_checks": [
                "Supported per-image Unity import properties and ordered source/meta identity",
                "Exact RGBA and aligned same-size duplicate audit against development pixels",
                "Independent human screening precision/recall and exact score of 8x8 fastest",
                "Paired V3 block match and strict quality with the frozen native policy",
            ],
            "requires_new_authorization": [
                "New cohort Unity import or native capture",
                "Independent encoding, inference or rating access",
            ],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--calibration-ratings", type=Path, required=True)
    parser.add_argument("--holdout-ratings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if any(
        not p.resolve().is_relative_to(RAW)
        for p in (
            args.evaluation,
            args.calibration,
            args.holdout,
            args.calibration_ratings,
            args.holdout_ratings,
        )
    ):
        parser.error("Expected the private V5 evaluation and rating results")
    output = args.output.resolve()
    if not output.is_relative_to(PUBLIC):
        parser.error("Write the protocol into the public V5 experiment report directory")
    freeze(
        args.evaluation,
        args.calibration,
        args.holdout,
        args.calibration_ratings,
        args.holdout_ratings,
        output,
    )
    print("V5 model, rating rule and source identities frozen for a future confirmation")


if __name__ == "__main__":
    main()
