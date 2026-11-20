"""Full-reference distortion scores on a source-derived gradient field."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates


def effective_support(weights: np.ndarray) -> float:
    """Count weighted samples using the Kish effective sample size."""
    total = float(weights.sum())
    sum_squared = float(np.square(weights).sum())
    return total**2 / sum_squared if sum_squared > 0 else 0.0


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float | None:
    """Return the first value whose cumulative weight reaches the quantile."""
    valid = weights > 0
    if not valid.any():
        return None
    values, weights = values[valid], weights[valid]
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    index = np.searchsorted(cumulative, quantile * cumulative[-1])
    return float(values[order[index]])


def tangential_error(residual: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Measure new color-gradient variation following the original contour."""
    residual_y, residual_x = np.gradient(residual, axis=(0, 1))
    tangent_x = -normal[..., 1, None]
    tangent_y = normal[..., 0, None]
    return np.linalg.norm(residual_x * tangent_x + residual_y * tangent_y, axis=2)


def sample_profiles(field: np.ndarray, coordinates: np.ndarray) -> np.ndarray:
    return np.stack(
        [
            map_coordinates(channel, coordinates, order=1, prefilter=False)
            for channel in np.moveaxis(field, -1, 0)
        ],
        axis=-1,
    )


def normal_steps(
    reference: np.ndarray,
    decoded: np.ndarray,
    normal: np.ndarray,
    weights: np.ndarray,
) -> dict[str, float | int | None]:
    """Find overshoot next to a flattened part of a monotone source profile."""
    empty = {
        "normal_step_p95": None,
        "normal_step_p99": None,
        "normal_step_peak": None,
        "normal_step_x": None,
        "normal_step_y": None,
        "normal_step_samples": 0,
    }
    height, width = weights.shape
    y, x = np.nonzero(weights >= 0.05)
    interior = (x >= 3) & (x < width - 3) & (y >= 3) & (y < height - 3)
    y, x = y[interior], x[interior]
    if x.size == 0:
        return empty

    # Five unit-pixel intervals, centered around the potentially enlarged step.
    # Bilinear sampling permits arbitrary directions on the native image grid.
    distance = np.arange(-2.5, 3.0, dtype=float)
    nx, ny = normal[y, x].T
    coordinates = np.stack(
        (y[:, None] + ny[:, None] * distance, x[:, None] + nx[:, None] * distance)
    )
    source_step = np.diff(sample_profiles(reference, coordinates), axis=1)
    test_step = np.diff(sample_profiles(decoded, coordinates), axis=1)
    source_size = np.linalg.norm(source_step, axis=2)
    center_direction = source_step[:, 2] / np.maximum(source_size[:, 2, None], 1e-12)
    alignment = np.sum(source_step * center_direction[:, None], axis=2)
    eligible = np.all((source_size >= 0.10) & (alignment >= 0.80 * source_size), axis=1)
    if not eligible.any():
        return empty

    source_step, source_size = source_step[eligible], source_size[eligible]
    test_step = test_step[eligible]
    x, y = x[eligible], y[eligible]
    projection = np.sum(test_step * source_step, axis=2) / source_size
    # Use the vector norm to distinguish a flat region from a hue change in a
    # different direction. Give tolerance to small changes on the plateau.
    attenuation = np.clip(1 - np.linalg.norm(test_step, axis=2) / (0.35 * source_size), 0, 1)
    plateau = np.maximum(attenuation[:, :2].mean(axis=1), attenuation[:, 3:].mean(axis=1))
    scores = plateau * np.maximum(0, projection[:, 2] - source_size[:, 2])
    peak = int(np.argmax(scores))
    has_peak = scores[peak] > 0
    return {
        "normal_step_p95": weighted_quantile(scores, weights[y, x], 0.95),
        "normal_step_p99": weighted_quantile(scores, weights[y, x], 0.99),
        "normal_step_peak": float(scores[peak]),
        "normal_step_x": int(x[peak]) if has_peak else None,
        "normal_step_y": int(y[peak]) if has_peak else None,
        "normal_step_samples": len(scores),
    }


def grid_phase(
    reference: np.ndarray,
    decoded: np.ndarray,
    weights: np.ndarray,
    block: int,
) -> dict[str, float | int | None]:
    """Compare the weighted edge-error percentile on actual and shifted grids."""
    phases = []
    for axis in (0, 1):
        src = reference.swapaxes(0, axis)
        dst = decoded.swapaxes(0, axis)
        weight = weights.swapaxes(0, axis)
        added = np.maximum(
            0,
            np.linalg.norm(np.diff(dst, axis=0), axis=2)
            - np.linalg.norm(np.diff(src, axis=0), axis=2),
        )
        surplus = np.maximum(0, added[1:-1] - (added[:-2] + added[2:]) / 2)
        center_weights = np.minimum(weight[1:-2], weight[2:-1])
        positions = np.arange(2, len(src) - 1)
        # Unity stores y from the bottom. PNG rows increase from the top.
        native_positions = len(src) - positions if axis == 0 else positions
        phases.append((native_positions % block, surplus, center_weights))

    phase_p95 = []
    sizes = []
    weight_totals = []
    for phase in range(block):
        edge_surplus = []
        edge_weights = []
        for axis_phases, surplus, center_weights in phases:
            indices = axis_phases == phase
            edge_surplus.append(surplus[indices].ravel())
            edge_weights.append(center_weights[indices].ravel())
        values = np.concatenate(edge_surplus)
        support = np.concatenate(edge_weights)
        size = effective_support(support)
        total = float(support.sum())
        sizes.append(size)
        weight_totals.append(total)
        # P95 needs multiple samples and a minimum absolute weight. Lack of a
        # gradient is a coverage result, rather than a measured zero artifact.
        score = weighted_quantile(values, support, 0.95) if size >= 16 and total >= 1 else None
        phase_p95.append(score)

    available = sum(score is not None for score in phase_p95)
    true = phase_p95[0]
    shifted = [score for score in phase_p95[1:] if score is not None]
    median = float(np.median(shifted)) if len(shifted) == block - 1 else None
    return {
        "grid_excess": max(0.0, true - median) if true is not None and median is not None else None,
        "grid_true_p95": true,
        "grid_shifted_median": median,
        "grid_phases_available": available,
        "grid_min_effective_support": min(sizes),
        "grid_min_weight": min(weight_totals),
    }


def measure_distortion(
    reference: np.ndarray,
    decoded: np.ndarray,
    support: dict[str, np.ndarray],
    block: int,
) -> dict[str, float | int | None]:
    """Measure added tangential variation, directional steps, and grid jumps."""
    if reference.ndim != 3 or reference.shape != decoded.shape or min(reference.shape[:2]) < 4:
        raise ValueError("Expected equal HWC images at least four pixels wide and tall")
    if block < 2:
        raise ValueError("Expected a block size of at least two")
    normal, weights = support["normal"], support["weight"]
    if normal.shape != (*reference.shape[:2], 2) or weights.shape != reference.shape[:2]:
        raise ValueError("Source support does not match image geometry")
    residual = decoded - reference
    tangent_weights = np.where(support["strength"] >= 0.10, weights, 0)
    tangent = tangential_error(residual, normal)
    # Exploratory fixed-scale result: suppress pixelwise noise before taking derivatives.
    smooth = gaussian_filter(residual, (block / 4, block / 4, 0), mode="nearest")
    return {
        "tangential_p95": weighted_quantile(tangent, tangent_weights, 0.95),
        "tangential_smoothed_p95": weighted_quantile(
            tangential_error(smooth, normal), tangent_weights, 0.95
        ),
        **normal_steps(reference, decoded, normal, weights),
        **grid_phase(reference, decoded, weights, block),
    }
