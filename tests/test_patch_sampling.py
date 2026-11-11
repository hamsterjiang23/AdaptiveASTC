from pathlib import Path

import numpy as np
import pytest

from adaptive_astc.data.patch_sampling import PatchSampling
from adaptive_astc.training.patch_trainer import PatchTrainConfig


def test_cap_zero_preserves_original_image_balanced_distribution() -> None:
    rows = [{"group": "a"}, {"group": "a"}, {"group": "b"}]
    indexes = np.array([0, 1, 1, 2, 2, 2], dtype=np.int64)
    weights = PatchSampling.weights(rows, indexes)
    np.testing.assert_array_equal(weights, 1.0 / np.bincount(indexes)[indexes])
    np.testing.assert_allclose(np.bincount(indexes, weights=weights), [1, 1, 1])


def test_cap_limits_total_group_mass_without_favoring_patch_rich_images() -> None:
    rows = [{"group": "a"}, {"group": "a"}, {"group": "b"}]
    indexes = np.array([0, 1, 1, 2, 2, 2], dtype=np.int64)
    weights = PatchSampling.weights(rows, indexes, group_image_cap=1)
    np.testing.assert_allclose(np.bincount(indexes, weights=weights), [0.5, 0.5, 1])
    assert weights[indexes < 2].sum() == pytest.approx(weights[indexes == 2].sum())


@pytest.mark.parametrize("indexes", [[-1, 0], [0, 2], [0, 0], []])
def test_malformed_or_missing_patch_coverage_is_rejected(indexes: list[int]) -> None:
    rows = [{"group": "a"}, {"group": "b"}]
    with pytest.raises(ValueError, match="indexes|at least one patch"):
        PatchSampling.weights(rows, np.array(indexes, dtype=np.int64))


def test_invalid_group_and_noninteger_cap_are_rejected() -> None:
    indexes = np.array([0], dtype=np.int64)
    with pytest.raises(ValueError, match="group names"):
        PatchSampling.weights([{"group": ""}], indexes, group_image_cap=1)
    with pytest.raises(ValueError, match="nonnegative integer"):
        PatchSampling.weights([{"group": "a"}], indexes, group_image_cap=True)


@pytest.mark.parametrize("cap", [-1, True])
def test_training_rejects_invalid_cap_before_loading_data(tmp_path: Path, cap: int) -> None:
    config = PatchTrainConfig(tmp_path, tmp_path, tmp_path, group_image_cap=cap)
    with pytest.raises(ValueError, match="nonnegative integer"):
        config.validate()


def test_valid_pixel_sampling_preserves_image_and_group_mass() -> None:
    rows = [{"group": "a"}, {"group": "a"}, {"group": "b"}]
    indexes = np.array([0, 1, 1, 2, 2, 2], dtype=np.int64)
    pixels = np.array([16, 12, 4, 16, 16, 4], dtype=np.int64)
    weights = PatchSampling.weights(rows, indexes, 1, pixels)
    np.testing.assert_allclose(np.bincount(indexes, weights=weights), [0.5, 0.5, 1])
    assert weights[1] / weights[2] == pytest.approx(3)
    assert weights[3] / weights[5] == pytest.approx(4)


def test_equal_size_patches_reproduce_uniform_sampling() -> None:
    rows = [{"group": "a"}, {"group": "b"}]
    indexes = np.array([0, 0, 1, 1, 1], dtype=np.int64)
    pixels = np.array([16, 16, 12, 12, 12], dtype=np.int64)
    np.testing.assert_array_equal(
        PatchSampling.weights(rows, indexes, 0, pixels), PatchSampling.weights(rows, indexes)
    )


@pytest.mark.parametrize("pixels", [[1, 0], [1, -1], [1], [1.5, 2.0]])
def test_invalid_pixel_counts_rejected(pixels: list[float]) -> None:
    with pytest.raises(ValueError, match="positive integer valid-pixel"):
        PatchSampling.weights([{"group": "a"}], np.array([0, 0]), pixel_counts=np.array(pixels))
