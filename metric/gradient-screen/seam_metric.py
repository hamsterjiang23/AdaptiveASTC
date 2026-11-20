"""Gradient-region and ASTC block-boundary scoring at the native pixel grid.

The numerical kernel is preserved from the 128x128 pilot for all-size validation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import correlate1d, label, uniform_filter, uniform_filter1d


XYZ = np.array([[.4124564, .3575761, .1804375], [.2126729, .7151522, .0721750],
                [.0193339, .1191920, .9503041]]) / np.array([.95047, 1., 1.08883])[:, None]


def rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def lab(pixels: np.ndarray) -> np.ndarray:
    encoded = pixels.astype(np.float64) / 255
    linear = np.where(encoded < .04045, encoded/12.92, ((encoded+.055)/1.055)**2.4)
    xyz = linear @ XYZ.T
    d = 6/29
    f = np.where(xyz > d**3, np.cbrt(xyz), xyz/(3*d**2) + 4/29)
    return np.stack((116*f[...,1]-16, 500*(f[...,0]-f[...,1]), 200*(f[...,1]-f[...,2])), axis=-1)


def gradient_mask(src: np.ndarray) -> np.ndarray:
    mask = np.zeros(src.shape[:2], dtype=bool)
    for width in (7, 15):
        if min(mask.shape) < width:
            continue
        radius = width//2
        axis = np.arange(-radius, radius+1, dtype=float)
        var_xy = np.mean(axis**2)
        filt = axis / np.dot(axis, axis)
        mean = uniform_filter(src, (width, width, 1), mode="nearest")
        variance = np.sum(uniform_filter(src**2, (width, width, 1), mode="nearest")-mean**2, axis=2)
        dx = uniform_filter1d(correlate1d(src, filt, axis=1, mode="nearest"), width, axis=0, mode="nearest")
        dy = uniform_filter1d(correlate1d(src, filt, axis=0, mode="nearest"), width, axis=1, mode="nearest")
        slope_sq = np.sum(dx**2 + dy**2, axis=2)
        in_patch = np.s_[radius:-radius, radius:-radius]
        good = (var_xy*slope_sq >= .85*np.maximum(variance, 1e-9)) & ((width-1)**2*slope_sq >= 2**2)
        mask[in_patch] |= good[in_patch]
    return mask


def evaluate(src: np.ndarray, dst: np.ndarray, mask: np.ndarray, block: int) -> tuple[dict[str, float | None], np.ndarray]:
    damaged = np.zeros(mask.shape, dtype=float)
    errors = []
    seams = []
    line_scores = []
    run = 4  # Use the same native-pixel segment length across all tested footprints.
    best_line: tuple[float, int, int, int] | None = None
    for axis in (0, 1):
        r = np.swapaxes(src, axis, 0)
        d = np.swapaxes(dst, axis, 0)
        m = np.swapaxes(mask, axis, 0)
        support = m[1:] & m[:-1]
        grad_ref = np.diff(r, axis=0)
        grad_dec = np.diff(d, axis=0)
        discrepancy = np.linalg.norm(grad_dec-grad_ref, axis=2)
        errors.append(discrepancy[support])
        plane = np.swapaxes(damaged, axis, 0)
        np.maximum(plane[1:], np.where(support, discrepancy, 0), out=plane[1:])
        extra = np.maximum(0, np.linalg.norm(grad_dec, axis=2)-np.linalg.norm(grad_ref, axis=2))
        positions = np.arange(1, len(r))
        native = len(r)-positions if axis == 0 else positions
        for k in np.flatnonzero((native % block == 0) & (positions >= 2) & (positions <= len(r)-2)):
            valid = support[k] & support[k-1] & support[k+1]
            surplus = np.maximum(0, extra[k] - (extra[k-1]+extra[k+1])/2)
            seams.append(surplus[valid])
            if len(valid) >= run:
                segment = np.lib.stride_tricks.sliding_window_view(surplus,run)
                accepted = np.lib.stride_tricks.sliding_window_view(valid,run).all(axis=1)
                if accepted.any():
                    minima = np.where(accepted,np.min(segment,axis=1),-np.inf)
                    start = int(minima.argmax())
                    value = float(minima[start])
                    line_scores.append(value)
                    if best_line is None or value > best_line[0]:
                        best_line = (value,axis,int(k)+1,start)
    err = np.concatenate(errors)
    grid = np.concatenate(seams) if seams else np.array([])
    labels, ncomp = label(mask)
    largest = int(np.bincount(labels[mask]).max()) if ncomp else 0
    return {"gradient_area_pct": float(100*mask.mean()), "largest_component_px": largest,
            "gradient_change_p95": float(np.quantile(err,.95)) if err.size else None,
            "grid_excess_p95": float(np.quantile(grid,.95)) if grid.size else None,
            "continuous_seam": max(line_scores,default=None),
            "seam_x": (best_line[2] if best_line[1] else best_line[3]) if best_line else None,
            "seam_y": (best_line[3] if best_line[1] else best_line[2]) if best_line else None}, damaged
