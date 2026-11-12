"""Native BN calibration must preserve RGBA, mask and metadata identities."""

from pathlib import Path

import numpy as np
import pytest
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from script.audit_unity_normalization import UnityNormalizationAudit


def test_native_calibration_inputs_preserve_image_views() -> None:
    batch = {
        "rgba": torch.rand(2, 3, 4, 8, 8),
        "valid_mask": torch.ones(2, 3, 1, 8, 8, dtype=torch.bool),
        "metadata": torch.arange(16).reshape(2, 8).float(),
    }
    rgba, mask, ids, metadata = UnityNormalizationAudit.calibration_inputs(batch)
    assert rgba.shape == (6, 4, 8, 8)
    assert mask.dtype == torch.bool
    torch.testing.assert_close(rgba, batch["rgba"].flatten(0, 1))
    torch.testing.assert_close(mask, batch["valid_mask"].flatten(0, 1))
    torch.testing.assert_close(ids, torch.tensor([0, 0, 0, 1, 1, 1]))
    torch.testing.assert_close(metadata[ids], batch["metadata"].repeat_interleave(3, dim=0))


def test_native_normalization_numeric_replay_rejects_drift(tmp_path: Path) -> None:
    path = tmp_path / "predictions.npz"
    saved = {"channel_zero": np.array([True]), "image_quality": np.array([21.0])}
    np.savez(path, channel_zero=saved["channel_zero"], image_quality=saved["image_quality"])
    UnityNormalizationAudit.verify_predictions(saved, path)
    with pytest.raises(AssertionError):
        UnityNormalizationAudit.verify_predictions(
            {**saved, "image_quality": np.array([21.001])}, path
        )


def test_native_normalization_rejects_manifest_drift(tmp_path: Path) -> None:
    manifest = tmp_path / "corpus.json"
    manifest.write_text('{"metadata":"original"}', encoding="utf-8")
    sources = {str(manifest): ArtifactStore.sha256_file(manifest)}
    UnityNormalizationAudit.verify_sources(sources)
    manifest.write_text('{"metadata":"changed"}', encoding="utf-8")
    with pytest.raises(ValueError, match="source changed"):
        UnityNormalizationAudit.verify_sources(sources)


def test_native_trainer_config_legacy_resolution_and_drift(tmp_path: Path) -> None:
    config = tmp_path / "trainer.json"
    config.write_text("{}", encoding="utf-8")
    settings = {"source_sha256": {str(config): ArtifactStore.sha256_file(config)}}
    assert UnityNormalizationAudit.training_config_path(settings) == config
    config.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="changed or is unbound"):
        UnityNormalizationAudit.training_config_path(settings)


def test_staged_trainer_config_requires_a_bound_explicit_path(tmp_path: Path) -> None:
    trainer, stage = tmp_path / "trainer.json", tmp_path / "stage.json"
    trainer.write_text("{}", encoding="utf-8")
    stage.write_text("{}", encoding="utf-8")
    settings: JsonDict = {
        "source_sha256": {
            str(trainer): ArtifactStore.sha256_file(trainer),
            str(stage): ArtifactStore.sha256_file(stage),
        }
    }
    with pytest.raises(ValueError, match="configuration path"):
        UnityNormalizationAudit.training_config_path(settings)
    settings["training_config_path"] = str(trainer)
    assert UnityNormalizationAudit.training_config_path(settings) == trainer
    settings["source_sha256"].pop(str(trainer))
    with pytest.raises(ValueError, match="changed or is unbound"):
        UnityNormalizationAudit.training_config_path(settings)
