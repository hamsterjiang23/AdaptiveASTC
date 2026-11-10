"""Torch dataset and loader construction for prepared texture views."""

from pathlib import Path

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

from adaptive_astc.config import SEED, JsonDict


class TextureDataset(Dataset[tuple[Tensor, int]]):
    def __init__(self, run_dir: Path, rows: list[JsonDict]) -> None:
        self.run_dir = run_dir
        self.rows = rows
        self.mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[Tensor, int]:
        row = self.rows[index]
        pixels = np.load(self.run_dir / row["cache"], allow_pickle=False)
        tensor = torch.from_numpy(pixels).permute(2, 0, 1).float().div_(255)
        return (tensor - self.mean) / self.std, int(row["class_id"])


class TextureDataModule:
    """Bind a cache root and worker policy to reproducibly seeded loaders."""

    def __init__(self, run_dir: Path, workers: int = 2) -> None:
        self.run_dir = run_dir
        self.workers = workers

    def loader(
        self, rows: list[JsonDict], batch_size: int, shuffle: bool = False, seed: int = SEED
    ) -> DataLoader:
        generator = torch.Generator().manual_seed(seed)
        return DataLoader(
            TextureDataset(self.run_dir, rows),
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=self.workers,
            pin_memory=torch.cuda.is_available(),
            generator=generator,
            persistent_workers=False,
        )
