"""Supervise additive channel errors separately from complete-image native quality."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch
from torch import Tensor, nn

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput


class UnityImageTargets:
    @staticmethod
    def build(rows: list[JsonDict]) -> dict[str, Tensor]:
        if not rows:
            raise ValueError("Image targets require nonempty native image rows")
        zero, channels, quality, active = [], [], [], []
        for row in rows:
            texture = UnityTextureInput.from_row(row)
            errors = np.asarray(row["full_channel_squared_errors"])
            if (
                errors.shape != (20, 4)
                or not np.issubdtype(errors.dtype, np.integer)
                or np.any(errors < 0)
            ):
                raise ValueError("Image zero-channel targets require exact full-image RGBA SSE")
            zero.append(errors == 0)
            channels.append([True, True, True, texture.need_alpha and not texture.alpha_constant])
            values = [
                [
                    q[name] if q[name] is not None else float("nan")
                    for name in UnityQualityPrediction.QUALITY_NAMES
                ]
                for q in row["image_quality"]
            ]
            quality.append(values)
            active.append([texture.srgb and not texture.normal, texture.normal, texture.normal])
        result = {
            "channel_zero": torch.from_numpy(np.asarray(zero, dtype=np.float32)),
            "channel_active": torch.tensor(channels, dtype=torch.bool),
            "image_quality": torch.tensor(quality, dtype=torch.float32),
            "quality_active": torch.tensor(active, dtype=torch.bool),
        }
        mask = result["quality_active"][:, None, :].expand_as(result["image_quality"])
        if (
            result["image_quality"].shape != (len(rows), 20, 3)
            or not torch.isfinite(result["image_quality"][mask]).all()
        ):
            raise ValueError("Applicable image-level target is missing or nonfinite")
        return result


@dataclass(frozen=True)
class UnityQualityLossConfig:
    zero_weight: float = 0.1
    ssim_weight: float = 0.1
    angle_weight: float = 0.1

    def validate(self) -> None:
        if any(
            not math.isfinite(x) or x < 0
            for x in [self.zero_weight, self.ssim_weight, self.angle_weight]
        ):
            raise ValueError("Native quality loss weights must be finite and nonnegative")


class UnityQualityLoss(nn.Module):
    def __init__(self, config: UnityQualityLossConfig = UnityQualityLossConfig()) -> None:
        super().__init__()
        config.validate()
        self.config = config

    @staticmethod
    def masked_huber(prediction: Tensor, target: Tensor, mask: Tensor, delta: float) -> Tensor:
        if mask.any():
            return nn.functional.huber_loss(prediction[mask].float(), target[mask], delta=delta)
        return prediction.sum() * 0

    def forward(
        self,
        outputs: dict[str, Tensor],
        patch_targets: Tensor,
        image_ids: Tensor,
        image_targets: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        predicted = outputs["channel_log_mse"]
        zero_logits = outputs["channel_zero_logits"]
        quality = outputs["image_quality"]
        target_quality = image_targets["image_quality"]
        if (
            predicted.ndim != 3
            or predicted.shape != patch_targets.shape
            or predicted.shape[1:] != (20, 4)
            or not len(predicted)
            or image_ids.shape != (len(predicted),)
            or image_ids.dtype != torch.int64
            or zero_logits.shape != image_targets["channel_zero"].shape
            or zero_logits.shape[1:] != (20, 4)
            or quality.shape != target_quality.shape
            or quality.shape != (len(zero_logits), 20, 3)
            or image_targets["channel_active"].shape != (len(zero_logits), 4)
            or image_targets["quality_active"].shape != (len(zero_logits), 3)
            or torch.any(image_ids < 0)
            or torch.any(image_ids >= len(zero_logits))
        ):
            raise ValueError(
                "Native patch and full-image loss targets have incompatible identities/shapes"
            )
        active_channels = image_targets["channel_active"][:, None, :].expand_as(zero_logits)
        patch = self.masked_huber(predicted, patch_targets, active_channels[image_ids], 0.1)
        zero = nn.functional.binary_cross_entropy_with_logits(
            zero_logits[active_channels].float(), image_targets["channel_zero"][active_channels]
        )
        quality_mask = image_targets["quality_active"][:, None, :].expand_as(quality)
        ssim = self.masked_huber(
            quality[:, :, :1], target_quality[:, :, :1], quality_mask[:, :, :1], 1
        )
        angle = self.masked_huber(
            quality[:, :, 1:], target_quality[:, :, 1:], quality_mask[:, :, 1:], 1
        )
        total = (
            patch
            + self.config.zero_weight * zero
            + self.config.ssim_weight * ssim
            + self.config.angle_weight * angle
        )
        if not torch.isfinite(total):
            raise ValueError("Nonfinite native quality supervision or prediction")
        return {"total": total, "patch": patch, "zero": zero, "ssim": ssim, "angle": angle}
