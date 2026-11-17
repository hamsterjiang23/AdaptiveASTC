"""Source-only inputs predicting Unity targets without reading Unity reference pixels."""

from __future__ import annotations

import hashlib
import io
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image
from PIL import __version__ as pillow_version
from torch import Tensor
from torch.utils.data import Dataset

from adaptive_astc.config import JsonDict
from adaptive_astc.data.patch_targets import PatchErrorGrid
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore

SourceInputMode = Literal["source_native", "source_aligned"]


@dataclass(frozen=True, eq=False)
class SourceTextureSpec:
    """Explicit source identity and target import settings; no supervision fields.

    Width/height fields in network metadata and policy inputs always describe the
    target Unity texture. ``source_native`` changes the patch grid only. Memory
    input is copied at construction so caller mutation cannot change this spec.
    ``file_sha256`` hashes encoded source-file bytes, not decoded pixels.
    """

    source: Path | NDArray[np.uint8]
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    srgb: bool
    normal: bool
    need_alpha: bool
    normal_metric_mips: int = 1
    asset: str | None = None
    file_sha256: str | None = None

    def __post_init__(self) -> None:
        dimensions = (
            self.source_width,
            self.source_height,
            self.target_width,
            self.target_height,
        )
        if any(type(value) is not int or value < 1 for value in dimensions):
            raise ValueError("Positive explicit source and target dimensions required")
        if any(type(value) is not bool for value in (self.srgb, self.normal, self.need_alpha)):
            raise ValueError("Source importer flags must be boolean")
        if (
            type(self.normal_metric_mips) is not int
            or not 1 <= self.normal_metric_mips <= 4
            or (not self.normal and self.normal_metric_mips != 1)
            or (self.normal and self.srgb)
        ):
            raise ValueError("Source inputs require valid Linear normal/mip scope")
        if self.asset is not None and (not isinstance(self.asset, str) or not self.asset.strip()):
            raise ValueError("An explicit source asset identity cannot be empty")
        if self.file_sha256 is not None and (
            not isinstance(self.file_sha256, str)
            or len(self.file_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.file_sha256)
            or not isinstance(self.source, Path)
        ):
            raise ValueError("file_sha256 requires a source Path and lowercase SHA256")
        if isinstance(self.source, np.ndarray):
            self.validate_rgba(self.source)
            pixels = np.array(self.source, dtype=np.uint8, order="C", copy=True)
            if pixels.shape[:2] != (self.source_height, self.source_width):
                raise ValueError("Memory source dimensions differ from the declared source")
            pixels.setflags(write=False)
            object.__setattr__(self, "source", pixels)
        elif not isinstance(self.source, Path):
            raise TypeError("Source must be a Path or an explicit RGBA8 numpy array")

    @staticmethod
    def validate_rgba(pixels: NDArray[np.uint8]) -> None:
        if (
            pixels.dtype != np.uint8
            or pixels.ndim != 3
            or pixels.shape[2] != 4
            or min(pixels.shape[:2]) < 1
        ):
            raise ValueError("Source memory requires nonempty height x width x 4 RGBA8")

    @classmethod
    def from_file(
        cls,
        source: Path,
        *,
        target_width: int,
        target_height: int,
        srgb: bool,
        normal: bool,
        need_alpha: bool,
        normal_metric_mips: int = 1,
        asset: str | None = None,
        file_sha256: str | None = None,
    ) -> SourceTextureSpec:
        with Image.open(source) as image:
            width, height = image.size
        return cls(
            source,
            width,
            height,
            target_width,
            target_height,
            srgb,
            normal,
            need_alpha,
            normal_metric_mips,
            asset,
            file_sha256,
        )

    @classmethod
    def from_rgba(
        cls,
        rgba: NDArray[np.uint8],
        *,
        target_width: int,
        target_height: int,
        srgb: bool,
        normal: bool,
        need_alpha: bool,
        normal_metric_mips: int = 1,
        asset: str | None = None,
    ) -> SourceTextureSpec:
        cls.validate_rgba(rgba)
        return cls(
            rgba,
            int(rgba.shape[1]),
            int(rgba.shape[0]),
            target_width,
            target_height,
            srgb,
            normal,
            need_alpha,
            normal_metric_mips,
            asset,
        )

    def decoded_pixels(self) -> NDArray[np.uint8]:
        """Decode in display row order; do not apply EXIF transforms or Unity processing."""
        return self.read_pixels()[0]

    def source_digest(self) -> str:
        if isinstance(self.source, Path):
            return ArtifactStore.sha256_file(self.source)
        return hashlib.sha256(self.source.tobytes()).hexdigest()

    def read_pixels(self) -> tuple[NDArray[np.uint8], str]:
        """Return decoded pixels and the identity of the bytes actually read."""
        if isinstance(self.source, Path):
            raw = self.source.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if self.file_sha256 is not None:
                if digest != self.file_sha256:
                    raise ValueError("Frozen source file SHA256 changed")
            with Image.open(io.BytesIO(raw)) as image:
                if image.size != (self.source_width, self.source_height):
                    raise ValueError("Source file dimensions differ from the declared source")
                pixels = np.array(image.convert("RGBA"), dtype=np.uint8, order="C", copy=True)
            pixels.setflags(write=False)
            return pixels, digest
        return self.source, self.source_digest()


class UnityV3InferenceInput(Dataset[dict[str, Tensor]]):
    """V2-compatible inference tensors derived exclusively from source pixels/settings."""

    def __init__(
        self,
        specs: list[SourceTextureSpec],
        mode: SourceInputMode = "source_aligned",
        patch_size: int = 240,
    ) -> None:
        if not specs or mode not in {"source_native", "source_aligned"}:
            raise ValueError("Nonempty source specs and an explicit supported source mode required")
        if type(patch_size) is not int:
            raise ValueError("Patch size must be an integer")
        grid = PatchErrorGrid(patch_size)
        self.textures = list(specs)
        self.mode = mode
        self.patch_size = patch_size
        self.timings = {"pixel_load_seconds": 0.0, "resize_seconds": 0.0}
        self.source_hashes: dict[int, str] = {}
        self.sizes: list[tuple[int, int]] = []
        self.source_sizes = [(spec.source_width, spec.source_height) for spec in specs]
        self.decision_inputs: list[UnityTextureInput] = []
        self.bindings: list[JsonDict] = []
        boxes, image_ids, metadata = [], [], []
        for image_id, spec in enumerate(specs):
            pixels = self.pixels(image_id)
            height, width = pixels.shape[:2]
            self.sizes.append((width, height))
            image_boxes = grid.boxes(width, height)
            boxes.append(image_boxes)
            image_ids.append(np.full(len(image_boxes), image_id, dtype=np.int64))
            alpha_constant = bool(pixels[:, :, 3].min() == pixels[:, :, 3].max())
            black = float(np.mean(np.all(pixels[:, :, :3] == 0, axis=2)))
            self.decision_inputs.append(
                UnityTextureInput(
                    spec.target_width,
                    spec.target_height,
                    spec.srgb,
                    spec.normal,
                    spec.need_alpha,
                    alpha_constant,
                    black,
                )
            )
            metadata.append(
                [
                    np.log2(spec.target_width),
                    np.log2(spec.target_height),
                    spec.srgb,
                    spec.normal,
                    spec.need_alpha,
                    alpha_constant,
                    spec.normal_metric_mips,
                    black,
                ]
            )
            self.bindings.append(
                {
                    "asset": spec.asset,
                    "source": str(spec.source.resolve())
                    if isinstance(spec.source, Path)
                    else "memory",
                    "source_size": [spec.source_width, spec.source_height],
                    "target_size": [spec.target_width, spec.target_height],
                    "input_size": [width, height],
                    "file_sha256": spec.file_sha256,
                    "source_sha256": self.source_hashes[image_id],
                    "input_rgba_sha256": hashlib.sha256(pixels.tobytes()).hexdigest(),
                    "srgb": spec.srgb,
                    "normal": spec.normal,
                    "need_alpha": spec.need_alpha,
                    "normal_metric_mips": spec.normal_metric_mips,
                    "alpha_constant": alpha_constant,
                    "black_pixel_ratio": black,
                }
            )
        self.boxes = np.concatenate(boxes)
        self.image_ids = np.concatenate(image_ids)
        self.pixel_counts = self.boxes[:, 2] * self.boxes[:, 3]
        self.input_metadata = np.asarray(metadata, dtype=np.float32)
        self.protocol: JsonDict = {
            "schema": "unity-v3-source-input-v1",
            "mode": mode,
            "patch_size": patch_size,
            "pillow_version": pillow_version,
            "decode": "Pillow convert RGBA; display row order; no EXIF transform",
            "resize": "BICUBIC to explicit target size" if mode == "source_aligned" else "none",
            "metadata_dimensions": "explicit target width/height",
            "pixel_statistics": "model input pixels only",
        }
        self.fingerprint = ArtifactStore.fingerprint(
            {
                "protocol": self.protocol,
                "inputs": self.bindings,
            }
        )

    def __len__(self) -> int:
        return len(self.boxes)

    def verify_sources(self) -> None:
        """Recheck source identities without opening Unity pixels or supervision."""
        for image_id, spec in enumerate(self.textures):
            if spec.source_digest() != self.source_hashes[image_id]:
                raise ValueError("Source identity changed after input construction")

    @lru_cache(maxsize=2)
    def pixels(self, image_id: int) -> NDArray[np.uint8]:
        spec = self.textures[image_id]
        started = time.perf_counter()
        pixels, digest = spec.read_pixels()
        if image_id in self.source_hashes and self.source_hashes[image_id] != digest:
            raise ValueError("Source identity changed during input iteration")
        self.source_hashes[image_id] = digest
        self.timings["pixel_load_seconds"] += time.perf_counter() - started
        if self.mode == "source_aligned" and pixels.shape[:2] != (
            spec.target_height,
            spec.target_width,
        ):
            started = time.perf_counter()
            image = Image.fromarray(pixels).resize(
                (spec.target_width, spec.target_height),
                resample=Image.Resampling.BICUBIC,
            )
            pixels = np.array(image, dtype=np.uint8, order="C", copy=True)
            pixels.setflags(write=False)
            self.timings["resize_seconds"] += time.perf_counter() - started
        return pixels

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
