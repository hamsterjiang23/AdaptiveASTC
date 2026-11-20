"""Exact mip0 errors on the bottom-anchored V5 analysis grid."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import correlate1d, uniform_filter, uniform_filter1d


@dataclass(frozen=True)
class UnityTileGrid:
    height: int
    width: int
    size: int = 8

    def __post_init__(self) -> None:
        if min(self.height, self.width, self.size) < 1:
            raise ValueError("Tile grid dimensions must be positive")

    @property
    def top_padding(self) -> int:
        return -self.height % self.size

    @property
    def rows(self) -> NDArray[np.intp]:
        return np.r_[0, np.arange(self.size - self.top_padding, self.height, self.size)]

    @property
    def columns(self) -> NDArray[np.intp]:
        return np.arange(0, self.width, self.size)

    def counts(self) -> NDArray[np.int64]:
        return np.multiply.outer(
            np.diff(self.rows, append=self.height), np.diff(self.columns, append=self.width)
        )

    def reduce(self, values: np.ndarray, operation: np.ufunc) -> np.ndarray:
        if values.shape[:2] != (self.height, self.width):
            raise ValueError("Array dimensions differ from the tile grid")
        return operation.reduceat(operation.reduceat(values, self.columns, axis=1), self.rows)

    def squared_errors(
        self, reference: NDArray[np.uint8], decoded: NDArray[np.uint8]
    ) -> NDArray[np.uint32]:
        if reference.shape != decoded.shape or reference.ndim != 3:
            raise ValueError("Tile error inputs must have matching HWC dimensions")
        difference = np.subtract(reference, decoded, dtype=np.int16)
        squared = np.square(difference, dtype=np.int32)
        return self.reduce(squared, np.add).astype(np.uint32)

    @staticmethod
    def psnr(sse: np.ndarray, samples: np.ndarray) -> NDArray[np.float64]:
        with np.errstate(divide="ignore"):
            return 10 * np.log10(255.0**2 * samples / sse)


class UnityTileViews:
    """Match the encoded-RGB and linear-light gray composite used in visual review."""

    _encoded = np.arange(256, dtype=np.float64) / 255
    _linear = np.where(_encoded <= 0.04045, _encoded / 12.92, ((_encoded + 0.055) / 1.055) ** 2.4)
    _xyz = (
        np.array(
            [
                [0.4124564, 0.3575761, 0.1804375],
                [0.2126729, 0.7151522, 0.0721750],
                [0.0193339, 0.1191920, 0.9503041],
            ]
        )
        / np.array([0.95047, 1.0, 1.08883])[:, None]
    )

    @classmethod
    def display(cls, rgba: NDArray[np.uint8], need_alpha: bool) -> NDArray[np.uint8]:
        rgb = rgba[..., :3]
        if not need_alpha:
            return rgb
        alpha = rgba[..., 3:] / 255
        linear = alpha * cls._linear[rgb] + (1 - alpha) * cls._linear[64]
        encoded = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)
        return np.rint(encoded * 255).clip(0, 255).astype(np.uint8)

    @classmethod
    def lab(cls, rgb: NDArray[np.uint8]) -> NDArray[np.float64]:
        xyz = cls._linear[rgb] @ cls._xyz.T
        delta = 6 / 29
        f = np.where(xyz > delta**3, np.cbrt(xyz), xyz / (3 * delta**2) + 4 / 29)
        x, y, z = np.moveaxis(f, -1, 0)
        return np.stack((116 * y - 16, 500 * (x - y), 200 * (y - z)), axis=-1)

    @classmethod
    def smooth_mask(cls, rgb: NDArray[np.uint8]) -> NDArray[np.bool_]:
        """Run the review gradient mask in strips with seven-pixel halos."""
        height, width = rgb.shape[:2]
        mask = np.zeros((height, width), dtype=bool)
        for start in range(0, height, 128):
            stop = min(start + 128, height)
            first, last = max(0, start - 7), min(height, stop + 7)
            lab = cls.lab(rgb[first:last])
            for window in (7, 15):
                if min(height, width) < window:
                    continue
                radius = window // 2
                y0, y1 = max(start, radius), min(stop, height - radius)
                if y0 >= y1:
                    continue
                axis = np.arange(-radius, radius + 1, dtype=float)
                kernel = axis / np.dot(axis, axis)
                mean = uniform_filter(lab, window, mode="nearest", axes=(0, 1))
                variance = np.sum(
                    uniform_filter(lab**2, window, mode="nearest", axes=(0, 1)) - mean**2, axis=2
                )
                dx = uniform_filter1d(
                    correlate1d(lab, kernel, axis=1, mode="nearest"), window, axis=0, mode="nearest"
                )
                dy = uniform_filter1d(
                    correlate1d(lab, kernel, axis=0, mode="nearest"), window, axis=1, mode="nearest"
                )
                slope_sq = np.sum(dx**2 + dy**2, axis=2)
                good = (np.mean(axis**2) * slope_sq >= 0.85 * np.maximum(variance, 1e-9)) & (
                    (window - 1) ** 2 * slope_sq >= 4
                )
                mask[y0:y1, radius:-radius] |= good[y0 - first : y1 - first, radius:-radius]
        return mask
