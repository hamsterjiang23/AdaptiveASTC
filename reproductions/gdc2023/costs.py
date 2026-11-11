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
