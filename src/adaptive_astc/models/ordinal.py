"""Shared-score cumulative classifier with explicitly ordered thresholds."""

import math

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from adaptive_astc.models.resnet import ASTCClassifier


class OrderedThresholdHead(nn.Module):
    """Return four stable log probabilities from three ordered cumulative logits."""

    def __init__(self, features: int) -> None:
        super().__init__()
        self.score = nn.Linear(features, 1, bias=False)
        self.first = nn.Parameter(torch.tensor(-1.0))
        self.raw_gaps = nn.Parameter(torch.full((2,), math.log(math.expm1(1.0 - 1e-4))))

    def forward(self, inputs: Tensor) -> Tensor:
        score = self.score(inputs).float()
        gaps = F.softplus(self.raw_gaps.float()) + 1e-4
        thresholds = torch.cat((self.first[None], self.first + gaps.cumsum(0)))
        ranks = score - thresholds
        middle = (
            F.logsigmoid(ranks[:, :-1])
            + F.logsigmoid(-ranks[:, 1:])
            + torch.log(-torch.expm1(-gaps))
        )
        return torch.cat((F.logsigmoid(-ranks[:, :1]), middle, F.logsigmoid(ranks[:, -1:])), 1)


class ASTCOrdinalClassifier(ASTCClassifier):
    def __init__(self, initialization: str) -> None:
        super().__init__(initialization)
        if not isinstance(self.fc, nn.Linear):
            raise TypeError("Expected the ResNet linear head before ordinal replacement")
        self.fc = OrderedThresholdHead(self.fc.in_features)


class ClassificationObjective(nn.Module):
    """Per-image CE or cumulative binary loss for the ordered shared-score head."""

    def __init__(self, name: str, smoothing: float = 0.0) -> None:
        super().__init__()
        if name not in {"cross_entropy", "ordered_cumulative"}:
            raise ValueError("Unknown classification objective")
        if not 0 <= smoothing < 1 or (name == "ordered_cumulative" and smoothing != 0):
            raise ValueError("Smoothing is supported only for cross entropy in [0,1)")
        self.name, self.smoothing = name, smoothing

    def forward(self, logits: Tensor, labels: Tensor) -> Tensor:
        if self.name == "cross_entropy":
            return F.cross_entropy(logits, labels, label_smoothing=self.smoothing, reduction="none")
        log_probabilities = F.log_softmax(logits.float(), dim=1)
        terms = [
            torch.where(
                labels > boundary,
                torch.logsumexp(log_probabilities[:, boundary + 1 :], dim=1),
                torch.logsumexp(log_probabilities[:, : boundary + 1], dim=1),
            )
            for boundary in range(3)
        ]
        return -torch.stack(terms, 1).sum(1)
