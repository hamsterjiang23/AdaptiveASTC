"""Atomic JSON artifacts and deterministic content fingerprints."""

import hashlib
import json
from pathlib import Path

from adaptive_astc.config import JsonDict


class ArtifactStore:
    """Stateless persistence operations shared by experiment components."""

    @staticmethod
    def read_json(path: Path) -> JsonDict:
        with path.open(encoding="utf-8-sig") as stream:
            return json.load(stream)

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def sha256_file(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def fingerprint(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
