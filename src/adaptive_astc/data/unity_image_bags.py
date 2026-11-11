"""Visit each selected native image once per epoch, sampling its patch views."""

from __future__ import annotations

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import Dataset

from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.training.unity_quality_loss import UnityImageTargets


class UnityImageBags(Dataset[tuple[dict[str, Tensor], dict[str, Tensor]]]):
    def __init__(self, patches: UnityPatchDataset, image_indices: list[int], views: int) -> None:
        if (
            type(views) is not int
            or views < 1
            or not image_indices
            or len(set(image_indices)) != len(image_indices)
            or any(type(i) is not int or not 0 <= i < len(patches.rows) for i in image_indices)
        ):
            raise ValueError("Unique valid native image indexes and positive patch views required")
        self.patches = patches
        self.image_indices = image_indices
        self.views = views
        counts = np.bincount(patches.image_ids, minlength=len(patches.rows))
        ordered = np.argsort(patches.image_ids, kind="stable")
        self.patch_indexes = np.split(ordered, np.cumsum(counts)[:-1])
        self.targets = UnityImageTargets.build([patches.rows[i] for i in image_indices])

    def __len__(self) -> int:
        return len(self.image_indices)

    def __getitem__(self, index: int) -> tuple[dict[str, Tensor], dict[str, Tensor]]:
        image_id = self.image_indices[index]
        available = self.patch_indexes[image_id]
        draws = torch.randint(len(available), (self.views,))
        items = [self.patches[int(available[i])] for i in draws]
        inputs = {
            key: torch.stack([row[key] for row in items])
            for key in ["rgba", "valid_mask", "channel_log_mse", "patch_index"]
        }
        inputs["metadata"] = torch.from_numpy(self.patches.input_metadata[image_id])
        inputs["original_image_index"] = torch.tensor(image_id, dtype=torch.int64)
        targets = {key: value[index] for key, value in self.targets.items()}
        return inputs, targets
