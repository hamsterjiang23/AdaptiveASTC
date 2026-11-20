"""Predict and screen V5 tile quality from Unity reference pixels and importer flags."""

from __future__ import annotations

from itertools import batched

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_dense_tile_dataset import UnityDensePatchGrid
from adaptive_astc.data.unity_inference import UnityInferenceTexture
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.data.unity_tile_errors import UnityTileGrid, UnityTileViews
from adaptive_astc.evaluation.unity_dense_tile_metrics import UnityDenseTileMetrics as Metrics
from adaptive_astc.models.unity_dense_tile import UnityDenseTileRegressor


class UnityDenseTileInference:
    def __init__(
        self,
        model: UnityDenseTileRegressor,
        device: torch.device,
        patch_size: int,
        batch_size: int,
    ) -> None:
        if batch_size < 1:
            raise ValueError("Require a positive V5 inference batch size")
        self.model = model.to(device).eval()
        self.device = device
        self.patch_size = patch_size
        self.batch_size = batch_size

    @staticmethod
    def metadata(rgba: NDArray[np.uint8], texture: UnityInferenceTexture) -> Tensor:
        height, width = rgba.shape[:2]
        alpha = rgba[..., 3]
        return torch.tensor(
            [
                np.log2(width),
                np.log2(height),
                texture.srgb,
                texture.normal,
                texture.need_alpha,
                alpha.min() == alpha.max(),
                texture.normal_metric_mips,
                np.mean(np.all(rgba[..., :3] == 0, axis=2)),
            ],
            dtype=torch.float32,
        )

    @torch.inference_mode()
    def predict(
        self, rgba: NDArray[np.uint8], texture: UnityInferenceTexture
    ) -> NDArray[np.float32]:
        texture.validate()
        if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.dtype != np.uint8 or not rgba.size:
            raise ValueError("V5 inference requires a nonempty 8-bit RGBA reference")
        height, width = rgba.shape[:2]
        patch_grid = UnityDensePatchGrid(UnityTileGrid(height, width), self.patch_size)
        rows, cols = patch_grid.grid.counts().shape
        predictions = np.full((20, rows, cols, 5), np.nan, dtype=np.float32)
        metadata = self.metadata(rgba, texture).to(self.device)
        for origins in batched(patch_grid.origins(), self.batch_size):
            patches, masks = zip(*(patch_grid.extract(rgba, y, x) for y, x in origins), strict=True)
            pixels = torch.stack(
                [torch.from_numpy(patch).permute(2, 0, 1).float().div_(255) for patch in patches]
            ).to(self.device)
            valid = torch.from_numpy(np.stack(masks)).to(self.device)[:, None]
            batch = self.model(pixels, valid, metadata.expand(len(origins), -1))
            for (y, x), patch in zip(origins, batch.cpu().numpy(), strict=True):
                h, w = min(patch.shape[0], rows - y), min(patch.shape[1], cols - x)
                predictions[:, y : y + h, x : x + w] = patch[:h, :w].transpose(2, 0, 1, 3)
        if not np.isfinite(predictions).all():
            raise ValueError("V5 inference failed to cover the finite tile grid")
        return predictions

    @staticmethod
    def screen(
        rgba: NDArray[np.uint8],
        texture: UnityInferenceTexture,
        prediction: NDArray[np.float32],
        y_values: list[float],
        x_share: float | None,
    ) -> tuple[JsonDict, dict[str, np.ndarray]]:
        if (
            not y_values
            or len(set(y_values)) != len(y_values)
            or any(not 0 < value <= 100 for value in y_values)
        ):
            raise ValueError("Choose unique PSNR thresholds above 0 and up to 100 dB")
        if x_share is not None and not 0 < x_share <= 1:
            raise ValueError("The bad-share threshold must be in (0, 1]")
        grid = UnityTileGrid(*rgba.shape[:2])
        pixels = grid.counts()
        if prediction.shape != (20, *pixels.shape, 5) or not np.isfinite(prediction).all():
            raise ValueError("Predictions must cover all twenty candidates and all tiles")
        display = UnityTileViews.display(rgba, texture.need_alpha)
        maximum = grid.reduce(display.max(axis=2), np.maximum)
        minimum = grid.reduce(display.min(axis=2), np.minimum)
        content = maximum - minimum >= 2
        smooth = 2 * grid.reduce(UnityTileViews.smooth_mask(display), np.add) >= pixels
        masks = dict(zip(Metrics.REGIONS, (np.ones_like(content), content, smooth), strict=True))
        denominators = {name: int(mask.sum()) for name, mask in masks.items()}
        normalized = np.clip(
            10.0 ** np.clip(prediction.astype(np.float64), -10, 0) - Metrics.EPSILON, 0, 1
        )
        arrays: dict[str, np.ndarray] = {
            "candidate_channel_log_mse": prediction,
            "valid_pixels": pixels.astype(np.uint8),
            "content": content,
            "smooth": smooth,
        }
        results = {}
        for name, mse in zip(Metrics.VIEWS, Metrics.views(normalized), strict=True):
            arrays[f"{name}_psnr_db"] = (-10 * np.log10(np.maximum(mse, Metrics.EPSILON))).astype(
                np.float32
            )
            thresholds = {}
            for y in y_values:
                below = mse > 10 ** (-y / 10)
                per_region = {}
                for region, mask in masks.items():
                    count = below[:, mask].sum(axis=1)
                    total = denominators[region]
                    shares = (count / total).tolist() if total else [None] * 20
                    flags = (
                        (count / total >= x_share).tolist()
                        if total and x_share is not None
                        else None
                    )
                    per_region[region] = {
                        "predicted_bad_tiles": count.tolist(),
                        "predicted_bad_share": shares,
                        "flagged": flags,
                    }
                thresholds[str(y)] = per_region
            results[name] = thresholds
        return {
            "scope": "input-only V5 tile prediction",
            "candidate_order": UnityTileArchive.GRID,
            "image_height": grid.height,
            "image_width": grid.width,
            "top_padding": grid.top_padding,
            "x_share": x_share,
            "region_tiles": denominators,
            "predicted_bad": results,
        }, arrays
