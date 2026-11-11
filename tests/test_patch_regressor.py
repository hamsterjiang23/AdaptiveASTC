from __future__ import annotations

import torch
from torch import nn
from torch.optim.swa_utils import AveragedModel, get_ema_multi_avg_fn

from adaptive_astc.models.patch_regressor import ASTCPatchRegressor


def test_monotone_patch_outputs_preserve_parameter_count() -> None:
    torch.set_num_threads(2)
    independent = ASTCPatchRegressor("scratch", remove_maxpool=False)
    monotone = ASTCPatchRegressor("scratch", remove_maxpool=False, monotone=True)
    assert sum(p.numel() for p in independent.parameters()) == sum(
        p.numel() for p in monotone.parameters()
    )
    monotone.eval()
    with torch.inference_mode():
        values = monotone(torch.zeros(2, 3, 32, 32))
    assert values.shape == (2, 4) and torch.isfinite(values).all()
    assert (values[:, 1:] > values[:, :-1]).all()


def test_ema_parameter_and_buffer_updates_follow_applied_steps() -> None:
    linear, batch_norm = nn.Linear(2, 2, bias=False), nn.BatchNorm1d(2)
    model = nn.Sequential(linear, batch_norm)
    assert batch_norm.running_mean is not None
    ema = AveragedModel(model, multi_avg_fn=get_ema_multi_avg_fn(0.5), use_buffers=True)
    with torch.no_grad():
        linear.weight.fill_(1)
        batch_norm.running_mean.fill_(2)
    ema.update_parameters(model)
    with torch.no_grad():
        linear.weight.fill_(3)
        batch_norm.running_mean.fill_(4)
    ema.update_parameters(model)
    assert int(ema.n_averaged) == 2
    torch.testing.assert_close(ema.module.state_dict()["0.weight"], torch.full((2, 2), 2.0))
    torch.testing.assert_close(ema.module.state_dict()["1.running_mean"], torch.full((2,), 3.0))
