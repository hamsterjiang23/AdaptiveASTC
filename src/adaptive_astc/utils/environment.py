"""CPU-only process and dependency provenance."""

import os
import platform
import sys
from pathlib import Path

import psutil

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore


class RunEnvironment:
    """Inspect execution provenance without importing the training stack."""

    @staticmethod
    def capture() -> JsonDict:
        process = psutil.Process()
        memory = psutil.virtual_memory()
        return {
            "python": sys.version,
            "platform": platform.platform(),
            "pid": os.getpid(),
            "rss_mib": process.memory_info().rss / 1024**2,
            "available_ram_gib": memory.available / 1024**3,
            "uv_lock_sha256": ArtifactStore.sha256_file(Path("uv.lock"))
            if Path("uv.lock").exists()
            else None,
            "argv": sys.argv,
        }
