"""Keep both successful and failed native-process outcomes in durable job receipts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.jobs import ReproductionJob


@pytest.mark.parametrize("interrupt_again", [False, True, "exit_during_interrupt"])
def test_interrupted_observer_waits_for_child_or_keeps_it_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt_again: bool | str
) -> None:
    config = tmp_path / "experiment report/.local/job/config.json"
    ArtifactStore.write_json(config, {"command": ["synthetic-child"]})

    class InterruptedProcess:
        pid = 123
        calls = 0
        finished = False

        def wait(self, timeout: int | None = None) -> int:
            self.calls += 1
            if self.calls == 1 or interrupt_again:
                if self.calls > 1 and interrupt_again == "exit_during_interrupt":
                    self.finished = True
                raise KeyboardInterrupt
            self.finished = True
            return 0

        def poll(self) -> int | None:
            return 0 if self.finished else None

    child = InterruptedProcess()

    def spawn(*args: object, **kwargs: object) -> InterruptedProcess:
        return child

    monkeypatch.setattr(subprocess, "Popen", spawn)
    job = ReproductionJob(tmp_path, config)
    if interrupt_again:
        with pytest.raises(KeyboardInterrupt):
            job.run()
        state = ArtifactStore.read_json(config.parent / "receipt.json")
        if interrupt_again == "exit_during_interrupt":
            assert state["status"] == "passed" and state["process_exit_code"] == 0
            assert "ended_utc" in state
        else:
            assert state["status"] == "running_child_unobserved"
            assert state["wall_seconds"] is None and "ended_utc" not in state
    else:
        state = job.run()
        assert state["status"] == "passed" and child.finished and child.calls == 2
        assert state["process_exit_code"] == 0 and "ended_utc" in state


@pytest.mark.parametrize("exit_code", [0, 7])
def test_job_persists_exit_and_logs(tmp_path: Path, exit_code: int) -> None:
    config = tmp_path / "experiment report/.local/job/config.json"
    ArtifactStore.write_json(
        config,
        {"command": [sys.executable, "-c", f"import sys; print('probe'); sys.exit({exit_code})"]},
    )
    job = ReproductionJob(tmp_path, config)
    result = job.run()
    assert result["process_exit_code"] == exit_code
    assert result["status"] == ("passed" if exit_code == 0 else "failed")
    assert result["wall_seconds"] > 0
    assert (config.parent / "stdout.log").read_text().strip() == "probe"
    assert ArtifactStore.read_json(config.parent / "receipt.json") == result
    with pytest.raises(FileExistsError):
        job.run()
