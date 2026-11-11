"""Native RGB patches with exact per-candidate normalized MSE supervision."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image
from torch import Tensor
from torch.utils.data import Dataset

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore


class NativePatchDataset(Dataset):
    def __init__(self, corpus: Path, split: str) -> None:
        if split not in {"train", "validation"}:
            raise ValueError("Development corpus only supports train and validation")
        document = ArtifactStore.read_json(corpus / "corpus.json")
        if document["status"] != "passed":
            raise ValueError("Patch preparation is incomplete")
        if ArtifactStore.fingerprint(document["config"]) != document["binding"]:
            raise ValueError("Patch preprocessing configuration changed")
        expected = ArtifactStore.fingerprint(
            {"binding": document["binding"], "splits": document["splits"]}
        )
        if expected != document["fingerprint"]:
            raise ValueError("Patch corpus fingerprint changed")
        self.fingerprint: str = document["fingerprint"]
        self.rows: list[JsonDict] = document["splits"][split]
        self.patch_size: int = document["config"]["patch_size"]
        boxes, errors, image_ids = [], [], []
        for image_id, row in enumerate(self.rows):
            if row["binding"] != document["binding"] or row["split"] != split:
                raise ValueError("Patch row belongs to a different corpus or split")
            for file_key, hash_key in [
                ("targets", "target_sha256"),
                ("reference", "reference_sha256"),
            ]:
                if ArtifactStore.sha256_file(Path(row[file_key])) != row[hash_key]:
                    raise ValueError(f"Frozen patch input changed: {row[file_key]}")
            with np.load(row["targets"], allow_pickle=False) as targets:
                boxes.append(targets["boxes"])
                errors.append(targets["squared_errors"])
                image_ids.append(np.full(len(targets["boxes"]), image_id, dtype=np.int64))
        self.boxes = np.concatenate(boxes)
        self.errors = np.concatenate(errors)
        self.image_ids = np.concatenate(image_ids)
        self.pixel_counts = self.boxes[:, 2] * self.boxes[:, 3]
        self.mse = self.errors.astype(np.float64) / (self.pixel_counts[:, None] * 3 * 255**2)
        self.targets = np.log10(self.mse + 1e-10).astype(np.float32)
        self.mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32)[:, None, None]
        self.std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32)[:, None, None]

    def __len__(self) -> int:
        return len(self.boxes)

    @lru_cache(maxsize=2)
    def _pixels(self, image_id: int) -> NDArray[np.uint8]:
        with Image.open(self.rows[image_id]["reference"]) as image:
            return np.asarray(image.convert("RGB"), dtype=np.uint8)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, int]:
        image = self._pixels(int(self.image_ids[index]))
        x, y, width, height = self.boxes[index]
        patch = image[y : y + height, x : x + width]
        patch = np.pad(
            patch,
            ((0, self.patch_size - height), (0, self.patch_size - width), (0, 0)),
            mode="edge",
        )
        tensor = torch.from_numpy(patch.copy()).permute(2, 0, 1).float() / 255.0
        return (tensor - self.mean) / self.std, torch.from_numpy(self.targets[index]), index

    def image_balanced_weights(self) -> Tensor:
        counts = np.bincount(self.image_ids)
        return torch.from_numpy(1.0 / counts[self.image_ids])

    def aggregate(self, predicted_log_mse: NDArray[np.float64]) -> NDArray[np.float64]:
        if predicted_log_mse.shape != self.mse.shape or not np.isfinite(predicted_log_mse).all():
            raise ValueError("Every patch requires four finite log MSE predictions")
        # Byte-domain normalized squared error lies in [0,1]. Zero is represented by epsilon.
        predicted_mse = np.maximum(10.0 ** np.clip(predicted_log_mse, -10, 0) - 1e-10, 0)
        sums = np.zeros((len(self.rows), 4), dtype=np.float64)
        np.add.at(sums, self.image_ids, predicted_mse * self.pixel_counts[:, None])
        return sums / np.bincount(self.image_ids, weights=self.pixel_counts)[:, None]
