"""Reject a different policy cache even when it produces identical choices."""

import json
import os
from pathlib import Path

import pytest

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.policy_audit import UnityPolicyAudit


def test_foreign_cache_cannot_substitute_for_original_policy(tmp_path: Path) -> None:
    original = os.environ.get("UNITY_POLICY_AUDIT_CONFIG")
    if not original:
        pytest.skip("Captured development policy audit not configured")
    config = ArtifactStore.read_json(Path(original))
    binding = config["policy_caches"][0]
    rows = [
        json.loads(line)
        for line in Path(binding["file"]).read_text("utf-8-sig").splitlines()
        if line
    ]
    next(row for row in rows if row.get("_kind") == "astc_cache_table_config")["tableConfig"][
        "targetNormalMeanDeg"
    ] = 3.2001
    foreign = tmp_path / "another-policy.jsonl"
    foreign.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    binding.update(file=str(foreign), sha256=ArtifactStore.sha256_file(foreign))
    config.update(output=str(tmp_path / "audit"), report=str(tmp_path / "report.json"))
    path = tmp_path / "config.json"
    ArtifactStore.write_json(path, config)
    with pytest.raises(ValueError, match="cache differs from the frozen original capture phase"):
        UnityPolicyAudit(path).run()
    assert not (tmp_path / "report.json").exists()
