"""Reject stale upstream jobs and incomplete coverage before expensive native work."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


def setup_pipeline(root: Path) -> tuple[Path, JsonDict, Path]:
    public = root / "experiment report/unity-accuracy90-20261111"
    local = root / "experiment report/.local/pipeline"
    bindings = {}
    for file in P.SOURCE_FILES:
        path = root / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file, encoding="utf-8")
        bindings[file] = A.sha256_file(path)
    queue_path = public / "queue-config.json"
    snapshot_path = public / "queue.json"
    A.write_json(queue_path, {"report": str(snapshot_path)})
    process = psutil.Process()
    job_path = root / "experiment report/.local/jobs/upstream/job.json"
    A.write_json(job_path, {"command": process.cmdline()})
    A.write_json(
        job_path.parent / "receipt.json",
        {
            "config_sha256": A.sha256_file(job_path),
            "command": process.cmdline(),
            "status": "running",
            "child_pid": process.pid,
            "process_id": process.pid,
            "started_utc": datetime.fromtimestamp(process.create_time(), UTC).isoformat(),
        },
    )
    config: JsonDict = {
        "mode": "complete",
        "output": str(local),
        "reports": str(public / "stages"),
        "report": str(public / "pipeline.json"),
        "sources_sha256": bindings,
        "expected_counts": {"train": 10000, "validation": 1000},
        "candidate_queue_config": str(queue_path),
        "candidate_queue_config_sha256": A.sha256_file(queue_path),
        "dependencies": [{"job_config": str(job_path), "sha256": A.sha256_file(job_path)}],
        "shards": str(root / "experiment report/.local/shards"),
        "poll_seconds": 1,
        "minimum_free_ram_gib": 0.001,
        "minimum_free_disk_gib": 0.001,
    }
    A.write_json(
        snapshot_path,
        {
            "status": "passed",
            "coverage": "complete",
            "test_opened": False,
            "config_sha256": A.sha256_file(queue_path),
            "counts": config["expected_counts"],
            "expected_counts": config["expected_counts"],
            "batches": [
                {"run_id": "train", "source_split": "train", "images": 10000},
                {"run_id": "validation", "source_split": "validation", "images": 1000},
            ],
        },
    )
    path = public / "pipeline-config.json"
    A.write_json(path, config)
    return path, config, snapshot_path


def pass_dependency(config: JsonDict) -> None:
    path = Path(config["dependencies"][0]["job_config"]).parent / "receipt.json"
    receipt = A.read_json(path)
    receipt.update(status="passed", process_exit_code=0)
    A.write_json(path, receipt)


def test_live_upstream_never_enters_preparation(tmp_path: Path) -> None:
    path, config, _ = setup_pipeline(tmp_path)
    result = P(tmp_path, path).run(follow=False)
    assert result["status"] == "waiting_upstream" and result["stages"] == []
    assert result["dependencies"][0]["pid"] == psutil.Process().pid
    assert not Path(config["shards"]).exists()
    with pytest.raises(FileExistsError, match="fresh"):
        P(tmp_path, path).run(follow=False)


@pytest.mark.parametrize("damage", ["small", "subset", "snapshot", "dependencies"])
def test_complete_mode_cannot_be_narrowed(tmp_path: Path, damage: str) -> None:
    path, config, _ = setup_pipeline(tmp_path)
    if damage == "small":
        config["expected_counts"] = {"train": 64, "validation": 2}
    elif damage == "subset":
        config["run_ids"] = ["train"]
    elif damage == "snapshot":
        config["snapshot"] = "old.json"
    else:
        config["dependencies"] = []
    A.write_json(path, config)
    with pytest.raises(ValueError, match="full coverage"):
        P(tmp_path, path)


@pytest.mark.parametrize("damage", ["status", "coverage", "counts", "test", "config", "duplicate"])
def test_incomplete_publication_fails_before_stages(tmp_path: Path, damage: str) -> None:
    path, config, snapshot_path = setup_pipeline(tmp_path)
    pass_dependency(config)
    snapshot = A.read_json(snapshot_path)
    if damage == "status":
        snapshot["status"] = "waiting_references"
    elif damage == "coverage":
        snapshot["coverage"] = "partial"
    elif damage == "counts":
        snapshot["counts"] = {"train": 9999, "validation": 1000}
    elif damage == "test":
        snapshot["test_opened"] = True
    elif damage == "config":
        snapshot["config_sha256"] = "wrong"
    else:
        snapshot["batches"].append(dict(snapshot["batches"][0]))
    A.write_json(snapshot_path, snapshot)
    with pytest.raises(ValueError):
        P(tmp_path, path).run(follow=False)
    report = A.read_json(Path(config["report"]))
    assert report["status"] == "failed" and report["stages"] == []
    assert not Path(config["shards"]).exists()


@pytest.mark.parametrize("damage", ["exit_code", "command", "config", "pid_reuse"])
def test_upstream_identity_and_exit_status_checked(tmp_path: Path, damage: str) -> None:
    _, config, _ = setup_pipeline(tmp_path)
    item = config["dependencies"][0]
    path = Path(item["job_config"]).parent / "receipt.json"
    receipt = A.read_json(path)
    if damage == "exit_code":
        receipt.update(status="passed", process_exit_code=1)
    elif damage == "command":
        receipt["command"] = ["other", "job"]
    elif damage == "config":
        receipt["config_sha256"] = "wrong"
    else:
        receipt["started_utc"] = "2000-01-01T00:00:00+00:00"
    A.write_json(path, receipt)
    with pytest.raises((ValueError, RuntimeError)):
        P.dependency_status(item)


def test_changed_source_is_detected_on_next_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, config, _ = setup_pipeline(tmp_path)
    pipeline = P(tmp_path, path)

    def change_source(seconds: float) -> None:
        assert seconds == 1
        (tmp_path / P.SOURCE_FILES[0]).write_text("changed", encoding="utf-8")

    monkeypatch.setattr(
        "reproductions.unity_search_baseline.native_data_pipeline.time.sleep", change_source
    )
    with pytest.raises(ValueError, match="source changed"):
        pipeline.run()
    report = A.read_json(Path(config["report"]))
    assert report["status"] == "failed" and report["stages"] == []


def test_missing_child_is_not_mistaken_for_success(tmp_path: Path) -> None:
    _, config, _ = setup_pipeline(tmp_path)
    item = config["dependencies"][0]
    path = Path(item["job_config"]).parent / "receipt.json"
    receipt = A.read_json(path)
    assert not psutil.pid_exists(2147483647)
    receipt["child_pid"] = 2147483647
    receipt["last_observed_alive_utc"] = datetime.now(UTC).isoformat()
    A.write_json(path, receipt)
    assert P.dependency_status(item)["status"] == "awaiting_terminal_receipt"
    receipt["last_observed_alive_utc"] = "2000-01-01T00:00:00+00:00"
    A.write_json(path, receipt)
    with pytest.raises(RuntimeError, match="missing"):
        P.dependency_status(item)


def test_initial_running_receipt_waits_for_child_start(tmp_path: Path) -> None:
    _, config, _ = setup_pipeline(tmp_path)
    item = config["dependencies"][0]
    path = Path(item["job_config"]).parent / "receipt.json"
    receipt = A.read_json(path)
    del receipt["child_pid"]
    A.write_json(path, receipt)
    assert P.dependency_status(item)["status"] == "awaiting_child_start"
    receipt["started_utc"] = "2000-01-01T00:00:00+00:00"
    A.write_json(path, receipt)
    with pytest.raises(RuntimeError, match="missing"):
        P.dependency_status(item)


def test_observer_terminal_publish_race_reloads_bound_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, config, _ = setup_pipeline(tmp_path)
    item = config["dependencies"][0]
    path = Path(item["job_config"]).parent / "receipt.json"
    receipt = A.read_json(path)
    del receipt["child_pid"]
    A.write_json(path, receipt)

    def finish_then_exit(pid: int) -> None:
        pass_dependency(config)
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(
        "reproductions.unity_search_baseline.native_data_pipeline.psutil.Process", finish_then_exit
    )
    assert P.dependency_status(item)["status"] == "passed"


def test_child_not_running_refreshes_just_published_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, config, _ = setup_pipeline(tmp_path)
    item = config["dependencies"][0]

    def finish_then_stop(self: psutil.Process) -> bool:
        pass_dependency(config)
        return False

    monkeypatch.setattr(psutil.Process, "is_running", finish_then_stop)
    assert P.dependency_status(item)["status"] == "passed"


def test_completed_jobs_wait_for_memory_without_writing_shards(tmp_path: Path) -> None:
    path, config, _ = setup_pipeline(tmp_path)
    pass_dependency(config)
    config["minimum_free_ram_gib"] = 1e10
    A.write_json(path, config)
    report = P(tmp_path, path).run(follow=False)
    assert report["status"] == "waiting_resources" and report["stages"] == []
    assert not Path(config["shards"]).exists()


@pytest.mark.parametrize("name", ["prepare.json", "prepare-config.json", "dataset.json"])
def test_main_report_cannot_alias_stage_artifacts(tmp_path: Path, name: str) -> None:
    path, config, _ = setup_pipeline(tmp_path)
    config["report"] = str(Path(config["reports"]) / name)
    A.write_json(path, config)
    with pytest.raises(ValueError, match="alias"):
        P(tmp_path, path)


def test_concurrent_public_identity_claim_preserves_other_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, config, _ = setup_pipeline(tmp_path)
    pipeline = P(tmp_path, path)
    original = Path.mkdir

    def race(self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        original(self, mode, parents, exist_ok)
        if self == pipeline.output:
            A.write_json(pipeline.report, {"competitor": True})

    monkeypatch.setattr(Path, "mkdir", race)
    with pytest.raises(FileExistsError):
        pipeline.run(follow=False)
    assert A.read_json(Path(config["report"])) == {"competitor": True}
