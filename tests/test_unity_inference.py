from pathlib import Path
from typing import cast

import numpy as np
import pytest
import torch
from PIL import Image
from torch import Tensor, nn

import reproductions.unity_search_baseline.inference_benchmark as benchmark_module
from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding
from reproductions.unity_search_baseline.inference_benchmark import UnityInferenceBenchmark
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline


def test_timing_summary_reports_batched_amortization_and_ignores_warmup() -> None:
    measurements = [
        {
            "warmup": warmup,
            "preprocess_inference_decision_seconds": seconds,
            "inference": {"patch_forward_and_transfer_seconds": seconds / 10, "patches": 30},
        }
        for warmup, seconds in [(True, 100), (False, 6), (False, 2), (False, 4)]
    ]
    result = UnityInferenceBenchmark.timing_summary(measurements, 2)
    assert result["validation_images"] == 2 and result["input_patches"] == 30
    assert result["median_preprocess_inference_decision_seconds"] == 4
    assert result["amortized_preprocess_inference_decision_seconds_per_image"] == 2
    assert result["median_patch_forward_and_transfer_seconds"] == pytest.approx(0.4)
    assert result["amortized_patch_forward_and_transfer_seconds_per_image"] == pytest.approx(0.2)


def test_benchmark_requires_explicit_matching_training_source_archive(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("original training source", encoding="utf-8")
    digest = A.sha256_file(source)
    archive = tmp_path / "archive"
    archive.mkdir()
    historical = archive / "source.py"
    historical.write_bytes(source.read_bytes())
    source.write_text("current runtime source", encoding="utf-8")
    path = tmp_path / "config.json"
    A.write_json(path, {})
    settings = {"source_sha256": {str(source): digest}}
    with pytest.raises(ValueError, match="changed"):
        UnityInferenceBenchmark(tmp_path, path).bind_training_sources(
            UnityFinalEncoding(tmp_path, path), settings
        )
    A.write_json(path, {"training_source_archive": str(archive)})
    runner, binding = UnityInferenceBenchmark(tmp_path, path), UnityFinalEncoding(tmp_path, path)
    result = runner.bind_training_sources(binding, settings)
    assert result is not None and result["archive"] == str(archive)
    assert binding.inputs[str(historical)] == digest
    historical.write_text("changed archive", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        binding.bind(historical, digest)
    with pytest.raises(ValueError, match="source snapshot"):
        runner.bind_training_sources(UnityFinalEncoding(tmp_path, path), settings)


def make_inputs(tmp_path: Path) -> UnityInferenceInput:
    paths = [tmp_path / "wide.png", tmp_path / "normal.png"]
    wide = np.zeros((123, 250, 4), dtype=np.uint8)
    wide[:, :, 3] = 255
    wide[1, 1] = [17, 25, 33, 200]
    Image.fromarray(wide).save(paths[0])
    normal = np.full((3, 5, 4), [128, 128, 255, 255], dtype=np.uint8)
    Image.fromarray(normal).save(paths[1])
    return UnityInferenceInput(
        [
            UnityInferenceTexture(paths[0], True, False, True),
            UnityInferenceTexture(paths[1], False, True, False, 3),
        ]
    )


def test_inputs_match_training_dataset_without_supervision_files(tmp_path: Path) -> None:
    inputs = make_inputs(tmp_path)
    assert inputs.sizes == [(250, 123), (5, 3)]
    assert inputs.boxes.tolist() == [[0, 0, 240, 123], [240, 0, 10, 123], [0, 0, 5, 3]]
    expected = np.array(
        [
            [np.log2(250), np.log2(123), 1, 0, 1, 0, 1, 1 - 1 / (250 * 123)],
            [np.log2(5), np.log2(3), 0, 1, 0, 1, 3, 0],
        ],
        dtype=np.float32,
    )
    np.testing.assert_array_equal(inputs.input_metadata, expected)
    training = object.__new__(UnityPatchDataset)
    training.rows = [{"reference": str(texture.reference)} for texture in inputs.textures]
    training.patch_size = 240
    training.boxes, training.image_ids = inputs.boxes, inputs.image_ids
    training.input_metadata = expected
    training.targets = np.zeros((len(inputs), 20, 4), dtype=np.float32)
    training.zero_error = np.ones((len(inputs), 20, 4), dtype=np.bool_)
    for index in range(len(inputs)):
        item, original = inputs[index], training[index]
        assert set(item) == {"rgba", "valid_mask", "metadata", "patch_index"}
        for key in item:
            torch.testing.assert_close(item[key], original[key], rtol=0, atol=0)
    assert inputs[1]["valid_mask"].sum().item() == 1230
    assert inputs[0]["rgba"][0, 1, 1].item() == pytest.approx(17 / 255)


@pytest.mark.parametrize(
    "srgb,normal,mips", [(True, True, 1), (False, True, 0), (False, True, 5), (True, False, 2)]
)
def test_invalid_importer_scope_rejected(srgb: bool, normal: bool, mips: int) -> None:
    with pytest.raises(ValueError, match="normal/mip scope"):
        UnityInferenceTexture(Path("unused"), srgb, normal, False, mips).validate()


def test_nonboolean_importer_flags_rejected() -> None:
    with pytest.raises(ValueError, match="boolean"):
        UnityInferenceTexture(Path("unused"), cast(bool, 1), False, False).validate()


class FakeModel(UnityQualityRegressor):
    def __init__(self) -> None:
        nn.Module.__init__(self)
        self.batch_lengths: list[int] = []

    def encode(self, rgba: Tensor, valid_mask: Tensor, metadata: Tensor) -> dict[str, Tensor]:
        self.batch_lengths.append(len(rgba))
        return {
            "features": torch.ones((len(rgba), 512)),
            "channel_log_mse": torch.full((len(rgba), 20, 4), -3.0),
        }

    def predict_images(
        self, features: Tensor, valid_pixels: Tensor, image_ids: Tensor, metadata: Tensor
    ) -> dict[str, Tensor]:
        return {
            "channel_zero_logits": torch.full((len(metadata), 20, 4), -4.0),
            "image_quality": torch.ones((len(metadata), 20, 3)),
        }


def test_streamed_prediction_covers_all_patches_and_aggregates_mse(tmp_path: Path) -> None:
    inputs, model = make_inputs(tmp_path), FakeModel()
    predictions, timing = UnityQualityInference(model, torch.device("cpu"), 2).run(inputs)
    assert model.batch_lengths == [2, 1] and not model.training
    assert predictions["channel_mse"].shape == (2, 20, 4)
    np.testing.assert_allclose(predictions["channel_mse"], 0.001 - 1e-10)
    assert not predictions["channel_zero"].any()
    assert timing["images"] == 2 and timing["patches"] == 3
    for key, value in timing.items():
        if key.endswith("seconds"):
            assert 0 <= value <= timing["total_seconds"]


@pytest.mark.parametrize(
    "batch,threshold", [(0, 0.5), (True, 0.5), (2, 0), (2, 1), (2, float("nan"))]
)
def test_invalid_inference_configuration_rejected(batch: int, threshold: float) -> None:
    with pytest.raises(ValueError, match="Positive inference batch"):
        UnityQualityInference(FakeModel(), torch.device("cpu"), batch, threshold)


@pytest.mark.parametrize("upstream_failed", [False, True])
def test_waits_for_terminal_job_before_input_or_cuda_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    upstream_failed: bool,
) -> None:
    events: list[str] = []
    report = tmp_path / "public.json"
    encoding = tmp_path / "encoding.json"
    A.write_json(encoding, {})
    config = tmp_path / "config.json"
    A.write_json(
        config,
        {
            "output": str(tmp_path / "experiment report/.local/queued"),
            "report": str(report),
            "warmups": 1,
            "repetitions": 3,
            "sources_sha256": {},
            "dependencies": [{}],
            "encoding_config": str(encoding),
            "encoding_config_sha256": A.sha256_file(encoding),
        },
    )

    def sources(root: Path) -> dict[str, str]:
        return {}

    def dependency(item: JsonDict) -> JsonDict:
        events.append("observe")
        if upstream_failed:
            raise RuntimeError("failed-upstream")
        return {"status": "passed" if "sleep" in events else "running"}

    def sleep(seconds: int) -> None:
        assert seconds == 15
        events.append("sleep")

    def prepare(self: UnityFinalEncoding) -> None:
        events.append("prepare")
        raise RuntimeError("stop-before-cuda")

    monkeypatch.setattr(UnityInferenceBenchmark, "execution_sources", staticmethod(sources))
    monkeypatch.setattr(UnityNativeDataPipeline, "dependency_status", dependency)
    monkeypatch.setattr(benchmark_module.time, "sleep", sleep)
    monkeypatch.setattr(UnityFinalEncoding, "prepare", prepare)
    expected = "failed-upstream" if upstream_failed else "stop-before-cuda"
    with pytest.raises(RuntimeError, match=expected):
        UnityInferenceBenchmark(tmp_path, config).run()
    assert events == (
        ["observe"] if upstream_failed else ["observe", "sleep", "observe", "prepare"]
    )
    result = A.read_json(report)
    assert result["status"] == "failed" and result["training_updates"] == 0
    assert result["measurements"] == [] and not result["test_opened"]


def test_empty_training_dependencies_are_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    A.write_json(
        config,
        {
            "output": str(tmp_path / "experiment report/.local/queued"),
            "report": str(tmp_path / "report.json"),
            "warmups": 1,
            "repetitions": 1,
            "dependencies": [],
        },
    )
    with pytest.raises(ValueError, match="bound training dependency"):
        UnityInferenceBenchmark(tmp_path, config).run()
    assert not (tmp_path / "report.json").exists()


def test_source_change_during_wait_fails_before_input_or_cuda(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[bool] = []
    config = tmp_path / "config.json"
    report = tmp_path / "report.json"
    A.write_json(
        config,
        {
            "output": str(tmp_path / "experiment report/.local/queued"),
            "report": str(report),
            "warmups": 1,
            "repetitions": 1,
            "dependencies": [{}],
            "sources_sha256": {"version": "before"},
        },
    )

    def sources(root: Path) -> dict[str, str]:
        return {"version": "after" if observed else "before"}

    def dependency(item: JsonDict) -> JsonDict:
        observed.append(True)
        return {"status": "passed"}

    monkeypatch.setattr(UnityInferenceBenchmark, "execution_sources", staticmethod(sources))
    monkeypatch.setattr(UnityNativeDataPipeline, "dependency_status", dependency)
    with pytest.raises(ValueError, match="changed while waiting"):
        UnityInferenceBenchmark(tmp_path, config).run()
    result = A.read_json(report)
    assert result["status"] == "failed" and result["measurements"] == []
