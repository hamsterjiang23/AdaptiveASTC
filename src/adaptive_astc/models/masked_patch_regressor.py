"""Parameter-preserving native-patch regression with valid-area feature pooling."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from adaptive_astc.models.patch_regressor import ASTCPatchRegressor


class ValidAreaPooling(nn.Module):
    """Weight final spatial features by pooled mask coverage; keep convolution unchanged."""

    def forward(self, features: Tensor, valid_mask: Tensor) -> Tensor:
        if (
            features.ndim != 4
            or len(features) < 1
            or not features.is_floating_point()
            or valid_mask.ndim != 4
            or valid_mask.shape[:2] != (len(features), 1)
            or valid_mask.dtype != torch.bool
            or valid_mask.device != features.device
            or min(*features.shape[2:], *valid_mask.shape[2:]) < 1
        ):
            raise ValueError("Require spatial features and same-device bool masks per patch")
        weights = nn.functional.adaptive_avg_pool2d(
            valid_mask.float(), (features.shape[2], features.shape[3])
        )
        totals = weights.sum((2, 3))
        if torch.any(totals <= 0):
            raise ValueError("Every patch must contain at least one valid pixel")
        # FP32 summation avoids underflow for thin or single-pixel valid areas under AMP.
        pooled = (features.float() * weights).sum((2, 3)) / totals
        return pooled.to(features.dtype)


class MaskedPatchRegressor(ASTCPatchRegressor):
    """Same weights/head as ASTCPatchRegressor; only the final pooling rule differs."""

    def __init__(
        self, initialization: str, remove_maxpool: bool = True, monotone: bool = False
    ) -> None:
        super().__init__(initialization, remove_maxpool, monotone)
        self.valid_area_pool = ValidAreaPooling()

    def forward(self, inputs: Tensor, valid_mask: Tensor) -> Tensor:
        if (
            inputs.ndim != 4
            or inputs.shape[1] != 3
            or valid_mask.shape
            != (
                len(inputs),
                1,
                *inputs.shape[2:],
            )
        ):
            raise ValueError("Require RGB inputs and a mask with matching original patch geometry")
        features = self.maxpool(self.relu(self.bn1(self.conv1(inputs))))
        for layer in [self.layer1, self.layer2, self.layer3, self.layer4]:
            features = layer(features)
        outputs = self.fc(self.valid_area_pool(features, valid_mask)).float()
        if not self.monotone:
            return outputs
        first = outputs[:, :1]
        return torch.cat((first, first + nn.functional.softplus(outputs[:, 1:]).cumsum(1)), 1)
