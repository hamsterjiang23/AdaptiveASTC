"""Keep stale training and failed input checks away from the shared test-set lock."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import torch
from torch import nn

import reproductions.gdc2023.evaluation as gdc_evaluation
import reproductions.gdc2023.training as gdc_training
from adaptive_astc.config import TrainConfig
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.checkpoints import CheckpointStore
from adaptive_astc.utils.evaluation_seal import EvaluationSeal
from reproductions.gdc2023.evaluation import GDCCompressionEvaluation
from reproductions.gdc2023.training import GDCTraining


@pytest.mark.parametrize("first", ["probability", "compression"])
def test_probability_and_compression_seals_share_unchanged_models(
    tmp_path: Path, first: str
) -> None:
    arms = {
        "pretrained": {"checkpoint_sha256": "a", "temperature_sha256": "temperature-a"},
        "scratch": {"checkpoint_sha256": "b", "temperature_sha256": "temperature-b"},
    }
    if first == "probability":
        EvaluationSeal.probabilities(tmp_path, "data", arms)
        EvaluationSeal.compression(tmp_path, "data", "pretrained", "a")
    else:
        EvaluationSeal.compression(tmp_path, "data", "pretrained", "a")
        EvaluationSeal.probabilities(tmp_path, "data", arms)
    locked = EvaluationSeal.probabilities(tmp_path, "data", arms)
    assert locked["arms"] == arms
    assert locked["compression_models"] == {"pretrained": "a"}
    original = (tmp_path / "test_seal.json").read_bytes()
    with pytest.raises(ValueError, match="differs"):
        EvaluationSeal.compression(tmp_path, "data", "pretrained", "changed")
    changed = {**arms, "pretrained": {**arms["pretrained"], "temperature_sha256": "changed"}}
    with pytest.raises(ValueError, match="changed"):
        EvaluationSeal.probabilities(tmp_path, "data", changed)
    assert (tmp_path / "test_seal.json").read_bytes() == original


def test_legacy_probability_seal_stays_compatible(tmp_path: Path) -> None:
    original = {
        "data_fingerprint": "data",
        "arms": {"pretrained": {"checkpoint_sha256": "a", "temperature_sha256": "t"}},
    }
    ArtifactStore.write_json(tmp_path / "test_seal.json", original)
    assert EvaluationSeal.probabilities(tmp_path, "data", original["arms"]) == original


def training_fixture(
    run: Path,
) -> tuple[Path, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    folder = run / "pretrained"
    folder.mkdir()
    config = {"epochs_target": 2, "max_steps": 0}
    history = [{"epoch": index} for index in [1, 2]]
    packet = {
        "epoch": 2,
        "history": history,
        "data_fingerprint": "data",
        "initialization": "pretrained",
        "best_key": [0.5, -0.5, 1],
    }
    ArtifactStore.write_json(folder / "config.json", config)
    ArtifactStore.write_json(folder / "history.json", {"epochs": history})
    ArtifactStore.write_json(
        folder / "training_complete.json",
        {"completed_epochs": 2, "best_epoch": 1, "config": config},
    )
    CheckpointStore.save(folder / "last.pt", packet)
    return folder, config, history, packet


@pytest.mark.parametrize("damage", ["config", "history", "last_epoch", "data"])
def test_stale_smoke_completion_is_rejected(tmp_path: Path, damage: str) -> None:
    folder, config, history, packet = training_fixture(tmp_path)
    manifest = {"smoke": True, "fingerprint": "data"}
    assert len(GDCCompressionEvaluation.completed_training(tmp_path, "pretrained", manifest)) == 4
    if damage == "config":
        ArtifactStore.write_json(folder / "config.json", {**config, "epochs_target": 10})
    elif damage == "history":
        ArtifactStore.write_json(folder / "history.json", {"epochs": [*history, {"epoch": 3}]})
    elif damage == "last_epoch":
        CheckpointStore.save(folder / "last.pt", {**packet, "epoch": 3})
    else:
        CheckpointStore.save(folder / "last.pt", {**packet, "data_fingerprint": "other"})
    with pytest.raises(ValueError, match="incomplete"):
        GDCCompressionEvaluation.completed_training(tmp_path, "pretrained", manifest)
    assert not (tmp_path / "test_seal.json").exists()


def test_missing_first_source_does_not_lock_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, run = tmp_path / "workspace", tmp_path / "run"
    folder = run / "pretrained"
    folder.mkdir(parents=True)
    codec = tmp_path / "placeholder-codec"
    codec.write_bytes(b"No native process should be called in this preflight-failure test")
    codec_hash = ArtifactStore.sha256_file(codec)
    protocol = {
        "encoder_sha256": codec_hash,
        "inputs": [{"split": "test", "path": "Assets/missing.png"}],
    }
    ArtifactStore.write_json(run / "protocol.json", protocol)
    ArtifactStore.write_json(run / "collection.json", {})
    manifest = {
        "classes": ["6x6", "8x8", "10x10", "12x12"],
        "seed": 0,
        "image_root": str(tmp_path / "project"),
        "label_protocol_sha256": ArtifactStore.sha256_file(run / "protocol.json"),
        "label_collection_sha256": ArtifactStore.sha256_file(run / "collection.json"),
        "splits": {"test": [{"path": "Assets/missing.png", "fileHash": "0" * 32}]},
    }
    manifest["fingerprint"] = ArtifactStore.fingerprint(manifest)
    ArtifactStore.write_json(run / "manifest.json", manifest)
    CheckpointStore.save(
        folder / "best.pt",
        {
            "model": {},
            "data_fingerprint": manifest["fingerprint"],
            "initialization": "pretrained",
            "epoch": 1,
        },
    )
    ArtifactStore.write_json(folder / "training_complete.json", {"best_epoch": 1})
    ArtifactStore.write_json(
        root
        / "experiment report/.local/reproduction-binaries/nah2022_psnr_search/build-receipt.json",
        {"executable": str(codec), "sha256": codec_hash},
    )

    def skip_baseline(path: Path) -> None:
        pass

    def completed(run_dir: Path, initialization: str, data: dict[str, Any]) -> dict[str, str]:
        return {}

    def cpu_runtime(seed: int) -> torch.device:
        return torch.device("cpu")

    def model(initialization: str, pretrained: bool) -> nn.Identity:
        return nn.Identity()

    monkeypatch.setattr(gdc_evaluation.BaselineGate, "require", skip_baseline)
    monkeypatch.setattr(GDCCompressionEvaluation, "completed_training", staticmethod(completed))
    monkeypatch.setattr(gdc_evaluation.ExperimentRuntime, "configure", cpu_runtime)
    monkeypatch.setattr(gdc_evaluation, "ASTCClassifier", model)
    output = run / "evaluations" / "missing-source"
    with pytest.raises(FileNotFoundError):
        GDCCompressionEvaluation(root, run, "pretrained").evaluate(output)
    assert not (run / "test_seal.json").exists()
    assert not output.exists()


def test_training_cost_preserves_unknown_interrupted_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    ArtifactStore.write_json(
        run / "training-attempts/pretrained-old.json", {"status": "running", "wall_seconds": None}
    )

    def data(self: GDCTraining) -> dict[str, Any]:
        return {"fingerprint": "data", "seed": 0}

    class PreparedTrainer:
        def fit(self) -> dict[str, int]:
            folder = run / "pretrained"
            folder.mkdir(exist_ok=True)
            for name in ["last.pt", "best.pt", "training_complete.json"]:
                (folder / name).write_bytes(b"timing-fixture")
            return {"completed_epochs": 1, "best_epoch": 1}

    def prepared(config: TrainConfig) -> PreparedTrainer:
        return PreparedTrainer()

    monkeypatch.setattr(GDCTraining, "validate_data", data)
    monkeypatch.setattr(gdc_training.Trainer, "from_config", prepared)
    receipt = GDCTraining(tmp_path, run, tmp_path / "report").train(epochs=1, workers=0)
    assert receipt["status"] == "passed"
    assert receipt["all_attempts_wall_seconds"] is None
    assert receipt["unknown_duration_attempts"] == 1
    assert receipt["all_attempts_known_wall_seconds"] > 0


def test_resuming_an_unmetered_checkpoint_keeps_prior_time_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    folder = run / "pretrained"
    folder.mkdir(parents=True)
    (folder / "last.pt").write_bytes(b"prior-unmetered-checkpoint")

    def data(self: GDCTraining) -> dict[str, Any]:
        return {"fingerprint": "data", "seed": 0}

    class PreparedTrainer:
        def fit(self) -> dict[str, int]:
            for name in ["last.pt", "best.pt", "training_complete.json"]:
                (folder / name).write_bytes(b"new-timing-fixture")
            return {"completed_epochs": 3, "best_epoch": 2}

    def prepared(config: TrainConfig) -> PreparedTrainer:
        return PreparedTrainer()

    monkeypatch.setattr(GDCTraining, "validate_data", data)
    monkeypatch.setattr(gdc_training.Trainer, "from_config", prepared)
    receipt = GDCTraining(tmp_path, run, tmp_path / "report").train(epochs=3, resume=True)
    assert receipt["unaccounted_prior_training"]
    assert receipt["unknown_duration_attempts"] == 0
    assert receipt["all_attempts_wall_seconds"] is None
    assert receipt["all_attempts_known_wall_seconds"] > 0
