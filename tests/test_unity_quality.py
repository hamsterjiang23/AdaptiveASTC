from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
import torch
from torchvision.models.resnet import BasicBlock, ResNet

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_quality_loss import UnityImageTargets, UnityQualityLoss
from tests.test_unity_search_policy import grid, policy


@pytest.mark.parametrize("pooling,parameters", [("mean", 21414140), ("mean_max", 21485820)])
def test_resnet34_pairs_heads_rng_and_restores_checkpoint(pooling: str, parameters: int) -> None:
    torch.manual_seed(19)
    reference = UnityQualityRegressor(image_pooling=pooling)
    rng = torch.get_rng_state().clone()
    torch.manual_seed(19)
    model = UnityQualityRegressor(image_pooling=pooling, backbone_name="resnet34").eval()
    assert torch.equal(torch.get_rng_state(), rng)
    assert sum(p.numel() for p in model.parameters()) == parameters
    assert all(
        torch.equal(value, model.state_dict()[name])
        for name, value in reference.state_dict().items()
        if not name.startswith("backbone.")
    )
    checkpoint = {
        "config": {"image_pooling": pooling, "backbone_name": "resnet34"},
        "model": model.state_dict(),
    }
    restored = UnityQualityRegressor.from_checkpoint(checkpoint, torch.device("cpu")).eval()
    assert all(
        torch.equal(value, restored.state_dict()[name])
        for name, value in model.state_dict().items()
    )
    with torch.inference_mode():
        inputs = (
            torch.zeros(1, 4, 32, 32),
            torch.ones(1, 1, 32, 32, dtype=torch.bool),
            torch.zeros(1, dtype=torch.int64),
            torch.zeros(1, 8),
        )
        actual, expected = restored(*inputs), model(*inputs)
    assert actual["image_quality"].shape == (1, 20, 3)
    for name, values in actual.items():
        torch.testing.assert_close(values, expected[name], rtol=0, atol=0)
        assert torch.isfinite(values).all()


def test_invalid_native_backbone_rejected() -> None:
    with pytest.raises(ValueError, match="Native backbone"):
        UnityQualityRegressor(backbone_name="unknown")


def test_resnet34_pretrained_state_uses_matching_rgb_encoder() -> None:
    weights = ResNet(BasicBlock, [3, 4, 6, 3]).state_dict()
    rgb = weights["conv1.weight"].clone()
    model = UnityQualityRegressor(
        image_pooling="mean", backbone_name="resnet34", backbone_weights=weights
    )
    assert isinstance(model.backbone, torch.nn.Sequential)
    stem = model.backbone[0]
    assert isinstance(stem, torch.nn.Conv2d)
    torch.testing.assert_close(stem.weight[:, :3], rgb, rtol=0, atol=0)
    assert torch.count_nonzero(stem.weight[:, 3:]) == 0
    with pytest.raises(RuntimeError):
        UnityQualityRegressor(backbone_name="resnet18", backbone_weights=weights)


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


def test_mean_only_pool_uses_pixel_weighted_features_and_gradients() -> None:
    features = torch.stack([torch.ones(512), torch.full((512,), 3.0), torch.full((512,), 7.0)])
    features.requires_grad_()
    pixels = torch.tensor([3, 1, 2])
    ids = torch.tensor([0, 0, 1])
    pooled = UnityQualityRegressor.pool_features(features, pixels, ids, 2, image_pooling="mean")
    assert pooled.shape == (2, 512)
    torch.testing.assert_close(pooled[0], torch.full((512,), 1.5))
    torch.testing.assert_close(pooled[1], torch.full((512,), 7.0))
    gradient = torch.autograd.grad(pooled.sum(), features)[0]
    torch.testing.assert_close(gradient[:, 0], torch.tensor([0.75, 0.25, 1.0]))


def test_mean_only_initialization_preserves_paired_weights_and_rng() -> None:
    torch.manual_seed(123)
    baseline = UnityQualityRegressor()
    next_baseline = torch.rand(3)
    torch.manual_seed(123)
    mean = UnityQualityRegressor(image_pooling="mean")
    next_mean = torch.rand(3)
    for name, value in baseline.state_dict().items():
        if name != "image_head.weight":
            assert torch.equal(value, mean.state_dict()[name])
    expected = torch.cat(
        (baseline.image_head.weight[:, :512], baseline.image_head.weight[:, -8:]), dim=1
    )
    assert torch.equal(mean.image_head.weight, expected)
    assert torch.equal(next_mean, next_baseline)
    assert sum(parameter.numel() for parameter in mean.parameters()) == 11305980


@pytest.mark.parametrize("pooling", ["mean_max", "mean"])
def test_checkpoint_factory_restores_pooling_and_legacy_default(pooling: str) -> None:
    original = UnityQualityRegressor(image_pooling=pooling)
    settings = {} if pooling == "mean_max" else {"image_pooling": pooling}
    restored = UnityQualityRegressor.from_checkpoint(
        {"config": settings, "model": original.state_dict()}, torch.device("cpu")
    )
    assert restored.image_pooling == pooling
    assert restored.image_head.in_features == original.image_head.in_features
    for name, value in original.state_dict().items():
        assert torch.equal(value, restored.state_dict()[name])


def test_backbone_transfer_zeroes_added_channels_and_preserves_paired_heads() -> None:
    source = ResNet(BasicBlock, [2, 2, 2, 2]).state_dict()
    source["conv1.weight"].fill_(0.125)
    source["bn1.running_mean"].fill_(2.0)
    torch.manual_seed(20261112)
    scratch = UnityQualityRegressor(image_pooling="mean")
    next_scratch = torch.rand(3)
    torch.manual_seed(20261112)
    transferred = UnityQualityRegressor(image_pooling="mean", backbone_weights=source)
    next_transferred = torch.rand(3)
    transferred_state = transferred.backbone.state_dict()
    assert torch.equal(transferred_state["0.weight"][:, :3], source["conv1.weight"])
    assert torch.count_nonzero(transferred_state["0.weight"][:, 3:]) == 0
    assert torch.equal(transferred_state["1.running_mean"], source["bn1.running_mean"])
    assert torch.equal(transferred_state["4.0.conv1.weight"], source["layer1.0.conv1.weight"])
    for name, value in scratch.state_dict().items():
        if not name.startswith("backbone."):
            assert torch.equal(value, transferred.state_dict()[name])
    assert torch.equal(next_scratch, next_transferred)


def test_pretrained_checkpoint_restore_is_self_contained(tmp_path: Path) -> None:
    model = UnityQualityRegressor(image_pooling="mean")
    restored = UnityQualityRegressor.from_checkpoint(
        {
            "config": {
                "image_pooling": "mean",
                "initialization": "pretrained",
                "pretrained_weights": str(tmp_path / "unavailable-initialization-weights.pth"),
            },
            "model": model.state_dict(),
        },
        torch.device("cpu"),
    )
    for name, value in model.state_dict().items():
        assert torch.equal(value, restored.state_dict()[name])


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
