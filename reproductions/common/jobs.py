"""Persist command logs and outcomes for reproduction jobs launched by the Windows broker."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adaptive_astc.utils.artifacts import ArtifactStore


class ReproductionJob:
    def __init__(self, root: Path, config: Path) -> None:
        self.root = root.resolve()
        self.config = config.resolve()
        if not self.config.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Reproduction job configuration must live in experiment report/.local")

    def run(self) -> dict[str, Any]:
        config = ArtifactStore.read_json(self.config)
        command = config["command"]
        if (
            not command
            or not isinstance(command, list)
            or not all(isinstance(value, str) for value in command)
        ):
            raise ValueError("Reproduction job command must be an argument list")
        folder = self.config.parent
        receipt = folder / "receipt.json"
        if receipt.exists():
            raise FileExistsError("Use a new job identity for a retry")
        state: dict[str, Any] = {
            "status": "running",
            "command": command,
            "process_id": os.getpid(),
            "started_utc": datetime.now(UTC).isoformat(),
            "wall_seconds": None,
            "scope": config.get("scope", "reproduction command including startup"),
            "config_sha256": ArtifactStore.sha256_file(self.config),
        }
        ArtifactStore.write_json(receipt, state)
        started = time.perf_counter()
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONUTF8"] = "1"
        process: subprocess.Popen[bytes] | None = None
        try:
            with (
                (folder / "stdout.log").open("xb") as stdout,
                (folder / "stderr.log").open("xb") as stderr,
            ):
                process = subprocess.Popen(
                    command,
                    cwd=self.root,
                    env=environment,
                    stdout=stdout,
                    stderr=stderr,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                state["child_pid"] = process.pid
                ArtifactStore.write_json(receipt, state)
                while True:
                    try:
                        state["process_exit_code"] = process.wait(timeout=30)
                        break
                    except subprocess.TimeoutExpired:
                        state["last_observed_alive_utc"] = datetime.now(UTC).isoformat()
                        ArtifactStore.write_json(receipt, state)
                state["status"] = "passed" if state["process_exit_code"] == 0 else "failed"
        except BaseException as error:
            state["observer_error"] = repr(error)
            if process is None:
                state["status"] = "failed"
                raise
            state["process_exit_code"] = process.wait()
            state["status"] = "passed" if state["process_exit_code"] == 0 else "failed"
        finally:
            exit_code = process.poll() if process is not None else None
            if process is not None and exit_code is None:
                state["status"] = "running_child_unobserved"
                state["wall_seconds"] = None
            else:
                if exit_code is not None:
                    state["process_exit_code"] = exit_code
                    state["status"] = "passed" if exit_code == 0 else "failed"
                state["wall_seconds"] = time.perf_counter() - started
                state["ended_utc"] = datetime.now(UTC).isoformat()
            ArtifactStore.write_json(receipt, state)
        return state
