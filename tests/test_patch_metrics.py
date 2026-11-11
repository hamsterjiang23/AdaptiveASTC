from __future__ import annotations

import json

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.patch_metrics import PatchRegressionMetrics
from adaptive_astc.training.patch_trainer import PatchTrainer


def metric_row(sse: int, pixels: int) -> JsonDict:
    return {
        "full_squared_errors": [sse] * 4,
        "pixel_count": pixels,
        "class_id": 3,
        "payload_bytes": [16] * 4,
        "group": "fixture",
        "width": pixels,
        "height": 1,
    }


def test_small_finite_errors_have_exact_consistent_psnr() -> None:
    mse = np.full((1, 4), 1 / (10_000_000 * 3 * 255**2))
    metrics, psnr = PatchRegressionMetrics.compute(mse, [metric_row(1, 10_000_000)])
    assert float(psnr.min()) > 100
    assert metrics["finite_candidate_rmse_db"] == 0
    assert metrics["near_threshold_rmse_db"] is None
    assert np.isinf(PatchTrainer.rmse_key(metrics))
    json.dumps(metrics, allow_nan=False)


def test_lossless_candidates_do_not_become_perfect_near_threshold_rmse() -> None:
    metrics, psnr = PatchRegressionMetrics.compute(np.zeros((1, 4)), [metric_row(0, 1)])
    assert np.isinf(psnr).all()
    assert metrics["near_threshold_candidate_count"] == 0
    assert metrics["near_threshold_evaluable"] is False
    assert metrics["near_threshold_rmse_db"] is None
    assert metrics["finite_candidate_rmse_db"] is None
    assert metrics["accuracy"] == 1
    json.dumps(metrics, allow_nan=False)


def test_incorrect_zero_error_predictions_are_penalized_and_counted() -> None:
    row = metric_row(62, 1)
    metrics, _ = PatchRegressionMetrics.compute(np.zeros((1, 4)), [row])
    assert metrics["near_threshold_evaluable"] is True
    assert metrics["near_threshold_rmse_db"] > 200
    assert metrics["zero_predicted_mse_candidates"] == 4
    assert metrics["zero_mse_diagnostic_psnr_db"] == 300
