"""ResNet-18 patch regression with a zero-initialized input-size correction."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from adaptive_astc.data.patch_metadata import PatchMetadata
from adaptive_astc.models.patch_regressor import ASTCPatchRegressor
from adaptive_astc.models.resnet import ASTCClassifier


class MetadataPatchRegressor(ASTCPatchRegressor):
    def __init__(
        self, initialization: str, remove_maxpool: bool = True, monotone: bool = False
    ) -> None:
        super().__init__(initialization, remove_maxpool, monotone)
        # No random draw: the backbone, head, and RNG state match the original model.
        self.metadata_weight = nn.Parameter(torch.zeros(4, len(PatchMetadata.FEATURE_NAMES)))

    def forward(self, inputs: Tensor, metadata: Tensor) -> Tensor:
        if metadata.shape != (len(inputs), len(PatchMetadata.FEATURE_NAMES)):
            raise ValueError("Every input patch requires the four input-size features")
        outputs = ASTCClassifier.forward(self, inputs).float()
        with torch.autocast(device_type=inputs.device.type, enabled=False):
            outputs = outputs + nn.functional.linear(metadata.float(), self.metadata_weight.float())
        if not self.monotone:
            return outputs
        first = outputs[:, :1]
        return torch.cat((first, first + nn.functional.softplus(outputs[:, 1:]).cumsum(1)), 1)
