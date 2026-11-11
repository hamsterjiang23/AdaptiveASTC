"""Input-only geometry for padded native-resolution patches."""

from __future__ import annotations

import torch
from torch import Tensor


class PatchGeometry:
    @staticmethod
    def valid_mask(boxes: Tensor, patch_size: int = 240) -> Tensor:
        """Map [x,y,width,height] boxes to top-left valid areas on the same device."""
        if (
            type(patch_size) is not int
            or patch_size < 1
            or boxes.ndim != 2
            or boxes.shape[1] != 4
            or len(boxes) < 1
            or boxes.dtype != torch.int64
            or torch.any(boxes[:, :2] < 0)
            or torch.any(boxes[:, 2:] <= 0)
            or torch.any(boxes[:, 2:] > patch_size)
        ):
            raise ValueError("Require positive in-patch int64 geometry and nonnegative origins")
        positions = torch.arange(patch_size, device=boxes.device)
        width = positions[None, None, :] < boxes[:, 2, None, None]
        height = positions[None, :, None] < boxes[:, 3, None, None]
        return (width & height)[:, None]
