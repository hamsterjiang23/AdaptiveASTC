from __future__ import annotations

import copy
from pathlib import Path

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_evidence import UnityConfirmationEvidence
from reproductions.unity_search_baseline.forward_system_evidence import (
    UnityForwardSystemEvidence as E,
)
from tests.test_unity_confirmation_evaluation import model_evidence, training


def qualified_system() -> tuple[JsonDict, JsonDict, JsonDict]:
    model = training()
    model["config"].update(
        backbone_name="resnet34",
        image_pooling="mean",
        head_patch_views=4,
        validation_batch_size=16,
        zero_probability_threshold=0.5,
    )
    model["checkpoint_audit"]["metrics"]["accuracy"] = 0.869
    model["checkpoint_audit"]["epoch"] = 15
    metrics = {"accuracy": 0.936, "images": 1000, "candidates_measured": {"total": 1627}}
    audit = {
        "actual_queried_candidates_verified": 1627,
        "starting_choices_exact": True,
        "forward_choices_and_query_order_exact": True,
        "all_query_payloads_pixels_and_native_quality_match": True,
        "fresh_prediction_max_abs_difference": dict.fromkeys(
            ["channel_mse", "channel_zero", "zero_probability", "image_quality"], 0.0
        ),
    }
    arm = {
        "status": "passed",
        "validation_metrics": metrics,
        "timings": {
            "inference_images": 1000,
            "encoded_images": 1000,
            "prediction_passes": 1,
            "encoding_calls": 1627,
        },
        "query_audit": audit,
    }
    runtime = {
        "status": "passed",
        "test_opened": False,
        "training_updates": 0,
        "model_parameters_and_buffers_unchanged": True,
        "checkpoint_sha256": "a",
        "config": {"variant": "B1_candidate_idx", "prediction_mode": "raw", "smoke": False},
        "inference_images": 1000,
        "encoded_images": 1000,
        "input_parity_patches": 7173,
        "summary": {"forward": {"validation_metrics": metrics}},
        "measurements": [
            {
                "repetition": index,
                "warmup": index == 0,
                "arms": {"forward": copy.deepcopy(arm), "fixed8": {"status": "passed"}},
            }
            for index in range(4)
        ],
    }
    freeze = {
        "status": "passed_validation_only_freeze",
        "validation_images": 1000,
        "test_opened": False,
        "training_updates": 0,
        "validation_system_accuracy": 0.936,
        "validation_pure_model_accuracy": 0.869,
        "identity": {
            "split": "validation",
            "model": {
                "name": "imagenet-resnet34-head-sampled4",
                "checkpoint_sha256": "a",
                "config_fingerprint": A.fingerprint(model["config"]),
                "selected_epoch": 15,
            },
            "decision": {
                "variant": "B1_candidate_idx",
                "prediction_mode": "raw",
                "start": "predicted_candidate_index",
                "direction": "canonical20_forward",
                "encoding_budget": None,
                "normal_native_search": False,
                "reuse_selected_encoded_result": True,
                "quality_margin_psnr_db": 0.0,
                "quality_margin_ms_ssim_db": 0.0,
                "quality_margin_normal_degrees": 0.0,
                "zero_probability_threshold": 0.5,
            },
            "runtime": {
                "inference_images": 1000,
                "inference_patches": 7173,
                "validation_batch_size": 16,
            },
        },
    }
    return freeze, runtime, model


def test_system_admission_keeps_original_model_accuracy() -> None:
    freeze, runtime, model = qualified_system()
    assert E.validate_system(freeze, runtime, model)["accuracy"] == 0.936
    assert model["checkpoint_audit"]["metrics"]["accuracy"] == 0.869
    with pytest.raises(ValueError, match="reached90"):
        UnityConfirmationEvidence.validate_training(model)


@pytest.mark.parametrize(
    "mutation",
    [
        "below90",
        "nan",
        "checkpoint",
        "raw",
        "margin",
        "budget",
        "normal",
        "count",
        "repeat",
        "query_audit",
        "empty_arrays",
        "prediction_drift",
        "backbone",
        "patch_shape",
    ],
)
def test_system_admission_rejects_changed_frozen_contract(mutation: str) -> None:
    freeze, runtime, model = qualified_system()
    if mutation == "below90":
        runtime["summary"]["forward"]["validation_metrics"]["accuracy"] = 0.899
    if mutation == "nan":
        runtime["summary"]["forward"]["validation_metrics"]["accuracy"] = float("nan")
    if mutation == "checkpoint":
        model["checkpoint_sha256"] = "changed"
    if mutation == "raw":
        freeze["identity"]["decision"]["prediction_mode"] = "calibrated"
    if mutation == "margin":
        freeze["identity"]["decision"]["quality_margin_psnr_db"] = 0.1
    if mutation == "budget":
        freeze["identity"]["decision"]["encoding_budget"] = 3
    if mutation == "normal":
        freeze["identity"]["decision"]["normal_native_search"] = True
    if mutation == "count":
        runtime["encoded_images"] = 999
    if mutation == "repeat":
        runtime["measurements"][2]["warmup"] = True
    if mutation == "query_audit":
        runtime["measurements"][2]["arms"]["forward"]["query_audit"][
            "actual_queried_candidates_verified"
        ] = 1000
    if mutation == "empty_arrays":
        runtime["measurements"][1]["arms"]["forward"]["query_audit"][
            "fresh_prediction_max_abs_difference"
        ] = {}
    if mutation == "prediction_drift":
        runtime["measurements"][3]["arms"]["forward"]["query_audit"][
            "fresh_prediction_max_abs_difference"
        ]["channel_mse"] = 0.1
    if mutation == "backbone":
        model["config"]["backbone_name"] = "resnet18"
    if mutation == "patch_shape":
        freeze["identity"]["runtime"]["inference_patches"] = 1
    with pytest.raises(ValueError):
        E.validate_system(freeze, runtime, model)


def test_training_source_replay_preserves_recorded_none_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = model_evidence(tmp_path, "initial")
    head = model_evidence(tmp_path, "head", parent)
    path = Path(head["report"]["path"])
    report = A.read_json(path)
    report["checkpoint_audit"]["metrics"]["accuracy"] = 0.869
    A.write_json(path, report)
    A.write_json(tmp_path / "head/checkpoint-audit.json", report["checkpoint_audit"])
    head["report"]["sha256"] = A.sha256_file(path)
    archives: list[Path | None] = []

    def sources(training: JsonDict, root: Path, archive: Path | None = None) -> JsonDict:
        archives.append(archive)
        return {
            "sources": [
                {"verified_source": name, "training_sha256": digest}
                for name, digest in training["source_files_sha256"].items()
            ]
        }

    def job(self: E, item: JsonDict, script: str, config: Path) -> None:
        assert script == item["expected_script"] and config.is_file()

    monkeypatch.setattr(PatchNormalizationAudit, "bind_training_sources", staticmethod(sources))
    monkeypatch.setattr(E, "job", job)
    evidence = E(tmp_path, {})
    evidence.replay_archive = tmp_path / "posthoc-source-replay"
    actual = evidence.training_stage(head, set())
    assert actual["training_source_binding"]["archive"] is None
    assert archives == [evidence.replay_archive, evidence.replay_archive]
    evidence.verify()


def test_training_original_archive_identity_cannot_be_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = model_evidence(tmp_path, "initial")
    head = model_evidence(tmp_path, "head", parent)
    head["initial_training"]["training_source_archive"] = str(tmp_path / "rewritten")
    monkeypatch.setattr(E, "job", lambda self, item, script, config: None)
    with pytest.raises(ValueError, match="Original head-stage"):
        E(tmp_path, {}).training_stage(head, set())
