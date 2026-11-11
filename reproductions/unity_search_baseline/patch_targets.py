"""Native-grid RGBA error targets paired with the original Unity search labels."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.patch_targets import PatchErrorGrid
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class UnityChannelErrors:
    """Aggregate channel SSE first, then apply Unity's image-level channel mask."""

    def __init__(self, patch_size: int = 240) -> None:
        self.grid = PatchErrorGrid(patch_size)

    def squared_errors(
        self, reference: NDArray[np.uint8], decoded: NDArray[np.uint8]
    ) -> NDArray[np.int64]:
        if (
            reference.dtype != np.uint8
            or decoded.dtype != np.uint8
            or reference.shape != decoded.shape
            or reference.ndim != 3
            or reference.shape[2] != 4
        ):
            raise ValueError("Equal uint8 RGBA images required")
        boxes = self.grid.boxes(reference.shape[1], reference.shape[0])
        sums = np.empty((len(boxes), 4), dtype=np.int64)
        for index, (x, y, width, height) in enumerate(boxes):
            error = reference[y : y + height, x : x + width].astype(np.int32)
            error -= decoded[y : y + height, x : x + width].astype(np.int32)
            sums[index] = np.sum(error * error, axis=(0, 1), dtype=np.int64)
        return sums

    @staticmethod
    def psnr(
        sums: NDArray[np.int64], pixel_count: int, *, need_alpha: bool, alpha_constant: bool
    ) -> NDArray[np.float64]:
        if (
            sums.ndim != 2
            or sums.shape[1] != 4
            or not np.issubdtype(sums.dtype, np.integer)
            or (sums < 0).any()
            or type(pixel_count) is not int
            or pixel_count < 1
            or type(need_alpha) is not bool
            or type(alpha_constant) is not bool
        ):
            raise ValueError("Nonnegative candidate RGBA sums and image metadata required")
        mse = sums.astype(np.float64) / pixel_count
        mask = mse > 1e-10
        mask[:, 3] &= need_alpha and not alpha_constant
        count = mask.sum(axis=1)
        average = (mse * mask).sum(axis=1) / np.maximum(count, 1)
        result = np.full(len(sums), 100.0, dtype=np.float64)
        lossy = count > 0
        result[lossy] = 20 * np.log10(255 / np.sqrt(average[lossy]))
        return result


class UnityPatchCorpus:
    """Extract all20 candidate targets; retain nonadditive quality as image labels."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path.resolve()
        self.config = ArtifactStore.read_json(config_path)
        self.output = Path(self.config["output"])
        self.errors = UnityChannelErrors(self.config.get("patch_size", 240))
        self.measured_runs: dict[Path, JsonDict] = {}

    def prepare(self) -> JsonDict:
        started = time.perf_counter()
        path = Path(self.config["candidate_manifest"])
        if ArtifactStore.sha256_file(path) != self.config["candidate_manifest_sha256"]:
            raise ValueError("Frozen candidate manifest changed")
        manifest = ArtifactStore.read_json(path)
        if (
            manifest["status"] != "passed"
            or manifest["test_opened"] is not False
            or manifest["original_search_labels_preserved"] is not True
            or set(manifest["splits"]) != {"train", "validation"}
        ):
            raise ValueError("Require a completed development candidate manifest")
        seen: set[str] = set()
        for split, rows in manifest["splits"].items():
            if len(rows) != manifest["counts"][split]:
                raise ValueError("Candidate split count changed")
            for row in rows:
                if row["source_split"] != split or row["path"] in seen:
                    raise ValueError("Candidate split identity or uniqueness changed")
                seen.add(row["path"])
        if not seen:
            raise ValueError("No candidate rows")
        binding_config = {
            **self.config,
            "schema": "unity-rgba-channel-sse-v1",
            "source_sha256": ArtifactStore.sha256_file(Path(__file__)),
            "grid_source_sha256": ArtifactStore.sha256_file(
                Path(__file__).parents[2] / "src/adaptive_astc/data/patch_targets.py"
            ),
        }
        binding = ArtifactStore.fingerprint(binding_config)
        self.output.mkdir(parents=True, exist_ok=True)
        frozen = self.output / "config.json"
        if frozen.exists() and ArtifactStore.read_json(frozen) != binding_config:
            raise ValueError("Use a new output for a changed patch protocol")
        ArtifactStore.write_json(frozen, binding_config)
        splits: dict[str, list[JsonDict]] = {"train": [], "validation": []}
        for split in splits:
            for index, row in enumerate(manifest["splits"][split]):
                splits[split].append(self.prepare_image(row, split, index, binding))
                completed = sum(map(len, splits.values()))
                if completed % 16 == 0:
                    progress = {
                        "status": "preparing",
                        "images": completed,
                        "wall_seconds": time.perf_counter() - started,
                    }
                    ArtifactStore.write_json(self.output / "progress.json", progress)
                    print(progress, flush=True)
        records = [row for rows in splits.values() for row in rows]
        result = {
            "status": "passed",
            "config": binding_config,
            "binding": binding,
            "counts": {split: len(rows) for split, rows in splits.items()},
            "patch_counts": {
                split: sum(row["patch_count"] for row in rows) for split, rows in splits.items()
            },
            "candidate_count": 20 * len(records),
            "max_psnr_reconstruction_error_db": max(row["max_psnr_error_db"] for row in records),
            "normal_images": sum(row["metadata"]["is_normal"] for row in records),
            "multimip_normal_images": sum(
                row["metadata"]["is_normal"] and row["metadata"]["mip_count"] > 1 for row in records
            ),
            "splits": splits,
            "test_opened": False,
            "coverage": manifest["coverage"],
            "wall_seconds": time.perf_counter() - started,
            "scope": (
                "Native mip0 RGBA channel SSE; original20-candidate image quality and policy "
                "labels; SSIM and angular metrics are NOT patch averages"
            ),
        }
        result["fingerprint"] = ArtifactStore.fingerprint({"binding": binding, "splits": splits})
        corpus = self.output / "corpus.json"
        ArtifactStore.write_json(corpus, result)
        summary = {key: value for key, value in result.items() if key != "splits"}
        summary.update(corpus=str(corpus), corpus_sha256=ArtifactStore.sha256_file(corpus))
        ArtifactStore.write_json(Path(self.config["report"]), summary)
        ArtifactStore.write_json(self.output / "progress.json", summary)
        return summary

    def measured_image(self, row: JsonDict) -> JsonDict:
        folder = Path(row["candidate_directory"])
        run = folder.parent
        if run not in self.measured_runs:
            raw_path = run / "receipt.json"
            raw = ArtifactStore.read_json(raw_path)
            public_path = Path(raw["config"]["report"])
            public = ArtifactStore.read_json(public_path)
            if (
                ArtifactStore.sha256_file(public_path) != row["candidate_report_sha256"]
                or public["raw_receipt_sha256"] != ArtifactStore.sha256_file(raw_path)
                or Path(public["raw_receipt"]).resolve() != raw_path.resolve()
                or raw["status"] != "passed"
                or raw["test_opened"] is not False
            ):
                raise ValueError("Candidate run provenance changed")
            self.measured_runs[run] = {
                "report_sha256": row["candidate_report_sha256"],
                "rows": {item["index"]: item for item in raw["rows"]},
            }
        cached = self.measured_runs[run]
        measured = ArtifactStore.read_json(folder / "receipt.json")
        if (
            cached["report_sha256"] != row["candidate_report_sha256"]
            or measured != cached["rows"][row["capture_index"]]
            or ArtifactStore.sha256_file(folder / "candidates.json")
            != row["candidate_receipt_sha256"]
        ):
            raise ValueError("Candidate image receipt changed")
        return measured

    def prepare_image(self, row: JsonDict, split: str, index: int, binding: str) -> JsonDict:
        folder = Path(row["candidate_directory"])
        measured = self.measured_image(row)
        candidates_path = folder / "candidates.json"
        if (
            measured["path"] != row["path"]
            or measured["index"] != row["capture_index"]
            or measured["original_selection"] != row["selection"]
            or not measured["selected_payload_and_decode_match"]
            or ArtifactStore.sha256_file(candidates_path) != measured["candidate_receipt_sha256"]
        ):
            raise ValueError("Candidate image identity or original label changed")
        candidates = json.loads(candidates_path.read_text("utf-8"))
        grid = [
            (block, preset)
            for block in UnityASTCBackend.BLOCKS
            for preset in UnityASTCBackend.PRESETS
        ]
        if (
            candidates != measured["candidates"]
            or [(c["block"], c["preset"]) for c in candidates] != grid
        ):
            raise ValueError("Require the complete ordered20 candidate grid")
        reference_path = Path(row["reference_png"])
        if ArtifactStore.sha256_file(reference_path) != row["reference_sha256"]:
            raise ValueError("Imported reference PNG changed")
        with Image.open(reference_path) as image:
            reference = np.asarray(image.convert("RGBA"))
        if reference.shape != (row["height"], row["width"], 4):
            raise ValueError("Imported reference dimensions changed")
        boxes = self.errors.grid.boxes(row["width"], row["height"])
        metadata = measured["metadata"]
        alpha_constant = bool(reference[:, :, 3].min() == reference[:, :, 3].max())
        target_path = self.output / split / f"{index:05d}.npz"
        record_path = target_path.with_suffix(".json")
        identity = {
            "binding": binding,
            "index": index,
            "split": split,
            "path": row["path"],
            "reference": str(reference_path),
            "reference_sha256": row["reference_sha256"],
            "candidate_receipt_sha256": row["candidate_receipt_sha256"],
            "width": row["width"],
            "height": row["height"],
            "metadata": metadata,
            "original_selection": row["selection"],
            "import_metadata": row["import_metadata"],
            "actual_options": row["actual_options"],
            "alpha_constant": alpha_constant,
            "targets": str(target_path),
            "candidate_grid": [list(pair) for pair in grid],
            "image_quality": [c["metrics"] for c in candidates],
            "payload_bytes": [c["payload_bytes"] for c in candidates],
            "group": str(Path(row["path"]).parent).replace("\\", "/"),
        }
        # Decode identity is checked even when resuming cached target extraction.
        for candidate in candidates:
            path = folder / f"{candidate['block']}x{candidate['block']}_{candidate['preset']}.png"
            if ArtifactStore.sha256_file(path) != candidate["decoded_png_sha256"]:
                raise ValueError("Candidate decoded PNG changed")
        if record_path.exists():
            record = ArtifactStore.read_json(record_path)
            if (
                any(record.get(key) != value for key, value in identity.items())
                or ArtifactStore.sha256_file(target_path) != record["target_sha256"]
            ):
                raise ValueError("Cached patch targets or identity changed")
            with np.load(target_path, allow_pickle=False) as archive:
                errors = archive["channel_squared_errors"]
                if not np.array_equal(archive["boxes"], boxes):
                    raise ValueError("Cached patch geometry changed")
        else:
            errors = np.empty((len(boxes), 20, 4), dtype=np.int64)
            for candidate_index, candidate in enumerate(candidates):
                path = (
                    folder / f"{candidate['block']}x{candidate['block']}_{candidate['preset']}.png"
                )
                with Image.open(path) as image:
                    decoded = np.asarray(image.convert("RGBA"))
                errors[:, candidate_index] = self.errors.squared_errors(reference, decoded)
        if errors.dtype != np.int64 or errors.shape != (len(boxes), 20, 4) or (errors < 0).any():
            raise ValueError("Patch channel SSE shape or values changed")
        reconstructed = self.errors.psnr(
            errors.sum(axis=0),
            row["width"] * row["height"],
            need_alpha=metadata["need_alpha"],
            alpha_constant=alpha_constant,
        )
        expected = np.asarray([c["metrics"]["psnr"] for c in candidates], dtype=np.float64)
        difference = float(np.max(np.abs(reconstructed - expected)))
        if not np.isfinite(difference) or difference > 1e-5:
            raise ValueError(f"Patch aggregation disagrees with Unity native PSNR: {difference}")
        if not record_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("wb") as stream:
                np.savez_compressed(stream, boxes=boxes, channel_squared_errors=errors)
        result = {
            **identity,
            "target_sha256": ArtifactStore.sha256_file(target_path),
            "patch_count": len(boxes),
            "pixel_count": row["width"] * row["height"],
            "max_psnr_error_db": difference,
            "full_channel_squared_errors": errors.sum(axis=0).tolist(),
            "black_pixel_ratio": float(np.mean(np.all(reference[:, :, :3] == 0, axis=2))),
        }
        ArtifactStore.write_json(record_path, result)
        return result
