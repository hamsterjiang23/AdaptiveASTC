"""Dense V5 log-MSE prediction from the native V3 ResNet-34 encoder."""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from adaptive_astc.models.unity_quality import UnityQualityRegressor


class UnityDenseTileRegressor(nn.Module):
    """Emit candidate-major RGBA and display-RGB errors on the fixed stride-eight grid."""

    CANDIDATES = 20
    CHANNELS = 5

    def __init__(self, native: UnityQualityRegressor, *, frozen: bool = True) -> None:
        super().__init__()
        stage1, stage2 = native.backbone[4], native.backbone[5]
        if not (
            isinstance(stage1, nn.Sequential)
            and isinstance(stage2, nn.Sequential)
            and len(stage1) == 3
            and len(stage2) == 4
            and native.channel_head.in_features == 512
        ):
            raise ValueError("V5 requires the native V3 ResNet-34 backbone")
        self.native = native
        self.tile_head = nn.Conv2d(128 + 512, self.CANDIDATES * self.CHANNELS, kernel_size=1)
        nn.init.normal_(self.tile_head.weight, std=0.001)
        bias = self.tile_head.bias
        assert bias is not None
        nn.init.constant_(bias, -3.5)
        self.set_frozen(frozen)

    def set_frozen(self, frozen: bool) -> None:
        self.frozen = frozen
        self.native.requires_grad_(not frozen)
        self.native.train(self.training and not frozen)

    def train(self, mode: bool = True) -> UnityDenseTileRegressor:
        super().train(mode)
        if self.frozen:
            self.native.eval()
        return self

    def forward(self, rgba: Tensor, valid_mask: Tensor, metadata: Tensor) -> Tensor:
        if (
            rgba.ndim != 4
            or rgba.shape[1] != 4
            or min(rgba.shape[2:]) < 8
            or any(size % 8 for size in rgba.shape[2:])
            or valid_mask.shape != (len(rgba), 1, *rgba.shape[2:])
            or valid_mask.dtype != torch.bool
            or metadata.shape != (len(rgba), 8)
        ):
            raise ValueError("Require aligned NCHW RGBA patches, pixel masks and native metadata")
        features = torch.cat((rgba * 2 - 1, valid_mask.to(rgba.dtype)), dim=1)
        for layer in list(self.native.backbone.children())[:6]:
            features = layer(features)
        shallow = features
        deep = self.native.backbone[7](self.native.backbone[6](shallow))
        scale = metadata.new_tensor([12, 12, 1, 1, 1, 1, 4, 1])
        gain, offset = self.native.metadata_conditioner(metadata / scale).float().chunk(2, dim=1)
        deep = deep * (1 + gain[:, :, None, None]) + offset[:, :, None, None]
        deep = F.interpolate(deep, size=shallow.shape[2:], mode="bilinear", align_corners=False)
        prediction = self.tile_head(torch.cat((shallow, deep), dim=1)).float()
        batch, _, tile_rows, tile_columns = prediction.shape
        return prediction.permute(0, 2, 3, 1).reshape(
            batch, tile_rows, tile_columns, self.CANDIDATES, self.CHANNELS
        )
