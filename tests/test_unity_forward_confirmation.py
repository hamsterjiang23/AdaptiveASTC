from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.data.unity_inference import UnityInferenceInput
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.deployment import (
    UnityDeploymentResult,
    UnityDeploymentTrial,
)
from reproductions.unity_search_baseline.forward_capture_output import (
    UnityForwardCaptureOutputAudit as Audit,
)
from reproductions.unity_search_baseline.forward_confirmation import (
    UnityForwardConfirmationEvaluation as V,
)
from reproductions.unity_search_baseline.forward_deployment import UnityForwardSearchTrial
from reproductions.unity_search_baseline.forward_system_evidence import UnityForwardSystemEvidence
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from tests.test_unity_capture_input import captured_row
from tests.test_unity_forward_deployment import (
    FakeBackend,
    FakePredictor,
    FakeQuality,
    metrics,
    policy,
)


class DecodingBackend(FakeBackend):
    def decode_payload(
        self, payload: bytes, width: int, height: int, block: int, *, srgb: bool
    ) -> tuple[NDArray[np.uint8], float]:
        return np.full((height, width, 4), payload[0] - 1, dtype=np.uint8), 0.0


def capture(root: Path, asset: str = "Assets/folder/image.png") -> JsonDict:
    root.mkdir(parents=True, exist_ok=True)
    row = captured_row(root, split="validation")
    pixels = np.full((7, 250, 4), 50, dtype=np.uint8)
    Image.fromarray(pixels).save(row["reference_png"])
    row["reference_sha256"] = hashlib.sha256(Path(row["reference_png"]).read_bytes()).hexdigest()
    row["actual_options"]["rgba_sha256"] = hashlib.sha256(pixels[::-1].tobytes()).hexdigest()
    row["path"] = row["actual_options"]["path"] = row["import_metadata"]["asset"] = asset
    row["selection"] = {
        "asset": asset,
        "block_size": "10x10",
        "preset": "thorough",
        "selection_reason": "first_valid",
    }
    return row


class CohortPredictor(FakePredictor):
    def __init__(self) -> None:
        super().__init__()
        self.model = torch.nn.Identity()
        self.cohorts: list[int] = []

    def run(self, dataset: UnityInferenceInput) -> tuple[dict[str, np.ndarray], JsonDict]:
        values, timing = super().run(dataset)
        self.cohorts.append(len(dataset.textures))
        return {
            name: np.repeat(value, len(dataset.textures), axis=0) for name, value in values.items()
        }, timing


def config() -> JsonDict:
    return {
        "schema": "unity-forward-confirmation-v1",
        "evaluation_object": "frozen_prediction_forward_search_system",
        "inference_scope": "whole_cohort",
        "split": "confirmation",
        "images": 2000,
        "warmups": 1,
        "repetitions": 3,
        "image_chunk_size": 2,
        "fixed8_preset": "medium",
        "confirmation_execution_authorized": False,
        "pixel_audit": None,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "old"),
        ("inference_scope", "chunks"),
        ("images", 1000),
        ("fixed8_preset", "fastest"),
        ("confirmation_execution_authorized", 1),
    ],
)
def test_configuration_rejects_changed_protocol(field: str, value: object) -> None:
    settings = config()
    V.validate_config(settings)
    settings[field] = value
    with pytest.raises(ValueError):
        V.validate_config(settings)


def test_execute_gate_runs_before_cohort_evidence() -> None:
    actual = object.__new__(V)
    actual.config = config()
    with pytest.raises(PermissionError, match="remains sealed"):
        actual.run()
    actual.config["confirmation_execution_authorized"] = True
    with pytest.raises(ValueError, match="cohort"):
        actual.run()


def runner(tmp_path: Path) -> V:
    result = object.__new__(V)
    result.config = config()
    result.output = tmp_path / "output"
    result.output.mkdir()
    result.report = tmp_path / "report.json"
    result.evidence = cast(
        UnityForwardSystemEvidence,
        SimpleNamespace(
            policies=[SimpleNamespace(policy=policy())],
            admission={"accuracy": 0.936},
            verify=lambda: None,
        ),
    )
    return result


def fixed_trial(self: UnityDeploymentTrial, *, predicted: bool) -> UnityDeploymentResult:
    assert not predicted
    containers = [
        backend.container(bytes([13]) * (((250 + 7) // 8) * 16), 250, 7, 8)
        for backend in self.backends
    ]
    return UnityDeploymentResult(
        containers,
        [{"selected_index": 12} for _ in containers],
        None,
        {"end_to_end_seconds": 0.01, "encoding_calls": len(containers), "images": len(containers)},
    )


def test_capture_output_audits_multi_query_count_and_selected_payload(tmp_path: Path) -> None:
    row = capture(tmp_path / "input")
    adapter = UnityCaptureInputAdapter([row], "validation")
    backend, quality = DecodingBackend(), FakeQuality({8: metrics(passed=True)})
    result = UnityForwardSearchTrial(
        adapter.textures,
        [policy()],
        [backend],
        [quality],
        cast(UnityQualityInference, FakePredictor()),
        240,
        [0],
    ).run()
    output = Audit.run(
        adapter, [policy()], [backend], [quality], [row["selection"]], result, tmp_path / "output"
    )
    assert (
        result.timings["encoding_calls"] == output["summary"]["candidates_measured"]["total"] == 2
    )
    assert (
        output["summary"]["footprint_accuracy"] == output["summary"]["full_choice_accuracy"] == 1.0
    )
    assert output["summary"]["quality_regression_images"] == 0
    assert output["rows"][0]["selected_index"] == 8
    assert (tmp_path / "output/00000.astc").read_bytes() == result.containers[0]


def test_fixed_control_keeps_real_single_encoding_count(tmp_path: Path) -> None:
    row = capture(tmp_path / "input")
    adapter = UnityCaptureInputAdapter([row], "validation")
    backend, quality = DecodingBackend(), FakeQuality({12: metrics(passed=True)})
    payload = bytes([13]) * (32 * 16)
    result = UnityDeploymentResult(
        [backend.container(payload, 250, 7, 8)],
        [{"selected_index": 12}],
        None,
        {"encoding_calls": 1},
    )
    output = Audit.run(
        adapter, [policy()], [backend], [quality], [row["selection"]], result, tmp_path / "output"
    )
    assert output["summary"]["candidates_measured"]["total"] == 1
    assert output["summary"]["payload_ratio_to_fixed8"] == 1.0


def test_whole_cohort_prediction_and_chunked_artifact_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(UnityDeploymentTrial, "run", fixed_trial)
    actual = runner(tmp_path)
    rows = [capture(tmp_path / f"input{i}", f"Assets/group{i}/image.png") for i in range(3)]
    predictor = CohortPredictor()
    state: JsonDict = {"training_updates": 0}
    result = actual.evaluate(
        rows,
        [0] * 3,
        cast(UnityQualityInference, predictor),
        [DecodingBackend()],
        FakeQuality({8: metrics(passed=True)}),
        state,
    )
    assert predictor.cohorts == [3] * 4
    assert result["repeated_prediction_arrays_exact"]
    assert result["summary"]["prediction"]["measured_encoding_calls"] == 18
    assert result["summary"]["prediction"]["warmup_encoding_calls"] == 6
    assert result["summary"]["fixed8"]["measured_encoding_calls"] == 9
    assert result["summary"]["prediction"]["footprint_accuracy"] == 1.0
    assert not state["test_opened"]
    assert state["chunks_completed"] == 8


def test_fixed_failure_preserves_current_forward_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(self: UnityDeploymentTrial, *, predicted: bool) -> UnityDeploymentResult:
        raise RuntimeError("native fixed failure")

    monkeypatch.setattr(UnityDeploymentTrial, "run", fail)
    actual = runner(tmp_path)
    state: JsonDict = {}
    with pytest.raises(RuntimeError, match="native fixed failure"):
        actual.evaluate(
            [capture(tmp_path / "input")],
            [0],
            cast(UnityQualityInference, CohortPredictor()),
            [DecodingBackend()],
            FakeQuality({8: metrics(passed=True)}),
            state,
        )
    assert state["active_arm"] == "fixed8" and state["active_stage"] == "timed_trial"
    assert state["active_measurement"]["arms"]["prediction"]["timings"]["encoding_calls"] == 2
    assert state["failure_progress"]["encoding_attempts"] is None
    assert (actual.output / "partial-0-prediction/choices.json").exists()
    assert (actual.output / "partial-0-prediction/predictions.npz").exists()


def test_result_slicing_preserves_actual_query_counts() -> None:
    result = UnityDeploymentResult(
        [b"a", b"b"],
        [{"candidates_measured": 3}, {"candidates_measured": 2}],
        {"channel_mse": np.zeros((2, 20, 4))},
        {"encoding_calls": 5},
    )
    sliced = V.slice_result(result, 1, 2)
    assert sliced.timings["encoding_calls"] == 2 and sliced.containers == [b"b"]


def test_confirmation_evaluation_requires_all2000_before_input_reads(tmp_path: Path) -> None:
    actual = runner(tmp_path)
    row = {"source_split": "confirmation"}
    with pytest.raises(PermissionError):
        actual.evaluate(
            [row],
            [0],
            cast(UnityQualityInference, None),
            cast(list[UnityASTCBackend], []),
            FakeQuality({}),
            {},
        )


def test_configuration_bytes_cannot_race_late_hash_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    settings = config()
    settings["system"] = {}
    A.write_json(path, settings)
    original = Path.read_bytes

    def read_then_change(self: Path) -> bytes:
        raw = original(self)
        if self == path:
            A.write_json(path, {**settings, "confirmation_execution_authorized": True})
        return raw

    monkeypatch.setattr(Path, "read_bytes", read_then_change)
    with pytest.raises(ValueError, match="changed"):
        V(tmp_path, path)


def test_execution_quality_must_match_frozen_validation_build(tmp_path: Path) -> None:
    actual = object.__new__(V)
    quality_path = str((tmp_path / "quality.json").resolve())
    actual.config = {
        "system": {"validation_freeze": {"path": "freeze.json"}},
        "quality_build": {"path": quality_path, "sha256": "different"},
    }
    actual.evidence = cast(
        UnityForwardSystemEvidence,
        SimpleNamespace(
            bound=lambda item: {"identity": {"files_sha256": {quality_path: "frozen"}}}
        ),
    )
    with pytest.raises(ValueError, match="Quality build differs"):
        actual.quality()


def test_audit_failure_preserves_both_completed_arms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(UnityDeploymentTrial, "run", fixed_trial)

    def fail_audit(*args: object, **kwargs: object) -> JsonDict:
        raise RuntimeError("quality audit failure")

    monkeypatch.setattr(Audit, "run", fail_audit)
    actual = runner(tmp_path)
    state: JsonDict = {}
    with pytest.raises(RuntimeError, match="quality audit failure"):
        actual.evaluate(
            [capture(tmp_path / "input")],
            [0],
            cast(UnityQualityInference, CohortPredictor()),
            [DecodingBackend()],
            FakeQuality({8: metrics(passed=True)}),
            state,
        )
    assert state["active_stage"] == "post_trial_audit"
    for arm in ["prediction", "fixed8"]:
        assert (actual.output / f"partial-0-{arm}/00000.astc").exists()
        assert (actual.output / f"partial-0-{arm}/choices.json").exists()
    assert (actual.output / "partial-0-prediction/predictions.npz").exists()
