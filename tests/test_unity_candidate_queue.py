"""Exercise the candidate follower boundaries without launching Unity or native encoding."""

from pathlib import Path

import psutil
import pytest
from test_unity_reference_series import make_series

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline import candidate_completion
from reproductions.unity_search_baseline.candidate_queue import UnityCandidateQueue


def make_queue(root: Path) -> UnityCandidateQueue:
    series = make_series(root)
    quality = root / "quality.json"
    ArtifactStore.write_json(quality, {"synthetic": True})
    path = root / "queue.json"
    ArtifactStore.write_json(
        path,
        {
            "reference_plan": str(series.config_path),
            "reference_plan_sha256": ArtifactStore.sha256_file(series.config_path),
            "reference_job_receipt": str(root / "job.json"),
            "completion_source_sha256": ArtifactStore.sha256_file(
                Path(candidate_completion.__file__)
            ),
            "quality_build_receipt": str(quality),
            "quality_build_sha256": ArtifactStore.sha256_file(quality),
            "output": str(root / "experiment report/.local/candidates"),
            "report": str(root / "candidate-progress.json"),
            "minimum_free_ram_gib": 0.001,
            "minimum_free_disk_gib": 0.001,
            "poll_seconds": 0.001,
        },
    )
    return UnityCandidateQueue(root, path)


def test_unready_references_cannot_be_reported_as_complete(tmp_path: Path) -> None:
    queue = make_queue(tmp_path)
    result = queue.run()
    assert result["status"] == "waiting_references"
    assert result["counts"] == {"train": 0, "validation": 0}
    assert not (queue.output / "manifest.json").exists()


def test_follower_does_not_consume_unpublished_live_batches(tmp_path: Path) -> None:
    queue = make_queue(tmp_path)
    for batch in queue.validate()[1]:
        ArtifactStore.write_json(
            queue.series.baseline(batch["config"]).run_dir / "options-receipt.json",
            {"status": "passed"},
        )
    ArtifactStore.write_json(
        queue.series.report,
        {"configuration_sha256": queue.config["reference_plan_sha256"], "batches": []},
    )
    ArtifactStore.write_json(Path(queue.config["reference_job_receipt"]), {"status": "failed"})
    with pytest.raises(RuntimeError, match="Reference job stopped"):
        queue.run(follow=True)
    state = ArtifactStore.read_json(queue.report)
    assert state["status"] == "failed" and state["counts"] == {"train": 0, "validation": 0}


def test_reference_plan_and_queue_config_cannot_drift(tmp_path: Path) -> None:
    queue = make_queue(tmp_path)
    ArtifactStore.write_json(queue.series.config_path, {"changed": True})
    with pytest.raises(ValueError, match="reference plan"):
        queue.validate()
    ArtifactStore.write_json(queue.config_path, {"changed": True})
    with pytest.raises(ValueError, match="configuration changed after loading"):
        queue.validate()


def test_follower_refreshes_final_publication_after_reference_process_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = make_queue(tmp_path)
    ArtifactStore.write_json(Path(queue.config["reference_job_receipt"]), {"status": "passed"})
    read_json = ArtifactStore.read_json
    reads = 0
    ArtifactStore.write_json(queue.series.report, {})

    def read(path: Path) -> JsonDict:
        nonlocal reads
        if path == queue.series.report:
            reads += 1
            return {
                "configuration_sha256": queue.config["reference_plan_sha256"],
                "batches": [],
                "status": "running" if reads == 1 else "passed",
            }
        return read_json(path)

    monkeypatch.setattr(ArtifactStore, "read_json", staticmethod(read))
    with pytest.raises(RuntimeError, match="Reference job stopped"):
        queue.run(follow=True)
    assert reads == 4  # A final changed publication gets another scheduling pass before failure.


@pytest.mark.parametrize("relative", [False, True])
def test_reference_liveness_normalizes_absolute_and_relative_config_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: bool
) -> None:
    queue = make_queue(tmp_path)
    plan = queue.series.config_path
    argument = plan.relative_to(tmp_path).as_posix() if relative else plan.as_posix()
    ArtifactStore.write_json(
        Path(queue.config["reference_job_receipt"]),
        {
            "status": "running",
            "command": ["python", "collect.py", "--config", argument],
            "process_id": 12345,
            "started_utc": "2026-11-12T00:00:00+00:00",
        },
    )

    class LiveProcess:
        def __init__(self, pid: int) -> None:
            assert pid == 12345

        def is_running(self) -> bool:
            return True

        def create_time(self) -> float:
            from datetime import datetime

            return datetime.fromisoformat("2026-11-12T00:00:00+00:00").timestamp()

        def cmdline(self) -> list[str]:
            return ["python", "script/run_reproduction_job.py"]

    monkeypatch.setattr(psutil, "Process", LiveProcess)
    assert queue.reference_is_live()


def test_follower_waits_for_first_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = make_queue(tmp_path)
    observations = 0

    def live() -> bool:
        nonlocal observations
        observations += 1
        return observations == 1

    monkeypatch.setattr(queue, "reference_is_live", live)
    with pytest.raises(RuntimeError, match="Reference job stopped"):
        queue.run(follow=True)
    assert observations == 2


def test_partial_attempt_is_retained_and_retry_gets_a_new_identity(tmp_path: Path) -> None:
    queue = make_queue(tmp_path)
    config = {"capture": "synthetic immutable input"}
    first = queue.prepare_attempt("batch", config)
    first_config = ArtifactStore.read_json(first)
    output = Path(first_config["output"])
    ArtifactStore.write_json(
        output / "receipt.json",
        {
            "status": "failed",
            "wall_seconds": 2.5,
            "error": "synthetic interrupted encoding",
        },
    )
    receipt_sha = ArtifactStore.sha256_file(output / "receipt.json")
    second = queue.prepare_attempt("batch", config)
    retry = ArtifactStore.read_json(second)
    assert first != second and retry["output"] != first_config["output"]
    assert retry["prior_attempts"][0]["wall_seconds"] == 2.5
    assert queue.prepare_attempt("batch", config) == second
    assert ArtifactStore.sha256_file(output / "receipt.json") == receipt_sha
    ArtifactStore.write_json(Path(retry["report"]), {"status": "passed"})
    assert queue.prepare_attempt("batch", config) == second


def test_completed_capture_must_be_the_same_frozen_batch(tmp_path: Path) -> None:
    queue = make_queue(tmp_path)
    batch = queue.validate()[1][0]
    baseline = queue.series.baseline(batch["config"])
    config = {
        "capture": str(baseline.run_dir / "references/normalized-batch"),
        "capture_run": str(baseline.run_dir),
        "capture_phase": "batch",
        "options_receipt": str(baseline.run_dir / "options-receipt.json"),
        "completion_source_sha256": queue.config["completion_source_sha256"],
        "quality_build_receipt": queue.config["quality_build_receipt"],
    }
    queue.verify_capture_binding(batch, config)
    # Reusing an older completed producer requires explicit identity in the frozen queue.
    current_producer = config["completion_source_sha256"]
    config["completion_source_sha256"] = "old-completed-producer"
    with pytest.raises(ValueError, match="frozen batch"):
        queue.verify_capture_binding(batch, config)
    queue.config["reuse"] = {
        batch["config"]["run_id"]: {"completion_source_sha256": "old-completed-producer"}
    }
    queue.verify_capture_binding(batch, config)
    config["completion_source_sha256"] = current_producer
    with pytest.raises(ValueError, match="frozen batch"):
        queue.verify_capture_binding(batch, config)
    queue.config["reuse"] = {}
    config["capture"] = str(tmp_path / "another-capture")
    with pytest.raises(ValueError, match="frozen batch"):
        queue.verify_capture_binding(batch, config)


def test_candidate_lock_excludes_duplicates_but_allows_reference_collection(tmp_path: Path) -> None:
    queue = make_queue(tmp_path)
    peer = UnityCandidateQueue(tmp_path, queue.config_path)
    with queue.series.project_lock(), queue.lock():
        with pytest.raises(RuntimeError, match="Another candidate queue"):
            with peer.lock():
                pytest.fail("Two candidate writers entered the shared project")
    with peer.lock():
        pass
