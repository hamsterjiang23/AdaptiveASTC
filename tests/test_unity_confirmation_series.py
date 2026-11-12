"""CPU contracts for full confirmation capture; fixtures never open Unity or a model."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from test_unity_confirmation_capture import fixture_config

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.unity_reference import UnityReferenceCapture
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture as C
from reproductions.unity_search_baseline.confirmation_series import UnityConfirmationSeries as S
from reproductions.unity_search_baseline.metadata import UnityOptionCapture
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


def make_series(root: Path, monkeypatch: pytest.MonkeyPatch) -> S:
    smoke_path = fixture_config(root, monkeypatch)
    job = root / "job.json"
    A.write_json(
        job,
        {
            "command": [
                sys.executable,
                "-u",
                "script/capture_unity_confirmation.py",
                "--config",
                str(smoke_path),
            ]
        },
    )
    sources = C.execution_sources(root)
    monkeypatch.setattr(S, "execution_sources", staticmethod(lambda _: sources))
    path = root / "series.json"
    A.write_json(
        path,
        {
            "smoke_config": {"path": str(smoke_path), "sha256": A.sha256_file(smoke_path)},
            "smoke_job": {"job_config": str(job), "sha256": A.sha256_file(job)},
            "sources_sha256": sources,
            "expected_images": 3,
            "batch_size": 256,
            "run_id": "confirmation-series",
            "report": str(root / "experiment report/series.json"),
        },
    )
    return S(root, path)


def test_full2000_ranges_reuse_two_and_partition_remaining_without_gaps() -> None:
    series = S.__new__(S)
    series.config = {"expected_images": 2000, "batch_size": 256}
    ranges = series.ranges()
    assert len(ranges) == 8 and ranges[-1] == (1794, 206)
    assert [i for start, count in ranges for i in range(start, start + count)] == list(
        range(2, 2000)
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("expected_images", 2),
        ("expected_images", 4),
        ("expected_images", True),
        ("batch_size", 0),
        ("batch_size", 257),
        ("batch_size", True),
        ("run_id", "../escape"),
    ],
)
def test_invalid_plan_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: object,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    config = copy.deepcopy(series.config)
    config[key] = value
    A.write_json(series.path, config)
    with pytest.raises(ValueError):
        S(tmp_path, series.path)


@pytest.mark.parametrize("kind", ["config", "smoke", "job", "source"])
def test_changed_execution_binding_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    path = {
        "config": series.path,
        "smoke": series.smoke.config_path,
        "job": Path(series.config["smoke_job"]["job_config"]),
        "source": tmp_path / "fixture.py",
    }[kind]
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        series.validate()


def test_smoke_command_binding_and_start_must_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    path = Path(series.config["smoke_job"]["job_config"])
    job = A.read_json(path)
    job["command"][-1] = "different-capture-config.json"
    A.write_json(path, job)
    series.config["smoke_job"]["sha256"] = A.sha256_file(path)
    A.write_json(series.path, series.config)
    with pytest.raises(ValueError, match="bound capture"):
        S(tmp_path, series.path)


def test_validate_only_does_not_create_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    result = series.validate()
    assert result["status"] == "validated" and result["images"] == 3
    assert not series.report.exists() and not series.output.exists()
    assert not series.smoke.baseline.run_dir.exists()


@pytest.mark.parametrize("which", ["output", "reports", "report"])
def test_existing_outputs_are_never_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    which: str,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    path: Path = getattr(series, which)
    if which == "report":
        path.parent.mkdir(parents=True)
        path.write_text("old report", encoding="utf-8")
    else:
        path.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        series.run()
    if which == "report":
        assert path.read_text(encoding="utf-8") == "old report"


def test_failed_smoke_never_starts_batch_or_publishes_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    monkeypatch.setattr(P, "dependency_status", staticmethod(lambda _: {"status": "failed"}))
    with pytest.raises(RuntimeError, match="dependency failed"):
        series.run()
    state = A.read_json(series.report)
    assert state["status"] == "failed" and state["captured_images"] == 0
    assert state["test_opened"] is False and state["native_labels_collected"] is False
    assert not list(series.reports.iterdir())


def fake_batch_rows(capture: C) -> tuple[list[JsonDict], JsonDict]:
    rows = [
        {
            "path": row["path"],
            "source_md4": row["fileHash"],
            "source_split": "confirmation",
        }
        for row in capture.rows
    ]
    return rows, {
        "images": len(rows),
        "start": capture.config["start"],
        "report_sha256": A.sha256_file(capture.report),
        "editor_process_seconds": 1.0,
    }


@pytest.mark.parametrize("fail_last", [False, True])
def test_series_orders_batches_and_retains_partial_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_last: bool,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    A.write_json(series.smoke.report, {"synthetic": True})
    observed: list[tuple[int, int]] = []

    def run(capture: C) -> JsonDict:
        observed.append((capture.config["start"], capture.config["images"]))
        assert capture.config["sources_sha256"] == series.smoke.config["sources_sha256"]
        assert capture.config["reservation_report"] == series.smoke.config["reservation_report"]
        assert capture.config["smoke_report"]["sha256"] == A.sha256_file(series.smoke.report)
        if fail_last:
            raise RuntimeError("synthetic final batch failure")
        A.write_json(capture.report, {"synthetic": True})
        return {"status": "passed"}

    monkeypatch.setattr(P, "dependency_status", staticmethod(lambda _: {"status": "passed"}))
    monkeypatch.setattr(S, "audit_batch", staticmethod(fake_batch_rows))
    monkeypatch.setattr(C, "run", run)
    if fail_last:
        with pytest.raises(RuntimeError, match="final batch"):
            series.run()
    else:
        series.run()
    state = A.read_json(series.report)
    manifest = A.read_json(Path(state["manifest"]))
    count = 2 if fail_last else 3
    assert observed == [(2, 1)]
    assert state["captured_images"] == count
    assert [row["path"] for row in manifest["splits"]["confirmation"]] == [
        row["path"] for row in series.rows[:count]
    ]
    assert state["status"] == ("failed" if fail_last else "passed")
    assert manifest["status"] == ("partial" if fail_last else "passed")
    assert state["test_opened"] is False and state["model_sealed"] is False
    assert state["training_updates"] == 0


def completed_fixture(capture: C, monkeypatch: pytest.MonkeyPatch) -> None:
    capture.baseline.prepare()
    baseline = capture.baseline
    native = [{"asset": row["path"], "block_size": "12x12"} for row in capture.rows]
    references = [
        {
            "path": row["path"],
            "source_split": "confirmation",
            "source_md4": row["fileHash"],
            "selection": native[i],
            "width": 1,
            "height": 1,
            "artifacts_sha256": {"original.png": "fixture-png-sha"},
        }
        for i, row in enumerate(capture.rows)
    ]
    options = {"rows": [{"path": row["path"]} for row in capture.rows], "candidate_callbacks": 2}
    restored = {"status": "restored", "original_sha256": "original", "restored_sha256": "original"}
    A.write_json(
        baseline.run_dir / "batch-receipt.json",
        {
            "status": "passed",
            "process_exit_code": 0,
            "metadata_restore_conflicts": [],
            "process_wall_seconds": 1.0,
        },
    )
    A.write_json(baseline.run_dir / "managed-hook/receipt.json", restored)
    A.write_json(
        baseline.run_dir / "references/normalized-batch/receipt.json", {"rows": references}
    )
    A.write_json(
        capture.report,
        {
            "status": "passed",
            "config_sha256": capture.config_sha,
            "configuration_path": str(capture.config_path),
            "source_split": "confirmation",
            "source_files_sha256": capture.config["sources_sha256"],
            "reservation_manifest_sha256": capture.reservation["manifest_sha256"],
            "images": len(capture.rows),
            "run_directory": str(baseline.run_dir),
            "test_opened": False,
            "training_updates": 0,
            "native_labels_collected": True,
            "managed_source_restoration": restored,
            "options_audit": options,
            "wall_seconds": 2.0,
        },
    )
    monkeypatch.setattr(
        UnityReferenceCapture, "collect", lambda _self, _phase: {"rows": references}
    )
    monkeypatch.setattr(UnityOptionCapture, "audit", staticmethod(lambda *_: options))
    monkeypatch.setattr(
        baseline,
        "_read_lines",
        lambda path: (
            native
            if path.name.endswith("native.jsonl")
            else [{"asset": r["path"]} for r in capture.rows]
        ),
    )


def test_complete_native_audit_retains_confirmation_reference_and_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    completed_fixture(series.smoke, monkeypatch)
    rows, binding = S.audit_batch(series.smoke)
    assert len(rows) == 2 and binding["images"] == 2
    assert rows[0]["path"] == series.rows[0]["path"]
    assert rows[0]["source_split"] == "confirmation"
    assert rows[0]["reference_png"].endswith("00000\\original.png")
    assert rows[0]["selection"]["block_size"] == "12x12"


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "running"),
        ("images", 1),
        ("source_split", "train"),
        ("config_sha256", "wrong"),
        ("native_labels_collected", False),
        ("test_opened", True),
        ("training_updates", 1),
        ("source_files_sha256", {}),
    ],
)
def test_native_audit_rejects_incomplete_or_relabelled_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    completed_fixture(series.smoke, monkeypatch)
    report = A.read_json(series.smoke.report)
    report[field] = value
    A.write_json(series.smoke.report, report)
    with pytest.raises(ValueError, match="complete bound native evidence"):
        S.audit_batch(series.smoke)


def test_native_restoration_failure_is_not_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    completed_fixture(series.smoke, monkeypatch)
    path = series.smoke.baseline.run_dir / "managed-hook/receipt.json"
    restoration = A.read_json(path)
    restoration["restored_sha256"] = "different"
    A.write_json(path, restoration)
    with pytest.raises(ValueError, match="restoration failed"):
        S.audit_batch(series.smoke)


def test_assembly_does_not_accept_changed_order_or_split(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series(tmp_path, monkeypatch)
    A.write_json(series.smoke.report, {"synthetic": True})
    rows, binding = fake_batch_rows(series.smoke)
    with pytest.raises(ValueError, match="primary order"):
        series.publish({"batches": [binding]}, list(reversed(rows)))
    rows[0]["source_split"] = "train"
    with pytest.raises(ValueError, match="primary order"):
        series.publish({"batches": [binding]}, rows)
