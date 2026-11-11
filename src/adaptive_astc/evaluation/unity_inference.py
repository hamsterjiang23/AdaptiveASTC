"""Run native quality inference with separate input, synchronized GPU and aggregation costs."""

from __future__ import annotations

import time

import numpy as np
import torch
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.models.unity_quality import UnityQualityRegressor


class UnityQualityInference:
    def __init__(
        self,
        model: UnityQualityRegressor,
        device: torch.device,
        batch_size: int,
        zero_threshold: float = 0.5,
    ) -> None:
        if (
            type(batch_size) is not int
            or batch_size < 1
            or type(zero_threshold) not in {int, float}
            or not 0 < zero_threshold < 1
        ):
            raise ValueError("Positive inference batch and zero threshold in(0,1) required")
        self.model, self.device = model.eval(), device
        self.batch_size, self.zero_threshold = batch_size, zero_threshold

    def synchronize(self) -> None:
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)

    def run(self, dataset: UnityInferenceInput) -> tuple[dict[str, np.ndarray], JsonDict]:
        self.synchronize()
        started = time.perf_counter()
        features = np.empty((len(dataset), 512), dtype=np.float32)
        logs = np.empty((len(dataset), 20, 4), dtype=np.float64)
        input_seconds = forward_seconds = 0.0
        loader = iter(DataLoader(dataset, batch_size=self.batch_size, num_workers=0))
        with torch.inference_mode():
            while True:
                before = time.perf_counter()
                try:
                    batch = next(loader)
                except StopIteration:
                    input_seconds += time.perf_counter() - before
                    break
                input_seconds += time.perf_counter() - before
                before = time.perf_counter()
                with torch.autocast(
                    self.device.type, dtype=torch.float16, enabled=self.device.type == "cuda"
                ):
                    output = self.model.encode(
                        batch["rgba"].to(self.device),
                        batch["valid_mask"].to(self.device),
                        batch["metadata"].to(self.device),
                    )
                indexes = batch["patch_index"].numpy()
                features[indexes] = output["features"].float().cpu().numpy()
                logs[indexes] = output["channel_log_mse"].float().cpu().numpy()
                self.synchronize()
                forward_seconds += time.perf_counter() - before
            before = time.perf_counter()
            with torch.autocast(
                self.device.type, dtype=torch.float16, enabled=self.device.type == "cuda"
            ):
                image = self.model.predict_images(
                    torch.from_numpy(features).to(self.device),
                    torch.from_numpy(dataset.pixel_counts).to(self.device),
                    torch.from_numpy(dataset.image_ids).to(self.device),
                    torch.from_numpy(dataset.input_metadata).to(self.device),
                )
            quality = image["image_quality"].cpu().numpy().astype(np.float64)
            probability = (
                torch.sigmoid(image["channel_zero_logits"]).cpu().numpy().astype(np.float64)
            )
            self.synchronize()
            image_head_seconds = time.perf_counter() - before
        before = time.perf_counter()
        mse = UnityQualityPrediction.aggregate_mse(
            logs, dataset.pixel_counts, dataset.image_ids, len(dataset.textures)
        )
        predictions = {
            "channel_mse": mse,
            "channel_zero": probability >= self.zero_threshold,
            "zero_probability": probability,
            "image_quality": quality,
        }
        aggregation_seconds = time.perf_counter() - before
        return predictions, {
            "total_seconds": time.perf_counter() - started,
            "patch_input_seconds": input_seconds,
            "patch_forward_and_transfer_seconds": forward_seconds,
            "image_head_and_transfer_seconds": image_head_seconds,
            "mse_aggregation_seconds": aggregation_seconds,
            "images": len(dataset.textures),
            "patches": len(dataset),
            "batch_size": self.batch_size,
            "scope": (
                "Input batching, forward/transfers and MSE aggregation; excludes initial "
                "PNG/metadata preparation and policy/encoding"
            ),
        }
