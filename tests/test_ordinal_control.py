from __future__ import annotations

import pytest
import torch
from torch.nn import functional as F

from adaptive_astc.models.ordinal import ClassificationObjective, OrderedThresholdHead


def test_ordered_probabilities_and_loss_match_cumulative_logits() -> None:
    head = OrderedThresholdHead(1)
    with torch.no_grad():
        head.score.weight.fill_(1)
    inputs = torch.tensor([[-100.0], [-1.5], [0.0], [1.5], [100.0]], requires_grad=True)
    labels = torch.tensor([0, 1, 2, 3, 2])
    logits = head(inputs)
    assert torch.isfinite(logits).all()
    torch.testing.assert_close(logits.exp().sum(1), torch.ones(5), atol=1e-6, rtol=1e-6)
    cumulative = 1 - logits.exp().cumsum(1)[:, :3]
    assert (cumulative[:, 1:] <= cumulative[:, :-1]).all()
    ranks = inputs - torch.tensor([-1.0, 0.0, 1.0])
    targets = (labels[:, None] > torch.arange(3)[None, :]).float()
    expected = F.binary_cross_entropy_with_logits(ranks, targets, reduction="none").sum(1)
    observed = ClassificationObjective("ordered_cumulative")(logits, labels)
    torch.testing.assert_close(observed, expected, atol=1e-5, rtol=1e-5)
    observed.mean().backward()
    assert inputs.grad is not None and torch.isfinite(inputs.grad).all()
    assert head.raw_gaps.grad is not None and torch.isfinite(head.raw_gaps.grad).all()


def test_cross_entropy_smoothing_is_applied_per_sample() -> None:
    logits = torch.tensor([[4.0, -2.0, 0.0, 1.0], [1.0, 2.0, 3.0, 4.0]], requires_grad=True)
    labels = torch.tensor([0, 2])
    loss = ClassificationObjective("cross_entropy", 0.1)(logits, labels)
    expected = 0.9 * F.cross_entropy(logits, labels, reduction="none")
    expected -= 0.1 * F.log_softmax(logits, 1).mean(1)
    torch.testing.assert_close(loss, expected)
    assert loss.shape == labels.shape


def test_smoothing_on_ordinal_objective_is_explicitly_rejected() -> None:
    with pytest.raises(ValueError):
        ClassificationObjective("ordered_cumulative", 0.1)
