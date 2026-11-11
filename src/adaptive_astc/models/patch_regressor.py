"""Independent or monotone native-patch log MSE at ResNet-18 capacity."""

import math

import torch
from torch import Tensor, nn

from adaptive_astc.models.resnet import ASTCClassifier


class ASTCPatchRegressor(ASTCClassifier):
    def __init__(
        self, initialization: str, remove_maxpool: bool = True, monotone: bool = False
    ) -> None:
        if initialization not in {"scratch", "pretrained"}:
            raise ValueError("Unsupported initialization")
        super().__init__(initialization)
        self.monotone = monotone
        if remove_maxpool:
            self.maxpool = nn.Identity()
        nn.init.normal_(self.fc.weight, std=0.001)
        nn.init.constant_(self.fc.bias, -3.5)
        if monotone:
            with torch.no_grad():
                self.fc.bias[1:].fill_(math.log(math.expm1(0.25)))

    def forward(self, inputs: Tensor) -> Tensor:
        outputs = super().forward(inputs).float()
        if not self.monotone:
            return outputs
        first = outputs[:, :1]
        return torch.cat((first, first + nn.functional.softplus(outputs[:, 1:]).cumsum(1)), 1)
