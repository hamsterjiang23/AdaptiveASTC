"""Atomic JSON artifacts and deterministic content fingerprints."""

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from adaptive_astc.config import JsonDict


class ArtifactStore:
    """Stateless persistence operations shared by experiment components."""

    @staticmethod
    def read_json(path: Path) -> JsonDict:
        content = path.read_text(encoding="utf-8-sig")
        return json.loads(content)

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(12):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == 11:
                    raise
                time.sleep(min(0.02 * (attempt + 1), 0.2))

    @staticmethod
    def sha256_file(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def fingerprint(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
