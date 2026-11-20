"""Primary-view L* step concentration benchmark on pre-decoded Unity candidates."""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray

from adaptive_astc.data.unity_tile_errors import UnityTileViews


class UnityGradientStep:
    WINDOW = 16
    STRIDE = 4
    MIN_WINDOWS = 8

    @classmethod
    def score(
        cls, reference: NDArray[np.uint8], decoded: NDArray[np.uint8]
    ) -> tuple[float | None, int]:
        """Return the historical L_p95_primary value and its window count."""
        if reference.shape != decoded.shape or reference.ndim != 3 or reference.shape[2] != 3:
            raise ValueError("Expected aligned RGB reference and decode")
        mask = UnityTileViews.smooth_mask(reference)
        ref = UnityTileViews.lab(reference)[..., 0].copy()
        dec = UnityTileViews.lab(decoded)[..., 0].copy()
        horizontal = cls.window_scores(ref, dec, mask)
        vertical = cls.window_scores(ref.T, dec.T, mask.T)
        count = len(horizontal) + len(vertical)
        if count < cls.MIN_WINDOWS:
            return None, count
        return float(np.quantile(np.concatenate((horizontal, vertical)), 0.95)), count

    @classmethod
    def window_scores(cls, ref: np.ndarray, dec: np.ndarray, mask: np.ndarray) -> np.ndarray:
        # Keep the historical exclusive right-edge start convention for this control.
        starts = np.arange(0, ref.shape[1] - cls.WINDOW, cls.STRIDE)
        if not len(starts):
            return np.empty(0)
        masked_count = np.pad(np.cumsum(mask, axis=1, dtype=np.int32), ((0, 0), (1, 0)))
        ends = starts + cls.WINDOW
        inside = masked_count[:, ends] - masked_count[:, starts] == cls.WINDOW
        if not inside.any():
            return np.empty(0)
        ref_steps = sliding_window_view(np.abs(np.diff(ref, axis=1)), cls.WINDOW - 1, axis=1)
        rows, cols = np.nonzero(inside)
        selected = ref_steps[rows, starts[cols]]
        tv_ref = selected.sum(axis=1)
        netto = np.abs(ref[rows, ends[cols] - 1] - ref[rows, starts[cols]])
        keep = (tv_ref >= 4) & (netto >= 0.8 * tv_ref)
        total = tv_ref[keep]
        if not len(total):
            return np.empty(0)
        dec_steps = sliding_window_view(np.abs(np.diff(dec, axis=1)), cls.WINDOW - 1, axis=1)
        dec_selected = dec_steps[rows[keep], starts[cols[keep]]]
        concentration_ref = selected[keep].max(axis=1) / total
        concentration_dec = dec_selected.max(axis=1) / np.maximum(dec_selected.sum(axis=1), 1e-9)
        return np.maximum(0, concentration_dec - concentration_ref) * total
