"""Score held-out bad-share estimates and validate human rating decisions."""

from __future__ import annotations

import csv
import io

import numpy as np
from sklearn.isotonic import IsotonicRegression

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_dense_screening import UnityDenseScreening
from adaptive_astc.evaluation.unity_dense_tile_metrics import UnityDenseTileMetrics


class UnityDenseReviewScoring:
    @staticmethod
    def share(row: JsonDict, rule: JsonDict, candidate: int, kind: str) -> float | None:
        region = rule["region"]
        total = row["regions"][region]
        if total == 0:
            return None
        return float(row["bad"][rule["view"]][str(rule["y_db"])][region][kind][candidate] / total)

    @classmethod
    def step_baseline(
        cls, dense: list[JsonDict], step: list[JsonDict], partition: JsonDict, candidate: int
    ) -> JsonDict:
        scope = {
            name: {item["index"] for item in partition["strata"][name]}
            for name in ("calibration", "holdout")
        }
        scores = {
            row["index"]: row["l_p95_primary"] for row in step if row["l_p95_primary"] is not None
        }
        by_threshold = {}
        for y in UnityDenseTileMetrics.THRESHOLDS:
            for region in UnityDenseTileMetrics.REGIONS:
                rule = {"view": "display", "y_db": y, "region": region}
                values: dict[str, list[tuple[float, float, float]]] = {key: [] for key in scope}
                for row in dense:
                    idx = row["index"]
                    truth = cls.share(row, rule, candidate, "true")
                    predicted = cls.share(row, rule, candidate, "predicted")
                    if idx not in scores or truth is None or predicted is None:
                        continue
                    for stratum, ids in scope.items():
                        if idx in ids:
                            values[stratum].append((scores[idx], truth, predicted))
                training = np.asarray(values["calibration"], dtype=float)
                held_out = np.asarray(values["holdout"], dtype=float)
                key = f"display@{y}:{region}"
                if len(training) < 2 or len(held_out) < 2:
                    by_threshold[key] = None
                    continue
                baseline = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
                baseline.fit(training[:, 0], training[:, 1])
                before = baseline.predict(held_out[:, 0])
                by_threshold[key] = {
                    "calibration_images": len(training),
                    "holdout_images": len(held_out),
                    "holdout_step_mae": float(np.abs(before - held_out[:, 1]).mean()),
                    "holdout_dense_mae": float(np.abs(held_out[:, 2] - held_out[:, 1]).mean()),
                    "step_x_knots": baseline.X_thresholds_.tolist(),
                    "step_y_knots": baseline.y_thresholds_.tolist(),
                }
        content = [by_threshold[f"display@{y}:content"] for y in UnityDenseTileMetrics.THRESHOLDS]
        better = (
            None
            if any(row is None for row in content)
            else (
                sum(row["holdout_dense_mae"] for row in content)
                < sum(row["holdout_step_mae"] for row in content)
            )
        )
        return {
            "scope": "Paired held-out development images with L_p95_primary and a valid region",
            "primary_gate": "Mean content share MAE at 28/30 dB",
            "dense_beats_step_on_primary_gate": better,
            "partitions": by_threshold,
        }

    @staticmethod
    def read_ratings(content: bytes, packet: JsonDict) -> dict[int, str]:
        expected = {row["index"] for row in packet["rows"]}
        ratings = {}
        with io.StringIO(content.decode("utf-8-sig"), newline="") as stream:
            for row in csv.DictReader(stream):
                index = int(row["id"])
                rating = row["visible_gradient_banding"].casefold().strip()
                if (
                    index not in expected
                    or index in ratings
                    or rating not in {"yes", "no", "uncertain"}
                ):
                    raise ValueError("Fill all expected rating rows with yes, no or uncertain")
                ratings[index] = rating
        if set(ratings) != expected:
            raise ValueError("Rating CSV does not cover exactly the nominated review images")
        return ratings

    @staticmethod
    def quality(positive: set[int], labels: dict[int, str], covered: set[int]) -> JsonDict:
        resolved = {i for i, value in labels.items() if value != "uncertain"}
        eligible = resolved & covered
        yes = {i for i in eligible if labels[i] == "yes"}
        no = eligible - yes
        tp, fp = len(positive & yes), len(positive & no)
        return {
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": len(no) - fp,
            "false_negative": len(yes) - tp,
            "resolved": len(resolved),
            "covered_resolved": len(eligible),
            "not_rated_definitively": len(labels) - len(resolved),
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / len(yes) if yes else None,
            "specificity": (len(no) - fp) / len(no) if no else None,
        }

    @classmethod
    def apply_rule(
        cls,
        dense: list[JsonDict],
        labels: dict[int, str],
        rule: JsonDict,
        candidate: int,
    ) -> JsonDict:
        true, predicted, covered = set(), set(), set()
        for row in dense:
            idx = row["index"]
            if idx not in labels:
                continue
            exact = cls.share(row, rule, candidate, "true")
            model = cls.share(row, rule, candidate, "predicted")
            if exact is None or model is None:
                continue
            covered.add(idx)
            if exact >= rule["x_share"]:
                true.add(idx)
            if model >= rule["x_share"]:
                predicted.add(idx)
        return {
            "dense": cls.quality(predicted, labels, covered),
            "exact_tiles": cls.quality(true, labels, covered),
        }

    @classmethod
    def select_rule(cls, dense: list[JsonDict], labels: dict[int, str], candidate: int) -> JsonDict:
        candidates = []
        for view in ("display", "native_rgb", "native_rgba"):
            for region in UnityDenseTileMetrics.REGIONS:
                for y in UnityDenseTileMetrics.THRESHOLDS:
                    for x in UnityDenseScreening.BUDGETS:
                        rule = {"view": view, "region": region, "y_db": y, "x_share": x}
                        result = cls.apply_rule(dense, labels, rule, candidate)
                        exact = result["exact_tiles"]
                        # Missed regions count as abstentions in the diagnostic, and as
                        # failures of the rule in the coverage-adjusted selection score.
                        coverage = exact["covered_resolved"] / max(1, exact["resolved"])
                        recall, specificity = exact["recall"], exact["specificity"]
                        accuracy = (
                            (recall + specificity) / 2 * coverage
                            if recall is not None and specificity is not None
                            else None
                        )
                        candidates.append(
                            {"rule": rule, "result": result, "selection_score": accuracy}
                        )
        valid = [row for row in candidates if row["selection_score"] is not None]
        if not valid:
            raise ValueError("Calibration requires resolved visible and clean ratings")
        best = max(valid, key=lambda row: row["selection_score"])
        return {
            "frozen_rule": best["rule"],
            "result": best["result"],
            "sweep": candidates,
            "selection_metric": "Coverage-adjusted exact balanced accuracy",
        }

    @classmethod
    def queue_quality(cls, packet: JsonDict, labels: dict[int, str]) -> JsonDict:
        return {
            "scope": "Recall over resolved positives in the annotated queue union",
            "methods": {
                method: cls.quality(set(ids), labels, set(labels))
                for method, ids in packet["nominated_indices"].items()
            },
        }
