from pathlib import Path
from typing import cast

import numpy as np
import pytest
import torch
from torch import Tensor, nn
from torch.optim.swa_utils import AveragedModel

from adaptive_astc.data.patch_dataset import NativePatchDataset
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.models.masked_patch_regressor import MaskedPatchRegressor
from adaptive_astc.models.patch_regressor import ASTCPatchRegressor
from adaptive_astc.training.patch_trainer import PatchTrainConfig, PatchTrainer


class GeometryDataset(NativePatchDataset):
    def __init__(self) -> None:
        self.boxes = np.array([[0, 0, 4, 4], [4, 0, 1, 2], [0, 4, 2, 3]], dtype=np.int64)
        self.patch_size = 4


class MaskRecorder(MaskedPatchRegressor):
    def __init__(self) -> None:
        nn.Module.__init__(self)
        self.anchor = nn.Parameter(torch.zeros(()))

    def forward(self, inputs: Tensor, valid_mask: Tensor) -> Tensor:
        return valid_mask.sum((1, 2, 3)).float() + self.anchor


@pytest.mark.parametrize("ema", [False, True])
def test_raw_and_ema_use_index_matched_input_geometry(ema: bool) -> None:
    dataset = GeometryDataset()
    model: nn.Module = MaskRecorder()
    if ema:
        model = AveragedModel(model)
    images = torch.randn(3, 3, 4, 4)
    arguments = PatchTrainer.model_inputs(model, images, torch.tensor([2, 0, 1]), dataset)
    assert arguments[0] is images and arguments[1].dtype == torch.bool
    torch.testing.assert_close(model(*arguments), torch.tensor([6.0, 16.0, 2.0]))


def test_legacy_forward_does_not_require_geometry_or_change_inputs() -> None:
    dataset = NativePatchDataset.__new__(NativePatchDataset)
    images = torch.randn(2, 3, 4, 4)
    arguments = PatchTrainer.model_inputs(nn.Identity(), images, torch.tensor([0, 1]), dataset)
    assert len(arguments) == 1 and arguments[0] is images


@pytest.mark.parametrize("enabled", [False, True])
def test_factory_selects_model_without_changing_capacity(enabled: bool) -> None:
    model = PatchTrainer.build_model("scratch", False, True, enabled)
    assert type(model) is (MaskedPatchRegressor if enabled else ASTCPatchRegressor)
    assert sum(parameter.numel() for parameter in model.parameters()) == 11178564


@pytest.mark.parametrize("value", [1, "true", None])
def test_nonboolean_pooling_config_is_rejected(tmp_path: Path, value: object) -> None:
    with pytest.raises(ValueError, match="pooling must be boolean"):
        PatchTrainConfig(
            tmp_path, tmp_path, tmp_path, valid_area_pooling=cast(bool, value)
        ).validate()


class MaskedBatchNorm(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.bn = nn.BatchNorm2d(3, momentum=0.2)
        self.mask_pixel_counts: list[int] = []

    def forward(self, pixels: Tensor, mask: Tensor) -> Tensor:
        assert mask.dtype == torch.bool
        self.mask_pixel_counts.append(int(mask.sum()))
        return self.bn(pixels) * mask


def test_bn_recalibration_preserves_masks_and_restores_modes() -> None:
    model = MaskedBatchNorm().eval()
    mask = torch.zeros(2, 1, 4, 4, dtype=torch.bool)
    mask[:, :, :2] = True
    batches = [(torch.full((2, 3, 4, 4), value), mask) for value in [2.0, 4.0]]
    count = PatchNormalizationAudit.recalibrate(model, batches, torch.device("cpu"))
    assert count == 4 and model.mask_pixel_counts == [16, 16]
    assert not model.training and not model.bn.training and model.bn.momentum == 0.2
    torch.testing.assert_close(model.bn.running_mean, torch.full((3,), 3.0))
