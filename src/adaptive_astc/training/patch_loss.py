"""Patch supervision and optional same-image, pixel-weighted MSE aggregation."""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn


class PatchRegressionLoss(nn.Module):
    """A sampled bag target is exact for that bag, not the complete image."""

    def __init__(self, bag_size: int = 1, aggregate_weight: float = 0.0) -> None:
        super().__init__()
        if type(bag_size) is not int or bag_size < 1:
            raise ValueError("Bag size must be a positive integer")
        if not math.isfinite(aggregate_weight) or aggregate_weight < 0:
            raise ValueError("Aggregate loss weight must be finite and nonnegative")
        if aggregate_weight and bag_size < 2:
            raise ValueError("Aggregate loss requires at least two same-image patches")
        self.bag_size = bag_size
        self.aggregate_weight = aggregate_weight

    @staticmethod
    def weighted_huber(predicted: Tensor, target: Tensor) -> Tensor:
        weights = 1 + 2 * torch.exp(-torch.abs(-10 * target - 35) / 3)
        return (
            nn.functional.huber_loss(predicted.float(), target, delta=0.1, reduction="none")
            * weights
        ).mean()

    @staticmethod
    def aggregate_log_mse(values: Tensor, pixel_counts: Tensor) -> Tensor:
        """Return log10(pixel-weighted MSE + epsilon), matching inference clipping."""
        if values.ndim != 3 or pixel_counts.shape != values.shape[:2]:
            raise ValueError("Expected [bags, patches, candidates] and [bags, patches]")
        if not torch.isfinite(pixel_counts).all() or torch.any(pixel_counts <= 0):
            raise ValueError("Only positive finite valid-pixel counts may enter aggregation")
        weights = pixel_counts.to(device=values.device, dtype=torch.float32)
        # exp(log(MSE+eps)) -> weighted mean; the common eps cancels then is restored.
        log_weights = torch.log(weights)
        return (
            torch.logsumexp(
                values.float().clamp(-10, 0) * math.log(10) + log_weights[..., None], dim=1
            )
            - torch.logsumexp(log_weights, dim=1)[..., None]
        ) / math.log(10)

    def forward(
        self, prediction: Tensor, targets: Tensor, pixel_counts: Tensor, image_ids: Tensor
    ) -> tuple[Tensor, Tensor, Tensor]:
        if prediction.ndim != 2 or prediction.shape != targets.shape or len(prediction) < 1:
            raise ValueError("Require equal nonempty [patches, candidates] predictions and targets")
        if len(prediction) % self.bag_size:
            raise ValueError("Incomplete same-image patch bag")
        if pixel_counts.shape != (len(prediction),) or image_ids.shape != (len(prediction),):
            raise ValueError("Every patch requires a valid-pixel count and image identity")
        identities = image_ids.reshape(-1, self.bag_size)
        if not torch.all(identities == identities[:, :1]):
            raise ValueError("A patch bag cannot mix image identities")
        patch_loss = self.weighted_huber(prediction, targets)
        aggregate_loss = prediction.new_zeros((), dtype=torch.float32)
        if self.aggregate_weight:
            shape = (-1, self.bag_size, prediction.shape[-1])
            pixels = pixel_counts.reshape(-1, self.bag_size)
            predicted = self.aggregate_log_mse(prediction.reshape(shape), pixels)
            target = self.aggregate_log_mse(targets.reshape(shape), pixels)
            aggregate_loss = self.weighted_huber(predicted, target)
        return patch_loss + self.aggregate_weight * aggregate_loss, patch_loss, aggregate_loss
