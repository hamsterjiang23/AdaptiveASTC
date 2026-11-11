"""Sample same-image patch bags while preserving marginal image/patch weights."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import torch
from numpy.typing import NDArray
from torch.utils.data import Sampler

from adaptive_astc.config import JsonDict
from adaptive_astc.data.patch_sampling import PatchSampling


class ImagePatchBatchSampler(Sampler[list[int]]):
    """Contiguous fixed-size bags; every index in a bag belongs to one image."""

    def __init__(
        self,
        rows: list[JsonDict],
        image_ids: NDArray[np.int64],
        *,
        batch_size: int,
        bag_size: int,
        num_samples: int,
        generator: torch.Generator,
        group_image_cap: int = 0,
    ) -> None:
        for value in [batch_size, bag_size, num_samples]:
            if type(value) is not int or value < 1:
                raise ValueError("Batch, bag and sample budget must be positive integers")
        if batch_size % bag_size or num_samples % bag_size:
            raise ValueError("Batch size and sample budget must contain complete bags")
        weights = PatchSampling.weights(rows, image_ids, group_image_cap)
        image_weights = np.bincount(image_ids, weights=weights, minlength=len(rows))
        self.image_weights = torch.from_numpy(image_weights)
        counts = np.bincount(image_ids, minlength=len(rows))
        ordered = np.argsort(image_ids, kind="stable")
        self.indexes = np.split(ordered, np.cumsum(counts)[:-1])
        self.batch_size = batch_size
        self.bag_size = bag_size
        self.num_samples = num_samples
        self.generator = generator

    def __len__(self) -> int:
        return (self.num_samples + self.batch_size - 1) // self.batch_size

    def __iter__(self) -> Iterator[list[int]]:
        image_draws = torch.multinomial(
            self.image_weights,
            self.num_samples // self.bag_size,
            replacement=True,
            generator=self.generator,
        )
        batch: list[int] = []
        for image_id in image_draws.tolist():
            indexes = self.indexes[image_id]
            patch_draws = torch.randint(
                len(indexes), (self.bag_size,), generator=self.generator
            ).numpy()
            batch.extend(indexes[patch_draws].tolist())
            if len(batch) == self.batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
