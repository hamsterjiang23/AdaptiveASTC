"""Regress transient Windows replacement locks and independent concurrent JSON writers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from adaptive_astc.utils.artifacts import ArtifactStore


def test_transient_replace_lock_preserves_complete_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "progress.json"
    ArtifactStore.write_json(path, {"images": 1})
    replace = Path.replace
    calls = 0

    def locked_once(source: Path, target: Path) -> Path:
        nonlocal calls
        calls += 1
        if calls == 1:
            assert ArtifactStore.read_json(path) == {"images": 1}
            raise PermissionError("injected transient sharing lock")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", locked_once)
    ArtifactStore.write_json(path, {"images": 2})
    assert calls == 2 and ArtifactStore.read_json(path) == {"images": 2}


def test_concurrent_writers_each_use_their_own_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    with ThreadPoolExecutor(max_workers=4) as executor:
        pending = [executor.submit(ArtifactStore.write_json, path, {"value": i}) for i in range(12)]
        for result in pending:
            result.result()
    assert ArtifactStore.read_json(path)["value"] in range(12)
