"""A failed fresh comparison audit preserves the supplied public result."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.reference_comparison import ReferenceComparison
from reproductions.gdc2023.reference_reporting import GDCReferenceReport


def test_failed_report_audit_preserves_original_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reproductions.common.reference_comparison as comparison

    public = (
        tmp_path / "experiment report/gdc2023/formal/reference64/pretrained-unity-reference.json"
    )
    ArtifactStore.write_json(
        public, {"binding": {"initialization": "pretrained"}, "original": True}
    )
    readme = public.parent / "README.md"
    readme.write_text("original evidence", encoding="utf-8")
    originals = public.read_bytes(), readme.read_bytes()
    (tmp_path / "experiment report/.local").mkdir()

    def baseline(path: Path) -> None:
        pass

    def cohort(path: Path) -> tuple[list[str], dict[str, str]]:
        return [], {}

    def audit(self: GDCReferenceReport) -> dict[str, Any]:
        ArtifactStore.write_json(self.report / public.name, {"different": True})
        (self.report / "README.md").write_text("audit copy", encoding="utf-8")
        return {}

    monkeypatch.setattr(comparison.BaselineGate, "require", baseline)
    monkeypatch.setattr(comparison.EvaluationCohort, "unity64", cohort)
    monkeypatch.setattr(GDCReferenceReport, "write", audit)
    with pytest.raises(ValueError, match="fresh artifact audit"):
        ReferenceComparison(tmp_path).write(public, tmp_path / "comparison")
    assert (public.read_bytes(), readme.read_bytes()) == originals
