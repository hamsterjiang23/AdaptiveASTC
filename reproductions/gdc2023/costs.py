"""Read optional whole-process data preparation costs without blocking compression."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from adaptive_astc.utils.artifacts import ArtifactStore


class PreparationCost:
    @staticmethod
    def load_optional(path: Path) -> dict[str, Any] | None:
        try:
            record = ArtifactStore.read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        required = {
            "status",
            "process_exit_code",
            "wall_seconds",
            "start_utc",
            "end_utc",
            "protocol_sha256",
            "collection_sha256",
            "manifest_sha256",
        }
        if not isinstance(record, dict) or not required.issubset(record):
            return None
        duration = record["wall_seconds"]
        if (
            record["status"] != "passed"
            or record["process_exit_code"] != 0
            or not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not math.isfinite(duration)
            or duration <= 0
            or any(
                not isinstance(record[key], str)
                for key in required - {"process_exit_code", "wall_seconds"}
            )
        ):
            return None
        try:
            elapsed = (
                datetime.fromisoformat(record["end_utc"])
                - datetime.fromisoformat(record["start_utc"])
            ).total_seconds()
        except (TypeError, ValueError):
            return None
        return record if abs(elapsed - duration) <= 1e-5 else None


class EvaluationProcessCost:
    """Retain failed and successful broker attempts for the exact evaluation output."""

    @staticmethod
    def load(run: Path, evaluation: Path) -> dict[str, Any]:
        attempts = []
        for config in sorted((run / "jobs").glob("*/config.json")):
            command = ArtifactStore.read_json(config)["command"]
            if "evaluate" not in command or "--reference-capture" in command:
                continue
            options = {
                key: command[command.index(key) + 1]
                for key in ["--method", "--run-id", "--evaluation-id", "--initialization"]
                if key in command and command.index(key) + 1 < len(command)
            }
            if options.get("--method") != "gdc2023" or options.get("--run-id") != run.name:
                continue
            identity = options.get("--evaluation-id")
            if identity is None or Path(identity).name != identity:
                continue
            initialization = options.get("--initialization", "pretrained")
            if (run / "evaluations" / identity / initialization).resolve() != evaluation.resolve():
                continue
            receipt_path = config.parent / "receipt.json"
            receipt = ArtifactStore.read_json(receipt_path)
            if receipt["command"] != command or receipt[
                "config_sha256"
            ] != ArtifactStore.sha256_file(config):
                raise ValueError("Evaluation job command or configuration changed")
            duration = receipt["wall_seconds"]
            known = receipt["status"] in {"passed", "failed"} and (
                isinstance(duration, (int, float))
                and not isinstance(duration, bool)
                and math.isfinite(duration)
                and duration > 0
            )
            if known and (receipt["process_exit_code"] == 0) != (receipt["status"] == "passed"):
                raise ValueError("Evaluation job exit code contradicts its terminal status")
            attempts.append(
                {
                    **receipt,
                    "accounted_wall_seconds": duration if known else None,
                    "receipt_sha256": ArtifactStore.sha256_file(receipt_path),
                    "logs_sha256": {
                        name: ArtifactStore.sha256_file(config.parent / name)
                        for name in ["stdout.log", "stderr.log"]
                        if (config.parent / name).exists()
                    },
                }
            )
        durations = [item["accounted_wall_seconds"] for item in attempts]
        known_sum = sum(value for value in durations if value is not None)
        unknown = sum(value is None for value in durations)
        return {
            "status": "recorded" if attempts else "unknown_unrecorded_process_wall",
            "all_attempts_wall_seconds": known_sum if attempts and unknown == 0 else None,
            "known_attempts_wall_seconds": known_sum,
            "unknown_duration_attempts": unknown,
            "attempts": attempts,
            "scope": "complete processes including startup, input audit, verification and retries",
        }
