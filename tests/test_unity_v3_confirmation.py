from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline import v3_confirmation as module
from reproductions.unity_search_baseline.deployment import UnityDeploymentResult
from reproductions.unity_search_baseline.v3_confirmation import UnityV3Confirmation


class FakeTrial:
    def __init__(self, indices: list[int]) -> None:
        self.indices = indices

    def run(
        self, arm: str, *, single_image: bool, reference_pixels: list[np.ndarray]
    ) -> UnityDeploymentResult:
        assert arm == "forward"
        assert len(reference_pixels) == len(self.indices)
        count = len(self.indices)
        values = np.asarray(self.indices, dtype=np.float64)
        return UnityDeploymentResult(
            [bytes([index]) for index in self.indices],
            [{"source_index": index} for index in range(count)],
            {"channel_mse": values[:, None, None] * np.ones((count, 20, 4))},
            {
                "end_to_end_seconds": count * 0.1,
                "encoding_calls": count,
                **({"single_image_latencies_seconds": [0.1] * count} if single_image else {}),
            },
        )


@pytest.mark.parametrize("mode", ["batch", "single"])
def test_pixels_ready_retains_predictions_and_global_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    evaluator = object.__new__(UnityV3Confirmation)
    image = tmp_path / "reference.png"
    Image.new("RGBA", (1, 1)).save(image)
    evaluator.entries = [{} for _ in range(10)]
    evaluator.textures = [SimpleNamespace(reference=image) for _ in range(10)]

    def trial(case: JsonDict, indices: list[int]) -> FakeTrial:
        assert case["arm"] == "forward"
        return FakeTrial(indices)

    monkeypatch.setattr(evaluator, "trial", trial)
    result = evaluator.measure({"arm": "forward"}, "pixels_ready", mode)
    assert [choice["source_index"] for choice in result.choices] == list(range(10))
    assert result.predictions is not None
    np.testing.assert_array_equal(result.predictions["channel_mse"][:, 0, 0], np.arange(10))
    assert result.timings["encoding_calls"] == 10
    if mode == "single":
        assert result.timings["single_image_latencies_seconds"] == [0.1] * 10


def test_output_manifest_detects_changed_saved_file(tmp_path: Path) -> None:
    output = tmp_path / "prediction.npz"
    output.write_bytes(b"original")
    manifest = tmp_path / "outputs.json"
    A.write_json(manifest, {"files_sha256": {str(output): A.sha256_file(output)}})
    trace = tmp_path / "trace.json.gz"
    trace.write_bytes(b"trace")
    measurements = [
        {
            "outputs_manifest": {"path": str(manifest), "sha256": A.sha256_file(manifest)},
            "trace": str(trace),
            "trace_sha256": A.sha256_file(trace),
            "predictions_archive": {"path": str(output), "sha256": A.sha256_file(output)},
        }
    ]
    UnityV3Confirmation.verify_outputs(measurements)
    output.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Saved confirmation output changed"):
        UnityV3Confirmation.verify_outputs(measurements)


def test_optional_absence_binding_is_verified(tmp_path: Path) -> None:
    evaluator = object.__new__(UnityV3Confirmation)
    absent = tmp_path / "batch-assembly.json"
    evaluator.bindings = {str(absent): None}
    evaluator.verify()
    absent.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Previously absent bound input appeared"):
        evaluator.verify()


class FakeAdapter:
    def __init__(self, rows: list[JsonDict], split: str) -> None:
        assert split == "validation"
        self.fingerprint = "smoke-input-fingerprint"


def prepared_evaluator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UnityV3Confirmation:
    evaluator = object.__new__(UnityV3Confirmation)
    evaluator.public = tmp_path
    evaluator.report = tmp_path / "result.json"
    evaluator.config_path = tmp_path / "config.json"
    A.write_json(evaluator.config_path, {"test": "fixed-config"})
    smoke_input = tmp_path / "smoke-input.json"
    A.write_json(smoke_input, {"rows": []})
    evaluator.config = {"smoke_inputs": str(smoke_input), "timing": {}}
    evaluator.bindings = {}
    evaluator.case = {"name": "forward-unity-full20"}
    evaluator.adapter = SimpleNamespace(fingerprint="b" * 64)
    evaluator.predictor = SimpleNamespace(device=torch.device("cpu"))
    evaluator.input_snapshot = {"reservation_sha256": "a" * 64, "policy_bindings": []}
    cohort = A.fingerprint({"reservation": "a" * 64, "split": "confirmation"})
    evaluator.contract = {
        "confirmation_registry": {"cohort_fingerprint": cohort, "registry": str(tmp_path)},
        "cohort": {"native_input_fingerprint": "b" * 64},
        "selected_system": {"checkpoint_sha256": "c" * 64},
    }
    A.write_json(
        tmp_path / "smoke-result.json",
        {
            "status": "passed",
            "test_opened": False,
            "execution_config_sha256": A.sha256_file(evaluator.config_path),
            "checkpoint_sha256": "c" * 64,
            "input_fingerprint": "smoke-input-fingerprint",
            "measurements": [],
        },
    )
    monkeypatch.setattr(module, "UnityCaptureInputAdapter", FakeAdapter)
    monkeypatch.setattr(evaluator, "load_inputs", lambda smoke: None)
    monkeypatch.setattr(evaluator, "verify_outputs", lambda measurements: None)
    return evaluator


def test_stale_smoke_config_rejected_before_cohort_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluator = prepared_evaluator(tmp_path, monkeypatch)
    A.write_json(evaluator.config_path, {"test": "changed-config"})
    with pytest.raises(ValueError, match="Development smoke must pass"):
        evaluator.run_confirmation()
    assert not (
        tmp_path / evaluator.contract["confirmation_registry"]["cohort_fingerprint"]
    ).exists()


def test_seal_verification_failure_marks_formal_report_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluator = prepared_evaluator(tmp_path, monkeypatch)

    class FailingSeal:
        def __init__(self, registry: Path, identity: JsonDict) -> None:
            self.path = registry / identity["cohort_fingerprint"] / "seal.json"
            self.fingerprint = "d" * 64

        def acquire(self) -> None:
            self.path.parent.mkdir(parents=True)
            self.path.write_text("{}", encoding="utf-8")

        def forward(self, operation: object) -> JsonDict:
            assert callable(operation)
            operation()
            raise ValueError("sealed input changed after evaluation")

    def evaluate(smoke: bool) -> JsonDict:
        assert smoke is False
        result = {"status": "audited_pending_seal_verification", "test_opened": True}
        A.write_json(evaluator.report, result)
        return result

    monkeypatch.setattr(module, "UnityEvaluationSeal", FailingSeal)
    monkeypatch.setattr(evaluator, "evaluate", evaluate)
    with pytest.raises(ValueError, match="sealed input changed"):
        evaluator.run_confirmation()
    report = A.read_json(evaluator.report)
    assert report["status"] == "failed"
    assert "sealed input changed" in report["error"]
