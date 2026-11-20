"""Score the completed independent blind ratings without changing the frozen V5 rule."""

import argparse
import hashlib
import json
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_dense_review_scoring import UnityDenseReviewScoring
from adaptive_astc.utils.artifacts import ArtifactStore as A
from script.evaluate_unity_v5_confirmation import OUTPUT, REPORT, RULE
from script.prepare_unity_v5_confirmation_capture import PUBLIC, checked, record


def summarize(rows: list[JsonDict], human: dict[int, str]) -> JsonDict:
    labels = {row["index"]: human[row["index"]] for row in rows}
    covered = {row["index"] for row in rows if row["content_tiles"] > 0}
    predicted = {row["index"] for row in rows if row["predicted_flag"] is True}
    exact = {row["index"] for row in rows if row["exact_flag"] is True}
    return {
        "images": len(rows),
        "coverage": len(covered),
        "threshold_metrics_on_covered_images": {
            "v5": UnityDenseReviewScoring.quality(predicted, labels, covered),
            "exact_tiles": UnityDenseReviewScoring.quality(exact, labels, covered),
        },
        "threshold_metrics_with_abstentions_unflagged": {
            "v5": UnityDenseReviewScoring.quality(predicted, labels, set(labels)),
            "exact_tiles": UnityDenseReviewScoring.quality(exact, labels, set(labels)),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-sha256", required=True)
    parser.add_argument("--ratings", type=Path, default=OUTPUT / "confirmation-ratings-web.csv")
    args = parser.parse_args()
    output = PUBLIC / "confirmation-human-v1.json"
    snapshot = OUTPUT / "confirmation-ratings-frozen-v1.csv"
    if output.exists() or snapshot.exists():
        raise FileExistsError("Preserve the earlier formal rating identity")
    raw = REPORT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.evaluation_sha256:
        raise ValueError("The formal evaluation digest changed")
    evaluation = json.loads(raw)
    if (
        evaluation["status"] != "machine_evaluation_complete_awaiting_independent_human_ratings"
        or evaluation["test_opened"] is not True
        or evaluation["screening_rule"] != RULE
        or evaluation["images"] != 1000
    ):
        raise ValueError("Expected the frozen, completed 1,000-image machine evaluation")
    packet = checked(evaluation["blind_review_packet"])
    stratum = A.read_json(packet)["strata"]["confirmation"]
    rows = A.read_json(checked(evaluation["measurements"]))["rows"]
    if [row["index"] for row in rows] != list(range(1000)) or [
        row["index"] for row in stratum["rows"]
    ] != list(range(1000)):
        raise ValueError("Formal ratings and predictions must share the entire cohort order")
    ratings_bytes = args.ratings.read_bytes()
    ratings = UnityDenseReviewScoring.read_ratings(ratings_bytes, stratum)
    for row in stratum["rows"]:
        for name, digest in row["display_sha256"].items():
            checked({"path": str(packet.parent / "confirmation/pairs" / name), "sha256": digest})
    result = {
        "status": "completed_independent_human_evaluation",
        "screening_rule": RULE,
        "all_inputs": summarize(rows, ratings),
        "srgb_color_inputs": summarize([row for row in rows if row["srgb_color"]], ratings),
        "human_ratings": len(ratings),
        "formal_evaluation": {"path": str(REPORT), "sha256": args.evaluation_sha256},
        "blind_review_packet": record(packet),
        "test_opened": True,
    }
    with snapshot.open("xb") as stream:
        stream.write(ratings_bytes)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(
            {**result, "ratings_snapshot": record(snapshot)}, stream, indent=2, allow_nan=False
        )
        stream.write("\n")
    print(f"V5 independent human results: {output}")


if __name__ == "__main__":
    main()
