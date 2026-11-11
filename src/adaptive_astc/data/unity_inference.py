"""Native model inputs built only from reference pixels and importer properties."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image
from torch import Tensor
from torch.utils.data import Dataset

from adaptive_astc.data.patch_targets import PatchErrorGrid


@dataclass(frozen=True)
class UnityInferenceTexture:
    reference: Path
    srgb: bool
    normal: bool
    need_alpha: bool
    normal_metric_mips: int = 1

    def validate(self) -> None:
        if any(type(value) is not bool for value in [self.srgb, self.normal, self.need_alpha]):
            raise ValueError("Native inference importer flags must be boolean")
        if (
            type(self.normal_metric_mips) is not int
            or not 1 <= self.normal_metric_mips <= 4
            or (not self.normal and self.normal_metric_mips != 1)
            or (self.normal and self.srgb)
        ):
            raise ValueError("Native LDR inference requires valid Linear normal/mip scope")


class UnityInferenceInput(Dataset[dict[str, Tensor]]):
    """Match the native training input contract without accepting labels or target files."""

    def __init__(self, textures: list[UnityInferenceTexture], patch_size: int = 240) -> None:
        if not textures:
            raise ValueError("At least one native texture is required")
        self.textures = textures
        self.patch_size = patch_size
        grid = PatchErrorGrid(patch_size)
        boxes, image_ids, metadata = [], [], []
        self.sizes: list[tuple[int, int]] = []
        for image_id, texture in enumerate(textures):
            texture.validate()
            reference = self.pixels(image_id)
            height, width = reference.shape[:2]
            self.sizes.append((width, height))
            image_boxes = grid.boxes(width, height)
            boxes.append(image_boxes)
            image_ids.append(np.full(len(image_boxes), image_id, dtype=np.int64))
            metadata.append(
                [
                    np.log2(width),
                    np.log2(height),
                    texture.srgb,
                    texture.normal,
                    texture.need_alpha,
                    bool(reference[:, :, 3].min() == reference[:, :, 3].max()),
                    texture.normal_metric_mips,
                    float(np.mean(np.all(reference[:, :, :3] == 0, axis=2))),
                ]
            )
        self.boxes = np.concatenate(boxes)
        self.image_ids = np.concatenate(image_ids)
        self.pixel_counts = self.boxes[:, 2] * self.boxes[:, 3]
        self.input_metadata = np.asarray(metadata, dtype=np.float32)

    def __len__(self) -> int:
        return len(self.boxes)

    @lru_cache(maxsize=2)
    def pixels(self, image_id: int) -> NDArray[np.uint8]:
        with Image.open(self.textures[image_id].reference) as image:
            # Training uses the displayed reference orientation; encoding flips separately.
            return np.asarray(image.convert("RGBA"), dtype=np.uint8)

    def __getitem__(self, index: int) -> dict[str, Tensor]:
        image_id = int(self.image_ids[index])
        x, y, width, height = self.boxes[index]
        patch = self.pixels(image_id)[y : y + height, x : x + width]
        padded = np.pad(
            patch,
            ((0, self.patch_size - height), (0, self.patch_size - width), (0, 0)),
            mode="edge",
        )
        mask = torch.zeros((1, self.patch_size, self.patch_size), dtype=torch.bool)
        mask[:, :height, :width] = True
        return {
            "rgba": torch.from_numpy(padded.copy()).permute(2, 0, 1).float() / 255,
            "valid_mask": mask,
            "metadata": torch.from_numpy(self.input_metadata[image_id]),
            "patch_index": torch.tensor(index, dtype=torch.int64),
        }
