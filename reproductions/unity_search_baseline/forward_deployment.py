"""Predict candidate starts and lazily encode, decode and quality-gate real candidates."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import asdict

import numpy as np
from numpy.typing import NDArray

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from reproductions.unity_search_baseline.deployment import (
    UnityDeploymentResult,
    UnityDeploymentTrial,
)
from reproductions.unity_search_baseline.policy import UnitySearchDecision, UnitySearchPolicy
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.system_variant_policy import (
    CandidateQueries,
    VariantOutcome,
    forward_search,
)


class NativeForwardQueries(CandidateQueries):
    def __init__(
        self,
        rgba: NDArray[np.uint8],
        spec: UnityInferenceTexture,
        texture: UnityTextureInput,
        policy: UnitySearchPolicy,
        predicted: UnitySearchDecision,
        backend: UnityASTCBackend,
        quality: UnityQuality,
    ) -> None:
        super().__init__(
            {
                "decision": predicted,
                "candidates": [{"metrics": {}} for _ in range(20)],
                "strict": [False] * 20,
            },
            predicted.selected_index,
            None,
        )
        self.rgba, self.spec, self.texture, self.policy = rgba, spec, texture, policy
        self.backend, self.quality = backend, quality
        self.containers: dict[int, bytes] = {}
        self.records: list[JsonDict] = []
        self.encode_attempts = 0
        self.hash_seconds = 0.0

    def measure(self, index: int) -> bool:
        if index in self.indices:
            return True
        if not super().measure(index):
            return False
        block, preset = UnityQualityPrediction.GRID[index]
        self.encode_attempts += 1
        payload, decoded, timings = self.backend.encode_decode(
            self.rgba,
            block,
            preset,
            srgb=self.spec.srgb,
            need_alpha=self.spec.need_alpha,
        )
        before = time.perf_counter()
        metrics = self.quality.measure(
            self.rgba,
            decoded,
            need_alpha=self.spec.need_alpha,
            compute_ssim=self.spec.srgb and not self.spec.normal,
            normal=self.spec.normal,
            mip_count=self.spec.normal_metric_mips,
        )
        timings["quality_seconds"] = time.perf_counter() - before
        self.entry["candidates"][index]["metrics"] = metrics
        self.entry["strict"][index] = UnityQualityPrediction.strict_quality(
            self.policy,
            self.texture,
            metrics,
            self.entry["decision"].effective_psnr_threshold,
        )
        container = self.backend.container(
            payload,
            self.texture.width,
            self.texture.height,
            block,
        )
        self.containers[index] = container
        before = time.perf_counter()
        container_sha = hashlib.sha256(container).hexdigest()
        decoded_sha = hashlib.sha256(decoded.tobytes()).hexdigest()
        hash_seconds = time.perf_counter() - before
        self.hash_seconds += hash_seconds
        self.records.append(
            {
                "selected_index": index,
                "block": block,
                "preset": preset,
                "metrics": metrics,
                "strict_quality_met": self.entry["strict"][index],
                "timings": timings,
                "container_sha256": container_sha,
                "decoded_native_rgba_sha256": decoded_sha,
                "trace_hash_seconds": hash_seconds,
            }
        )
        return True

    def outcome(self, selected: int, reason: str) -> VariantOutcome:
        # Runtime selection has no measurements for the skipped prefix.
        return VariantOutcome(selected, tuple(self.indices), tuple(self.indices), reason)


class UnityForwardSearchTrial:
    def __init__(
        self,
        textures: list[UnityInferenceTexture],
        policies: list[UnitySearchPolicy],
        backends: list[UnityASTCBackend],
        qualities: list[UnityQuality],
        predictor: UnityQualityInference,
        patch_size: int,
        encoding_indices: list[int],
        progress: Callable[[JsonDict], None] | None = None,
    ) -> None:
        if not textures or len({len(textures), len(policies), len(backends), len(qualities)}) != 1:
            raise ValueError("Every input requires a policy, encoder and quality evaluator")
        if (
            not encoding_indices
            or encoding_indices != sorted(set(encoding_indices))
            or any(
                type(index) is not int or not 0 <= index < len(textures)
                for index in encoding_indices
            )
        ):
            raise ValueError("Require unique ordered encoding indices within the inference inputs")
        for spec in textures:
            spec.validate()
        self.textures, self.policies = textures, policies
        self.backends, self.qualities = backends, qualities
        self.predictor, self.patch_size = predictor, patch_size
        self.encoding_indices, self.progress = encoding_indices, progress
        self.completed_images = 0
        self.completed_encode_attempts = 0
        self.active_queries: NativeForwardQueries | None = None

    def progress_state(self) -> JsonDict:
        active_attempts = self.active_queries.encode_attempts if self.active_queries else 0
        return {
            "completed_images": self.completed_images,
            "encoding_attempts": self.completed_encode_attempts + active_attempts,
        }

    def run(self) -> UnityDeploymentResult:
        self.completed_images = self.completed_encode_attempts = 0
        self.active_queries = None
        self.predictor.synchronize()
        started = time.perf_counter()
        dataset = UnityInferenceInput(self.textures, self.patch_size)
        preparation = time.perf_counter() - started
        predictions, phases = self.predictor.run(dataset)
        containers, choices = [], []
        loading = policy_seconds = hashing = reporting = 0.0
        native_totals = dict.fromkeys(["encode_seconds", "decode_seconds", "quality_seconds"], 0.0)
        for source_index in self.encoding_indices:
            spec, policy = self.textures[source_index], self.policies[source_index]
            before = time.perf_counter()
            pixels = dataset.pixels(source_index)
            rgba = np.ascontiguousarray(pixels[::-1])
            texture = UnityDeploymentTrial.texture_input(pixels, spec)
            loading += time.perf_counter() - before
            before = time.perf_counter()
            predicted = UnityQualityPrediction.select(
                policy,
                texture,
                predictions["channel_mse"][source_index],
                predictions["channel_zero"][source_index],
                predictions["image_quality"][source_index],
            )
            policy_seconds += time.perf_counter() - before
            queries = NativeForwardQueries(
                rgba,
                spec,
                texture,
                policy,
                predicted,
                self.backends[source_index],
                self.qualities[source_index],
            )
            self.active_queries = queries
            before = time.perf_counter()
            outcome = forward_search(queries)
            elapsed = time.perf_counter() - before
            measured = {
                name: sum(record["timings"][name] for record in queries.records)
                for name in native_totals
            }
            for name, seconds in measured.items():
                native_totals[name] += seconds
            policy_seconds += max(0.0, elapsed - sum(measured.values()) - queries.hash_seconds)
            hashing += queries.hash_seconds
            containers.append(queries.containers[outcome.selected_index])
            block, preset = UnityQualityPrediction.GRID[outcome.selected_index]
            choices.append(
                {
                    "source_index": source_index,
                    "starting_decision": asdict(predicted),
                    "selected_index": outcome.selected_index,
                    "block_size": f"{block}x{block}",
                    "preset": preset,
                    "selection_reason": outcome.reason,
                    "candidates_measured": len(queries.indices),
                    "measured_indices": queries.indices,
                    "strict_quality_met": queries.strict(outcome.selected_index),
                    "queries": queries.records,
                    "selected_encoded_result_reused": True,
                    "unmeasured_prefix_backfill_needed": None,
                }
            )
            self.completed_images += 1
            self.completed_encode_attempts += queries.encode_attempts
            self.active_queries = None
            if self.progress is not None:
                before = time.perf_counter()
                self.progress(self.progress_state())
                reporting += time.perf_counter() - before
        self.predictor.synchronize()
        wall = time.perf_counter() - started
        return UnityDeploymentResult(
            containers,
            choices,
            predictions,
            {
                "end_to_end_seconds": wall - hashing - reporting,
                "wall_including_trace_and_progress_seconds": wall,
                "trace_hash_seconds": hashing,
                "progress_write_seconds": reporting,
                "reference_and_metadata_seconds": preparation,
                "reference_load_and_flip_seconds": loading,
                "inference": phases,
                "policy_and_bookkeeping_seconds": policy_seconds,
                **{f"native_{name}": seconds for name, seconds in native_totals.items()},
                "encoding_calls": self.completed_encode_attempts,
                "prediction_passes": 1,
                "inference_images": len(self.textures),
                "encoded_images": len(self.encoding_indices),
                "scope": (
                    "Reference PNG to selected in-memory mip0 ASTC with real quality gating. "
                    "Synchronous trace hashes and progress writes recorded separately"
                ),
            },
        )
