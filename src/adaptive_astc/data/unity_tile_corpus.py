"""Materialize and re-open the exact V5 development labels image by image."""

from __future__ import annotations

import msvcrt
import os
import time
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_archive import UnityTileArchive, UnityTileImage
from adaptive_astc.data.unity_tile_errors import UnityTileGrid
from adaptive_astc.data.unity_tile_labels import UnityTileLabels
from adaptive_astc.utils.artifacts import ArtifactStore


class UnityTileCorpus:
    def __init__(self, archive: UnityTileArchive, output: Path) -> None:
        self.archive = archive
        self.output = output.resolve()
        source = Path(__file__).parent
        self.sources = [
            source / name
            for name in (
                "unity_tile_archive.py",
                "unity_tile_errors.py",
                "unity_tile_labels.py",
                "unity_tile_corpus.py",
            )
        ]
        self.contract = {
            "schema": "unity-tile-sse-v1",
            "development_corpus_sha256": archive.sha256,
            "grid": "8x8_bottom_anchored_display_order",
            "candidate_grid": [list(choice) for choice in archive.GRID],
            "channels": list(UnityTileLabels.CHANNELS),
            "sources_sha256": self.source_hashes(),
        }
        self.binding = ArtifactStore.fingerprint(self.contract)

    def source_hashes(self) -> dict[str, str]:
        return {source.name: ArtifactStore.sha256_file(source) for source in self.sources}

    @staticmethod
    def read_labels(path: Path, image: UnityTileImage) -> UnityTileLabels:
        row = image.row
        grid = UnityTileGrid(row["height"], row["width"])
        with np.load(path, allow_pickle=False) as archive:
            labels = UnityTileLabels(
                grid, archive["pixels"], archive["content"], archive["smooth"], archive["sse"]
            )
        labels.verify(row["full_channel_squared_errors"])
        return labels

    def prepare(self, split: str, index: int) -> JsonDict:
        image = self.archive.image(split, index)
        path = self.output / split / f"{index:05d}.npz"
        receipt = path.with_suffix(".json")
        identity = {
            "binding": self.binding,
            "split": split,
            "index": index,
            "asset": image.row["path"],
            "reference_sha256": image.row["reference_sha256"],
            "candidate_receipt_sha256": image.row["candidate_receipt_sha256"],
        }
        if receipt.exists():
            old = ArtifactStore.read_json(receipt)
            if any(old[key] != value for key, value in identity.items()):
                raise ValueError(f"Cached tile label identity changed: {receipt}")
            if ArtifactStore.sha256_file(path) != old["target_sha256"]:
                raise ValueError(f"Cached tile labels changed: {path}")
            self.read_labels(path, image)
            return old

        labels = UnityTileLabels.measure(image)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".npz.partial")
        with temporary.open("wb") as stream:
            np.savez(
                stream,
                pixels=labels.pixels,
                content=labels.content,
                smooth=labels.smooth,
                sse=labels.squared_errors,
            )
            stream.flush()
            os.fsync(stream.fileno())
        reloaded = self.read_labels(temporary, image)
        for field in ("pixels", "content", "smooth", "squared_errors"):
            if not np.array_equal(getattr(labels, field), getattr(reloaded, field)):
                raise ValueError(f"Reopened tile labels differ for {path}: {field}")
        temporary.replace(path)
        record = identity | {
            "target": path.relative_to(self.output).as_posix(),
            "target_sha256": ArtifactStore.sha256_file(path),
            "bytes": path.stat().st_size,
            "tiles": int(labels.pixels.size),
        }
        ArtifactStore.write_json(receipt, record)
        return record

    def run(self, selection: dict[str, list[int]]) -> JsonDict:
        if set(selection) != set(self.archive.splits) or not any(selection.values()):
            raise ValueError("Select from train and validation only")
        for split, indices in selection.items():
            if len(set(indices)) != len(indices) or any(
                not 0 <= index < len(self.archive.splits[split]) for index in indices
            ):
                raise ValueError(f"Invalid or duplicate indices: {split}")
        self.output.mkdir(parents=True, exist_ok=True)
        with (self.output / "writer.lock").open("a+b") as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            return self._run_locked(selection)

    def _run_locked(self, selection: dict[str, list[int]]) -> JsonDict:
        start = time.perf_counter()
        contract = self.contract | {"selection": selection}
        config = self.output / "config.json"
        if config.exists():
            if ArtifactStore.read_json(config) != contract:
                raise ValueError("Use a new output directory for a changed V5 label run")
        else:
            ArtifactStore.write_json(config, contract)
        completed: dict[str, list[JsonDict]] = {split: [] for split in selection}
        for split, indices in selection.items():
            for index in indices:
                try:
                    completed[split].append(self.prepare(split, index))
                except Exception as error:
                    ArtifactStore.write_json(
                        self.output / f"failure-{time.time_ns()}.json",
                        {
                            "split": split,
                            "index": index,
                            "error": str(error),
                            "binding": self.binding,
                        },
                    )
                    raise
                if len(completed[split]) % 32 == 0:
                    print(
                        f"{split}: {len(completed[split])}/{len(indices)} labels verified",
                        flush=True,
                    )
        if self.source_hashes() != self.contract["sources_sha256"]:
            raise ValueError("V5 label implementation changed during the run")
        counts = {split: len(records) for split, records in completed.items()}
        rows = [record for records in completed.values() for record in records]
        report = {
            "status": "passed",
            "binding": self.binding,
            "counts": counts,
            "coverage": "complete" if counts == {"train": 10000, "validation": 1000} else "partial",
            "candidate_images": 20 * len(rows),
            "tiles": sum(record["tiles"] for record in rows),
            "bytes": sum(record["bytes"] for record in rows),
            "test_opened": False,
            "wall_seconds": time.perf_counter() - start,
            "splits": completed,
        }
        corpus = self.output / "corpus.json"
        if corpus.exists():
            original = ArtifactStore.read_json(corpus)
            if any(
                original[key] != value for key, value in report.items() if key != "wall_seconds"
            ):
                raise ValueError("Published tile corpus disagrees with verified receipts")
            return original
        ArtifactStore.write_json(corpus, report)
        return report
