"""Regression checks for script configuration and SwanLab lifecycle."""

import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import swanlab
import torch

from adaptive_astc.cli import ExperimentCLI
from adaptive_astc.config import JsonDict, SwanLabConfig, TrainConfig
from adaptive_astc.tracking.swanlab import SwanLabTracker
from adaptive_astc.tracking.upload import MetricsUploader
from adaptive_astc.utils.artifacts import ArtifactStore


class FakeRun:
    """SDK boundary double that records writes without external side effects."""

    def __init__(self) -> None:
        self.id = "tracking-test-run"
        self.url = "https://example.invalid/tracking-test-run"
        self.logged: list[tuple[JsonDict, int | None]] = []
        self.state: str | None = None

    def log(self, data: JsonDict, step: int | None = None) -> None:
        self.logged.append((data, step))

    def finish(
        self,
        state: str = "success",
        error: str | None = None,
        async_log_timeout: int | None = None,
    ) -> None:
        self.state = state


def test_toml_configuration_and_explicit_overrides(tmp_path: Path) -> None:
    path = tmp_path / "train.toml"
    path.write_text(
        '[training]\nrun_dir="data"\nreport_dir="report"\nlearning_rate=0.02\n'
        'micro_batch=16\neffective_batch=32\n[swanlab]\nmode="offline"\ntags=["test"]\n',
        encoding="utf-8",
    )
    config = TrainConfig.load(path, {"epochs": 2, "workers": None})
    assert config.run_dir == tmp_path / "data"
    assert config.report_dir == tmp_path / "report"
    assert config.learning_rate == 0.02 and config.epochs == 2 and config.workers == 2
    assert config.optimization_signature()["effective_batch"] == 32
    assert config.to_dict()["run_dir"] == str(tmp_path / "data")
    assert SwanLabConfig.load(path, {}).tags == ("test",)
    assert SwanLabConfig.load(path, {"mode": "disabled"}).mode == "disabled"
    with pytest.raises(ValueError, match="divide"):
        TrainConfig(micro_batch=64, effective_batch=32)
    with pytest.raises(ValueError, match="finite"):
        TrainConfig(learning_rate=float("nan"))
    path.write_text("[unknown]\nvalue=1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sections"):
        TrainConfig.load(path, {})


def test_tracker_logging_finish_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[JsonDict] = []
    run = FakeRun()

    def init(**kwargs: Any) -> FakeRun:
        calls.append(kwargs)
        return run

    monkeypatch.setattr(swanlab, "init", init)
    config = SwanLabConfig(mode="online")
    with SwanLabTracker(
        config, tmp_path, "train", {"data_fingerprint": "fixed"}, "scratch"
    ) as tracker:
        tracker.log_epoch(
            {
                "epoch": 3,
                "lr": 0.01,
                "train": {"loss": 1.0, "accuracy": 0.5},
                "validation": {"nll": 0.8, "per_class": {"6x6": {"recall": 0.4}}},
                "epoch_seconds": 2.0,
                "peak_vram_mib": 800.0,
                "rss_mib": 2000.0,
            }
        )
        tracker.log_metrics("test", {"accuracy": 0.6, "invalid": float("nan"), "bins": []}, 3)
    assert run.state == "success"
    assert calls[0]["public"] is False and calls[0]["settings"].interactive is False
    assert run.logged[0][1] == 3
    assert run.logged[0][0]["train/accuracy"] == 0.5
    assert run.logged[0][0]["validation/per_class/6x6/recall"] == 0.4
    assert "test/invalid" not in run.logged[1][0]
    with SwanLabTracker(config, tmp_path, "train", {"data_fingerprint": "fixed"}, "scratch", True):
        pass
    assert calls[1]["resume"] == "must" and calls[1]["id"] == run.id
    with pytest.raises(ValueError, match="identity differs"):
        with SwanLabTracker(
            config, tmp_path, "train", {"data_fingerprint": "changed"}, "scratch", True
        ):
            pass
    assert len(calls) == 2


def test_tracker_failure_and_disabled_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun()
    monkeypatch.setattr(swanlab, "init", lambda **kwargs: run)
    with pytest.raises(RuntimeError, match="training failed"):
        with SwanLabTracker(SwanLabConfig(mode="offline"), tmp_path, "train", {}) as tracker:
            raise RuntimeError("training failed")
    assert run.state == "crashed"
    assert ArtifactStore.read_json(tracker.identity_path)["state"] == "crashed"
    with SwanLabTracker(SwanLabConfig(), tmp_path, "disabled", {}) as tracker:
        tracker.log_metrics("test", {"accuracy": 0.5})
    assert tracker.run is None and not tracker.identity_path.exists()


def test_offline_tracker_does_not_request_cloud_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = FakeRun()

    def unavailable_url(self: FakeRun) -> str:
        raise ValueError("Offline SDK has no cloud URL")

    monkeypatch.setattr(FakeRun, "url", property(unavailable_url), raising=False)
    monkeypatch.setattr(swanlab, "init", lambda **kwargs: run)
    with SwanLabTracker(SwanLabConfig(mode="offline"), tmp_path, "offline", {}) as tracker:
        assert tracker.identity["url"] is None


def test_rejected_train_preserves_swanlab_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_tracking_start(self: SwanLabTracker) -> SwanLabTracker:
        raise AssertionError("Training must be validated before starting tracking")

    monkeypatch.setattr(SwanLabTracker, "__enter__", unexpected_tracking_start)
    config = TrainConfig(run_dir=tmp_path, initialization="scratch")
    ArtifactStore.write_json(tmp_path / "manifest.json", {"fingerprint": "data"})
    (tmp_path / "scratch").mkdir()
    torch.save(
        {
            "data_fingerprint": "data",
            "initialization": "scratch",
            "optimization_config": config.optimization_signature(),
        },
        tmp_path / "scratch/last.pt",
    )
    identity_path = tmp_path / "tracking/train-scratch.json"
    ArtifactStore.write_json(identity_path, {"id": "existing-tracked-run"})
    before = identity_path.read_bytes()
    with pytest.raises(ValueError, match="requires --resume"):
        ExperimentCLI.train(config, SwanLabConfig(mode="online"))
    assert identity_path.read_bytes() == before
    changed = TrainConfig(
        run_dir=tmp_path, initialization="scratch", resume=True, learning_rate=0.02
    )
    with pytest.raises(ValueError, match="optimization configuration differs"):
        ExperimentCLI.train(changed, SwanLabConfig(mode="online"))
    assert identity_path.read_bytes() == before


def test_import_rejects_mismatched_metrics_before_tracking(tmp_path: Path) -> None:
    ArtifactStore.write_json(tmp_path / "manifest.json", {"fingerprint": "expected"})
    ArtifactStore.write_json(tmp_path / "metrics.json", {"data_fingerprint": "different"})
    with pytest.raises(ValueError, match="fingerprints differ"):
        MetricsUploader(tmp_path, tmp_path, SwanLabConfig(mode="online")).upload()


@pytest.mark.parametrize("name", ["prepare", "train", "calibrate", "evaluate", "upload_metrics"])
def test_script_help(name: str) -> None:
    result = subprocess.run(
        [sys.executable, f"script/{name}.py", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "usage:" in result.stdout


@pytest.mark.parametrize("name", ["prepare", "train", "calibrate", "evaluate", "upload_metrics"])
def test_script_stages_share_default_configuration(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []

    def capture_cli(command: str | None = None, arguments: list[str] | None = None) -> None:
        assert command == name and arguments is not None
        captured.append(arguments)

    def capture_upload(arguments: list[str] | None = None) -> None:
        assert arguments is not None
        captured.append(arguments)

    monkeypatch.setattr(ExperimentCLI, "main", staticmethod(capture_cli))
    monkeypatch.setattr(MetricsUploader, "main", staticmethod(capture_upload))
    monkeypatch.setattr(sys, "argv", [f"script/{name}.py"])
    runpy.run_path(f"script/{name}.py", run_name="__main__")
    assert captured[0][0] == "--config"
    path = Path(captured[0][1])
    assert path.resolve() == Path("script/train_config.toml").resolve()
    config = TrainConfig.load(path, {})
    assert (
        config.run_dir
        == Path("experiment report/.local/gdc-script-resnet18-seed20261109").resolve()
    )
