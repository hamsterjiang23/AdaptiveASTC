from __future__ import annotations

import sys
from pathlib import Path

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.training import patch_suite
from adaptive_astc.training.classification_control import ClassificationControlConfig
from adaptive_astc.training.patch_suite import PatchExperimentSuite
from adaptive_astc.training.patch_trainer import PatchTrainConfig
from adaptive_astc.utils.artifacts import ArtifactStore
from script import run_classification_controls


class FailingTrial:
    def __init__(self, config: ClassificationControlConfig | PatchTrainConfig) -> None:
        self.config = config

    def fit(self) -> JsonDict:
        raise RuntimeError("test failure")


@pytest.mark.parametrize("kind", ["classification", "patch"])
def test_suite_records_terminal_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    config = tmp_path / "suite.json"
    summary = tmp_path / "summary.json"
    ArtifactStore.write_json(
        config,
        {
            "summary": str(summary),
            "trials": [
                {
                    "name": "failing",
                    "config": {
                        "source" if kind == "classification" else "corpus": str(
                            tmp_path / "source"
                        ),
                        "output": str(tmp_path / "output"),
                        "report": str(tmp_path / "report.json"),
                    },
                }
            ],
        },
    )
    with pytest.raises(RuntimeError, match="test failure"):
        if kind == "classification":
            monkeypatch.setattr(
                run_classification_controls, "ClassificationControlTrainer", FailingTrial
            )
            monkeypatch.setattr(
                sys, "argv", ["run_classification_controls.py", "--config", str(config)]
            )
            run_classification_controls.main()
        else:
            monkeypatch.setattr(patch_suite, "PatchTrainer", FailingTrial)
            PatchExperimentSuite(config).run()
    result = ArtifactStore.read_json(summary)
    assert result["status"] == "failed" and result["current_trial"] == "failing"
    assert result["wall_seconds"] >= 0 and "test failure" in result["error"]
