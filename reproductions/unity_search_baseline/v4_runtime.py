"""Fresh inference and native V4 execution, separate from archived scoring data."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict

import numpy as np
from numpy.typing import NDArray

from adaptive_astc.data.unity_inference import UnityInferenceTexture
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from reproductions.unity_search_baseline.deployment import (
    UnityDeploymentResult,
    UnityDeploymentTrial,
)
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.v3_deployment import (
    V3NativeQueries,
    V3ReferencePixels,
    V3UnityInferenceInput,
)
from reproductions.unity_search_baseline.v3_policy import UnityV3Policy
from reproductions.unity_search_baseline.v4_policy import UnityV4Policy, V4Options


class UnityV4Trial:
    """Accept deployment inputs only; labels and archived quality remain in the caller."""

    def __init__(
        self,
        textures: list[UnityInferenceTexture],
        policies: list[UnityV3Policy],
        predictor: UnityQualityInference,
        backend: UnityASTCBackend,
        quality: UnityQuality,
        options: V4Options,
    ) -> None:
        if not textures or len(textures) != len(policies):
            raise ValueError("Ordered input and rule counts must agree")
        for texture in textures:
            texture.validate()
        self.textures, self.policies = textures, policies
        self.predictor, self.backend, self.quality = predictor, backend, quality
        self.options = options

    def run(self, buffers: list[NDArray[np.uint8]] | None = None) -> UnityDeploymentResult:
        if buffers is not None and len(buffers) != len(self.textures):
            raise ValueError("Pixels-ready buffers must cover every input")
        self.predictor.synchronize()
        started = time.perf_counter()
        resources = V3ReferencePixels(self.textures, buffers)
        before = time.perf_counter()
        dataset = V3UnityInferenceInput(resources, 240)
        input_seconds = time.perf_counter() - before
        before = time.perf_counter()
        predictions, phases = self.predictor.run(dataset)
        self.predictor.synchronize()
        inference_seconds = time.perf_counter() - before
        containers, choices = [], []
        decision_seconds = flip_seconds = hashing = 0.0
        totals = dict.fromkeys(["encode_seconds", "decode_seconds", "quality_seconds"], 0.0)
        for index, (spec, base) in enumerate(zip(self.textures, self.policies, strict=True)):
            before = time.perf_counter()
            pixels = resources.pixels(index)
            texture = UnityDeploymentTrial.texture_input(pixels, spec)
            width, height = dataset.sizes[index]
            metadata = dataset.input_metadata[index]
            context = type(texture)(
                width,
                height,
                spec.srgb,
                spec.normal,
                spec.need_alpha,
                bool(metadata[5]),
                float(metadata[7]),
            )
            rgba = np.ascontiguousarray(pixels[::-1])
            flip_seconds += time.perf_counter() - before
            before = time.perf_counter()
            candidates = UnityQualityPrediction.candidates(
                context,
                predictions["channel_mse"][index],
                predictions["channel_zero"][index],
                predictions["image_quality"][index],
            )
            queries = V3NativeQueries(rgba, spec, texture, base, self.backend, self.quality)
            result = UnityV4Policy(base, self.options).search(
                queries.measure, texture, candidates, prediction_texture=context
            )
            elapsed = time.perf_counter() - before
            measured = {
                name: sum(row["timings"][name] for row in queries.records) for name in totals
            }
            for name, value in measured.items():
                totals[name] += value
            hashing += queries.hash_seconds
            decision_seconds += max(0.0, elapsed - sum(measured.values()) - queries.hash_seconds)
            selected = result.decision.selected_index
            containers.append(queries.containers[selected])
            choices.append(
                {
                    **result.record(),
                    "queries": queries.records,
                    "selected_metrics": queries.metrics[selected],
                    "gate_context": asdict(texture),
                    "prediction_context": asdict(context),
                    "source_index": index,
                    "selected_encoded_result_reused": True,
                }
            )
        self.predictor.synchronize()
        wall = time.perf_counter() - started
        return UnityDeploymentResult(
            containers,
            choices,
            predictions,
            {
                "end_to_end_seconds": wall - hashing,
                "wall_including_trace_hashes_seconds": wall,
                "input_preparation_seconds": input_seconds,
                "inference_wall_seconds": inference_seconds,
                "inference": phases,
                "reference_pixel_load_seconds": resources.load_seconds,
                "reference_load_metadata_and_flip_seconds": flip_seconds,
                "policy_and_bookkeeping_seconds": decision_seconds,
                "trace_hash_seconds": hashing,
                **{f"native_{name}": value for name, value in totals.items()},
                "encoding_calls": sum(len(row["measured_indices"]) for row in choices),
                "prediction_passes": 1,
                "images": len(choices),
                "scope": "pixels_ready" if buffers is not None else "files",
                "scope_details": (
                    "Input preparation, fresh inference, decision, native encoding, decoding "
                    "and quality gating. Model/DLL load, output audit/writes and trace hashes "
                    "recorded separately."
                ),
            },
        )


def model_digest(predictor: UnityQualityInference) -> str:
    digest = hashlib.sha256()
    for name, tensor in predictor.model.state_dict().items():
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()
