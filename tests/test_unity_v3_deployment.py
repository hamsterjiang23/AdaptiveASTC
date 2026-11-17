from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.data.unity_v3_input import SourceTextureSpec
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.v3_deployment import (
    UnityV3DeploymentTrial,
    V3NativeQueries,
)
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy
from tests.test_unity_deployment import RecordingBackend
from tests.test_unity_forward_deployment import FakeBackend, FakeQuality, metrics, policy


class Predictor:
    def __init__(self, target: int = 7, psnr: float = 40.0) -> None:
        self.target, self.psnr = target, psnr
        self.calls = self.syncs = 0
        self.inputs: list[NDArray[np.float32]] = []

    def synchronize(self) -> None:
        self.syncs += 1

    def run(self, dataset: UnityInferenceInput) -> tuple[dict[str, np.ndarray], JsonDict]:
        self.calls += 1
        self.inputs.append(dataset.input_metadata.copy())
        # Exercise iteration too: file-to-ASTC timing includes misses in the bounded cache.
        for index in range(len(dataset)):
            assert dataset[index]["rgba"].shape == (4, 240, 240)
        count = len(dataset.textures)
        mse = np.full((count, 20, 4), 0.1)
        mse[:, self.target] = 10 ** (-self.psnr / 10)
        quality = np.full((count, 20, 3), 10.0)
        quality[:, self.target, 0] = 30.0
        return {
            "channel_mse": mse,
            "channel_zero": np.zeros(mse.shape, dtype=np.bool_),
            "zero_probability": np.zeros_like(mse),
            "image_quality": quality,
        }, {"total_seconds": 0.0, "images": count, "patches": len(dataset)}


def make_trial(
    tmp_path: Path,
    *,
    values: dict[int, JsonDict] | None = None,
    candidate_set: NativeCandidateSet = NativeCandidateSet(),
    source: NDArray[np.uint8] | None = None,
    input_mode: str = "unity",
    predictor: Predictor | None = None,
    backend: UnityASTCBackend | None = None,
) -> tuple[UnityV3DeploymentTrial, FakeBackend | UnityASTCBackend, FakeQuality, Predictor]:
    reference = np.full((4, 4, 4), 50, dtype=np.uint8)
    path = tmp_path / "reference.png"
    Image.fromarray(reference).save(path)
    encoder = backend if backend is not None else FakeBackend()
    quality = FakeQuality(values if values is not None else {7: metrics(passed=True)})
    model = predictor if predictor is not None else Predictor()
    sources = None
    if source is not None:
        source_path = tmp_path / "source.png"
        Image.fromarray(source).save(source_path)
        sources = [
            SourceTextureSpec.from_file(
                source_path,
                target_width=4,
                target_height=4,
                srgb=True,
                normal=False,
                need_alpha=False,
            )
        ]
    trial = UnityV3DeploymentTrial(
        [UnityInferenceTexture(path, True, False, False)],
        [policy()],
        [encoder],
        [quality],
        cast(UnityQualityInference, model),
        candidate_set=candidate_set,
        source_specs=sources,
        input_mode=input_mode,
    )
    return trial, encoder, quality, model


def test_forward_uses_real_queries_and_reuses_selected_astc(tmp_path: Path) -> None:
    trial, backend, quality, predictor = make_trial(tmp_path, values={8: metrics(passed=True)})
    result = trial.run("forward")
    assert predictor.calls == 1 and predictor.syncs >= 2
    assert cast(FakeBackend, backend).calls == quality.calls == [7, 8]
    choice = result.choices[0]
    assert choice["starting_decision"]["selected_index"] == 7
    assert choice["selected_index"] == 8
    assert choice["measured_indices"] == choice["quality_checked_indices"] == [7, 8]
    assert choice["selected_encoded_result_reused"]
    assert result.timings["encoding_calls"] == 2
    assert result.timings["file_to_astc_seconds"] == result.timings["end_to_end_seconds"]
    assert result.timings["pixels_ready_seconds"] is None


def test_original_search_does_not_run_model_or_read_source(tmp_path: Path) -> None:
    trial, backend, quality, _ = make_trial(tmp_path, values={2: metrics(passed=True)})
    trial.predictor = None
    trial.input_mode = "source_native"
    result = trial.run("original")
    assert cast(FakeBackend, backend).calls == quality.calls == [0, 1, 2]
    assert result.predictions is None and result.timings["prediction_passes"] == 0
    assert result.choices[0]["starting_decision"] is None
    assert result.choices[0]["selection_reason"] == "first_valid"


def test_source_start_is_independent_of_unity_reference_and_gate_uses_true_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = np.zeros((8, 8, 4), dtype=np.uint8)
    source[:, :, 3] = np.arange(8, dtype=np.uint8)
    trial, backend, quality, predictor = make_trial(
        tmp_path,
        source=source,
        input_mode="source_aligned",
        predictor=Predictor(psnr=34),
        values={7: metrics(psnr=32) | {"ms_ssim_db": 30.0}},
    )
    original_open = Image.open

    def guarded_open(fp: object, *args: object, **kwargs: object) -> Image.Image:
        if fp == trial.textures[0].reference:
            assert predictor.calls == 1, "Unity reference was read before source prediction"
        return original_open(fp, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Image, "open", guarded_open)
    result = trial.run("forward")
    choice = result.choices[0]
    assert choice["prediction_context"]["black_pixel_ratio"] == 1.0
    assert choice["gate_context"]["black_pixel_ratio"] == 0.0
    assert choice["starting_decision"]["effective_psnr_threshold"] == 37.0
    assert choice["effective_psnr_threshold"] == 30.0
    assert choice["context_difference"]["alpha_constant_changed"]
    assert choice["context_difference"]["threshold"] == -7.0
    assert cast(FakeBackend, backend).calls == quality.calls == [7]
    assert result.timings["source_input_timings"]["resize_seconds"] > 0


def test_no_exhaustive_queries_or_fallback_even_when_predictions_prefer_it(tmp_path: Path) -> None:
    trial, backend, quality, _ = make_trial(
        tmp_path,
        candidate_set=NativeCandidateSet.no_exhaustive16(),
        predictor=Predictor(4),
        values={4: metrics(passed=True), 5: metrics(passed=True)},
    )
    result = trial.run("forward")
    assert result.choices[0]["starting_decision"]["selected_index"] == 0
    assert result.choices[0]["selected_index"] == 5
    assert cast(FakeBackend, backend).calls == quality.calls == [0, 1, 2, 3, 5]
    assert all(index % 5 != 4 for index in result.choices[0]["measured_indices"])


@pytest.mark.parametrize("arm,target", [("pure", 7), ("fixed8", 12)])
def test_single_encode_arms_have_no_runtime_quality_audit(
    tmp_path: Path,
    arm: str,
    target: int,
) -> None:
    backend = RecordingBackend()
    trial, _, quality, predictor = make_trial(tmp_path, backend=backend)
    if arm == "fixed8":
        trial.predictor = None
    result = trial.run(arm)
    assert len(backend.calls) == 1 and not quality.calls
    assert predictor.calls == int(arm == "pure")
    assert result.choices[0]["selected_index"] == target
    assert result.choices[0]["selected_metrics"] is None
    assert result.choices[0]["strict_quality_met"] is None
    assert result.choices[0]["quality_checked_indices"] == []
    assert result.timings["native_decode_seconds"] == 0
    assert result.timings["native_quality_seconds"] == 0


@pytest.mark.parametrize("mode", ["unity", "source_native", "source_aligned"])
def test_pixels_ready_is_independent_measured_scope_without_file_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    source = np.full((8, 8, 4), 50, dtype=np.uint8)
    trial, _, _, _ = make_trial(
        tmp_path,
        source=source if mode != "unity" else None,
        input_mode=mode,
    )
    reference = np.full((4, 4, 4), 50, dtype=np.uint8)

    def no_open(*args: object, **kwargs: object) -> Image.Image:
        raise AssertionError("Pixels-ready trial must not open image files")

    monkeypatch.setattr(Image, "open", no_open)
    result = trial.run(
        "forward",
        reference_pixels=[reference],
        source_pixels=[source] if mode != "unity" else None,
    )
    assert result.timings["file_to_astc_seconds"] is None
    assert result.timings["pixels_ready_seconds"] == result.timings["end_to_end_seconds"]
    assert result.timings["reference_pixel_load_seconds"] == 0
    if mode == "source_native":
        assert result.choices[0]["prediction_context"]["width"] == 4


def test_partial_buffer_scope_is_rejected(tmp_path: Path) -> None:
    source = np.full((4, 4, 4), 50, dtype=np.uint8)
    trial, _, _, _ = make_trial(tmp_path, source=source, input_mode="source_aligned")
    with pytest.raises(ValueError, match="both source and reference"):
        trial.run(reference_pixels=[source])


def test_single_image_latency_uses_separate_prediction_calls(tmp_path: Path) -> None:
    trial, _, _, predictor = make_trial(tmp_path)
    for attr in ["textures", "policies", "backends", "qualities"]:
        setattr(trial, attr, getattr(trial, attr) * 2)
    batch = trial.run()
    assert predictor.calls == 1
    assert batch.timings["single_image_latency_seconds"] is None
    assert "single_image_p95_seconds" not in batch.timings
    single = trial.run(single_image=True)
    assert predictor.calls == 3
    assert single.timings["prediction_passes"] == 2
    assert len(single.timings["single_image_latencies_seconds"]) == 2
    assert single.timings["single_image_p95_seconds"] == float(
        np.percentile(
            single.timings["single_image_latencies_seconds"],
            95,
        )
    )
    assert single.predictions is not None and len(single.predictions["channel_mse"]) == 2
    assert [choice["source_index"] for choice in single.choices] == [0, 1]
    assert trial.progress_state() == {"completed_images": 2, "encoding_attempts": 2}
    assert single.timings["file_to_astc_seconds"] == single.timings["end_to_end_seconds"]


def test_native_failure_preserves_attempt_count(tmp_path: Path) -> None:
    trial, _, _, _ = make_trial(tmp_path, backend=FakeBackend(fail_at=7))
    with pytest.raises(RuntimeError, match="Fake native failure"):
        trial.run()
    assert trial.progress_state() == {"completed_images": 0, "encoding_attempts": 1}
    assert trial.active_queries is not None and trial.active_queries.records == []


def test_native_query_reuses_measured_candidate_without_second_encoding(tmp_path: Path) -> None:
    trial, backend, quality, _ = make_trial(tmp_path)
    pixels = np.full((4, 4, 4), 50, dtype=np.uint8)
    from reproductions.unity_search_baseline.deployment import UnityDeploymentTrial

    query = V3NativeQueries(
        pixels,
        trial.textures[0],
        UnityDeploymentTrial.texture_input(pixels, trial.textures[0]),
        UnityV3Policy(policy()),
        backend,
        cast(UnityQuality, quality),
    )
    first = query.measure(7)
    assert query.measure(7) is first
    assert cast(FakeBackend, backend).calls == [7]
    assert query.containers[7][4:7] == bytes([10, 10, 1])


def test_source_target_mismatch_fails_before_encoding(tmp_path: Path) -> None:
    trial, backend, _, _ = make_trial(
        tmp_path,
        source=np.full((8, 8, 4), 50, dtype=np.uint8),
        input_mode="source_native",
    )
    assert trial.source_specs is not None
    from dataclasses import replace

    trial.source_specs[0] = replace(trial.source_specs[0], target_width=5)
    with pytest.raises(ValueError, match="target dimensions"):
        trial.run()
    assert cast(FakeBackend, backend).calls == []


def test_normal_uses_captured_mip_scope_and_true_reference_row_order(tmp_path: Path) -> None:
    class InspectingBackend(FakeBackend):
        def encode_decode(
            self,
            rgba: NDArray[np.uint8],
            block: int,
            preset: str,
            *,
            srgb: bool,
            need_alpha: bool,
        ) -> tuple[bytes, NDArray[np.uint8], JsonDict]:
            np.testing.assert_array_equal(rgba, pixels[::-1])
            assert not srgb and need_alpha
            return super().encode_decode(rgba, block, preset, srgb=srgb, need_alpha=need_alpha)

    pixels = np.arange(4 * 5 * 4, dtype=np.uint8).reshape(4, 5, 4)
    path = tmp_path / "normal.png"
    Image.fromarray(pixels).save(path)
    backend, quality = InspectingBackend(), FakeQuality({7: metrics(passed=True)})
    trial = UnityV3DeploymentTrial(
        [UnityInferenceTexture(path, False, True, True, 4)],
        [policy()],
        [backend],
        [quality],
        cast(UnityQualityInference, Predictor()),
    )
    result = trial.run()
    assert backend.calls == [7] and quality.mips == [4]
    assert result.choices[0]["strict_quality_met"]


def test_single_image_failure_keeps_completed_and_current_attempt_counts(tmp_path: Path) -> None:
    trial, _, quality, predictor = make_trial(tmp_path)
    trial.textures *= 2
    trial.policies *= 2
    backends: list[UnityASTCBackend] = [FakeBackend(), FakeBackend(fail_at=7)]
    qualities: list[UnityQuality] = [quality, FakeQuality({7: metrics(passed=True)})]
    trial.backends, trial.qualities = backends, qualities
    with pytest.raises(RuntimeError, match="Fake native failure"):
        trial.run(single_image=True)
    assert predictor.calls == 2
    assert trial.progress_state() == {"completed_images": 1, "encoding_attempts": 2}
