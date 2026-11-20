"""Pair bottom-aligned RGBA patches with exact candidate tile supervision."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor
from torch.utils.data import Dataset, Sampler

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.data.unity_tile_corpus import UnityTileCorpus
from adaptive_astc.data.unity_tile_errors import UnityTileGrid
from adaptive_astc.data.unity_tile_labels import UnityTileLabels
from adaptive_astc.utils.artifacts import ArtifactStore


@dataclass(frozen=True)
class UnityDensePatchGrid:
    grid: UnityTileGrid
    patch_size: int

    def __post_init__(self) -> None:
        if self.grid.size != 8 or self.patch_size not in (128, 240):
            raise ValueError("Use native stride-eight tiles and either 128 or 240 pixel patches")

    def origins(self) -> Iterator[tuple[int, int]]:
        for y in range(0, self.grid.height + self.grid.top_padding, self.patch_size):
            for x in range(0, self.grid.width, self.patch_size):
                yield y // 8, x // 8

    def extract(
        self, rgba: NDArray[np.uint8], tile_y: int, tile_x: int
    ) -> tuple[NDArray[np.uint8], NDArray[np.bool_]]:
        y, x = tile_y * 8 - self.grid.top_padding, tile_x * 8
        y0, y1 = max(0, y), min(self.grid.height, y + self.patch_size)
        x1 = min(self.grid.width, x + self.patch_size)
        pad_top, pad_bottom, pad_right = y0 - y, y + self.patch_size - y1, x + self.patch_size - x1
        real = rgba[y0:y1, x:x1]
        padded = np.pad(real, ((pad_top, pad_bottom), (0, pad_right), (0, 0)), mode="edge")
        mask = np.zeros((self.patch_size, self.patch_size), dtype=bool)
        mask[pad_top : pad_top + len(real), : real.shape[1]] = True
        return padded, mask


class UnityDenseTileDataset(Dataset[dict[str, Tensor]]):
    EPSILON = 1e-10

    def __init__(
        self,
        archive: UnityTileArchive,
        corpus: Path,
        split: str,
        manifest: JsonDict,
        patch_size: int,
    ) -> None:
        if split not in ("train", "validation"):
            raise ValueError("Only V5 development splits can be opened for training")
        self.archive = archive
        self.corpus = corpus.resolve()
        self.split = split
        self.patch_size = patch_size
        self.records: list[JsonDict] = manifest["splits"][split]
        self.rows = [archive.splits[split][record["index"]] for record in self.records]
        if not self.rows or len({row["index"] for row in self.rows}) != len(self.rows):
            raise ValueError("V5 data requires a nonempty unique image selection")
        self.patches: list[tuple[int, int, int]] = []
        self.image_patch_ranges: list[range] = []
        self.grids = []
        for image, (record, row) in enumerate(zip(self.records, self.rows, strict=True)):
            if (
                record["split"] != split
                or record["binding"] != manifest["binding"]
                or row["split"] != split
                or record["asset"] != row["path"]
                or record["reference_sha256"] != row["reference_sha256"]
                or record["candidate_receipt_sha256"] != row["candidate_receipt_sha256"]
                or record["target"] != f"{split}/{row['index']:05d}.npz"
                or (patch_size == 128 and (row["width"], row["height"]) != (128, 128))
            ):
                raise ValueError("V5 corpus image identity or prototype size changed")
            geometry = UnityDensePatchGrid(UnityTileGrid(row["height"], row["width"]), patch_size)
            self.grids.append(geometry)
            start = len(self.patches)
            self.patches.extend((image, y, x) for y, x in geometry.origins())
            self.image_patch_ranges.append(range(start, len(self.patches)))

    def __len__(self) -> int:
        return len(self.patches)

    @lru_cache(maxsize=2)
    def load(self, index: int) -> tuple[NDArray[np.uint8], Tensor, UnityTileLabels]:
        row = self.rows[index]
        record = self.records[index]
        image = self.archive.image(self.split, row["index"])
        path = self.corpus / record["target"]
        if ArtifactStore.sha256_file(path) != record["target_sha256"]:
            raise ValueError(f"V5 labels changed: {path}")
        labels = UnityTileCorpus.read_labels(path, image)
        rgba = image.reference()
        metadata = torch.tensor(
            [
                np.log2(row["width"]),
                np.log2(row["height"]),
                row["import_metadata"]["srgb"],
                row["metadata"]["is_normal"],
                row["actual_options"]["need_alpha"],
                rgba[..., 3].min() == rgba[..., 3].max(),
                row["metadata"]["mip_count"],
                np.mean(np.all(rgba[..., :3] == 0, axis=2)),
            ],
            dtype=torch.float32,
        )
        return rgba, metadata, labels

    def __getitem__(self, index: int) -> dict[str, Tensor]:
        image, y, x = self.patches[index]
        rgba, metadata, labels = self.load(image)
        padded, mask = self.grids[image].extract(rgba, y, x)
        tiles = self.patch_size // 8
        active = np.s_[y : y + tiles, x : x + tiles]
        pixel_counts = mask.reshape(tiles, 8, tiles, 8).sum(axis=(1, 3))
        valid = labels.pixels[active]
        height, width = valid.shape
        if (
            not np.array_equal(pixel_counts[:height, :width], valid)
            or pixel_counts.sum() != valid.sum()
        ):
            raise ValueError("Patch pixel mask disagrees with the V5 tile counts")
        sse = labels.squared_errors[:, active[0], active[1], :].transpose(1, 2, 0, 3)
        channel_samples = np.array([1, 1, 1, 1, 3], dtype=np.float32)
        mse = np.zeros((tiles, tiles, 20, 5), dtype=np.float32)
        mse[:height, :width] = sse / (valid[..., None, None] * channel_samples * 255**2)
        return {
            "rgba": torch.from_numpy(padded).permute(2, 0, 1).float().div_(255),
            "valid_mask": torch.from_numpy(mask[None]),
            "metadata": metadata,
            "pixels": torch.from_numpy(pixel_counts),
            "log_mse": torch.from_numpy(np.log10(mse + self.EPSILON)),
            "image": torch.tensor(image),
            "origin": torch.tensor((y, x)),
        }


class UnityDenseImageSampler(Sampler[int]):
    """Shuffle image order each epoch while keeping an image's patch reads adjacent."""

    def __init__(self, dataset: UnityDenseTileDataset, seed: int) -> None:
        self.dataset = dataset
        self.generator = torch.Generator().manual_seed(seed)

    def __len__(self) -> int:
        return len(self.dataset)

    def __iter__(self) -> Iterator[int]:
        for index in torch.randperm(len(self.dataset.image_patch_ranges), generator=self.generator):
            yield from self.dataset.image_patch_ranges[int(index)]
