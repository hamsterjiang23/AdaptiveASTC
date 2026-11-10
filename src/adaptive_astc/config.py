"""Frozen reproduction defaults and external JSON boundary types."""

import math
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

CLASSES = ("6x6", "8x8", "10x10", "12x12")
SEED = 20261109
SNAPSHOT_SHA256 = "4b7a5a7314f4e58cefc1a578d7b3d4f609024971692ef8a3c8c65828c548f843"
RUN_ID = "gdc-lite-rgb-resnet18-seed20261109"
REPORT_ROOT = Path("experiment report")
DEFAULT_RUN = REPORT_ROOT / ".local" / RUN_ID / "coverage-v2"
DEFAULT_REPORT = REPORT_ROOT / RUN_ID
JsonDict = dict[str, Any]


FORMAL_SIZES = {"test": 2000, "calibration": 1000, "validation": 1000, "train": 10000}
SMOKE_SIZES = {"test": 16, "calibration": 8, "validation": 8, "train": 32}
SUFFIXES = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff"}
EXCLUDED = (
    "Assets/Editor/",
    "Assets/Editor Default Resources/",
    "Assets/Plugins/",
    "Assets/Tools/",
    "Packages/",
)


@dataclass(frozen=True)
class TrainConfig:
    """Typed launch configuration with the original optimization defaults."""

    run_dir: Path = DEFAULT_RUN
    report_dir: Path = DEFAULT_REPORT
    initialization: Literal["pretrained", "scratch"] = "pretrained"
    epochs: int = 30
    micro_batch: int = 64
    workers: int = 2
    resume: bool = False
    max_steps: int = 0
    learning_rate: float = 0.01
    momentum: float = 0.9
    weight_decay: float = 0.0001
    effective_batch: int = 64
    scheduler_t_max: int = 30
    seed: int = SEED

    def __post_init__(self) -> None:
        if self.initialization not in {"pretrained", "scratch"}:
            raise ValueError("initialization must be pretrained or scratch")
        integers = (self.epochs, self.micro_batch, self.effective_batch, self.scheduler_t_max)
        if any(type(value) is not int or value <= 0 for value in integers):
            raise ValueError("epochs and batch/scheduler sizes must be positive integers")
        if self.micro_batch not in {16, 32, 64} or self.effective_batch % self.micro_batch:
            raise ValueError("micro_batch must be 16/32/64 and divide effective_batch")
        if type(self.workers) is not int or self.workers < 0:
            raise ValueError("workers must be a non-negative integer")
        if type(self.max_steps) is not int or self.max_steps < 0:
            raise ValueError("max_steps must be a non-negative integer")
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2**32)")
        if type(self.resume) is not bool:
            raise ValueError("resume must be a boolean")
        if not all(
            math.isfinite(value) for value in (self.learning_rate, self.momentum, self.weight_decay)
        ):
            raise ValueError("optimizer parameters must be finite")
        if self.learning_rate <= 0 or self.momentum < 0 or self.weight_decay < 0:
            raise ValueError("learning_rate must be positive, momentum/weight_decay non-negative")

    @classmethod
    def load(cls, path: Path | None, overrides: JsonDict) -> "TrainConfig":
        values: JsonDict = {}
        if path is not None:
            with path.open("rb") as stream:
                document = tomllib.load(stream)
            if set(document) - {"training", "swanlab"}:
                raise ValueError("Config sections must be training and swanlab")
            values = dict(document.get("training", {}))
            for name in ("run_dir", "report_dir"):
                if name in values:
                    values[name] = (path.resolve().parent / values[name]).resolve()
        values.update({name: value for name, value in overrides.items() if value is not None})
        return cls(**values)

    def to_dict(self) -> JsonDict:
        values = asdict(self)
        values.update(run_dir=str(self.run_dir), report_dir=str(self.report_dir))
        return values

    def optimization_signature(self) -> JsonDict:
        return {
            "seed": self.seed,
            "effective_batch": self.effective_batch,
            "optimizer": {
                "name": "SGD",
                "lr": self.learning_rate,
                "momentum": self.momentum,
                "weight_decay": self.weight_decay,
            },
            "scheduler": {"name": "CosineAnnealingLR", "T_max": self.scheduler_t_max, "eta_min": 0},
        }


@dataclass(frozen=True)
class SwanLabConfig:
    """Public tracking settings. Credentials are managed by the SwanLab SDK."""

    mode: Literal["online", "offline", "disabled"] = "disabled"
    project: str = "AdaptiveASTC"
    workspace: str | None = None
    name: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in {"online", "offline", "disabled"}:
            raise ValueError("SwanLab mode must be online, offline, or disabled")
        if not self.project.strip():
            raise ValueError("SwanLab project must be non-empty")

    @classmethod
    def load(cls, path: Path | None, overrides: JsonDict) -> "SwanLabConfig":
        values: JsonDict = {}
        if path is not None:
            with path.open("rb") as stream:
                values = dict(tomllib.load(stream).get("swanlab", {}))
        values.update({name: value for name, value in overrides.items() if value is not None})
        if "tags" in values:
            values["tags"] = tuple(values["tags"])
        return cls(**values)
