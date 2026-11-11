"""Exact native-grid patch errors from frozen GDC candidate reconstructions."""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import CLASSES, JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.gdc2023.dataset import GDCLabelSelection


class PatchErrorGrid:
    """Partition all real pixels once; edge padding never enters the targets."""

    def __init__(self, patch_size: int = 240) -> None:
        if patch_size < 120 or patch_size % 120:
            raise ValueError("Patch size must be a positive multiple of grid LCM 120")
        self.patch_size = patch_size

    def boxes(self, width: int, height: int) -> NDArray[np.int64]:
        if min(width, height) < 1:
            raise ValueError("Positive image dimensions required")
        return np.asarray(
            [
                (x, y, min(self.patch_size, width - x), min(self.patch_size, height - y))
                for y in range(0, height, self.patch_size)
                for x in range(0, width, self.patch_size)
            ],
            dtype=np.int64,
        )

    def squared_errors(
        self, reference: NDArray[np.uint8], decoded: NDArray[np.uint8]
    ) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
        if reference.shape != decoded.shape or reference.ndim != 3 or reference.shape[2] != 3:
            raise ValueError("Equal RGB image shapes required")
        boxes = self.boxes(reference.shape[1], reference.shape[0])
        sums = np.empty(len(boxes), dtype=np.int64)
        for index, (x, y, width, height) in enumerate(boxes):
            error = reference[y : y + height, x : x + width].astype(np.int32)
            error -= decoded[y : y + height, x : x + width].astype(np.int32)
            sums[index] = np.sum(error * error, dtype=np.int64)
        return boxes, sums

    @staticmethod
    def psnr(mse: NDArray[np.float64]) -> NDArray[np.float64]:
        with np.errstate(divide="ignore"):
            return -10.0 * np.log10(mse)

    @staticmethod
    def choose(psnr: NDArray[np.float64], margin: float = 0.0) -> NDArray[np.int64]:
        """GDC largest passing footprint, with highest-PSNR fallback."""
        if psnr.ndim != 2 or psnr.shape[1] != 4 or np.isnan(psnr).any():
            raise ValueError("Four non-NaN candidate qualities required")
        passing = psnr > 35.0 + margin
        largest = np.max(np.where(passing, np.arange(4), -1), axis=1)
        # Square footprints have nonincreasing payload at any fixed dimensions.
        # The last maximum therefore also implements smallest-payload / largest-area ties.
        fallback = 3 - psnr[:, ::-1].argmax(axis=1)
        return np.where(largest >= 0, largest, fallback).astype(np.int64)


class GDCPatchCorpus:
    """Archive train/validation patch SSE with receipt and decoded-pixel provenance."""

    def __init__(self, measured: Path, output: Path, patch_size: int = 240) -> None:
        self.measured, self.output = measured.resolve(), output.resolve()
        self.grid = PatchErrorGrid(patch_size)

    def prepare(self, train_limit: int = 0, validation_limit: int = 0) -> JsonDict:
        if min(train_limit, validation_limit) < 0:
            raise ValueError("Limits must be nonnegative; zero means the full split")
        started = time.perf_counter()
        manifest_path = self.measured / "manifest.json"
        manifest = ArtifactStore.read_json(manifest_path)
        protocol = ArtifactStore.read_json(self.measured / "protocol.json")
        if (
            ArtifactStore.sha256_file(self.measured / "protocol.json")
            != manifest["label_protocol_sha256"]
        ):
            raise ValueError("Measured protocol hash differs from manifest")
        if manifest["classes"] != list(CLASSES) or protocol["target_psnr"] != 35.0:
            raise ValueError("Expected the frozen four-candidate GDC 35 dB protocol")
        index_by_path = {row["path"]: i for i, row in enumerate(protocol["inputs"])}
        config = {
            "schema": "gdc-native-patch-sse-v1",
            "manifest_sha256": ArtifactStore.sha256_file(manifest_path),
            "measured_root": str(self.measured),
            "patch_size": self.grid.patch_size,
            "limits": {"train": train_limit, "validation": validation_limit},
            "normalization": "SSE / (valid_width * valid_height * 3 * 255^2)",
            "edge_targets": "real pixels only; no overlap; input edge replication at training",
            "classes": list(CLASSES),
            "source_code_sha256": ArtifactStore.sha256_file(Path(__file__)),
        }
        binding = ArtifactStore.fingerprint(config)
        self.output.mkdir(parents=True, exist_ok=True)
        config_path = self.output / "config.json"
        if config_path.exists() and ArtifactStore.read_json(config_path) != config:
            raise ValueError("Patch corpus configuration changed; use a new output directory")
        ArtifactStore.write_json(config_path, config)
        split_rows: dict[str, list[JsonDict]] = {}
        groups: dict[str, set[str]] = {}
        for split, limit in config["limits"].items():
            rows = manifest["splits"][split]
            # Spread the smoke sample over the frozen order instead of taking one asset folder.
            if limit and limit < len(rows):
                indexes = np.linspace(0, len(rows) - 1, limit, dtype=np.int64)
                rows = [rows[int(i)] for i in indexes]
            groups[split] = {row["group"] for row in rows}
            split_rows[split] = []
            for row in rows:
                index = index_by_path[row["path"]]
                record = self._prepare_image(index, split, row, binding)
                split_rows[split].append(record)
                completed = sum(len(items) for items in split_rows.values())
                if completed % 32 == 0:
                    progress = {
                        "status": "preparing",
                        "images": completed,
                        "seconds": time.perf_counter() - started,
                        "split": split,
                    }
                    ArtifactStore.write_json(self.output / "progress.json", progress)
                    print(progress, flush=True)
        if groups["train"] & groups["validation"]:
            raise ValueError("Asset groups overlap between train and validation")
        result: JsonDict = {
            "status": "passed",
            "config": config,
            "binding": binding,
            "splits": split_rows,
            "counts": {split: len(rows) for split, rows in split_rows.items()},
            "patch_counts": {
                split: sum(row["patch_count"] for row in rows) for split, rows in split_rows.items()
            },
            "max_psnr_reconstruction_error_db": max(
                row["max_psnr_error_db"] for rows in split_rows.values() for row in rows
            ),
            "wall_seconds": time.perf_counter() - started,
            "test_opened": False,
            "scope": "source RGB GDC development; not Unity production acceptance",
        }
        result["fingerprint"] = ArtifactStore.fingerprint(
            {"binding": binding, "splits": split_rows}
        )
        ArtifactStore.write_json(self.output / "corpus.json", result)
        ArtifactStore.write_json(
            self.output / "progress.json",
            {key: value for key, value in result.items() if key != "splits"},
        )
        return result

    def _prepare_image(self, index: int, split: str, row: JsonDict, binding: str) -> JsonDict:
        folder = self.measured / "labels" / f"{index:05d}"
        receipt_path = folder / "receipt.json"
        if ArtifactStore.sha256_file(receipt_path) != row["label_receipt_sha256"]:
            raise ValueError(f"Receipt changed for {row['path']}")
        receipt = ArtifactStore.read_json(receipt_path)
        if receipt["status"] != "passed" or any(
            receipt[key] != value
            for key, value in {
                "index": index,
                "split": split,
                "path": row["path"],
                "fileHash": row["fileHash"],
            }.items()
        ):
            raise ValueError("Receipt identity differs from frozen manifest")
        candidates = receipt["candidates"]
        if [item["name"] for item in candidates] != list(CLASSES):
            raise ValueError("Candidate order or coverage changed")
        chosen, target_met = GDCLabelSelection.choose(candidates, 35.0)
        if chosen != receipt["selected"] or chosen["name"] != CLASSES[row["class_id"]]:
            raise ValueError("Measured selection disagrees with training label")
        for name in ["input.png", *(f"{name}.png" for name in CLASSES)]:
            if ArtifactStore.sha256_file(folder / name) != receipt["artifacts_sha256"][name]:
                raise ValueError(f"Frozen reconstruction changed: {folder / name}")
        cache_path = self.output / "targets" / f"{index:05d}.npz"
        record_path = cache_path.with_suffix(".json")
        if record_path.exists():
            cached = ArtifactStore.read_json(record_path)
            if cached["binding"] != binding or cached["target_sha256"] != ArtifactStore.sha256_file(
                cache_path
            ):
                raise ValueError("Patch target cache changed")
            expected_identity = {
                "index": index,
                "split": split,
                "path": row["path"],
                "group": row["group"],
                "class_id": row["class_id"],
                "width": row["width"],
                "height": row["height"],
                "reference": str(folder / "input.png"),
                "reference_sha256": receipt["artifacts_sha256"]["input.png"],
                "receipt_sha256": row["label_receipt_sha256"],
                "targets": str(cache_path),
                "pixel_count": row["width"] * row["height"],
                "target_met": target_met,
                "payload_bytes": [item["payload_bytes"] for item in candidates],
            }
            if any(cached.get(key) != value for key, value in expected_identity.items()):
                raise ValueError("Patch cache sample identity changed")
            with np.load(cache_path, allow_pickle=False) as archive:
                expected_boxes = self.grid.boxes(row["width"], row["height"])
                errors = archive["squared_errors"]
                if (
                    not np.array_equal(archive["boxes"], expected_boxes)
                    or errors.dtype != np.int64
                    or errors.shape != (len(expected_boxes), 4)
                    or (errors < 0).any()
                    or cached["patch_count"] != len(expected_boxes)
                    or cached["full_squared_errors"] != errors.sum(axis=0).tolist()
                ):
                    raise ValueError("Patch cache statistics changed")
            return cached
        with Image.open(folder / "input.png") as image:
            reference = np.asarray(image.convert("RGB"), dtype=np.uint8)
        height, width = reference.shape[:2]
        if (width, height) != (row["width"], row["height"]):
            raise ValueError("Reference dimensions changed")
        boxes = self.grid.boxes(width, height)
        errors = np.empty((len(boxes), 4), dtype=np.int64)
        differences: list[float] = []
        for candidate_index, candidate in enumerate(candidates):
            with Image.open(folder / f"{candidate['name']}.png") as image:
                decoded = np.asarray(image.convert("RGB"), dtype=np.uint8)
            _, errors[:, candidate_index] = self.grid.squared_errors(reference, decoded)
            mse = float(errors[:, candidate_index].sum()) / (width * height * 3 * 255**2)
            psnr = -10.0 * math.log10(mse) if mse else math.inf
            if candidate["lossless"]:
                if mse != 0 or candidate["rgb_psnr"] is not None:
                    raise ValueError("Lossless marker disagrees with decoded pixels")
            else:
                difference = abs(psnr - candidate["rgb_psnr"])
                if difference > 1e-8:
                    raise ValueError("Patch PSNR reconstruction differs from measured receipt")
                differences.append(difference)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            np.savez_compressed(stream, boxes=boxes, squared_errors=errors)
        temporary.replace(cache_path)
        result = {
            "binding": binding,
            "index": index,
            "split": split,
            "path": row["path"],
            "group": row["group"],
            "class_id": row["class_id"],
            "width": width,
            "height": height,
            "reference": str(folder / "input.png"),
            "reference_sha256": receipt["artifacts_sha256"]["input.png"],
            "receipt_sha256": row["label_receipt_sha256"],
            "targets": str(cache_path),
            "target_sha256": ArtifactStore.sha256_file(cache_path),
            "patch_count": len(boxes),
            "pixel_count": width * height,
            "max_psnr_error_db": max(differences, default=0.0),
            "full_squared_errors": errors.sum(axis=0).tolist(),
            "payload_bytes": [item["payload_bytes"] for item in candidates],
            "target_met": target_met,
        }
        ArtifactStore.write_json(record_path, result)
        return result
