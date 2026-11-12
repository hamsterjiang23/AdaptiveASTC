"""Keep frozen-prediction diagnostics behind completed, hash-bound training."""

from pathlib import Path

import pytest

from adaptive_astc.utils.artifacts import ArtifactStore
from script.attribute_unity_errors import run


def test_active_training_is_rejected_before_prediction_access(tmp_path: Path) -> None:
    training = tmp_path / "training.json"
    ArtifactStore.write_json(training, {"status": "running"})
    config = tmp_path / "config.json"
    ArtifactStore.write_json(
        config,
        {
            "training_report": str(training),
            "training_report_sha256": ArtifactStore.sha256_file(training),
            "smoke": False,
            "output": str(tmp_path / "forbidden-output"),
        },
    )
    with pytest.raises(ValueError, match="terminal successful training identity"):
        run(config)
    assert not (tmp_path / "forbidden-output").exists()


def test_training_report_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    training = tmp_path / "training.json"
    ArtifactStore.write_json(training, {"status": "completed"})
    config = tmp_path / "config.json"
    ArtifactStore.write_json(
        config,
        {
            "training_report": str(training),
            "training_report_sha256": "0" * 64,
            "smoke": False,
        },
    )
    with pytest.raises(ValueError, match="Completed training report changed"):
        run(config)
