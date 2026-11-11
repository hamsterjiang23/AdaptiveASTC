"""Fully connected TexNN networks using the supplied Appendix's layer dimensions."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

from torch import Tensor, nn


class TexNNClassifier(nn.Module):
    def __init__(
        self,
        footprint: tuple[int, int],
        network: Literal["pnn", "demnn"],
        *,
        dropout: float = 0.6,
        activation: Literal["relu", "selu"] = "relu",
        initialization_std: float = 0.01,
    ) -> None:
        super().__init__()
        if footprint not in {(4, 4), (6, 6), (8, 8)}:
            raise ValueError("TexNN Appendix specifies 4x4, 6x6 and 8x8 networks")
        if network not in {"pnn", "demnn"} or activation not in {"relu", "selu"}:
            raise ValueError("Unsupported TexNN network or activation")
        if not 0 <= dropout < 1 or not math.isfinite(initialization_std) or initialization_std <= 0:
            raise ValueError("Invalid dropout probability or Gaussian initialization scale")
        architecture = json.loads(
            Path(__file__).with_name("architectures.json").read_text(encoding="utf-8")
        )
        sizes: list[int] = architecture[network][f"{footprint[0]}x{footprint[1]}"]
        self.input_features = footprint[0] * footprint[1] * 3
        if network == "demnn":
            # Four partitions, two RGB ideal endpoints each, padded for unused partitions.
            self.input_features += 4 * 2 * 3
        self.output_classes = sizes[-1]
        modules: list[nn.Module] = []
        previous = self.input_features
        for index, size in enumerate(sizes):
            layer = nn.Linear(previous, size)
            nn.init.normal_(layer.weight, mean=0.0, std=initialization_std)
            nn.init.zeros_(layer.bias)
            modules.append(layer)
            if index < len(sizes) - 1:
                modules.append(nn.ReLU() if activation == "relu" else nn.SELU())
                modules.append(nn.Dropout(p=dropout))
            previous = size
        self.layers = nn.Sequential(*modules)

    def forward(self, features: Tensor) -> Tensor:
        if features.ndim != 2 or features.shape[1] != self.input_features:
            raise ValueError(f"Expected a batch of {self.input_features} TexNN features")
        return self.layers(features)
