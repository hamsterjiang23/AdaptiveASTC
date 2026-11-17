"""Measure V3 prediction and real native searches with separate input and gate contexts."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from functools import lru_cache
from typing import cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.data.unity_v3_input import (
    SourceInputMode,
    SourceTextureSpec,
    UnityV3InferenceInput,
)
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from reproductions.unity_search_baseline.deployment import (
    UnityDeploymentResult,
    UnityDeploymentTrial,
)
from reproductions.unity_search_baseline.policy import UnitySearchDecision, UnitySearchPolicy
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy


class V3ReferencePixels:
    """A bounded displayed-orientation reference cache shared with the Unity input arm."""

    def __init__(
        self,
        textures: list[UnityInferenceTexture],
        buffers: list[NDArray[np.uint8]] | None,
    ) -> None:
        self.textures, self.buffers = textures, buffers
        self.load_seconds = 0.0

    @staticmethod
    def validate(pixels: NDArray[np.uint8]) -> None:
        if (
            not isinstance(pixels, np.ndarray)
            or pixels.dtype != np.uint8
            or pixels.ndim != 3
            or pixels.shape[2] != 4
            or min(pixels.shape[:2]) < 1
        ):
            raise ValueError("Require nonempty displayed-orientation RGBA8 pixels")

    @lru_cache(maxsize=2)
    def pixels(self, index: int) -> NDArray[np.uint8]:
        if self.buffers is not None:
            result = self.buffers[index]
        else:
            started = time.perf_counter()
            with Image.open(self.textures[index].reference) as image:
                result = np.asarray(image.convert("RGBA"), dtype=np.uint8)
            self.load_seconds += time.perf_counter() - started
        self.validate(result)
        return result


class V3UnityInferenceInput(UnityInferenceInput):
    def __init__(self, resources: V3ReferencePixels, patch_size: int) -> None:
        self.resources = resources
        super().__init__(resources.textures, patch_size)

    def pixels(self, image_id: int) -> NDArray[np.uint8]:
        return self.resources.pixels(image_id)


class V3NativeQueries:
    """Native candidate measurements contain no archived quality or reference labels."""

    def __init__(
        self,
        rgba: NDArray[np.uint8],
        spec: UnityInferenceTexture,
        texture: UnityTextureInput,
        policy: UnityV3Policy,
        backend: UnityASTCBackend,
        quality: UnityQuality,
    ) -> None:
        self.rgba, self.spec, self.texture = rgba, spec, texture
        self.policy, self.backend, self.quality = policy, backend, quality
        self.containers: dict[int, bytes] = {}
        self.records: list[JsonDict] = []
        self.metrics: dict[int, JsonDict] = {}
        self.encode_attempts = 0
        self.hash_seconds = 0.0

    def measure(self, index: int) -> JsonDict:
        block, preset = self.policy.candidate_set.candidate(index)
        if index in self.metrics:
            return self.metrics[index]
        self.encode_attempts += 1
        payload, decoded, timings = self.backend.encode_decode(
            self.rgba, block, preset, srgb=self.spec.srgb, need_alpha=self.spec.need_alpha
        )
        started = time.perf_counter()
        metrics = self.quality.measure(
            self.rgba,
            decoded,
            need_alpha=self.spec.need_alpha,
            compute_ssim=self.spec.srgb and not self.spec.normal,
            normal=self.spec.normal,
            mip_count=self.spec.normal_metric_mips,
        )
        quality_seconds = time.perf_counter() - started
        container = self.backend.container(payload, self.texture.width, self.texture.height, block)
        started = time.perf_counter()
        hashes = {
            "container_sha256": hashlib.sha256(container).hexdigest(),
            "decoded_native_rgba_sha256": hashlib.sha256(decoded.tobytes()).hexdigest(),
        }
        hashing = time.perf_counter() - started
        self.hash_seconds += hashing
        self.metrics[index], self.containers[index] = metrics, container
        self.records.append(
            {
                "selected_index": index,
                "block": block,
                "preset": preset,
                "metrics": metrics,
                "strict_quality_met": self.policy.strict_quality(metrics, self.texture),
                "timings": {
                    "encode_seconds": float(timings["encode_seconds"]),
                    "decode_seconds": float(timings["decode_seconds"]),
                    "quality_seconds": quality_seconds,
                },
                "trace_hash_seconds": hashing,
                **hashes,
            }
        )
        return metrics


class UnityV3DeploymentTrial:
    """Run a single measured arm; the caller owns preheating, repeats and post-audits.

    No supplied buffers means file-to-ASTC. Supplying all required displayed RGBA
    buffers performs a separate pixels-ready trial. The two scopes are never
    inferred by subtracting estimated I/O time. Source predictions and candidate
    starts are completed before loading actual Unity reference pixels.
    """

    def __init__(
        self,
        textures: list[UnityInferenceTexture],
        policies: list[UnitySearchPolicy],
        backends: list[UnityASTCBackend],
        qualities: list[UnityQuality],
        predictor: UnityQualityInference | None,
        patch_size: int = 240,
        *,
        candidate_set: NativeCandidateSet = NativeCandidateSet(),
        input_mode: str = "unity",
        source_specs: list[SourceTextureSpec] | None = None,
        fixed8_preset: str = "medium",
        progress: Callable[[JsonDict], None] | None = None,
    ) -> None:
        if not textures or len({len(textures), len(policies), len(backends), len(qualities)}) != 1:
            raise ValueError("Every image requires one reference, policy, backend and quality DLL")
        if input_mode not in {"unity", "source_native", "source_aligned"}:
            raise ValueError("Unknown V3 input mode")
        if type(patch_size) is not int or patch_size < 1:
            raise ValueError("Positive integer patch size required")
        if not isinstance(candidate_set, NativeCandidateSet):
            raise ValueError("Explicit V3 candidate set required")
        if fixed8_preset not in UnityASTCBackend.PRESETS:
            raise ValueError("Explicit fixed8 preset required")
        if (8, fixed8_preset) not in [candidate_set.GRID[i] for i in candidate_set.active_ids]:
            raise ValueError("The fixed8 preset is excluded by the candidate set")
        for texture in textures:
            texture.validate()
        if source_specs is not None:
            if len(source_specs) != len(textures):
                raise ValueError("Source specifications must align with all reference images")
            for spec, texture in zip(source_specs, textures, strict=True):
                if any(
                    getattr(spec, key) != getattr(texture, key)
                    for key in ["srgb", "normal", "need_alpha", "normal_metric_mips"]
                ):
                    raise ValueError("Source and encoding importer flags must match")
        self.textures, self.policies = textures, policies
        self.backends, self.qualities, self.predictor = backends, qualities, predictor
        self.patch_size, self.candidate_set, self.input_mode = patch_size, candidate_set, input_mode
        self.source_specs, self.fixed8_preset, self.progress = source_specs, fixed8_preset, progress
        self.completed_images = self.completed_encode_attempts = 0
        self.active_queries: V3NativeQueries | None = None

    def progress_state(self) -> JsonDict:
        active = self.active_queries.encode_attempts if self.active_queries else 0
        return {
            "completed_images": self.completed_images,
            "encoding_attempts": self.completed_encode_attempts + active,
        }

    def _validate_buffers(
        self,
        predicted: bool,
        reference_pixels: list[NDArray[np.uint8]] | None,
        source_pixels: list[NDArray[np.uint8]] | None,
    ) -> bool:
        source_needed = predicted and self.input_mode != "unity"
        if source_pixels is not None and not source_needed:
            raise ValueError("Source buffers are only valid for a source prediction arm")
        if source_needed and ((reference_pixels is None) != (source_pixels is None)):
            raise ValueError("Pixels-ready source trial requires both source and reference buffers")
        for buffers in [reference_pixels, source_pixels]:
            if buffers is not None:
                if len(buffers) != len(self.textures):
                    raise ValueError("Pixel buffers must cover the complete ordered input list")
                for pixels in buffers:
                    V3ReferencePixels.validate(pixels)
        return reference_pixels is not None

    def run(
        self,
        arm: str = "forward",
        *,
        single_image: bool = False,
        reference_pixels: list[NDArray[np.uint8]] | None = None,
        source_pixels: list[NDArray[np.uint8]] | None = None,
    ) -> UnityDeploymentResult:
        if arm not in {"original", "pure", "forward", "fixed8"}:
            raise ValueError("Require original, pure, forward or fixed8 deployment arm")
        if type(single_image) is not bool:
            raise ValueError("Explicit single_image boolean required")
        predicted = arm in {"pure", "forward"}
        if predicted and self.predictor is None:
            raise ValueError("Prediction arms require a loaded predictor")
        if predicted and self.input_mode != "unity" and self.source_specs is None:
            raise ValueError("Source prediction arm requires explicit source specifications")
        ready = self._validate_buffers(predicted, reference_pixels, source_pixels)
        if single_image and len(self.textures) > 1:
            return self._single_image_trials(arm, reference_pixels, source_pixels)
        self.completed_images = self.completed_encode_attempts = 0
        self.active_queries = None
        if predicted:
            assert self.predictor is not None
            self.predictor.synchronize()
        started = time.perf_counter()
        resources = V3ReferencePixels(self.textures, reference_pixels)
        dataset: UnityInferenceInput | UnityV3InferenceInput | None = None
        predictions: dict[str, np.ndarray] | None = None
        phases: JsonDict = {}
        preparation = prediction_seconds = policy_seconds = 0.0
        starts: list[UnitySearchDecision] = []
        prediction_contexts: list[UnityTextureInput] = []
        active_policies = [UnityV3Policy(policy, self.candidate_set) for policy in self.policies]
        if predicted:
            before = time.perf_counter()
            if self.input_mode == "unity":
                dataset = V3UnityInferenceInput(resources, self.patch_size)
            else:
                assert self.source_specs is not None
                specs = self.source_specs
                if source_pixels is not None:
                    specs = [
                        replace(spec, source=pixels, file_sha256=None)
                        for spec, pixels in zip(specs, source_pixels, strict=True)
                    ]
                dataset = UnityV3InferenceInput(
                    specs, cast(SourceInputMode, self.input_mode), self.patch_size
                )
            preparation = time.perf_counter() - before
            before = time.perf_counter()
            assert self.predictor is not None
            predictions, phases = self.predictor.run(cast(UnityInferenceInput, dataset))
            self.predictor.synchronize()
            prediction_seconds = time.perf_counter() - before
            before = time.perf_counter()
            for index, (spec, policy) in enumerate(
                zip(self.textures, active_policies, strict=True)
            ):
                if self.input_mode == "unity":
                    # Metadata was computed during input preparation, not from quality targets.
                    width, height = dataset.sizes[index]
                    metadata = dataset.input_metadata[index]
                    context = UnityTextureInput(
                        width,
                        height,
                        spec.srgb,
                        spec.normal,
                        spec.need_alpha,
                        bool(metadata[5]),
                        float(metadata[7]),
                    )
                else:
                    assert isinstance(dataset, UnityV3InferenceInput)
                    context = dataset.decision_inputs[index]
                prediction_contexts.append(context)
                candidates = UnityQualityPrediction.candidates(
                    context,
                    predictions["channel_mse"][index],
                    predictions["channel_zero"][index],
                    predictions["image_quality"][index],
                )
                starts.append(policy.select(candidates, context))
            policy_seconds += time.perf_counter() - before

        containers: list[bytes] = []
        choices: list[JsonDict] = []
        hashing = reporting = flip_seconds = 0.0
        native_totals = dict.fromkeys(["encode_seconds", "decode_seconds", "quality_seconds"], 0.0)
        for index, (spec, policy, backend, quality) in enumerate(
            zip(self.textures, active_policies, self.backends, self.qualities, strict=True)
        ):
            before = time.perf_counter()
            pixels = resources.pixels(index)
            texture = UnityDeploymentTrial.texture_input(pixels, spec)
            if predicted and self.input_mode != "unity":
                assert self.source_specs is not None
                source = self.source_specs[index]
                if (source.target_width, source.target_height) != (texture.width, texture.height):
                    raise ValueError("Explicit source target dimensions differ from encoding input")
            rgba = np.ascontiguousarray(pixels[::-1])
            flip_seconds += time.perf_counter() - before
            start = starts[index] if predicted else None
            context = prediction_contexts[index] if predicted else None
            before = time.perf_counter()
            if arm in {"original", "forward"}:
                queries = V3NativeQueries(rgba, spec, texture, policy, backend, quality)
                self.active_queries = queries
                outcome = policy.search(
                    queries.measure, texture, start.selected_index if start is not None else None
                )
                elapsed = time.perf_counter() - before
                measured = {
                    name: sum(row["timings"][name] for row in queries.records)
                    for name in native_totals
                }
                for name, seconds in measured.items():
                    native_totals[name] += seconds
                policy_seconds += max(0.0, elapsed - sum(measured.values()) - queries.hash_seconds)
                hashing += queries.hash_seconds
                choice = asdict(outcome.decision)
                choice.update(
                    measured_indices=list(outcome.measured_indices),
                    quality_checked_indices=list(outcome.quality_checked_indices),
                    queries=queries.records,
                    selected_metrics=queries.metrics[outcome.decision.selected_index],
                )
                container = queries.containers[outcome.decision.selected_index]
                self.completed_encode_attempts += queries.encode_attempts
                self.active_queries = None
            else:
                selected = (
                    start.selected_index
                    if start is not None
                    else self.candidate_set.GRID.index((8, self.fixed8_preset))
                )
                block, preset = self.candidate_set.candidate(selected)
                self.completed_encode_attempts += 1
                container, encoding = UnityDeploymentTrial.encode(
                    backend, rgba, block, preset, spec
                )
                native_totals["encode_seconds"] += encoding
                policy_seconds += max(0.0, time.perf_counter() - before - encoding)
                choice = {
                    "selected_index": selected,
                    "block_size": f"{block}x{block}",
                    "preset": preset,
                    "selection_reason": "pure_model" if predicted else "fixed8",
                    "candidates_measured": 1,
                    "measured_indices": [selected],
                    "quality_checked_indices": [],
                    "queries": [],
                    "selected_metrics": None,
                    "strict_quality_met": None,
                    "effective_psnr_threshold": policy.effective_threshold(texture),
                }
            choice.update(
                source_index=index,
                starting_decision=asdict(start) if start is not None else None,
                prediction_context=asdict(context) if context is not None else None,
                gate_context=asdict(texture),
                context_difference=(
                    {
                        "black_pixel_ratio": texture.black_pixel_ratio - context.black_pixel_ratio,
                        "alpha_constant_changed": texture.alpha_constant != context.alpha_constant,
                        "threshold": policy.effective_threshold(texture)
                        - policy.effective_threshold(context),
                    }
                    if context is not None
                    else None
                ),
                selected_encoded_result_reused=arm in {"original", "forward"},
            )
            containers.append(container)
            choices.append(choice)
            self.completed_images += 1
            if self.progress is not None:
                before = time.perf_counter()
                self.progress(self.progress_state())
                reporting += time.perf_counter() - before
        if predicted:
            assert self.predictor is not None
            self.predictor.synchronize()
        wall = time.perf_counter() - started
        elapsed = wall - hashing - reporting
        source_timings = getattr(dataset, "timings", {}) if self.input_mode != "unity" else {}
        return UnityDeploymentResult(
            containers,
            choices,
            predictions,
            {
                "arm": arm,
                "input_mode": self.input_mode,
                "candidate_set": self.candidate_set.name,
                "end_to_end_seconds": elapsed,
                "file_to_astc_seconds": None if ready else elapsed,
                "pixels_ready_seconds": elapsed if ready else None,
                "wall_including_trace_and_progress_seconds": wall,
                "trace_hash_seconds": hashing,
                "progress_write_seconds": reporting,
                "input_preparation_seconds": preparation,
                "inference": phases,
                "inference_wall_seconds": prediction_seconds,
                "reference_pixel_load_seconds": resources.load_seconds,
                "reference_load_metadata_and_flip_seconds": flip_seconds,
                "source_input_timings": source_timings,
                "policy_and_bookkeeping_seconds": policy_seconds,
                **{f"native_{name}": seconds for name, seconds in native_totals.items()},
                "encoding_calls": self.completed_encode_attempts,
                "prediction_passes": int(predicted),
                "images": len(self.textures),
                "batch_amortized_seconds_per_image": elapsed / len(self.textures),
                "single_image_latency_seconds": elapsed if len(self.textures) == 1 else None,
                "scope": (
                    "Displayed source/reference RGBA buffers to selected in-memory mip0 ASTC"
                    if ready
                    else "Required source/reference files to selected in-memory mip0 ASTC"
                ),
                "scope_details": (
                    "Includes input preparation, actual read/decode/resize, fresh prediction, "
                    "decision, native encoding and runtime quality gating where applicable. "
                    "Trace hashes/progress writes excluded and reported separately; model/DLL "
                    "loading, Unity import, output writes and post-selection audit excluded. "
                    "Nested component timings may overlap; do not sum them."
                ),
            },
        )

    def _single_image_trials(
        self,
        arm: str,
        reference_pixels: list[NDArray[np.uint8]] | None,
        source_pixels: list[NDArray[np.uint8]] | None,
    ) -> UnityDeploymentResult:
        self.completed_images = self.completed_encode_attempts = 0
        self.active_queries = None
        results: list[UnityDeploymentResult] = []
        for index in range(len(self.textures)):
            trial = UnityV3DeploymentTrial(
                [self.textures[index]],
                [self.policies[index]],
                [self.backends[index]],
                [self.qualities[index]],
                self.predictor,
                self.patch_size,
                candidate_set=self.candidate_set,
                input_mode=self.input_mode,
                source_specs=[self.source_specs[index]] if self.source_specs is not None else None,
                fixed8_preset=self.fixed8_preset,
            )
            try:
                result = trial.run(
                    arm,
                    reference_pixels=[reference_pixels[index]]
                    if reference_pixels is not None
                    else None,
                    source_pixels=[source_pixels[index]] if source_pixels is not None else None,
                )
            except BaseException:
                self.completed_encode_attempts += trial.completed_encode_attempts
                self.active_queries = trial.active_queries
                raise
            result.choices[0]["source_index"] = index
            results.append(result)
            self.completed_images += 1
            self.completed_encode_attempts += trial.completed_encode_attempts
            if self.progress is not None:
                self.progress(self.progress_state())
        latencies = [result.timings["end_to_end_seconds"] for result in results]
        predictions = None
        if results[0].predictions is not None:
            parts = [result.predictions for result in results]
            if any(part is None for part in parts):
                raise ValueError("Prediction identity changed between single-image trials")
            predictions = {
                key: np.concatenate([part[key] for part in parts if part is not None])
                for key in results[0].predictions
            }
        return UnityDeploymentResult(
            [container for result in results for container in result.containers],
            [choice for result in results for choice in result.choices],
            predictions,
            {
                "arm": arm,
                "input_mode": self.input_mode,
                "candidate_set": self.candidate_set.name,
                "end_to_end_seconds": sum(latencies),
                "file_to_astc_seconds": sum(latencies) if reference_pixels is None else None,
                "pixels_ready_seconds": sum(latencies) if reference_pixels is not None else None,
                "single_image_latencies_seconds": latencies,
                "single_image_mean_seconds": float(np.mean(latencies)),
                "single_image_median_seconds": float(np.median(latencies)),
                "single_image_p95_seconds": float(np.percentile(latencies, 95)),
                "encoding_calls": sum(result.timings["encoding_calls"] for result in results),
                "prediction_passes": sum(result.timings["prediction_passes"] for result in results),
                "measurements": [result.timings for result in results],
                "scope": (
                    "Independent sequential one-image trials, each with fresh prediction "
                    "when the selected arm uses a model; aggregation/progress excluded"
                ),
            },
        )
