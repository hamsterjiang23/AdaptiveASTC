from pathlib import Path

import numpy as np
import pytest
import torch
from torch import Tensor
from torch.utils.data import WeightedRandomSampler

from adaptive_astc.data.patch_dataset import NativePatchDataset
from adaptive_astc.data.patch_sampling import PatchSampling
from adaptive_astc.training.patch_loss import PatchRegressionLoss
from adaptive_astc.training.patch_trainer import PatchTrainConfig, PatchTrainer


class TinyPatchDataset(NativePatchDataset):
    def __init__(self) -> None:
        self.rows = [{"group": "a"}, {"group": "a"}, {"group": "b"}]
        self.image_ids = np.array([0, 1, 1, 2, 2, 2], dtype=np.int64)
        self.pixel_counts = np.array([12, 16, 8, 16, 16, 4], dtype=np.int64)

    def __len__(self) -> int:
        return len(self.image_ids)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, int]:
        return torch.full((3, 4, 4), float(index)), torch.full((4,), -3.0 - index / 10), index


@pytest.mark.parametrize("cap", [0, 1])
def test_default_loader_preserves_legacy_draw_sequence(tmp_path: Path, cap: int) -> None:
    dataset = TinyPatchDataset()
    config = PatchTrainConfig(
        tmp_path, tmp_path, tmp_path, batch_size=8, workers=0, group_image_cap=cap
    )
    actual = torch.cat(
        [indexes for _, _, indexes in PatchTrainer(config).training_batches(dataset)]
    )
    expected = list(
        WeightedRandomSampler(
            PatchSampling.weights(dataset.rows, dataset.image_ids, cap).tolist(),
            12,
            replacement=True,
            generator=torch.Generator().manual_seed(config.seed),
        )
    )
    assert actual.tolist() == expected


def test_paired_loss_controls_use_identical_bags_and_valid_pixel_mapping(tmp_path: Path) -> None:
    dataset = TinyPatchDataset()
    draws: list[list[int]] = []
    for weight in [0.0, 1.0]:
        config = PatchTrainConfig(
            tmp_path,
            tmp_path,
            tmp_path,
            batch_size=8,
            workers=0,
            bag_size=4,
            aggregate_loss_weight=weight,
        )
        indexes_seen: list[int] = []
        criterion = PatchRegressionLoss(config.bag_size, config.aggregate_loss_weight)
        for images, targets, indexes in PatchTrainer(config).training_batches(dataset):
            np.testing.assert_array_equal(images[:, 0, 0, 0].numpy(), indexes.numpy())
            pixels = torch.from_numpy(dataset.pixel_counts[indexes.numpy()])
            ids = torch.from_numpy(dataset.image_ids[indexes.numpy()])
            prediction = (targets + 0.2).requires_grad_()
            loss, patch, aggregate = criterion(prediction, targets, pixels, ids)
            assert loss.item() == pytest.approx((patch + weight * aggregate).item())
            assert (aggregate.item() > 0) == bool(weight)
            loss.backward()
            assert prediction.grad is not None and torch.isfinite(prediction.grad).all()
            indexes_seen.extend(indexes.tolist())
        assert len(indexes_seen) == 12
        draws.append(indexes_seen)
    assert draws[0] == draws[1]


@pytest.mark.parametrize(
    "bag_size,weight,batch",
    [(0, 0.0, 8), (4, -1.0, 8), (1, 1.0, 8), (4, 1.0, 6), (4, float("nan"), 8)],
)
def test_invalid_bag_training_config_rejected(
    tmp_path: Path, bag_size: int, weight: float, batch: int
) -> None:
    with pytest.raises(ValueError):
        PatchTrainConfig(
            tmp_path,
            tmp_path,
            tmp_path,
            bag_size=bag_size,
            aggregate_loss_weight=weight,
            batch_size=batch,
        ).validate()


def test_sampling_budget_must_contain_complete_bags(tmp_path: Path) -> None:
    config = PatchTrainConfig(
        tmp_path, tmp_path, tmp_path, batch_size=8, bag_size=4, patches_per_image=1, workers=0
    )
    with pytest.raises(ValueError, match="complete bags"):
        PatchTrainer(config).training_batches(TinyPatchDataset())
