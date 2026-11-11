"""Count actual optimizer calls when GradScaler skips overflowing gradients."""

from __future__ import annotations

import pytest
import torch
from torch import nn
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader, TensorDataset

from adaptive_astc.training.trainer import Trainer


@pytest.mark.parametrize("overflow", [False, True])
def test_optimizer_updates_distinguish_scaler_skips(overflow: bool) -> None:
    torch.manual_seed(17)
    model = nn.Linear(2, 4)
    features = torch.full((2, 2), 1e10 if overflow else 1.0)
    targets = torch.tensor([0, 1])
    batches = DataLoader(TensorDataset(features, targets), batch_size=2)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    scaler = GradScaler("cpu", init_scale=float(2**120) if overflow else 1.0)
    before = [parameter.detach().clone() for parameter in model.parameters()]
    metrics = Trainer.train_epoch(model, batches, torch.device("cpu"), optimizer, scaler, 2, 0, 2)
    assert metrics["samples"] == 2 and metrics["steps"] == 1
    assert metrics["optimizer_updates"] == (0 if overflow else 1)
    assert metrics["amp_skipped_steps"] == (1 if overflow else 0)
    unchanged = all(
        torch.equal(old, new) for old, new in zip(before, model.parameters(), strict=True)
    )
    assert unchanged == overflow
