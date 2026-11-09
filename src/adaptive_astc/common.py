"""Small shared I/O and experiment constants."""

import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

import psutil

CLASSES = ("6x6", "8x8", "10x10", "12x12")
SEED = 20261109
SNAPSHOT_SHA256 = "4b7a5a7314f4e58cefc1a578d7b3d4f609024971692ef8a3c8c65828c548f843"
RUN_ID = "gdc-lite-rgb-resnet18-seed20261109"
REPORT_ROOT = Path("experiment report")
DEFAULT_RUN = REPORT_ROOT / ".local" / RUN_ID / "coverage-v2"
DEFAULT_REPORT = REPORT_ROOT / RUN_ID
JsonDict = dict[str, Any]


def read_json(path: Path) -> JsonDict:
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def environment() -> JsonDict:
    process = psutil.Process()
    memory = psutil.virtual_memory()
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "rss_mib": process.memory_info().rss / 1024**2,
        "available_ram_gib": memory.available / 1024**3,
        "uv_lock_sha256": sha256_file(Path("uv.lock")) if Path("uv.lock").exists() else None,
        "argv": sys.argv,
    }
