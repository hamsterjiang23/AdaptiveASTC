"""Shared helpers (read-only inputs). lab/gradient_mask copied from tmp/gradient-diagnostics-20261119/probe.py."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import correlate1d, uniform_filter, uniform_filter1d

ROOT = Path("E:/ASTC_Compression")
OUTPUTS = ROOT / "outputs/01a1eca4-b759-74d2-82d5-2d27a4db8e18"
MEDIA = OUTPUTS / "media"
MANIFEST_PATH = ROOT / "tmp/multimetric-review-20261118/population/fixed8_manifest.json"
XYZ = np.array([[.4124564, .3575761, .1804375], [.2126729, .7151522, .0721750],
                [.0193339, .1191920, .9503041]]) / np.array([.95047, 1., 1.08883])[:, None]


@lru_cache(maxsize=1)
def _manifest() -> dict[tuple[int, str], dict]:
    return {(r["validation_index"], r["preset"]): r for r in json.loads(MANIFEST_PATH.read_bytes())}


MANIFEST = _manifest


@lru_cache(maxsize=1)
def assets() -> dict[int, dict]:
    text = (OUTPUTS / "data.js").read_text(encoding="utf-8")
    return {a["id"]: a for a in json.loads(text.split("=", 1)[1].rstrip().rstrip(";"))["assets"]}


def native_paths(idx: int, preset: str) -> tuple[Path, Path]:
    r = _manifest()[(idx, preset)]
    return Path(r["reference_path"]), Path(r["decoded_path"])


def rgba(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA"))


def rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def view_of(idx: int) -> str:
    v = assets()[idx]["views"]
    return "dark" if "dark" in v else "rgb"


def lab(pixels: np.ndarray) -> np.ndarray:
    encoded = pixels.astype(np.float64) / 255
    linear = np.where(encoded < .04045, encoded / 12.92, ((encoded + .055) / 1.055) ** 2.4)
    xyz = linear @ XYZ.T
    d = 6 / 29
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d ** 2) + 4 / 29)
    return np.stack((116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])), axis=-1)


def gradient_mask(src: np.ndarray) -> np.ndarray:
    mask = np.zeros(src.shape[:2], dtype=bool)
    for width in (7, 15):
        if min(mask.shape) < width:
            continue
        radius = width // 2
        axis = np.arange(-radius, radius + 1, dtype=float)
        var_xy = np.mean(axis ** 2)
        filt = axis / np.dot(axis, axis)
        mean = uniform_filter(src, (width, width, 1), mode="nearest")
        variance = np.sum(uniform_filter(src ** 2, (width, width, 1), mode="nearest") - mean ** 2, axis=2)
        dx = uniform_filter1d(correlate1d(src, filt, axis=1, mode="nearest"), width, axis=0, mode="nearest")
        dy = uniform_filter1d(correlate1d(src, filt, axis=0, mode="nearest"), width, axis=1, mode="nearest")
        slope_sq = np.sum(dx ** 2 + dy ** 2, axis=2)
        in_patch = np.s_[radius:-radius, radius:-radius]
        good = (var_xy * slope_sq >= .85 * np.maximum(variance, 1e-9)) & ((width - 1) ** 2 * slope_sq >= 2 ** 2)
        mask[in_patch] |= good[in_patch]
    return mask


def display_mask(idx: int) -> np.ndarray:
    return gradient_mask(lab(rgb(MEDIA / f"{idx:04d}" / f"ref-{view_of(idx)}.png")))


def s2l(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64) / 255
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def l2s(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return 255 * np.where(x <= .0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - .055)


def composite(pixels: np.ndarray, background: float | None) -> np.ndarray:
    """Straight-alpha over a flat sRGB background in linear light; None means opaque RGB."""
    p = pixels.astype(np.float64)
    if background is None:
        return p[..., :3]
    a = p[..., 3:4] / 255
    return l2s(a * s2l(p[..., :3]) + (1 - a) * s2l(np.full(3, background)))
