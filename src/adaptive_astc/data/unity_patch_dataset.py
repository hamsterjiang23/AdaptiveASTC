"""Frozen Unity RGBA patch inputs and channel targets, without search-label leakage."""

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
from adaptive_astc.data.patch_targets import PatchErrorGrid
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.patch_targets import UnityChannelErrors
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class UnityPatchDataset(Dataset[dict[str, Tensor]]):
    """Expose patch SSE supervision separately from nonadditive image quality targets."""

    METADATA_NAMES = (
        "log2_width",
        "log2_height",
        "srgb",
        "normal",
        "need_alpha",
        "alpha_constant",
        "normal_metric_mips",
        "black_pixel_ratio",
    )

    def __init__(self, corpus: Path, split: str, *, expected_sha256: str) -> None:
        if split not in {"train", "validation"}:
            raise ValueError("Unity development Dataset does not open test or calibration")
        path = corpus / "corpus.json"
        if ArtifactStore.sha256_file(path) != expected_sha256:
            raise ValueError("Frozen Unity corpus SHA differs from the experiment configuration")
        document = ArtifactStore.read_json(path)
        if (
            document["status"] != "passed"
            or document["test_opened"] is not False
            or document["config"]["schema"] != "unity-rgba-channel-sse-v1"
            or set(document["splits"]) != {"train", "validation"}
            or ArtifactStore.fingerprint(document["config"]) != document["binding"]
            or ArtifactStore.fingerprint(
                {"binding": document["binding"], "splits": document["splits"]}
            )
            != document["fingerprint"]
        ):
            raise ValueError("Require an intact, completed native RGBA development corpus")
        identities: set[str] = set()
        for name, rows in document["splits"].items():
            if len(rows) != document["counts"][name]:
                raise ValueError("Unity corpus split count changed")
            for row in rows:
                key = row["path"].replace("\\", "/").casefold()
                if (
                    row["split"] != name
                    or row["binding"] != document["binding"]
                    or key in identities
                ):
                    raise ValueError("Unity asset split, binding or uniqueness changed")
                identities.add(key)
        self.rows: list[JsonDict] = document["splits"][split]
        if not self.rows:
            raise ValueError("Requested Unity development split is empty")
        self.fingerprint: str = document["fingerprint"]
        self.corpus_sha256 = expected_sha256
        self.split = split
        self.patch_size: int = document["config"].get("patch_size", 240)
        grid = PatchErrorGrid(self.patch_size)
        expected_grid = [[b, p] for b in UnityASTCBackend.BLOCKS for p in UnityASTCBackend.PRESETS]
        self.candidate_grid = expected_grid
        boxes, errors, image_ids, metadata = [], [], [], []
        self.reconstructed_psnr: list[NDArray[np.float64]] = []
        for image_id, row in enumerate(self.rows):
            if row["candidate_grid"] != expected_grid or len(row["image_quality"]) != 20:
                raise ValueError("Unity targets must retain the canonical ordered20 candidate grid")
            for file_key, sha_key in [
                ("reference", "reference_sha256"),
                ("targets", "target_sha256"),
            ]:
                if ArtifactStore.sha256_file(Path(row[file_key])) != row[sha_key]:
                    raise ValueError(f"Frozen Unity {file_key} changed")
            with np.load(row["targets"], allow_pickle=False) as archive:
                image_boxes = archive["boxes"]
                channel_errors = archive["channel_squared_errors"]
            expected_boxes = grid.boxes(row["width"], row["height"])
            if (
                not np.array_equal(image_boxes, expected_boxes)
                or len(image_boxes) != row["patch_count"]
                or row["pixel_count"] != row["width"] * row["height"]
                or channel_errors.dtype != np.int64
                or channel_errors.shape != (len(image_boxes), 20, 4)
                or (channel_errors < 0).any()
            ):
                raise ValueError("Unity patch geometry or channel SSE changed")
            pixels = image_boxes[:, 2] * image_boxes[:, 3]
            if np.any(channel_errors > pixels[:, None, None] * 255**2):
                raise ValueError("Unity byte-channel SSE exceeds its physical range")
            total = channel_errors.sum(axis=0)
            if total.tolist() != row["full_channel_squared_errors"]:
                raise ValueError("Patch SSE no longer reconstructs the recorded full image")
            meta = row["metadata"]
            actual = row["actual_options"]
            if (
                meta["is_hdr"] is not False
                or actual["profile"] not in {0, 1}
                or actual["channel"] != 4
                or (actual["width"], actual["height"]) != (row["width"], row["height"])
                or actual["need_alpha"] != meta["need_alpha"]
                or (actual["profile"] == 0) != row["import_metadata"]["srgb"]
                or meta["is_normal"] != (actual["texture_type_importer"] == "NormalMap")
                or row["original_selection"]["asset"].replace("\\", "/").casefold()
                != row["path"].replace("\\", "/").casefold()
                or not row["original_selection"]["search_executed"]
                or row["original_selection"]["cache_hit"]
            ):
                raise ValueError(
                    "Captured Unity input metadata or original search identity changed"
                )
            reference = self._pixels(image_id)
            black = float(np.mean(np.all(reference[:, :, :3] == 0, axis=2)))
            if (
                reference.shape != (row["height"], row["width"], 4)
                or bool(reference[:, :, 3].min() == reference[:, :, 3].max())
                != row["alpha_constant"]
                or black != row["black_pixel_ratio"]
            ):
                raise ValueError("Unity reference pixels disagree with input-only metadata")
            psnr = UnityChannelErrors.psnr(
                total,
                row["pixel_count"],
                need_alpha=meta["need_alpha"],
                alpha_constant=row["alpha_constant"],
            )
            expected = np.array([quality["psnr"] for quality in row["image_quality"]])
            if not np.isfinite(expected).all() or np.max(np.abs(psnr - expected)) > 1e-5:
                raise ValueError("Unity native PSNR disagrees with channel supervision")
            self.reconstructed_psnr.append(psnr)
            boxes.append(image_boxes)
            errors.append(channel_errors)
            image_ids.append(np.full(len(image_boxes), image_id, dtype=np.int64))
            metadata.append(
                [
                    np.log2(row["width"]),
                    np.log2(row["height"]),
                    actual["profile"] == 0,
                    meta["is_normal"],
                    meta["need_alpha"],
                    row["alpha_constant"],
                    meta["mip_count"] if meta["is_normal"] else 1,
                    black,
                ]
            )
        self.boxes = np.concatenate(boxes)
        self.errors = np.concatenate(errors)
        self.image_ids = np.concatenate(image_ids)
        self.pixel_counts = self.boxes[:, 2] * self.boxes[:, 3]
        self.mse = self.errors.astype(np.float64) / (self.pixel_counts[:, None, None] * 255**2)
        self.targets = np.log10(self.mse + 1e-10).astype(np.float32)
        self.zero_error = self.errors == 0
        self.input_metadata = np.asarray(metadata, dtype=np.float32)
        if len(self.boxes) != document["patch_counts"][split]:
            raise ValueError("Unity corpus patch count changed")

    def __len__(self) -> int:
        return len(self.boxes)

    @lru_cache(maxsize=2)
    def _pixels(self, image_id: int) -> NDArray[np.uint8]:
        with Image.open(self.rows[image_id]["reference"]) as image:
            return np.asarray(image.convert("RGBA"), dtype=np.uint8)

    def __getitem__(self, index: int) -> dict[str, Tensor]:
        image_id = int(self.image_ids[index])
        x, y, width, height = self.boxes[index]
        patch = self._pixels(image_id)[y : y + height, x : x + width]
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
            "channel_log_mse": torch.from_numpy(self.targets[index]),
            "channel_zero_error": torch.from_numpy(self.zero_error[index]),
            "valid_pixels": torch.tensor(int(width * height), dtype=torch.int64),
            "patch_index": torch.tensor(index, dtype=torch.int64),
            "image_index": torch.tensor(image_id, dtype=torch.int64),
        }
