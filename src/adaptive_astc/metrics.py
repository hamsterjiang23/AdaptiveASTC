"""Classification metrics and scalar temperature fitting."""

import math
from typing import cast

import numpy as np
import torch
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from torch import Tensor

from adaptive_astc.common import CLASSES, JsonDict


def probability_metrics(logits: Tensor, labels: Tensor, temperature: float = 1.0) -> JsonDict:
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
        mask = (confidence >= lower) & (confidence <= upper if index == 14 else confidence < upper)
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


def fit_temperature(logits: Tensor, labels: Tensor) -> JsonDict:
    # Inference-mode tensors must be cloned before the autograd-based temperature fit.
    scores = logits.detach().cpu().double().clone()
    truth = labels.detach().cpu().long().clone()
    initial = float(torch.nn.functional.cross_entropy(scores, truth))
    log_temperature = torch.zeros((), dtype=torch.float64, requires_grad=True)
    optimizer = torch.optim.LBFGS(
        [log_temperature],
        lr=1.0,
        max_iter=100,
        tolerance_grad=1e-9,
        tolerance_change=1e-12,
        line_search_fn="strong_wolfe",
    )
    history: list[JsonDict] = []

    def closure() -> Tensor:
        optimizer.zero_grad()
        temperature = log_temperature.exp()
        loss = torch.nn.functional.cross_entropy(scores / temperature, truth)
        if not torch.isfinite(loss) or not torch.isfinite(temperature) or temperature <= 0:
            raise ValueError("Non-finite temperature fit")
        loss.backward()
        history.append({"temperature": float(temperature.detach()), "nll": float(loss.detach())})
        return loss

    status = "fitted"
    error_text: str | None = None
    try:
        optimizer.step(closure)
        temperature = float(log_temperature.detach().exp())
        fitted = float(torch.nn.functional.cross_entropy(scores / temperature, truth))
        if not math.isfinite(temperature) or temperature <= 0 or not math.isfinite(fitted):
            raise ValueError("Invalid fitted value")
        if fitted >= initial:
            temperature, fitted, status = 1.0, initial, "no_improvement"
    except (ValueError, RuntimeError) as error:
        temperature, fitted, status = 1.0, initial, "failed"
        error_text = str(error)
    state = optimizer.state.get(log_temperature, {})
    return {
        "temperature": temperature,
        "status": status,
        "error": error_text,
        "initial_nll": initial,
        "fitted_nll": fitted,
        "history": history,
        "optimizer_iterations": int(state.get("n_iter", 0)),
        "gradient_abs": float(log_temperature.grad.abs())
        if log_temperature.grad is not None
        else None,
        "max_iterations": 100,
    }
