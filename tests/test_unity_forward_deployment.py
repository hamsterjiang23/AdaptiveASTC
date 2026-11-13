from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from reproductions.unity_search_baseline.deployment import UnityDeploymentTrial
from reproductions.unity_search_baseline.forward_deployment import (
    NativeForwardQueries,
    UnityForwardSearchTrial,
)
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.system_variant_policy import forward_search


def policy() -> UnitySearchPolicy:
    return UnitySearchPolicy(
        {
            "schemaVersion": 2,
            "astcOptimizerEnabled": True,
            "rdoGlobalEnabled": False,
            "targetPsnrDb": 30,
            "targetMsSsimDb": 21,
            "targetNormalMeanDeg": 3.2,
            "targetNormalP95Deg": 9,
            "blackPixelRatioMild": 0.4,
            "blackPixelRatioStrong": 0.8,
            "blackElevatedPsnrMildDb": 35,
            "blackElevatedPsnrStrongDb": 37,
            "sizeFirstMinSideLarge": 512,
        }
    )


def metrics(*, passed: bool = False, psnr: float = 20.0) -> JsonDict:
    return {
        "psnr": 35.0 if passed else psnr,
        "black_pixel_ratio": 0.0,
        "ms_ssim_db": 25.0 if passed else 10.0,
        "normal_mean_deg": 2.0 if passed else 5.0,
        "normal_p95_deg": 5.0 if passed else 12.0,
        "mip_count": 1,
        "need_alpha": False,
    }


class FakeBackend(UnityASTCBackend):
    def __init__(self, fail_at: int | None = None) -> None:
        self.calls: list[int] = []
        self.fail_at = fail_at

    def encode_decode(
        self,
        rgba: NDArray[np.uint8],
        block: int,
        preset: str,
        *,
        srgb: bool,
        need_alpha: bool,
    ) -> tuple[bytes, NDArray[np.uint8], JsonDict]:
        index = UnityQualityPrediction.GRID.index((block, preset))
        self.calls.append(index)
        if index == self.fail_at:
            raise RuntimeError("Fake native failure")
        height, width = rgba.shape[:2]
        payload = bytes([index + 1]) * (
            16 * ((width + block - 1) // block) * ((height + block - 1) // block)
        )
        decoded = np.full(rgba.shape, index, dtype=np.uint8)
        return payload, decoded, {"encode_seconds": 0.0, "decode_seconds": 0.0}


class FakeQuality(UnityQuality):
    def __init__(self, values: dict[int, JsonDict]) -> None:
        self.values = values
        self.calls: list[int] = []
        self.mips: list[int] = []

    def measure(
        self,
        original: NDArray[np.uint8],
        decoded: NDArray[np.uint8],
        *,
        need_alpha: bool,
        compute_ssim: bool,
        normal: bool = False,
        mip_count: int = 1,
    ) -> JsonDict:
        index = int(decoded[0, 0, 0])
        self.calls.append(index)
        self.mips.append(mip_count)
        return {
            **self.values.get(index, metrics()),
            "need_alpha": need_alpha,
            "mip_count": mip_count,
        }


def queries(
    index: int,
    values: dict[int, JsonDict],
    *,
    large: bool = False,
    normal: bool = False,
    fail_at: int | None = None,
) -> tuple[NativeForwardQueries, FakeBackend, FakeQuality]:
    side = 512 if large else 4
    rgba = np.full((side, side, 4), 50, dtype=np.uint8)
    spec = UnityInferenceTexture(Path("unused.png"), not normal, normal, False, 4 if normal else 1)
    texture = UnityDeploymentTrial.texture_input(rgba, spec)
    candidates = [
        {"block": block, "preset": preset, "metrics": metrics()}
        for block, preset in UnityQualityPrediction.GRID
    ]
    candidates[index]["metrics"] = metrics(passed=True)
    native_policy = policy()
    predicted = native_policy.select(
        candidates, width=side, height=side, srgb=not normal, normal=normal
    )
    assert predicted.selected_index == index
    backend, quality = FakeBackend(fail_at), FakeQuality(values)
    return (
        NativeForwardQueries(rgba, spec, texture, native_policy, predicted, backend, quality),
        backend,
        quality,
    )


def test_real_query_stops_at_first_pass_and_reuses_measured_container() -> None:
    query, backend, quality = queries(7, {7: metrics(passed=True)})
    outcome = forward_search(query)
    assert outcome.selected_index == 7
    assert backend.calls == quality.calls == [7]
    assert query.measure(7)
    assert backend.calls == [7] and query.encode_attempts == 1
    assert query.containers[7].startswith(bytes.fromhex("13aba15c"))
    assert query.entry["candidates"][0]["metrics"] == {}


def test_real_quality_can_reject_model_start_and_continue_forward() -> None:
    query, backend, quality = queries(7, {9: metrics(passed=True)})
    outcome = forward_search(query)
    assert outcome.selected_index == 9
    assert backend.calls == quality.calls == [7, 8, 9]
    assert outcome.reason == "first_valid"


def test_real_large_lock_counts_lookahead_and_retains_last_psnr_pass() -> None:
    query, backend, _ = queries(
        5, {7: metrics(psnr=34.0), 9: metrics(psnr=31.0), 10: metrics(passed=True)}, large=True
    )
    outcome = forward_search(query)
    assert outcome.selected_index == 9 and outcome.reason == "size_first_relaxed"
    assert backend.calls == [5, 6, 7, 8, 9, 10]


def test_real_fallback_uses_measured_candidates_and_leaves_prefix_unobserved() -> None:
    query, backend, _ = queries(17, {0: metrics(psnr=100.0), 18: metrics(psnr=29.0)})
    outcome = forward_search(query)
    assert outcome.selected_index == 18
    assert backend.calls == [17, 18, 19]
    assert query.entry["candidates"][0]["metrics"] == {}


def test_real_normal_quality_uses_captured_mip_scope() -> None:
    query, backend, quality = queries(7, {7: metrics(passed=True)}, normal=True)
    outcome = forward_search(query)
    assert outcome.selected_index == 7 and backend.calls == [7]
    assert quality.mips == [4]


def test_native_failure_preserves_attempt_count_without_synthetic_result() -> None:
    query, backend, _ = queries(7, {}, fail_at=7)
    with pytest.raises(RuntimeError, match="Fake native failure"):
        forward_search(query)
    assert query.encode_attempts == 1 and backend.calls == [7]
    assert query.records == [] and query.containers == {}


class FakePredictor:
    def __init__(self) -> None:
        self.calls = 0

    def synchronize(self) -> None:
        return None

    def run(self, dataset: UnityInferenceInput) -> tuple[dict[str, np.ndarray], JsonDict]:
        self.calls += 1
        mse = np.full((1, 20, 4), 0.01, dtype=np.float64)
        mse[0, 7] = 10**-3.5
        quality = np.full((1, 20, 3), 10.0, dtype=np.float64)
        quality[0, 7, 0] = 25.0
        return {
            "channel_mse": mse,
            "channel_zero": np.zeros(mse.shape, dtype=np.bool_),
            "zero_probability": np.zeros_like(mse),
            "image_quality": quality,
        }, {"patches": len(dataset)}


def test_trial_fresh_prediction_then_real_gating_accepts_input_specs_only(tmp_path: Path) -> None:
    path = tmp_path / "reference.png"
    Image.fromarray(np.full((4, 4, 4), 50, dtype=np.uint8)).save(path)
    spec = UnityInferenceTexture(path, True, False, False)
    predictor = FakePredictor()
    backend, quality = FakeBackend(), FakeQuality({8: metrics(passed=True)})
    trial = UnityForwardSearchTrial(
        [spec], [policy()], [backend], [quality], cast(UnityQualityInference, predictor), 240, [0]
    )
    result = trial.run()
    assert predictor.calls == 1
    assert result.choices[0]["starting_decision"]["selected_index"] == 7
    assert result.choices[0]["selected_index"] == 8
    assert result.timings["encoding_calls"] == 2
    assert result.choices[0]["selected_encoded_result_reused"] is True
    assert result.choices[0]["unmeasured_prefix_backfill_needed"] is None
    assert backend.calls == quality.calls == [7, 8]
