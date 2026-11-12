"""Check frozen native feature bags and image-only loss consistency."""

from pathlib import Path

import numpy as np
import pytest
import torch
from torch import Tensor, nn

from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_quality_loss import UnityQualityLoss
from script.refit_unity_image_head import NativeFeatureCache, UnityImageHeadRefit
from tests.test_unity_quality_training import paired_dataset


def test_head_loss_weights_inherit_and_can_restore_quality_after_preparation() -> None:
    initial = {"zero_weight": 0.1, "ssim_weight": 0.0, "angle_weight": 0.0}
    assert UnityImageHeadRefit.loss_config({}, initial).ssim_weight == 0.0
    restored = UnityImageHeadRefit.loss_config({"ssim_weight": 0.1, "angle_weight": 0.1}, initial)
    assert restored.zero_weight == restored.ssim_weight == restored.angle_weight == 0.1
    with pytest.raises(ValueError, match="positive supervision"):
        UnityImageHeadRefit.loss_config({"zero_weight": 0.0}, initial)


def feature_cache() -> NativeFeatureCache:
    features = torch.zeros(4, 512)
    features[:, 0] = torch.tensor([1.0, 5.0, 7.0, 9.0])
    return NativeFeatureCache(
        [{}, {}],
        features,
        torch.tensor([1, 3, 2, 2]),
        torch.tensor([[8, 9, 1, 0, 1, 0, 1, 0], [7, 6, 0, 1, 0, 1, 4, 0.5]]).float(),
        [torch.tensor([0, 1]), torch.tensor([2, 3])],
        np.zeros((2, 20, 4)),
        {},
    )


def test_complete_feature_bags_preserve_pixel_weights_and_metadata() -> None:
    cache = feature_cache()
    model = UnityQualityRegressor(image_pooling="mean")
    captured: list[Tensor] = []

    def capture(module: nn.Module, arguments: tuple[Tensor, ...]) -> None:
        captured.append(arguments[0].detach().clone())

    hook = model.image_head.register_forward_pre_hook(capture)
    cache.predict(model, torch.tensor([1, 0]))
    hook.remove()
    torch.testing.assert_close(captured[0][:, 0], torch.tensor([8.0, 4.0]))
    torch.testing.assert_close(captured[0][:, 1:512], torch.zeros(2, 511))
    scale = torch.tensor([12, 12, 1, 1, 1, 1, 4, 1])
    torch.testing.assert_close(captured[0][:, -8:], cache.metadata[[1, 0]] / scale)


def test_sampled_feature_bags_use_their_independent_generator() -> None:
    cache = feature_cache()
    model = UnityQualityRegressor(image_pooling="mean")
    first = cache.predict(model, torch.arange(2), 4, torch.Generator().manual_seed(31))
    torch.manual_seed(999)
    second = cache.predict(model, torch.arange(2), 4, torch.Generator().manual_seed(31))
    for name in first:
        torch.testing.assert_close(first[name], second[name], rtol=0, atol=0)


def test_image_only_loss_matches_native_components_and_updates_only_image_head() -> None:
    model = UnityQualityRegressor(image_pooling="mean")
    model.requires_grad_(False)
    model.image_head.requires_grad_(True)
    outputs = feature_cache().predict(model, torch.arange(2))
    targets = {
        "channel_zero": torch.zeros(2, 20, 4),
        "channel_active": torch.tensor([[True, True, True, False], [True, True, True, True]]),
        "quality_active": torch.tensor([[True, False, False], [False, True, True]]),
        "image_quality": torch.tensor(
            [[[21.0, float("nan"), float("nan")]] * 20, [[float("nan"), 3.2, 9.0]] * 20]
        ),
    }
    weights = {"zero_weight": 0.1, "ssim_weight": 0.1, "angle_weight": 0.1}
    actual = UnityImageHeadRefit.image_losses(outputs, targets, weights)
    patch = torch.zeros(2, 20, 4)
    native = UnityQualityLoss()(
        {**outputs, "channel_log_mse": patch}, patch, torch.arange(2), targets
    )
    for name in actual:
        torch.testing.assert_close(actual[name], native[name])
    actual["total"].backward()
    assert all(
        parameter.grad is None
        for name, parameter in model.named_parameters()
        if not name.startswith("image_head.")
    )
    assert model.image_head.weight.grad is not None
    assert torch.isfinite(model.image_head.weight.grad).all()


class EncodedInputProbe(UnityQualityRegressor):
    def encode(self, rgba: Tensor, valid_mask: Tensor, metadata: Tensor) -> dict[str, Tensor]:
        return {
            "features": rgba[:, :1].mean((2, 3)).repeat(1, self.channel_head.in_features),
            "channel_log_mse": rgba.new_zeros((len(rgba), 20, 4)),
        }


@pytest.mark.parametrize("backbone_name", ["resnet18", "resnet50"])
def test_feature_cache_remaps_a_source_subset_without_other_image_patches(
    tmp_path: Path, backbone_name: str
) -> None:
    dataset = paired_dataset(tmp_path)
    output = tmp_path / "cache"
    output.mkdir()
    model = EncodedInputProbe(image_pooling="mean", backbone_name=backbone_name)
    cache, files = NativeFeatureCache.prepare(
        dataset,
        [1],
        model,
        2,
        torch.device("cpu"),
        output,
        "train",
    )
    assert cache.rows == [dataset.rows[1]]
    assert cache.features.shape == (2, model.channel_head.in_features)
    assert cache.channel_mse.shape == (1, 20, 4)
    torch.testing.assert_close(cache.patch_indexes[0], torch.tensor([0, 1]))
    assert len(files) == 2
    with np.load(output / "train-indexes.npz") as indexes:
        np.testing.assert_array_equal(indexes["source_images"], [1])
        np.testing.assert_array_equal(
            indexes["source_patches"], np.flatnonzero(dataset.image_ids == 1)
        )
        np.testing.assert_array_equal(indexes["image_ids"], [0, 0])
