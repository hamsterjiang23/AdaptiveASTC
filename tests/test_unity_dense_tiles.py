import numpy as np
import torch

from adaptive_astc.data.unity_dense_tile_dataset import UnityDensePatchGrid
from adaptive_astc.data.unity_tile_errors import UnityTileGrid
from adaptive_astc.data.unity_tile_labels import UnityTileLabels
from adaptive_astc.evaluation.unity_dense_tile_metrics import UnityDenseTileMetrics
from adaptive_astc.training.unity_dense_tile_trainer import UnityDenseTileTrainer


def test_v5_patches_cover_nondivisible_image_on_one_grid() -> None:
    grid = UnityTileGrid(241, 243)
    geometry = UnityDensePatchGrid(grid, 240)
    mask_tiles = np.zeros_like(grid.counts())
    image = np.broadcast_to(np.arange(241, dtype=np.uint8)[:, None, None], (241, 243, 4))
    for y, x in geometry.origins():
        patch, mask = geometry.extract(image, y, x)
        first_real = np.argmax(mask[:, 0])
        assert patch[first_real, 0, 0] == max(0, y * 8 - grid.top_padding)
        extent = mask_tiles[y : y + 30, x : x + 30]
        populated = mask.reshape(30, 8, 30, 8).sum(axis=(1, 3))
        extent[:] = populated[: extent.shape[0], : extent.shape[1]]
        assert extent.sum() == mask.sum()
    np.testing.assert_array_equal(mask_tiles, grid.counts())


def test_v5_label_metrics_preserve_candidate_axis_and_view_denominators() -> None:
    grid = UnityTileGrid(8, 9)
    pixels = grid.counts().astype(np.uint8)
    sse = np.zeros((20, 1, 2, 5), dtype=np.uint32)
    sse[11, 0, 1, 4] = 3 * 8 * 11**2
    labels = UnityTileLabels(
        grid, pixels, np.array([[False, True]]), np.array([[False, False]]), sse
    )
    target = sse / (pixels[..., None] * np.array([1, 1, 1, 1, 3]) * 255**2)
    metrics = UnityDenseTileMetrics()
    metrics.add(np.log10(target + 1e-10).astype(np.float32), labels, 0)
    record = metrics.values[0]["bad"]["display"]["28"]["content"]
    assert np.flatnonzero(record["true"]).tolist() == [11]
    assert record["predicted"] == record["true"]
    assert metrics.bad_share_mae("display", 28, "smooth") is None


def test_v5_padded_tiles_do_not_contribute_training_loss() -> None:
    prediction = torch.zeros((1, 1, 2, 20, 5))
    target = prediction.clone()
    target[:, :, 1] = -10
    assert UnityDenseTileTrainer.loss(prediction, target, torch.tensor([[[64, 0]]])) == 0


def test_v5_loss_cap_censors_high_psnr_without_changing_near_threshold_loss() -> None:
    pixels = torch.tensor([[[64]]])
    prediction = torch.full((1, 1, 1, 20, 5), -6.0)
    zero = torch.full_like(prediction, -10.0)
    near = torch.full_like(prediction, -3.0)
    assert UnityDenseTileTrainer.loss(prediction, zero, pixels, cap_db=45) == 0
    uncapped = UnityDenseTileTrainer.loss(prediction, near, pixels)
    assert torch.equal(UnityDenseTileTrainer.loss(prediction, near, pixels, cap_db=45), uncapped)
