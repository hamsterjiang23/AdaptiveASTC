from __future__ import annotations

import ctypes
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from PIL import Image

import reproductions.unity_search_baseline.deployment_benchmark as benchmark_module
from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.deployment import (
    UnityDeploymentResult,
    UnityDeploymentTrial,
)
from reproductions.unity_search_baseline.deployment_benchmark import UnityDeploymentBenchmark
from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from tests.test_unity_search_policy import policy


class RecordingBackend(UnityASTCBackend):
    def __init__(self) -> None:
        self.calls: list[JsonDict] = []
        self.empty = False

    def encode_function(
        self,
        pointer: int,
        width: int,
        height: int,
        preset: float,
        hdr: bool,
        block: int,
        output: int,
        profile: int,
        normal: bool,
        name: str | None,
        alpha: bool,
        rdo: bool,
        strength: float,
        threads: int,
    ) -> None:
        source = np.ctypeslib.as_array(
            (ctypes.c_uint8 * (width * height * 4)).from_address(pointer)
        )
        self.calls.append(
            {
                "rgba": source.copy().reshape(height, width, 4),
                "block": block,
                "preset": preset,
                "profile": profile,
                "alpha": alpha,
                "hdr": hdr,
                "normal": normal,
                "name": name,
                "rdo": rdo,
                "strength": strength,
                "threads": threads,
            }
        )
        size = ((width + block - 1) // block) * ((height + block - 1) // block) * 16
        if not self.empty:
            ctypes.memset(output, block, size)

    def decode_payload(
        self, payload: bytes, width: int, height: int, block: int, *, srgb: bool
    ) -> tuple[NDArray[np.uint8], float]:
        raise AssertionError("Decode must not occur inside the measured trial")


class FakePredictor(UnityQualityInference):
    def __init__(self) -> None:
        self.calls = 0
        self.sync_calls = 0
        self.target_index = 10
        self.device = torch.device("cpu")

    def synchronize(self) -> None:
        self.sync_calls += 1

    def run(self, dataset: UnityInferenceInput) -> tuple[dict[str, np.ndarray], JsonDict]:
        self.calls += 1
        assert set(dataset[0]) == {"rgba", "valid_mask", "metadata", "patch_index"}
        mse = np.ones((len(dataset.textures), 20, 4)) * 0.1
        mse[:, self.target_index] = 1e-5
        return {
            "channel_mse": mse,
            "channel_zero": np.zeros(mse.shape, dtype=bool),
            "zero_probability": np.zeros(mse.shape),
            "image_quality": np.full((len(dataset.textures), 20, 3), 30.0),
        }, {"total_seconds": 0.0}


def make_trial(
    tmp_path: Path,
) -> tuple[UnityDeploymentTrial, RecordingBackend, FakePredictor, np.ndarray]:
    pixels = np.arange(7 * 13 * 4, dtype=np.uint8).reshape(7, 13, 4)
    path = tmp_path / "reference.png"
    Image.fromarray(pixels).save(path)
    backend, predictor = RecordingBackend(), FakePredictor()
    trial = UnityDeploymentTrial(
        [UnityInferenceTexture(path, True, False, True)],
        [policy()],
        [backend],
        predictor,
        240,
        "medium",
    )
    return trial, backend, predictor, pixels


def test_dynamic_prediction_selects_exactly_one_encoding_without_decode(tmp_path: Path) -> None:
    trial, backend, predictor, pixels = make_trial(tmp_path)
    first = trial.run(predicted=True)
    predictor.target_index = 18
    second = trial.run(predicted=True)
    fixed = trial.run(predicted=False)
    assert predictor.calls == 2 and predictor.sync_calls == 4
    assert [(c["block"], c["preset"]) for c in backend.calls] == [(8, 0), (6, 98), (8, 60)]
    for call in backend.calls:
        np.testing.assert_array_equal(call["rgba"], pixels[::-1])
        assert call["profile"] == 0 and call["alpha"]
        assert not call["hdr"] and not call["normal"] and not call["rdo"]
        assert call["name"] is None and call["strength"] == call["threads"] == 0
    for result, block in [(first, 8), (second, 6), (fixed, 8)]:
        assert result.timings["encoding_calls"] == 1
        assert result.timings["end_to_end_seconds"] >= result.timings["native_encode_seconds"]
        assert result.containers[0][4:7] == bytes([block, block, 1])
        assert (
            len(result.containers[0])
            == 16 + ((13 + block - 1) // block) * ((7 + block - 1) // block) * 16
        )
    assert fixed.predictions is None and not fixed.timings["inference"]


@pytest.mark.parametrize("srgb,alpha", [(False, False), (False, True), (True, False)])
def test_encoder_profile_and_alpha_are_input_properties(srgb: bool, alpha: bool) -> None:
    backend = RecordingBackend()
    spec = UnityInferenceTexture(Path("unused"), srgb, False, alpha)
    UnityDeploymentTrial.encode(backend, np.ones((3, 5, 4), dtype=np.uint8), 12, "fast", spec)
    assert backend.calls[0]["profile"] == (0 if srgb else 1)
    assert backend.calls[0]["alpha"] is alpha


def test_empty_encoder_output_is_failure(tmp_path: Path) -> None:
    trial, backend, _, _ = make_trial(tmp_path)
    backend.empty = True
    with pytest.raises(RuntimeError, match="empty deployment"):
        trial.run(predicted=False)


def test_pixel_metadata_keeps_exact_black_ratio(tmp_path: Path) -> None:
    pixels = np.ones((7, 13, 4), dtype=np.uint8)
    pixels[0, 0, :3] = 0
    spec = UnityInferenceTexture(tmp_path / "unused", False, False, False)
    texture = UnityDeploymentTrial.texture_input(pixels, spec)
    assert texture.black_pixel_ratio == 1 / 91
    assert texture.black_pixel_ratio != float(np.float32(1 / 91))
    assert texture.alpha_constant


@pytest.mark.parametrize("changed", ["empty", "counts", "preset"])
def test_invalid_trial_inputs_rejected(tmp_path: Path, changed: str) -> None:
    trial, backend, predictor, _ = make_trial(tmp_path)
    with pytest.raises(ValueError):
        UnityDeploymentTrial(
            [] if changed == "empty" else trial.textures,
            [policy()],
            [] if changed == "counts" else [backend],
            predictor,
            240,
            "unknown" if changed == "preset" else "medium",
        )


@pytest.mark.parametrize("case", ["empty", "failed", "changed", "wait"])
def test_dependency_gate_precedes_inputs_and_cuda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    events: list[str] = []
    config, report = tmp_path / "config.json", tmp_path / "report.json"
    encoding = tmp_path / "encoding.json"
    A.write_json(encoding, {})
    A.write_json(
        config,
        {
            "output": str(tmp_path / "experiment report/.local/queued"),
            "report": str(report),
            "warmups": 1,
            "repetitions": 1,
            "dependencies": [] if case == "empty" else [{}],
            "sources_sha256": {"version": "before"},
            "encoding_config": str(encoding),
            "encoding_config_sha256": A.sha256_file(encoding),
        },
    )

    def sources(root: Path) -> dict[str, str]:
        return {"version": "after" if case == "changed" and events else "before"}

    def dependency(item: JsonDict) -> JsonDict:
        events.append("observe")
        if case == "failed":
            raise RuntimeError("failed upstream")
        return {"status": "running" if case == "wait" and "sleep" not in events else "passed"}

    def sleep(seconds: int) -> None:
        assert seconds == 15
        events.append("sleep")

    def prepare(self: UnityFinalEncoding) -> None:
        events.append("prepare")
        raise RuntimeError("stop before cuda")

    monkeypatch.setattr(UnityDeploymentBenchmark, "execution_sources", staticmethod(sources))
    monkeypatch.setattr(UnityNativeDataPipeline, "dependency_status", dependency)
    monkeypatch.setattr(benchmark_module.time, "sleep", sleep)
    monkeypatch.setattr(UnityFinalEncoding, "prepare", prepare)
    with pytest.raises((RuntimeError, ValueError)):
        UnityDeploymentBenchmark(tmp_path, config).run()
    expected = {
        "empty": [],
        "failed": ["observe"],
        "changed": ["observe"],
        "wait": ["observe", "sleep", "observe", "prepare"],
    }
    assert events == expected[case]
    if case == "empty":
        assert not report.exists()
    else:
        state = A.read_json(report)
        assert state["status"] == "failed" and not state["measurements"]
        assert not state["test_opened"] and state["training_updates"] == 0


def test_audit_rejects_wrong_fresh_choice_before_decoding(tmp_path: Path) -> None:
    result = UnityDeploymentResult(
        [b"unused"], [{"selected_index": 0}], {"channel_zero": np.zeros((1, 20, 4), dtype=bool)}, {}
    )
    binding = cast(UnityFinalEncoding, object())
    with pytest.raises(ValueError, match="Fresh deployment choices"):
        UnityDeploymentBenchmark.audit(
            binding,
            result,
            [],
            [{"predicted_decision": {"selected_index": 1}}],
            [],
            {"channel_zero": np.zeros((1, 20, 4), dtype=bool)},
            tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()
