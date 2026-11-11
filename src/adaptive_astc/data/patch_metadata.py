"""Input-only size features for native RGB patch error regression."""

from __future__ import annotations

import torch
from torch import Tensor


class PatchMetadata:
    FEATURE_NAMES = (
        "log2_image_width_div12",
        "log2_image_height_div12",
        "valid_patch_width_fraction",
        "valid_patch_height_fraction",
    )

    @staticmethod
    def encode(image_sizes: Tensor, valid_sizes: Tensor, patch_size: int) -> Tensor:
        """Sizes are [width, height]; neither labels nor measured errors are inputs."""
        if type(patch_size) is not int or patch_size < 1:
            raise ValueError("Positive integer patch size required")
        if image_sizes.ndim != 2 or image_sizes.shape[1] != 2 or len(image_sizes) < 1:
            raise ValueError("Image sizes must be nonempty [batch, 2]")
        if valid_sizes.shape != image_sizes.shape or valid_sizes.device != image_sizes.device:
            raise ValueError("Image and valid patch sizes must have matching shape and device")
        if (
            not torch.isfinite(image_sizes).all()
            or not torch.isfinite(valid_sizes).all()
            or torch.any(image_sizes <= 0)
            or torch.any(valid_sizes <= 0)
            or torch.any(valid_sizes > patch_size)
            or torch.any(valid_sizes > image_sizes)
            or torch.any(image_sizes != image_sizes.round())
            or torch.any(valid_sizes != valid_sizes.round())
        ):
            raise ValueError("Sizes must be positive integer pixels with valid patch bounds")
        return torch.cat(
            (torch.log2(image_sizes.float()) / 12.0, valid_sizes.float() / patch_size), dim=1
        )
