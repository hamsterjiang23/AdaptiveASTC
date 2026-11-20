"""Compare dense predictions with exact tile labels before applying a review budget."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_labels import UnityTileLabels


class UnityDenseTileMetrics:
    EPSILON = 1e-10
    THRESHOLDS = (28, 30)
    NEAR_DB = 2
    VIEWS = ("native_rgb", "native_rgba", "display")
    REGIONS = ("all", "content", "smooth")

    def __init__(self) -> None:
        self.values: list[JsonDict] = []
        self.log_sse = np.zeros((3, 20), dtype=np.float64)
        self.near_sse = np.zeros((3, 2, 20), dtype=np.float64)
        self.near_counts = np.zeros((3, 2, 20), dtype=np.int64)
        self.tiles = 0

    @staticmethod
    def views(channel_mse: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (
            channel_mse[..., :3].mean(axis=-1),
            channel_mse[..., :4].mean(axis=-1),
            channel_mse[..., 4],
        )

    def add(self, prediction: NDArray[np.float32], labels: UnityTileLabels, index: int) -> None:
        if prediction.shape != labels.squared_errors.shape or not np.isfinite(prediction).all():
            raise ValueError("V5 dense predictions must exactly cover the real image tile grid")
        predicted_mse = np.clip(
            10.0 ** np.clip(prediction.astype(np.float64), -10, 0) - self.EPSILON, 0, 1
        )
        denominator = labels.pixels[..., None].astype(np.float64) * 255**2
        truth_mse = labels.squared_errors / (denominator * np.array([1, 1, 1, 1, 3]))
        self.tiles += labels.pixels.size
        view_results = {}
        masks = (np.ones(labels.pixels.shape, dtype=bool), labels.content, labels.smooth)
        for v, (view, truth, predicted) in enumerate(
            zip(
                self.VIEWS,
                self.views(truth_mse),
                self.views(predicted_mse),
                strict=True,
            )
        ):
            true_log = np.log10(truth + self.EPSILON)
            predicted_log = np.log10(predicted + self.EPSILON)
            self.log_sse[v] += np.square(predicted_log - true_log).sum(axis=(1, 2))
            # Values below the finite zero-log floor can never enter the near-threshold band.
            true_psnr = -10 * np.log10(np.maximum(truth, self.EPSILON))
            predicted_psnr = -10 * np.log10(np.maximum(predicted, self.EPSILON))
            psnr_error = np.square(predicted_psnr - true_psnr)
            thresholds = {}
            for t, y in enumerate(self.THRESHOLDS):
                near = np.abs(true_psnr - y) <= self.NEAR_DB
                self.near_counts[v, t] += near.sum(axis=(1, 2))
                self.near_sse[v, t] += (psnr_error * near).sum(axis=(1, 2))
                cutoff = 10 ** (-y / 10)
                true_bad, predicted_bad = truth > cutoff, predicted > cutoff
                thresholds[str(y)] = {
                    region: {
                        "true": true_bad[:, mask].sum(axis=1).tolist(),
                        "predicted": predicted_bad[:, mask].sum(axis=1).tolist(),
                    }
                    for region, mask in zip(self.REGIONS, masks, strict=True)
                }
            view_results[view] = thresholds
        self.values.append(
            {
                "index": index,
                "regions": {
                    region: int(mask.sum())
                    for region, mask in zip(self.REGIONS, masks, strict=True)
                },
                "bad": view_results,
            }
        )

    def summarize(self) -> JsonDict:
        if not self.tiles:
            raise ValueError("Empty V5 validation coverage")
        view_metrics = {}
        for v, view in enumerate(self.VIEWS):
            counts = self.near_counts[v]
            near = np.sqrt(self.near_sse[v] / np.maximum(counts, 1))
            view_metrics[view] = {
                "log_mse_rmse": float(np.sqrt(self.log_sse[v].sum() / (20 * self.tiles))),
                "near_threshold_psnr_rmse_db": {
                    str(y): [
                        float(error) if count else None
                        for error, count in zip(near[i], counts[i], strict=True)
                    ]
                    for i, y in enumerate(self.THRESHOLDS)
                },
                "bad_share_mae": {
                    str(y): {region: self.bad_share_mae(view, y, region) for region in self.REGIONS}
                    for y in self.THRESHOLDS
                },
            }
        return {
            "images": len(self.values),
            "tiles": self.tiles,
            "near_range_db": self.NEAR_DB,
            "views": view_metrics,
        }

    def bad_share_mae(self, view: str, y: int, region: str) -> float | None:
        errors = []
        for row in self.values:
            if denominator := row["regions"][region]:
                counts = row["bad"][view][str(y)][region]
                errors.append(
                    np.abs(np.subtract(counts["predicted"], counts["true"])) / denominator
                )
        return float(np.mean(errors)) if errors else None
