from pathlib import Path
from typing import cast

import numpy as np
import pytest
import torch
from torch import Tensor, nn
from torch.optim.swa_utils import AveragedModel

from adaptive_astc.data.patch_dataset import NativePatchDataset
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.models.metadata_patch_regressor import MetadataPatchRegressor
from adaptive_astc.training.patch_trainer import PatchTrainConfig, PatchTrainer


class SizeDataset(NativePatchDataset):
    def __init__(self) -> None:
        self.boxes = np.array([[0, 0, 4, 4], [4, 0, 1, 2], [0, 4, 2, 3]], dtype=np.int64)
        self.image_ids = np.array([1, 0, 1], dtype=np.int64)
        self.rows = [{"width": 8, "height": 8}, {"width": 16, "height": 32}]
        self.patch_size = 4


class MetadataRecorder(MetadataPatchRegressor):
    def __init__(self) -> None:
        nn.Module.__init__(self)
        self.anchor = nn.Parameter(torch.zeros(()))

    def forward(self, inputs: Tensor, metadata: Tensor) -> Tensor:
        return metadata + self.anchor


@pytest.mark.parametrize("ema", [False, True])
def test_raw_and_ema_match_sizes_to_patch_and_image_indices(ema: bool) -> None:
    dataset = SizeDataset()
    model: nn.Module = MetadataRecorder()
    if ema:
        model = AveragedModel(model)
    images = torch.randn(3, 3, 4, 4)
    arguments = PatchTrainer.model_inputs(model, images, torch.tensor([2, 0, 1]), dataset)
    assert arguments[0] is images and arguments[1].dtype == torch.float32
    assert arguments[1].device == images.device
    torch.testing.assert_close(
        model(*arguments),
        torch.tensor(
            [[4 / 12, 5 / 12, 0.5, 0.75], [4 / 12, 5 / 12, 1, 1], [0.25, 0.25, 0.25, 0.5]]
        ),
    )


@pytest.mark.parametrize("value", [1, "true", None])
def test_nonboolean_metadata_config_is_rejected(tmp_path: Path, value: object) -> None:
    with pytest.raises(ValueError, match="metadata must be boolean"):
        PatchTrainConfig(tmp_path, tmp_path, tmp_path, size_metadata=cast(bool, value)).validate()


def test_metadata_and_pooling_require_separate_controls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="separate controls"):
        PatchTrainConfig(
            tmp_path, tmp_path, tmp_path, size_metadata=True, valid_area_pooling=True
        ).validate()
    with pytest.raises(ValueError, match="separate controls"):
        PatchTrainer.build_model("scratch", False, True, True, True)


def test_factory_and_strict_weight_reload_preserve_metadata_predictions() -> None:
    model = PatchTrainer.build_model("scratch", False, True, size_metadata=True).eval()
    assert isinstance(model, MetadataPatchRegressor)
    assert sum(p.numel() for p in model.parameters()) == 11178580
    with torch.no_grad():
        model.metadata_weight.fill_(0.1)
    restored = PatchTrainer.build_model("scratch", False, True, size_metadata=True).eval()
    restored.load_state_dict(model.state_dict(), strict=True)
    pixels, metadata = torch.randn(2, 3, 32, 32), torch.full((2, 4), 0.5)
    with torch.no_grad():
        torch.testing.assert_close(
            model(pixels, metadata), restored(pixels, metadata), rtol=0, atol=0
        )


class MetadataBatchNorm(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.bn = nn.BatchNorm2d(3, momentum=0.2)
        self.seen: list[Tensor] = []

    def forward(self, pixels: Tensor, metadata: Tensor) -> Tensor:
        self.seen.append(metadata.detach().cpu().clone())
        return self.bn(pixels) + metadata[:, :1, None, None]


def test_bn_recalibration_receives_metadata_and_restores_state() -> None:
    model = MetadataBatchNorm().eval()
    metadata = torch.tensor([[0.5, 0.25, 1, 1], [0.75, 0.5, 0.5, 0.25]])
    batches = [(torch.full((2, 3, 4, 4), value), metadata) for value in [2.0, 4.0]]
    count = PatchNormalizationAudit.recalibrate(model, batches, torch.device("cpu"))
    assert count == 4 and len(model.seen) == 2
    assert all(torch.equal(value, metadata) for value in model.seen)
    assert not model.training and not model.bn.training and model.bn.momentum == 0.2
    torch.testing.assert_close(model.bn.running_mean, torch.full((3,), 3.0))
