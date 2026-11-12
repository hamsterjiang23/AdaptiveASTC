"""Explicit per-epoch native image sampling controls with observed-order receipts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

import torch
from torch.utils.data import Sampler

from adaptive_astc.config import JsonDict
from adaptive_astc.data.splitting import DatasetSplitter
from adaptive_astc.evaluation.unity_quality import UnityTextureInput


class UnityImageSampler(Sampler[int]):
    @staticmethod
    def validate(group_image_cap: int, normal_image_repeats: int) -> None:
        if type(group_image_cap) is not int or group_image_cap < 0:
            raise ValueError("Native asset-group cap must be a nonnegative integer")
        if type(normal_image_repeats) is not int or normal_image_repeats < 1:
            raise ValueError("Normal image repeats must be a positive integer")
        if group_image_cap and normal_image_repeats != 1:
            raise ValueError("Evaluate native group capping and normal repeats individually")

    def __init__(
        self,
        rows: list[JsonDict],
        generator: torch.Generator,
        *,
        group_image_cap: int = 0,
        normal_image_repeats: int = 1,
    ) -> None:
        self.validate(group_image_cap, normal_image_repeats)
        if not rows:
            raise ValueError("Native image sampling requires nonempty training rows")
        self.groups = [
            DatasetSplitter.asset_group(row["path"].replace("\\", "/")).casefold() for row in rows
        ]
        if any(not isinstance(group, str) or not group for group in self.groups):
            raise ValueError("Native sampling requires nonempty asset-group names")
        self.normal = [UnityTextureInput.from_row(row).normal for row in rows]
        self.normal_indices = [i for i, normal in enumerate(self.normal) if normal]
        self.group_indices: dict[str, list[int]] = {}
        for index, group in enumerate(self.groups):
            self.group_indices.setdefault(group, []).append(index)
        self.generator = generator
        self.cap, self.repeats = group_image_cap, normal_image_repeats
        self.last_order: list[int] = []

    def __len__(self) -> int:
        if self.cap:
            return sum(min(len(indices), self.cap) for indices in self.group_indices.values())
        return len(self.groups) + (self.repeats - 1) * len(self.normal_indices)

    def __iter__(self) -> Iterator[int]:
        selected = list(range(len(self.groups)))
        if self.cap:
            selected = []
            for indices in self.group_indices.values():
                if len(indices) > self.cap:
                    order = torch.randperm(len(indices), generator=self.generator).tolist()
                    selected.extend(indices[i] for i in order[: self.cap])
                else:
                    selected.extend(indices)
        selected.extend(self.normal_indices * (self.repeats - 1))
        shuffle = torch.randperm(len(selected), generator=self.generator).tolist()
        self.last_order = [selected[i] for i in shuffle]
        return iter(self.last_order)

    def receipt(self, source_indices: list[int], observed: list[int]) -> JsonDict:
        if len(source_indices) != len(self.groups) or observed != [
            source_indices[i] for i in self.last_order
        ]:
            raise ValueError("Observed native training image order differs from its sampler")
        if len(observed) != len(self):
            raise ValueError("Native training did not consume the complete epoch sampling plan")
        group_draws = Counter(self.groups[i] for i in self.last_order)
        return {
            "image_indices": observed,
            "image_draws": len(observed),
            "unique_images": len(set(observed)),
            "normal_image_draws": sum(self.normal[i] for i in self.last_order),
            "asset_groups": len(group_draws),
            "maximum_asset_group_draws": max(group_draws.values()),
            "group_image_cap": self.cap,
            "normal_image_repeats": self.repeats,
        }
