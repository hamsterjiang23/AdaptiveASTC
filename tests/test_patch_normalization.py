from __future__ import annotations

import numpy as np
import torch
from torch import nn

from adaptive_astc.evaluation.patch_metrics import PatchRegressionMetrics
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit


def test_recalibration_preserves_weights_modes_and_momentum() -> None:
    model = nn.Sequential(nn.BatchNorm2d(3, momentum=0.2), nn.Dropout(p=0.5))
    model.eval()
    weights = {name: value.detach().clone() for name, value in model.named_parameters()}
    data = [torch.full((2, 3, 8, 8), 2.0), torch.full((2, 3, 8, 8), 4.0)]
    count = PatchNormalizationAudit.recalibrate(model, data, torch.device("cpu"))
    assert count == 4
    torch.testing.assert_close(model[0].running_mean, torch.full((3,), 3.0))
    assert model[0].num_batches_tracked == 2
    assert model[0].momentum == 0.2
    assert all(not layer.training for layer in model.modules())
    for name, value in model.named_parameters():
        torch.testing.assert_close(value, weights[name], rtol=0, atol=0)


def test_lossless_validation_can_reproduce_undefined_neighborhood_rmse() -> None:
    row = {
        "full_squared_errors": [0] * 4,
        "pixel_count": 1,
        "class_id": 3,
        "payload_bytes": [16] * 4,
        "group": "fixture",
        "width": 1,
        "height": 1,
    }
    measured, _ = PatchRegressionMetrics.compute(np.zeros((1, 4)), [row])
    assert measured["near_threshold_rmse_db"] is None
    assert PatchNormalizationAudit.baseline_matches(measured, measured)
    assert not PatchNormalizationAudit.baseline_matches(
        measured, {**measured, "near_threshold_rmse_db": 0.0}
    )
