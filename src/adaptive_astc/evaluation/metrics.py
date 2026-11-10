"""Four-class probability and reliability metrics."""

import math
from typing import cast

import numpy as np
import torch
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from torch import Tensor

from adaptive_astc.config import CLASSES, JsonDict


class ClassificationMetrics:
    """Compute the unchanged classification and calibration metric protocol."""

    @staticmethod
    def compute(logits: Tensor, labels: Tensor, temperature: float = 1.0) -> JsonDict:
        if not math.isfinite(temperature) or temperature <= 0:
            raise ValueError("Temperature must be finite and positive")
        scaled = logits.detach().cpu().double() / temperature
        truth = labels.detach().cpu().long()
        probabilities = scaled.softmax(dim=1)
        confidence, predicted = probabilities.max(dim=1)
        correct = predicted.eq(truth)
        one_hot = torch.nn.functional.one_hot(truth, num_classes=4).double()
        # scikit-learn's stub omits numeric zero_division and the average=None array result.
        per_class = precision_recall_fscore_support(
            truth.numpy(),
            predicted.numpy(),
            labels=list(range(4)),
            zero_division=0,  # pyright: ignore[reportArgumentType]
        )
        precision, recall, f1, support = cast(
            tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray], per_class
        )
        bins: list[JsonDict] = []
        ece = 0.0
        for index in range(15):
            lower, upper = index / 15, (index + 1) / 15
            mask = (confidence >= lower) & (
                confidence <= upper if index == 14 else confidence < upper
            )
            count = int(mask.sum())
            mean_confidence = float(confidence[mask].mean()) if count else None
            accuracy = float(correct[mask].double().mean()) if count else None
            if mean_confidence is not None and accuracy is not None:
                ece += count / len(truth) * abs(float(mean_confidence) - float(accuracy))
            bins.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": count,
                    "confidence": mean_confidence,
                    "accuracy": accuracy,
                }
            )
        present = support > 0
        return {
            "count": len(truth),
            "accuracy": float(correct.double().mean()),
            "macro_f1": float(np.mean(f1)),
            "balanced_accuracy": float(np.mean(recall[present])),
            "nll": float(torch.nn.functional.cross_entropy(scaled, truth)),
            "brier": float(((probabilities - one_hot) ** 2).sum(dim=1).mean()),
            "ece_15_equal_width": ece,
            "confusion_matrix": confusion_matrix(
                truth.numpy(), predicted.numpy(), labels=list(range(4))
            ).tolist(),
            "per_class": {
                name: {
                    "precision": float(precision[index]),
                    "recall": float(recall[index]),
                    "f1": float(f1[index]),
                    "support": int(support[index]),
                }
                for index, name in enumerate(CLASSES)
            },
            "reliability_bins": bins,
        }
