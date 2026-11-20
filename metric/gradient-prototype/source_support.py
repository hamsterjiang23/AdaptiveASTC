"""Detect smooth, directional gradients using only the reference color field."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import correlate1d, uniform_filter


def _fit_energies(field: np.ndarray, width: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the total, linear, and quadratic variance over full windows."""
    axis = np.arange(width, dtype=np.float64) - width // 2
    quadratic = axis**2 - np.mean(axis**2)
    filters = (
        np.full(width, 1.0 / width),
        axis / (width * np.sqrt(np.mean(axis**2))),
        quadratic / (width * np.sqrt(np.mean(quadratic**2))),
    )
    along_x = [correlate1d(field, kernel, axis=1, mode="nearest") for kernel in filters]
    energies = []
    for terms in (((1, 0), (0, 1)), ((2, 0), (1, 1), (0, 2))):
        energy = np.zeros(field.shape[:2], dtype=np.float64)
        for degree_x, degree_y in terms:
            coefficient = correlate1d(along_x[degree_x], filters[degree_y], axis=0, mode="nearest")
            energy += np.sum(coefficient**2, axis=2)
        energies.append(energy)
    # SciPy accepts one width per axis, including size 1 for the channel axis.
    average = uniform_filter(along_x[0], size=(width, 1, 1), mode="nearest")  # pyright: ignore[reportArgumentType]
    second_moment = uniform_filter(field**2, size=(width, width, 1), mode="nearest")  # pyright: ignore[reportArgumentType]
    variance = second_moment - average**2
    return np.maximum(0.0, variance.sum(axis=2)), energies[0], energies[1]


def _source_orientation(field: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Use a locally averaged tensor for coherence and a pixel-local normal."""
    dy = np.gradient(field, axis=0) if field.shape[0] > 1 else np.zeros_like(field)
    dx = np.gradient(field, axis=1) if field.shape[1] > 1 else np.zeros_like(field)
    xx = np.sum(dx**2, axis=2)
    yy = np.sum(dy**2, axis=2)
    xy = np.sum(dx * dy, axis=2)
    angle = 0.5 * np.arctan2(2 * xy, xx - yy)
    normal = np.stack((np.cos(angle), np.sin(angle)), axis=-1)
    xx_avg = uniform_filter(xx, size=5, mode="nearest")
    yy_avg = uniform_filter(yy, size=5, mode="nearest")
    xy_avg = uniform_filter(xy, size=5, mode="nearest")
    coherence = np.hypot(xx_avg - yy_avg, 2 * xy_avg) / np.maximum(xx_avg + yy_avg, 1e-10)
    return normal, np.clip(coherence, 0.0, 1.0), np.sqrt(xx + yy)


def source_support(field: np.ndarray) -> dict[str, np.ndarray]:
    """Return hard masks, a soft mask, and source directions for an HWC color field.

    Fit quality and amplitude are independent of the decoded image. The normal
    has x/y components and arbitrary sign. Use gradient strength to exclude
    points with no defined local direction, even if they lie on a smooth ridge.
    """
    field = np.asarray(field, dtype=np.float64)
    if field.ndim != 3 or min(field.shape) == 0:
        raise ValueError("Expected a nonempty HWC reference field")

    normal, coherence, strength = _source_orientation(field)
    shape = field.shape[:2]
    linear = np.zeros(shape, dtype=bool)
    quadratic = np.zeros(shape, dtype=bool)
    weight = np.zeros(shape, dtype=np.float64)
    fit_quality = np.zeros_like(weight)
    amplitude = np.zeros_like(weight)
    for width in (7, 11):
        if min(shape) < width:
            continue
        radius = width // 2
        interior = np.s_[radius:-radius, radius:-radius]
        variance, linear_energy, curvature_energy = _fit_energies(field, width)
        variance = np.maximum(variance[interior], 1e-10)
        linear_energy = linear_energy[interior]
        fitted_energy = linear_energy + curvature_energy[interior]
        rms = np.sqrt(fitted_energy)
        fit = np.clip(fitted_energy / variance, 0.0, 1.0)
        coherent = coherence[interior]
        linear[interior] |= (
            (linear_energy / variance >= 0.85) & (linear_energy >= 0.60**2) & (coherent >= 0.5)
        )
        quadratic[interior] |= (fit >= 0.88) & (rms >= 0.60) & (coherent >= 0.5)
        local_weight = (
            np.clip((fit - 0.76) / 0.16, 0.0, 1.0)
            * np.clip((coherent - 0.25) / 0.55, 0.0, 1.0)
            * np.clip((rms - 0.25) / 0.75, 0.0, 1.0)
        )
        weight[interior] = np.maximum(weight[interior], local_weight)
        fit_quality[interior] = np.maximum(fit_quality[interior], fit)
        amplitude[interior] = np.maximum(amplitude[interior], rms)
    return {
        "linear": linear,
        "quadratic": quadratic | linear,
        "coherence": coherence,
        "normal": normal,
        "strength": strength,
        "weight": weight,
        "fit_quality": fit_quality,
        "amplitude": amplitude,
    }
