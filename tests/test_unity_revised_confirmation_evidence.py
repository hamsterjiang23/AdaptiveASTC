"""Reject altered revised-cohort native sources and data-only execution receipts."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.revised_confirmation_evidence import (
    UnityRevisedConfirmationEvidence as E,
)
from reproductions.unity_search_baseline.revised_forward_confirmation import (
    UnityRevisedForwardConfirmationEvaluation as V,
)


def test_revised_json_binding_uses_current_bytes_and_rejects_changes(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    A.write_json(path, {"value": 1})
    evidence = E(tmp_path, {})
    assert evidence.read(path, A.sha256_file(path)) == {"value": 1}
    A.write_json(path, {"value": 2})
    with pytest.raises(ValueError, match="evidence changed"):
        evidence.read(path)


def native_fixture() -> tuple[JsonDict, JsonDict, JsonDict, JsonDict, JsonDict]:
    source = {
        "path": "Assets/image.png",
        "fileHash": "source",
        "source_sha256": "source-sha",
        "meta_sha256": "meta-sha",
    }
    reference = {
        "path": source["path"],
        "source_split": "confirmation",
        "width": 4,
        "height": 3,
        "artifacts_sha256": {"original.png": "png-sha"},
        "selection": {"block_size": "8x8", "preset": "fast"},
    }
    actual = {"path": source["path"], "rgba_sha256": "callback"}
    imported = {"asset": source["path"], "srgb": True}
    row = {
        "path": source["path"],
        "source_md4": source["fileHash"],
        "source_sha256": source["source_sha256"],
        "meta_sha256": source["meta_sha256"],
        "source_split": "confirmation",
        "reference_sha256": "png-sha",
        "width": 4,
        "height": 3,
        "selection": dict(reference["selection"]),
        "actual_options": dict(actual),
        "import_metadata": dict(imported),
    }
    return row, source, reference, actual, imported


def test_native_origin_matches_original_source_receipts() -> None:
    E.validate_native_row(*native_fixture())


@pytest.mark.parametrize(
    "damage",
    [
        "source_md4",
        "source_sha256",
        "meta_sha256",
        "reference_sha256",
        "selection",
        "actual_options",
        "import_metadata",
        "source_split",
    ],
)
def test_native_origin_changes_are_rejected(damage: str) -> None:
    row, source, reference, actual, imported = native_fixture()
    row[damage] = "changed"
    with pytest.raises(ValueError, match="original source receipts"):
        E.validate_native_row(row, source, reference, actual, imported)


@pytest.mark.parametrize("exact", [True, False])
@pytest.mark.parametrize("damage", ["none", "command", "counter", "config_sha"])
def test_data_job_requires_actual_bound_command_and_zero_model_scope(
    tmp_path: Path, exact: bool, damage: str
) -> None:
    evidence = E(tmp_path, {})
    local = tmp_path / "experiment report/.local/unity-v2-20261112"
    local.mkdir(parents=True)
    name = (
        "run_confirmation_pixel_guarded_v3.py" if exact else "run_confirmation_data_guarded_v3.py"
    )
    runner = local / name
    runner.write_text("# Synthetic unit-test source identity\n", encoding="utf-8")
    archive = {
        "files": {
            str(runner.relative_to(tmp_path)).replace("\\", "/"): {"sha256": A.sha256_file(runner)}
        }
    }

    def bound(name: str, value: JsonDict) -> JsonDict:
        path = tmp_path / name
        A.write_json(path, value)
        return {"path": str(path), "sha256": A.sha256_file(path)}

    config = bound("config.json", {"scope": "synthetic data-only audit"})
    guard_path = tmp_path / "guard.json"
    script = (
        "script/audit_unity_confirmation_revision_pixels.py"
        if exact
        else ("script/audit_unity_near_duplicates.py")
    )
    target = tmp_path / script
    target.parent.mkdir(exist_ok=True)
    target.write_text("# Synthetic target entry point\n", encoding="utf-8")
    command = [sys.executable, "-X", "utf8", "-u", str(runner)]
    if not exact:
        command.extend(["--script", str(target)])
    command.extend(["--config", config["path"], "--guard-report", str(guard_path)])
    job_command = copy.deepcopy(command)
    if damage == "command":
        job_command[-1] = "different-guard.json"
    job = bound("job.json", {"command": job_command})
    receipt = bound(
        "receipt.json",
        {
            "command": job_command,
            "status": "passed",
            "process_exit_code": 0,
            "config_sha256": job["sha256"],
        },
    )
    guard = {
        "status": "passed",
        "test_opened": False,
        "config_sha256": config["sha256"],
        "guard_sha256": A.sha256_file(runner),
        "model_forward_calls": 0,
        "training_updates": 0,
        "blocked_model_file_access_attempts": 0,
        "model_initializations": 0,
        "optimizer_initializations": 0,
        "cuda_initializations": 0,
        "blocked_model_import_attempts": 0,
        "script_sha256": A.sha256_file(target),
    }
    if damage == "counter":
        guard["model_forward_calls"] = 1
    if damage == "config_sha":
        guard["config_sha256"] = "changed"
    stage = {"job": job, "receipt": receipt, "config": config, "guard": bound("guard.json", guard)}
    if damage == "none":
        evidence.data_stage(stage, script, archive)
        evidence.verify()
    else:
        with pytest.raises(ValueError, match="zero-model execution"):
            evidence.data_stage(stage, script, archive)


def test_revised_entry_keeps_explicit_execution_gate() -> None:
    evaluation = object.__new__(V)
    evaluation.config = {"confirmation_execution_authorized": False}
    with pytest.raises(PermissionError):
        evaluation.run()


@pytest.mark.parametrize("damage", ["none", "report_config", "guard_source"])
def test_capture_execution_cross_binds_report_config_and_guard_source(damage: str) -> None:
    data = {"capture_config": {"sha256": "config-sha"}}
    sources = {"reproductions/unity_search_baseline/policy.py": "policy-sha"}
    config = {"sources_sha256": sources}
    capture = {
        "status": "passed",
        "captured_images": 2000,
        "model_forward_calls": 0,
        "training_updates": 0,
        "test_opened": False,
        "config_sha256": "config-sha",
        "sources_sha256": sources,
    }
    guard = {
        "status": "passed",
        "test_opened": False,
        "config_sha256": "config-sha",
        "guard_sha256": "guard-sha",
        "model_forward_calls": 0,
        "training_updates": 0,
        "blocked_model_import_attempts": 0,
        "blocked_model_file_access_attempts": 0,
    }
    if damage == "report_config":
        capture["config_sha256"] = "0" * 64
    if damage == "guard_source":
        guard["guard_sha256"] = "0" * 64
    if damage == "none":
        E.validate_capture_execution(data, config, capture, guard, "guard-sha")
    else:
        with pytest.raises(ValueError, match="execution chain changed"):
            E.validate_capture_execution(data, config, capture, guard, "guard-sha")
