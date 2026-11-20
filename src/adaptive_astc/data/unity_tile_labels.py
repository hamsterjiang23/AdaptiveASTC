"""Exact per-candidate tile labels before any training-time transformation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from adaptive_astc.data.unity_tile_archive import UnityTileImage
from adaptive_astc.data.unity_tile_errors import UnityTileGrid, UnityTileViews


@dataclass(frozen=True)
class UnityTileLabels:
    """Store native channel SSE and summed display RGB SSE, in 8-bit code units."""

    grid: UnityTileGrid
    pixels: NDArray[np.uint8]
    content: NDArray[np.bool_]
    smooth: NDArray[np.bool_]
    squared_errors: NDArray[np.uint32]

    CHANNELS = ("native_r", "native_g", "native_b", "native_a", "display_rgb_sum")

    @classmethod
    def measure(cls, image: UnityTileImage) -> UnityTileLabels:
        row = image.row
        reference = image.reference()
        grid = UnityTileGrid(row["height"], row["width"])
        pixels = grid.counts()
        if pixels.sum() != row["pixel_count"] or not np.all((pixels >= 1) & (pixels <= 64)):
            raise ValueError("Tile counts do not cover the reference's exact pixel extent")
        need_alpha = row["metadata"]["need_alpha"]
        display = UnityTileViews.display(reference, need_alpha)
        rgb_min = grid.reduce(display.min(axis=2), np.minimum)
        rgb_max = grid.reduce(display.max(axis=2), np.maximum)
        content = rgb_max - rgb_min >= 2
        smooth_pixels = UnityTileViews.smooth_mask(display)
        smooth = 2 * grid.reduce(smooth_pixels, np.add) >= pixels
        selected = row["original_selection"]
        errors = np.empty(
            (len(image.candidates), *pixels.shape, len(cls.CHANNELS)), dtype=np.uint32
        )
        oriented = False
        for candidate_index, candidate in enumerate(image.candidates):
            decoded = image.decode(candidate)
            block, preset = candidate["block"], candidate["preset"]
            if (f"{block}x{block}", preset) == (selected["block_size"], selected["preset"]):
                image.verify_selected_orientation(decoded)
                oriented = True
            rgba = grid.squared_errors(reference, decoded)
            errors[candidate_index, ..., :4] = rgba
            rgb = (
                grid.squared_errors(display, UnityTileViews.display(decoded, need_alpha))
                if need_alpha
                else rgba[..., :3]
            )
            errors[candidate_index, ..., 4] = rgb.sum(axis=2, dtype=np.uint32)
        if not oriented:
            raise ValueError("Original choice is absent from the V5 grid")
        labels = cls(grid, pixels.astype(np.uint8), content, smooth, errors)
        labels.verify(row["full_channel_squared_errors"])
        return labels

    def verify(self, native_totals: list[list[int]]) -> None:
        dims = self.pixels.shape
        if (
            self.pixels.dtype != np.uint8
            or not np.array_equal(self.pixels, self.grid.counts())
            or self.content.shape != dims
            or self.content.dtype != np.bool_
            or self.smooth.shape != dims
            or self.smooth.dtype != np.bool_
            or self.squared_errors.shape != (20, *dims, len(self.CHANNELS))
            or self.squared_errors.dtype != np.uint32
        ):
            raise ValueError("Tile label shape, data type or valid counts changed")
        max_sse = self.pixels.astype(np.uint32) * 255**2
        if np.any(self.squared_errors[..., :4] > max_sse[..., None]) or np.any(
            self.squared_errors[..., 4] > 3 * max_sse
        ):
            raise ValueError("Tile SSE exceeds the valid 8-bit sample range")
        if self.squared_errors[..., :4].sum(axis=(1, 2)).tolist() != native_totals:
            raise ValueError("Tile totals differ from the original native patch SSE")
