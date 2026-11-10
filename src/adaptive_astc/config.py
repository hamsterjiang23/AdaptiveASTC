"""Frozen reproduction defaults and external JSON boundary types."""

from pathlib import Path
from typing import Any

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
