from dataclasses import asdict

import numpy as np
import pytest
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_quality_loss import UnityImageTargets, UnityQualityLoss
from tests.test_unity_search_policy import grid, policy


def measured_row(normal: bool = False, srgb: bool = True, width: int = 240) -> JsonDict:
    candidates = grid()
    candidates[10]["metrics"].update(
        psnr=35.0, ms_ssim_db=24.0, normal_mean_deg=2.0, normal_p95_deg=5.0
    )
    result = policy().select(candidates, width=width, height=240, srgb=srgb, normal=normal)
    return {
        "path": "Assets/A.png",
        "width": width,
        "height": 240,
        "metadata": {"is_hdr": False, "is_normal": normal, "need_alpha": True},
        "import_metadata": {"srgb": srgb},
        "alpha_constant": True,
        "black_pixel_ratio": 0.0,
        "candidate_grid": [list(x) for x in UnityQualityPrediction.GRID],
        "image_quality": [x["metrics"] for x in candidates],
        "original_selection": asdict(result),
        "payload_bytes": [
            16 * ((width + b - 1) // b) * ((240 + b - 1) // b)
            for b, _ in UnityQualityPrediction.GRID
        ],
        "full_channel_squared_errors": np.ones((20, 4), dtype=np.int64).tolist(),
    }


def predictions(row: JsonDict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mse = np.repeat(
        10.0 ** (-np.array([q["psnr"] for q in row["image_quality"]])[:, None] / 10), 4, axis=1
    )
    quality = np.array(
        [[q[n] for n in UnityQualityPrediction.QUALITY_NAMES] for q in row["image_quality"]]
    )
    return mse, np.zeros((20, 4), dtype=bool), quality


@pytest.mark.parametrize(
    "normal,srgb,width",
    [(False, True, 240), (False, True, 1024), (True, False, 240), (False, False, 240)],
)
def test_exact_quality_replays_native_choice_and_accounts_payload(
    normal: bool, srgb: bool, width: int
) -> None:
    row = measured_row(normal, srgb, width)
    mse, zero, quality = predictions(row)
    result, rows = UnityQualityPrediction.score(
        [row], [policy()], mse[None], zero[None], quality[None]
    )
    assert result["accuracy"] == result["full_choice_accuracy"] == 1
    assert result["selected_payload_bytes"] == result["original_payload_bytes"]
    assert result["actual_quality_pass_rate"] == 1 and len(rows) == 1


def test_prediction_inputs_do_not_consume_measured_labels_or_quality() -> None:
    row = measured_row()
    original = UnityTextureInput.from_row(row)
    row["original_selection"] = None
    row["image_quality"] = "poison"
    row["full_channel_squared_errors"] = None
    assert UnityTextureInput.from_row(row) == original


def test_zero_channel_dilution_can_pass_predicted_quality_but_fail_actual_quality() -> None:
    row = measured_row()
    row["image_quality"][0].update(psnr=29.0, ms_ssim_db=24.0)
    mse, _, quality = predictions(row)
    mse[:, 1:] = 0
    zero = mse == 0
    actual = UnityQualityPrediction.select(
        policy(), UnityTextureInput.from_row(row), mse, zero, quality
    )
    assert actual.selected_index == 10
    floor = np.maximum(mse, 1e-9)
    summary, decisions = UnityQualityPrediction.score(
        [row], [policy()], floor[None], np.zeros_like(zero)[None], quality[None]
    )
    assert summary["accuracy"] == 0 and summary["actual_quality_pass_rate"] == 0
    assert decisions[0]["predicted_decision"]["strict_quality_met"] is True


def test_psnr_mask_excludes_constant_alpha_and_zero_channels_after_aggregation() -> None:
    texture = UnityTextureInput.from_row(measured_row())
    mse = np.zeros((20, 4))
    mse[:, 0] = 0.001
    mse[:, 3] = 1
    zero = mse == 0
    np.testing.assert_allclose(UnityQualityPrediction.psnr(mse, zero, texture), 30)
    mse[:, 0] = 0
    zero = mse == 0
    np.testing.assert_array_equal(UnityQualityPrediction.psnr(mse, zero, texture), 100)


def test_patch_mse_aggregation_is_pixel_weighted_and_precedes_psnr() -> None:
    mse = np.stack([np.full((20, 4), 0.001), np.full((20, 4), 0.01)])
    aggregate = UnityQualityPrediction.aggregate_mse(
        np.log10(mse + 1e-10), np.array([3, 1]), np.array([0, 0]), 1
    )
    np.testing.assert_allclose(aggregate, 0.00325)
    with pytest.raises(ValueError, match="coverage"):
        UnityQualityPrediction.aggregate_mse(
            np.log10(mse + 1e-10), np.array([3, 1]), np.array([0, 0]), 2
        )


def test_aggregate_preserves_exact_zero_and_maximum_byte_error() -> None:
    mse = np.ones((1, 20, 4), dtype=np.float64)
    mse[:, :, :2] = 0
    actual = UnityQualityPrediction.aggregate_mse(
        np.log10(mse + 1e-10), np.array([57600]), np.array([0]), 1
    )
    np.testing.assert_array_equal(actual, mse)


def test_score_rejects_mismatched_original_policy_or_payload() -> None:
    for field in ["original_selection", "payload_bytes"]:
        row = measured_row()
        mse, zero, quality = predictions(row)
        if field == "original_selection":
            row[field]["preset"] = "exhaustive"
        else:
            row[field][0] += 16
        with pytest.raises(ValueError):
            UnityQualityPrediction.score([row], [policy()], mse[None], zero[None], quality[None])


def test_targets_mask_irrelevant_quality_but_require_applicable_metrics() -> None:
    row = measured_row()
    row["image_quality"] = [
        {**q, "normal_mean_deg": None, "normal_p95_deg": None} for q in row["image_quality"]
    ]
    targets = UnityImageTargets.build([row])
    assert not targets["quality_active"][0, 1:].any()
    assert torch.isnan(targets["image_quality"][0, :, 1:]).all()
    row["metadata"]["is_normal"] = True
    with pytest.raises(ValueError, match="missing"):
        UnityImageTargets.build([row])


def test_native_loss_has_finite_gradients_and_does_not_use_inactive_alpha() -> None:
    rows = [measured_row(), measured_row(True, False)]
    targets = UnityImageTargets.build(rows)
    outputs = {
        "channel_log_mse": torch.full((4, 20, 4), -3.0, requires_grad=True),
        "channel_zero_logits": torch.zeros((2, 20, 4), requires_grad=True),
        "image_quality": torch.full((2, 20, 3), 4.0, requires_grad=True),
    }
    loss = UnityQualityLoss()(
        outputs, torch.full((4, 20, 4), -3.5), torch.tensor([0, 0, 1, 1]), targets
    )
    loss["total"].backward()
    for value in outputs.values():
        assert value.grad is not None and torch.isfinite(value.grad).all()
    assert outputs["channel_log_mse"].grad is not None
    assert torch.count_nonzero(outputs["channel_log_mse"].grad[:, :, 3]) == 0
    assert all(loss[name] > 0 for name in ["patch", "zero", "ssim", "angle"])


def test_feature_pool_is_weighted_per_image_and_permutation_invariant() -> None:
    features = torch.stack([torch.ones(512), torch.full((512,), 3.0), torch.full((512,), 7.0)])
    pixels = torch.tensor([3, 1, 2])
    ids = torch.tensor([0, 0, 1])
    pooled = UnityQualityRegressor.pool_features(features, pixels, ids, 2)
    torch.testing.assert_close(pooled[0, :512], torch.full((512,), 1.5))
    torch.testing.assert_close(pooled[0, 512:], torch.full((512,), 3.0))
    order = torch.tensor([2, 0, 1])
    torch.testing.assert_close(
        pooled, UnityQualityRegressor.pool_features(features[order], pixels[order], ids[order], 2)
    )


def test_feature_pool_gradients_match_weighted_mean_and_maximum() -> None:
    features = torch.randn(7, 512, requires_grad=True)
    pixels = torch.tensor([3, 5, 7, 2, 8, 9, 4])
    ids = torch.tensor([1, 0, 1, 0, 1, 0, 1])
    pooled = UnityQualityRegressor.pool_features(features, pixels, ids, 2)
    reference = torch.stack(
        [
            torch.cat(
                (
                    (features[ids == image] * pixels[ids == image, None]).sum(0)
                    / pixels[ids == image].sum(),
                    features[ids == image].amax(0),
                )
            )
            for image in range(2)
        ]
    )
    actual_grad = torch.autograd.grad(pooled.square().sum(), features, retain_graph=True)[0]
    expected_grad = torch.autograd.grad(reference.square().sum(), features)[0]
    torch.testing.assert_close(pooled, reference)
    torch.testing.assert_close(actual_grad, expected_grad)


def test_feature_pool_tied_maxima_share_negative_upstream_gradient() -> None:
    features = torch.ones((3, 512), requires_grad=True)
    pixels = torch.ones(3)
    ids = torch.zeros(3, dtype=torch.int64)
    pooled = UnityQualityRegressor.pool_features(features, pixels, ids, 1)
    gradient = torch.autograd.grad(-pooled[:, 512:].sum(), features)[0]
    torch.testing.assert_close(gradient, torch.full_like(features, -1 / 3))


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA pool replay regression")
def test_cuda_feature_pool_repeated_outputs_are_bit_identical() -> None:
    features = torch.randn(4096, 512, device="cuda")
    pixels = torch.randint(1, 57601, (4096,), device="cuda")
    ids = torch.arange(4096, device="cuda") % 128
    expected = UnityQualityRegressor.pool_features(features, pixels, ids, 128)
    for _ in range(3):
        actual = UnityQualityRegressor.pool_features(features, pixels, ids, 128)
        assert torch.equal(actual, expected)


def test_native_model_input_contract_and_trainable_parameter_accounting() -> None:
    torch.set_num_threads(2)
    model = UnityQualityRegressor().eval()
    with torch.inference_mode():
        result = model(
            torch.rand((2, 4, 240, 240)),
            torch.ones((2, 1, 240, 240), dtype=torch.bool),
            torch.tensor([0, 0]),
            torch.tensor([[8.0, 8.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]]),
        )
    assert result["channel_log_mse"].shape == (2, 20, 4)
    assert result["channel_zero_logits"].shape == (1, 20, 4)
    assert result["image_quality"].shape == (1, 20, 3)
    assert all(torch.isfinite(value).all() for value in result.values())
    assert sum(p.numel() for p in model.parameters()) == 11377660
    assert model.backbone[0].in_channels == 5


def test_import_metadata_can_condition_patch_error_predictions() -> None:
    torch.set_num_threads(2)
    model = UnityQualityRegressor().eval()
    with torch.no_grad():
        model.metadata_conditioner.weight[512:, 2] = 1
        model.channel_head.weight.fill_(0.01)
    metadata = torch.tensor(
        [[8.0, 8.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0], [8.0, 8.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]]
    )
    with torch.inference_mode():
        result = model(
            torch.zeros((2, 4, 240, 240)),
            torch.ones((2, 1, 240, 240), dtype=torch.bool),
            torch.tensor([0, 1]),
            metadata,
        )
    torch.testing.assert_close(
        result["channel_log_mse"][1] - result["channel_log_mse"][0],
        torch.full((20, 4), 5.12),
        atol=1e-5,
        rtol=0,
    )


@pytest.mark.parametrize("damage", ["nan", "wrong_grid", "missing_quality"])
def test_prediction_boundary_rejects_invalid_inputs(damage: str) -> None:
    row = measured_row()
    mse, zero, quality = predictions(row)
    if damage == "nan":
        mse[0, 0] = float("nan")
    elif damage == "wrong_grid":
        row["candidate_grid"] = list(reversed(row["candidate_grid"]))
    else:
        quality[0, 0] = float("nan")
    with pytest.raises(ValueError):
        UnityQualityPrediction.score([row], [policy()], mse[None], zero[None], quality[None])
