"""Resume admits verified complete samples and preserves failed attempts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.gdc2023.costs import EvaluationProcessCost
from reproductions.gdc2023.recovery import EvaluationRecovery


def recovery_fixture(output: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    folder = output / "00000"
    folder.mkdir(parents=True)
    image = Image.new("RGB", (1, 1), (8, 16, 32))
    for name in ["input.png", "selected.png", "fixed8.png"]:
        image.save(folder / name)
    for name, footprint in [("selected", 12), ("fixed8", 8)]:
        header = bytes.fromhex("13aba15c") + bytes([footprint, footprint, 1])
        (folder / f"{name}.astc").write_bytes(header + bytes([1, 0, 0]) * 3 + bytes(16))
        (folder / f"{name}.txt").write_text("native log", encoding="utf-8")
    artifacts = {path.name: ArtifactStore.sha256_file(path) for path in folder.iterdir()}
    row = {"path": "Assets/A.png", "fileHash": "source", "class_id": 3}
    label = {
        "selected": {"name": "12x12", "payload_bytes": 16},
        "target_met": True,
        "artifacts_sha256": {
            "input.png": artifacts["input.png"],
            "12x12.astc": artifacts["selected.astc"],
            "12x12.png": artifacts["selected.png"],
            "8x8.astc": artifacts["fixed8.astc"],
            "8x8.png": artifacts["fixed8.png"],
        },
    }
    receipt = {
        "status": "passed",
        "index": 0,
        "path": row["path"],
        "fileHash": "source",
        "predicted_class": 3,
        "predicted_footprint": "12x12",
        "confidence": 0.8,
        "label_class": 3,
        "label_target_met": True,
        "label_payload_bytes": 16,
        "rgb_psnr": None,
        "lossless": True,
        "target_met": True,
        "fixed8_rgb_psnr": None,
        "fixed8_lossless": True,
        "fixed8_target_met": True,
        "payload_bytes": 16,
        "fixed8_payload_bytes": 16,
        "timings": {
            "source_rgb_seconds": 1,
            "classifier_preprocessing_seconds": 1,
            "inference_seconds": 1,
            "final_encode_seconds": 1,
            "model_pipeline_seconds": 4,
            "fixed8_encode_seconds": 1,
            "fixed8_pipeline_seconds": 2,
            "verification_seconds": 1,
        },
        "artifacts_sha256": artifacts,
    }
    ArtifactStore.write_json(folder / "receipt.json", receipt)
    return row, label


def test_reuse_does_not_depend_on_progress_file(tmp_path: Path) -> None:
    row, label = recovery_fixture(tmp_path)
    (tmp_path / "progress.json").write_text("incomplete", encoding="utf-8")
    original = (tmp_path / "00000/receipt.json").read_bytes()
    assert EvaluationRecovery.reuse(tmp_path, 0, row, label, 35)
    assert (tmp_path / "00000/receipt.json").read_bytes() == original


@pytest.mark.parametrize(
    "damage", ["identity", "payload", "quality", "timing", "artifact", "missing"]
)
def test_invalid_samples_are_preserved_for_reencoding(tmp_path: Path, damage: str) -> None:
    row, label = recovery_fixture(tmp_path)
    path = tmp_path / "00000/receipt.json"
    receipt = ArtifactStore.read_json(path)
    if damage == "identity":
        receipt["index"] = 1
    elif damage == "payload":
        receipt["payload_bytes"] = 32
    elif damage == "quality":
        receipt["target_met"] = False
    elif damage == "timing":
        receipt["timings"]["model_pipeline_seconds"] = 5
    elif damage == "artifact":
        (tmp_path / "00000/selected.txt").write_text("changed", encoding="utf-8")
    else:
        (tmp_path / "00000/selected.astc").unlink()
    ArtifactStore.write_json(path, receipt)
    assert not EvaluationRecovery.reuse(tmp_path, 0, row, label, 35)
    assert not (tmp_path / "00000").exists()
    archive = list((tmp_path / "attempts").iterdir())
    assert len(archive) == 1 and (archive[0] / "recovery-error.json").exists()


def test_resume_requires_identical_binding_and_incomplete_output(tmp_path: Path) -> None:
    output = tmp_path / "evaluation"
    binding = {"checkpoint_sha256": "frozen", "split": "test"}
    EvaluationRecovery.prepare(output, binding, False)
    EvaluationRecovery.prepare(output, binding, True)
    with pytest.raises(ValueError, match="binding changed"):
        EvaluationRecovery.prepare(output, {**binding, "checkpoint_sha256": "other"}, True)
    ArtifactStore.write_json(output / "receipt.json", {"status": "passed"})
    with pytest.raises(FileExistsError):
        EvaluationRecovery.prepare(output, binding, True)


def test_prior_progress_hash_detects_consistent_timing_rewrite(tmp_path: Path) -> None:
    row, label = recovery_fixture(tmp_path)
    receipt = tmp_path / "00000/receipt.json"
    original = ArtifactStore.sha256_file(receipt)
    ArtifactStore.write_json(
        tmp_path / "progress.json", {"results": [{"index": 0, "receipt_sha256": original}]}
    )
    anchors = EvaluationRecovery.anchors(tmp_path)
    value = ArtifactStore.read_json(receipt)
    value["timings"]["inference_seconds"] = 2
    value["timings"]["model_pipeline_seconds"] = 5
    ArtifactStore.write_json(receipt, value)
    assert not EvaluationRecovery.reuse(tmp_path, 0, row, label, 35, anchors[0])


def test_process_cost_keeps_failed_attempt_and_filters_other_outputs(tmp_path: Path) -> None:
    run = tmp_path / "formal"
    for identity, code, duration, output in [
        ("initial", 1, 600, "test2000"),
        ("resume", 0, 1000, "test2000"),
        ("other", 0, 40, "shared64"),
    ]:
        folder = run / "jobs" / identity
        command = [
            "python",
            "-u",
            "reproduce.py",
            "evaluate",
            "--method",
            "gdc2023",
            "--run-id",
            "formal",
            "--evaluation-id",
            output,
        ]
        ArtifactStore.write_json(folder / "config.json", {"command": command})
        ArtifactStore.write_json(
            folder / "receipt.json",
            {
                "command": command,
                "config_sha256": ArtifactStore.sha256_file(folder / "config.json"),
                "status": "passed" if code == 0 else "failed",
                "process_exit_code": code,
                "wall_seconds": duration,
            },
        )
        for name in ["stdout.log", "stderr.log"]:
            (folder / name).write_text("process log", encoding="utf-8")
    costs = EvaluationProcessCost.load(run, run / "evaluations/test2000/pretrained")
    assert len(costs["attempts"]) == 2 and costs["all_attempts_wall_seconds"] == 1600
    path = run / "jobs/initial/receipt.json"
    interrupted = ArtifactStore.read_json(path)
    interrupted.update(status="running", wall_seconds=None)
    ArtifactStore.write_json(path, interrupted)
    costs = EvaluationProcessCost.load(run, run / "evaluations/test2000/pretrained")
    assert costs["all_attempts_wall_seconds"] is None
    assert costs["known_attempts_wall_seconds"] == 1000
    assert costs["unknown_duration_attempts"] == 1
