"""Select an explicit diagnostic cohort without changing a frozen dataset identity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adaptive_astc.utils.artifacts import ArtifactStore


class EvaluationCohort:
    @staticmethod
    def unity64(baseline: Path) -> tuple[list[str], dict[str, str]]:
        receipt = ArtifactStore.read_json(baseline / "full-receipt.json")
        lock_path = baseline / "protocol-lock.json"
        lock = ArtifactStore.read_json(lock_path)
        config_path = baseline / "smoke1-config.json"
        digest = ArtifactStore.sha256_file(config_path)
        if (
            ArtifactStore.sha256_file(lock_path) != receipt["provenance"]["protocol_sha256"]
            or digest != lock["smoke1-config.json"]
        ):
            raise ValueError("Frozen Unity64 cohort configuration changed")
        config = ArtifactStore.read_json(config_path)
        paths = [row["path"] for row in config["assets"]]
        if len(paths) != 64 or len(set(path.casefold() for path in paths)) != 64:
            raise ValueError("Frozen Unity64 requires 64 unique assets")
        return paths, {"name": "unity64", "config_sha256": digest}

    @staticmethod
    def rows(
        manifest: dict[str, Any], split: str, paths: list[str] | None = None
    ) -> list[dict[str, Any]]:
        if split not in {"train", "validation", "test"}:
            raise ValueError("Evaluation requires train, validation or test inputs")
        if split == "train" and paths is None:
            raise ValueError("Training diagnostics require an explicit shared input cohort")
        rows = manifest["splits"][split]
        if paths is None:
            return rows
        keys = [path.casefold() for path in paths]
        lookup = {row["path"].casefold(): row for row in rows}
        if not keys or len(set(keys)) != len(keys) or any(key not in lookup for key in keys):
            raise ValueError("Diagnostic cohort is empty, duplicated or outside the selected split")
        return [lookup[key] for key in keys]
