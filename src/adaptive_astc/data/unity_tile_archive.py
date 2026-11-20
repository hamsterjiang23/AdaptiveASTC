"""Read the frozen Unity development inputs for V5 without opening confirmation."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore


@dataclass(frozen=True)
class UnityTileImage:
    row: JsonDict
    candidate_source: JsonDict
    candidates: list[JsonDict]

    @property
    def folder(self) -> Path:
        return Path(self.candidate_source["candidate_directory"])

    def reference(self) -> NDArray[np.uint8]:
        rgba = self.read_png(Path(self.row["reference"]), self.row["reference_sha256"])
        if (
            hashlib.sha256(rgba[::-1].tobytes()).hexdigest()
            != self.row["actual_options"]["rgba_sha256"]
        ):
            raise ValueError("Display reference disagrees with the flipped Unity callback")
        return rgba

    def decode(self, candidate: JsonDict) -> NDArray[np.uint8]:
        block, preset = candidate["block"], candidate["preset"]
        path = self.folder / f"{block}x{block}_{preset}.png"
        return self.read_png(path, candidate["decoded_png_sha256"])

    def verify_selected_orientation(self, decoded: NDArray[np.uint8]) -> None:
        folder = Path(self.candidate_source["capture_directory"])
        index = self.candidate_source["capture_index"]
        with Image.open(folder / f"{index:05d}" / "unity-native.png") as image:
            native = np.asarray(image.convert("RGBA"))
        if not np.array_equal(decoded, native[::-1]):
            raise ValueError("Archived selected decode disagrees with flipped native PNG")

    def read_png(self, path: Path, expected_sha256: str) -> NDArray[np.uint8]:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError(f"PNG SHA-256 changed: {path}")
        with Image.open(io.BytesIO(data)) as image:
            if image.size != (self.row["width"], self.row["height"]) or image.mode != "RGBA":
                raise ValueError(f"PNG dimensions or mode changed: {path}")
            return np.asarray(image, dtype=np.uint8)


class UnityTileArchive:
    GRID = [
        (b, p)
        for b in (12, 10, 8, 6)
        for p in ("fastest", "fast", "medium", "thorough", "exhaustive")
    ]

    def __init__(self, handoff: Path) -> None:
        development = ArtifactStore.read_json(handoff)["development"]
        self.path = Path(development["path"])
        self.sha256: str = development["sha256"]
        corpus = self.read_bound_json(self.path, self.sha256, dict)
        self.splits: dict[str, list[JsonDict]] = corpus["splits"]
        if (
            corpus["status"] != "passed"
            or corpus["coverage"] != "complete"
            or corpus["test_opened"] is not False
            or {split: len(rows) for split, rows in self.splits.items()}
            != {"train": 10000, "validation": 1000}
        ):
            raise ValueError("V5 requires the complete train/validation handoff")
        self.manifests: dict[tuple[Path, str], JsonDict] = {}

    @staticmethod
    def read_bound_json[T](path: Path, expected_sha256: str, expected_type: type[T]) -> T:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError(f"JSON SHA-256 changed: {path}")
        decoded = json.loads(data)
        if not isinstance(decoded, expected_type):
            raise ValueError(f"Unexpected JSON structure: {path}")
        return decoded

    def image(self, split: str, index: int) -> UnityTileImage:
        if split not in self.splits or not 0 <= index < len(self.splits[split]):
            raise ValueError(f"Expected a development image index: {split}/{index}")
        row = self.splits[split][index]
        shard = row["source_shard"]
        key = (Path(shard["corpus"]), shard["sha256"])
        if key not in self.manifests:
            original = self.read_bound_json(*key, dict)
            if original["binding"] != shard["binding"] or original["test_opened"] is not False:
                raise ValueError("Source shard binding or split changed")
            config = original["config"]
            self.manifests[key] = self.read_bound_json(
                Path(config["candidate_manifest"]), config["candidate_manifest_sha256"], dict
            )
        source = self.manifests[key]["splits"][split][shard["index"]]
        if (
            row["split"] != split
            or row["index"] != index
            or row["path"] != source["path"]
            or row["reference"] != source["reference_png"]
            or row["reference_sha256"] != source["reference_sha256"]
            or row["candidate_receipt_sha256"] != source["candidate_receipt_sha256"]
        ):
            raise ValueError(f"Candidate manifest disagrees with the development handoff: {index}")
        candidates: list[JsonDict] = self.read_bound_json(
            Path(source["candidate_directory"]) / "candidates.json",
            row["candidate_receipt_sha256"],
            list,
        )
        if [(x["block"], x["preset"]) for x in candidates] != self.GRID:
            raise ValueError("Wrong V5 candidate order")
        return UnityTileImage(row, source, candidates)
