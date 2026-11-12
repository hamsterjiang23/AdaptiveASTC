"""Confirmation capture cannot be relabeled as development or start before its gates."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from Crypto.Hash import MD4

from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.collection import UnityReferenceSeries
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture
from reproductions.unity_search_baseline.metadata import ManagedCaptureHook
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


def fixture_config(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sources = {}
    for name in ["fixture.py", "fixture_dependency.py"]:
        path = root / name
        path.write_text("# source identity fixture", encoding="utf-8")
        sources[name] = A.sha256_file(path)
    monkeypatch.setattr(
        UnityConfirmationCapture, "execution_sources", staticmethod(lambda _: sources)
    )
    project = root / "project"
    rows = []
    for i in range(3):
        asset = f"Assets/Group{i}/test.png"
        path = project / asset
        path.parent.mkdir(parents=True)
        data = f"unseen-{i}".encode()
        path.write_bytes(data)
        meta = Path(str(path) + ".meta")
        meta.write_bytes(b"frozen import options")
        rows.append(
            {
                "path": asset,
                "fileHash": MD4.new(data).hexdigest(),
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "meta_sha256": A.sha256_file(meta),
            }
        )
    manifest_path = root / "reservation-manifest.json"
    manifest = {"status": "reserved", "primary": rows, "reserves": [], "test_opened": False}
    manifest["fingerprint"] = A.fingerprint(manifest)
    A.write_json(manifest_path, manifest)
    reserved_config = root / "reserved-config.json"
    A.write_json(reserved_config, {"image_root": str(project)})
    reserved_report = root / "reserved-report.json"
    A.write_json(
        reserved_report,
        {
            "status": "reserved",
            "manifest": str(manifest_path),
            "manifest_sha256": A.sha256_file(manifest_path),
            "config_sha256": A.sha256_file(reserved_config),
        },
    )
    editor = root / "editor.exe"
    editor.write_bytes(b"synthetic editor identity")
    plugins = project / "Assets/Editor/Astc/Plugins"
    plugins.mkdir(parents=True)
    encoders = {}
    for name in ["astcenc-avx2-shared.dll", "astcenc-avx2-static.dll"]:
        path = plugins / name
        path.write_bytes(b"synthetic encoder identity")
        encoders[name] = A.sha256_file(path)
    series_path = root / "development-series.json"
    A.write_json(
        series_path,
        {
            "project": str(project),
            "editor": str(editor),
            "editor_sha256": A.sha256_file(editor),
            "encoder_dlls": encoders,
            "output": str(root / "experiment report/.local/development"),
            "report": str(root / "development-report.json"),
        },
    )
    config = root / "confirmation-config.json"
    A.write_json(
        config,
        {
            "reservation_report": {
                "path": str(reserved_report),
                "sha256": A.sha256_file(reserved_report),
            },
            "reservation_config": {
                "path": str(reserved_config),
                "sha256": A.sha256_file(reserved_config),
            },
            "development_series": {"path": str(series_path), "sha256": A.sha256_file(series_path)},
            "sources_sha256": sources,
            "dependencies": [{"job_config": "synthetic-not-launched", "sha256": "fixture"}],
            "start": 0,
            "images": 2,
            "run_id": "confirmation-smoke",
            "report": str(root / "experiment report/confirmation-smoke.json"),
            "minimum_free_ram_gib": 20,
            "minimum_free_disk_gib": 40,
        },
    )
    return config


def test_prepare_has_explicit_confirmation_identity_and_no_quality_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = UnityConfirmationCapture(tmp_path, fixture_config(tmp_path, monkeypatch))
    assert capture.validate()["status"] == "validated"
    baseline = capture.baseline
    baseline.prepare()
    baseline.verify_protocol()
    identity = A.read_json(baseline.run_dir / "identity.json")
    manifest = A.read_json(baseline.manifest)
    config = A.read_json(baseline.run_dir / "batch-config.json")
    assert identity["source_split"] == "confirmation" and "train_count" not in identity
    assert set(manifest["splits"]) == {"confirmation"}
    assert [row["path"] for row in config["assets"]] == baseline.capture_paths
    assert config["warmup"] == config["assets"] and config["captureReferences"] is True
    assert all("blockSize" not in row and "psnr" not in row for row in capture.rows)
    with pytest.raises(FileExistsError):
        baseline.prepare()


@pytest.mark.parametrize("field", ["source_sha256", "meta_sha256"])
def test_source_or_import_setting_changes_stop_before_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    capture = UnityConfirmationCapture(tmp_path, fixture_config(tmp_path, monkeypatch))
    path = Path(capture.environment["project"]) / capture.rows[0]["path"]
    if field == "meta_sha256":
        path = Path(str(path) + ".meta")
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        capture.validate()
    assert not capture.baseline.run_dir.exists()


def test_reservation_mutation_after_construction_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = UnityConfirmationCapture(tmp_path, fixture_config(tmp_path, monkeypatch))
    Path(capture.reservation["manifest"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest changed"):
        capture.baseline.prepare()


@pytest.mark.parametrize(
    "key,value",
    [
        ("start", -1),
        ("start", 3),
        ("images", 0),
        ("images", 257),
        ("images", True),
        ("run_id", "../escape"),
        ("minimum_free_ram_gib", 0),
        ("dependencies", []),
    ],
)
def test_invalid_batch_and_runtime_limits_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str, value: object
) -> None:
    path = fixture_config(tmp_path, monkeypatch)
    config = A.read_json(path)
    config[key] = value
    A.write_json(path, config)
    with pytest.raises(ValueError):
        UnityConfirmationCapture(tmp_path, path)


def test_larger_batch_requires_matching_successful_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fixture_config(tmp_path, monkeypatch)
    config = A.read_json(path)
    config["images"] = 3
    A.write_json(path, config)
    with pytest.raises(ValueError, match="completed two-image smoke"):
        UnityConfirmationCapture(tmp_path, path)
    smoke = tmp_path / "smoke.json"
    A.write_json(smoke, {"status": "passed", "images": 2, "reservation_manifest_sha256": "wrong"})
    config["smoke_report"] = {"path": str(smoke), "sha256": A.sha256_file(smoke)}
    A.write_json(path, config)
    with pytest.raises(ValueError, match="reserved cohort"):
        UnityConfirmationCapture(tmp_path, path).validate()
    reserved = A.read_json(Path(config["reservation_report"]["path"]))
    A.write_json(
        smoke,
        {
            "status": "passed",
            "images": 2,
            "reservation_manifest_sha256": reserved["manifest_sha256"],
        },
    )
    config["smoke_report"]["sha256"] = A.sha256_file(smoke)
    A.write_json(path, config)
    with pytest.raises(ValueError, match="complete native evidence"):
        UnityConfirmationCapture(tmp_path, path).validate()


def test_incomplete_execution_source_binding_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fixture_config(tmp_path, monkeypatch)
    config = A.read_json(path)
    config["sources_sha256"].pop("fixture_dependency.py")
    A.write_json(path, config)
    with pytest.raises(ValueError, match="incomplete"):
        UnityConfirmationCapture(tmp_path, path)


def test_failed_dependency_never_prepares_or_opens_editor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = UnityConfirmationCapture(tmp_path, fixture_config(tmp_path, monkeypatch))
    monkeypatch.setattr(P, "dependency_status", staticmethod(lambda _: {"status": "failed"}))
    with pytest.raises(RuntimeError, match="dependency failed"):
        capture.run()
    assert not capture.baseline.run_dir.exists()
    report = A.read_json(capture.report)
    assert report["status"] == "failed" and report["native_labels_collected"] is False
    assert report["test_opened"] is False
    with pytest.raises(FileExistsError):
        capture.run()


def test_confirmation_does_not_weaken_development_constructor(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="excludes calibration and test"):
        UnitySearchBaseline(
            tmp_path,
            tmp_path,
            tmp_path,
            tmp_path,
            source_split="confirmation",
            capture_references=True,
            capture_paths=["Assets/a.png"],
        )


def test_failed_editor_restores_hook_and_environment_before_unlock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fixture_config(tmp_path, monkeypatch)
    config = A.read_json(path)
    config.update(minimum_free_ram_gib=0.001, minimum_free_disk_gib=0.001)
    A.write_json(path, config)
    capture = UnityConfirmationCapture(tmp_path, path)
    monkeypatch.setattr(P, "dependency_status", staticmethod(lambda _: {"status": "passed"}))
    monkeypatch.setenv("ASTC_TRAINING_CAPTURE_OPTIONS", "original-value")
    restored: list[bool] = []

    def install(hook: ManagedCaptureHook, source: Path) -> None:
        A.write_json(hook.folder / "receipt.json", {"synthetic": True})

    def restore(hook: ManagedCaptureHook) -> dict[str, str]:
        restored.append(True)
        return {"status": "restored"}

    def fail(phase: str, no_upm: bool = False) -> dict[str, object]:
        assert os.environ["ASTC_TRAINING_CAPTURE_OPTIONS"].endswith("batch-options.jsonl")
        raise RuntimeError("synthetic Editor failure")

    monkeypatch.setattr(ManagedCaptureHook, "install", install)
    monkeypatch.setattr(ManagedCaptureHook, "restore", restore)
    monkeypatch.setattr(capture.baseline, "run", fail)
    with pytest.raises(RuntimeError, match="synthetic Editor failure"):
        capture.run()
    assert restored == [True]
    assert os.environ["ASTC_TRAINING_CAPTURE_OPTIONS"] == "original-value"
    report = A.read_json(capture.report)
    assert report["status"] == "failed"
    assert report["managed_source_restoration"]["status"] == "restored"
    assert report["native_labels_collected"] is False and report["test_opened"] is False
    series = UnityReferenceSeries(tmp_path, Path(config["development_series"]["path"]))
    with series.project_lock():
        assert True


def test_active_project_lock_stops_capture_before_prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fixture_config(tmp_path, monkeypatch)
    capture = UnityConfirmationCapture(tmp_path, path)
    monkeypatch.setattr(P, "dependency_status", staticmethod(lambda _: {"status": "passed"}))
    series = UnityReferenceSeries(tmp_path, Path(capture.config["development_series"]["path"]))
    with series.project_lock():
        with pytest.raises(RuntimeError, match="owns this Unity project"):
            capture.run()
    assert not capture.baseline.run_dir.exists()


def test_explicit_confirmation_batch_cannot_start_full_training_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = UnityConfirmationCapture(tmp_path, fixture_config(tmp_path, monkeypatch))
    with pytest.raises(ValueError, match="explicit batches"):
        capture.baseline.run("full")
