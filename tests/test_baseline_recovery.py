"""Exercise retry assembly separately from native image measurements."""

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.recovery import BaselineRecovery


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_retry_assembly_preserves_original_failure_and_is_repeatable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    (project / "Assets").mkdir(parents=True)
    editor = tmp_path / "Editor.exe"
    editor.write_bytes(b"fixture")
    baseline = UnitySearchBaseline(tmp_path, project, editor, tmp_path / "manifest.json")
    baseline.run_dir.mkdir(parents=True)
    recovery = BaselineRecovery(baseline)
    recovery.repair.run_dir.mkdir()
    config = {
        "assets": [{"path": f"Assets/{name}.png"} for name in ["a", "b", "c"]],
        "backupDirectory": str(baseline.run_dir / "meta"),
        "cacheDirectory": "cache/full",
    }
    retry_config = {
        "assets": [{"path": "Assets/b.png"}],
        "backupDirectory": str(recovery.repair.run_dir / "meta"),
        "cacheDirectory": "cache/repair",
    }
    for path, document in [
        (baseline.run_dir / "full-config.json", config),
        (baseline.run_dir / "identity.json", {}),
        (baseline.run_dir / "protocol-lock.json", {}),
        (baseline.run_dir / "full-launch.json", {}),
        (recovery.repair.run_dir / "repair-config.json", retry_config),
        (recovery.repair.run_dir / "identity.json", {}),
        (recovery.repair.run_dir / "protocol-lock.json", {}),
        (recovery.repair.run_dir / "repair-launch.json", {}),
    ]:
        baseline._write(path, document)
    (recovery.repair.run_dir / "BenchmarkRunner.cs").write_text("fixture", encoding="utf-8")
    imports = [
        {"asset": f"Assets/{name}.png", "success": name != "b", "import_wall_ms": 3}
        for name in ["a", "b", "c"]
    ]
    native = [
        {
            "asset": f"Assets/{name}.png",
            "success": True,
            "cache_hit": False,
            "search_executed": True,
            "search_ms": 1,
            "select_and_encode_ms": 2,
            "candidates_attempted": 1,
            "candidates_measured": 1,
        }
        for name in ["a", "c"]
    ]
    write_rows(baseline.run_dir / "full-imports.jsonl", imports)
    write_rows(baseline.run_dir / "full-native.jsonl", native)
    baseline._write(
        baseline.run_dir / "full-receipt.json",
        {
            "status": "failed",
            "process_exit_code": 1,
            "process_wall_seconds": 10,
        },
    )
    baseline._write(
        recovery.repair.run_dir / "repair-receipt.json",
        {
            "status": "passed",
            "process_exit_code": 0,
            "process_wall_seconds": 5,
        },
    )
    write_rows(
        recovery.repair.run_dir / "repair-imports.jsonl",
        [
            {"asset": "Assets/b.png", "success": True, "import_wall_ms": 4},
        ],
    )
    write_rows(
        recovery.repair.run_dir / "repair-native.jsonl", [dict(native[0], asset="Assets/b.png")]
    )
    write_rows(
        project / "cache/full/parameter_cache_detail.jsonl",
        [
            {"tableConfig": {"fixture": True}},
            {"filePath": "Assets/a.png"},
            {"filePath": "Assets/c.png"},
        ],
    )
    write_rows(
        project / "cache/repair/parameter_cache_detail.jsonl",
        [
            {"tableConfig": {"fixture": True}},
            {"filePath": "Assets/b.png"},
        ],
    )
    # Native protocol validation has dedicated runtime checks. This fixture tests assembly.
    monkeypatch.setattr(UnitySearchBaseline, "verify_protocol", lambda _self: "fixture")
    monkeypatch.setattr(UnitySearchBaseline, "audit", lambda _self, _phase: {})
    first = recovery.assemble()
    assert first["status"] == "passed_with_retries"
    assert first["imports"] == 3
    assert first["native_records"] == 3
    assert first["process_exit_codes"] == [1, 0]
    timings = cast(dict[str, dict[str, float]], first["timings"])
    assert timings["import_wall_ms"]["sum"] == 10
    archived = baseline._read_lines(
        baseline.run_dir / "attempts/full-initial-cohort/full-imports.jsonl"
    )
    assert archived[1]["success"] is False
    assembled = baseline._read_lines(baseline.run_dir / "full-imports.jsonl")
    assert assembled[1]["success"] is True
    bundle = json.loads((baseline.run_dir / "full-assembly.json").read_text(encoding="utf-8"))
    for item in bundle["inputs"]:
        assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
    assert recovery.assemble()["timings"] == first["timings"]
