from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from torch import nn

from adaptive_astc.evaluation.patch_metrics import PatchRegressionMetrics
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.utils.artifacts import ArtifactStore


def test_training_source_binding_requires_explicit_exact_archive(tmp_path: Path) -> None:
    root = tmp_path / "project"
    source = root / "src/model.py"
    source.parent.mkdir(parents=True)
    source.write_text("original", encoding="utf-8")
    expected = ArtifactStore.sha256_file(source)
    settings = {"source_files_sha256": {str(source): expected}}
    assert PatchNormalizationAudit.bind_training_sources(settings, root, None)["archive"] is None
    archive = tmp_path / "archive"
    saved = archive / "src/model.py"
    saved.parent.mkdir(parents=True)
    saved.write_bytes(source.read_bytes())
    source.write_text("current", encoding="utf-8")
    with pytest.raises(ValueError, match="bound source snapshot"):
        PatchNormalizationAudit.bind_training_sources(settings, root, None)
    bound = PatchNormalizationAudit.bind_training_sources(settings, root, archive)
    assert bound["sources"][0]["training_sha256"] == expected
    assert bound["sources"][0]["current_sha256"] == ArtifactStore.sha256_file(source)
    assert bound["sources"][0]["verified_source"] == str(saved)
    saved.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="bound source snapshot"):
        PatchNormalizationAudit.bind_training_sources(settings, root, archive)


def test_training_source_binding_rejects_incomplete_archive(tmp_path: Path) -> None:
    source = tmp_path / "model.py"
    source.write_text("model", encoding="utf-8")
    settings = {"source_files_sha256": {str(source): ArtifactStore.sha256_file(source)}}
    archive = tmp_path / "archive"
    archive.mkdir()
    with pytest.raises(ValueError, match="bound source snapshot"):
        PatchNormalizationAudit.bind_training_sources(settings, tmp_path, archive)
    with pytest.raises(ValueError, match="existing directory"):
        PatchNormalizationAudit.bind_training_sources(settings, tmp_path, archive / "missing")


def test_training_source_binding_rejects_outside_project_and_empty(tmp_path: Path) -> None:
    source = tmp_path / "outside.py"
    source.write_text("model", encoding="utf-8")
    settings = {"source_files_sha256": {str(source): ArtifactStore.sha256_file(source)}}
    with pytest.raises(ValueError, match="outside the project"):
        PatchNormalizationAudit.bind_training_sources(settings, tmp_path / "project", None)
    with pytest.raises(ValueError, match="bindings are required"):
        PatchNormalizationAudit.bind_training_sources({"source_files_sha256": {}}, tmp_path, None)


def test_execution_bindings_include_current_inference_and_cli() -> None:
    sources = PatchNormalizationAudit.execution_sources()
    assert len(sources) == 14
    assert any(path.endswith("patch_normalization.py") for path in sources)
    assert any(path.endswith("masked_patch_regressor.py") for path in sources)
    for name, sha in sources.items():
        assert ArtifactStore.sha256_file(Path(name)) == sha


def test_recalibration_preserves_weights_modes_and_momentum() -> None:
    model = nn.Sequential(nn.BatchNorm2d(3, momentum=0.2), nn.Dropout(p=0.5))
    model.eval()
    weights = {name: value.detach().clone() for name, value in model.named_parameters()}
    data = [torch.full((2, 3, 8, 8), 2.0), torch.full((2, 3, 8, 8), 4.0)]
    count = PatchNormalizationAudit.recalibrate(model, data, torch.device("cpu"))
    assert count == 4
    torch.testing.assert_close(model[0].running_mean, torch.full((3,), 3.0))
    assert model[0].num_batches_tracked == 2
    assert model[0].momentum == 0.2
    assert all(not layer.training for layer in model.modules())
    for name, value in model.named_parameters():
        torch.testing.assert_close(value, weights[name], rtol=0, atol=0)


def test_lossless_validation_can_reproduce_undefined_neighborhood_rmse() -> None:
    row = {
        "full_squared_errors": [0] * 4,
        "pixel_count": 1,
        "class_id": 3,
        "payload_bytes": [16] * 4,
        "group": "fixture",
        "width": 1,
        "height": 1,
    }
    measured, _ = PatchRegressionMetrics.compute(np.zeros((1, 4)), [row])
    assert measured["near_threshold_rmse_db"] is None
    assert PatchNormalizationAudit.baseline_matches(measured, measured)
    assert not PatchNormalizationAudit.baseline_matches(
        measured, {**measured, "near_threshold_rmse_db": 0.0}
    )
