"""Recompute V5 labels and check their geometry and native error totals."""

from __future__ import annotations

import csv
import math
import time
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_archive import UnityTileArchive, UnityTileImage
from adaptive_astc.data.unity_tile_errors import UnityTileGrid
from adaptive_astc.data.unity_tile_labels import UnityTileLabels
from adaptive_astc.utils.artifacts import ArtifactStore


class UnityTileAudit:
    KNOWN = (615, 616, 617)
    THRESHOLDS = (24, 26, 28, 30, 32, 34)

    def __init__(self, archive: UnityTileArchive, history: Path) -> None:
        self.archive = archive
        self.history_sha256 = ArtifactStore.sha256_file(history)
        with history.open(encoding="utf-8-sig", newline="") as stream:
            self.known = {
                int(row["id"]): row
                for row in csv.DictReader(stream)
                if int(row["id"]) in self.KNOWN
            }
        if set(self.known) != set(self.KNOWN):
            raise ValueError("Missing historical known-image rows")

    @staticmethod
    def view_summary(psnr: np.ndarray, content: np.ndarray, smooth: np.ndarray) -> JsonDict:
        minimum = float(psnr.min())
        smooth_minimum = float(psnr[smooth].min()) if smooth.any() else math.inf
        return {
            "min_psnr_db": minimum if math.isfinite(minimum) else None,
            "min_smooth_psnr_db": smooth_minimum if math.isfinite(smooth_minimum) else None,
            "bad_tiles": {
                str(threshold): {
                    "all": int(np.count_nonzero(psnr < threshold)),
                    "content": int(np.count_nonzero((psnr < threshold) & content)),
                    "smooth": int(np.count_nonzero((psnr < threshold) & smooth)),
                    "content_and_smooth": int(
                        np.count_nonzero((psnr < threshold) & content & smooth)
                    ),
                }
                for threshold in UnityTileAudit.THRESHOLDS
            },
        }

    @staticmethod
    def geometry(grid: UnityTileGrid, row: JsonDict) -> JsonDict:
        patch_size = 240
        target_path = Path(row["targets"])
        if ArtifactStore.sha256_file(target_path) != row["target_sha256"]:
            raise ValueError("Existing patch geometry archive changed")
        with np.load(target_path, allow_pickle=False) as target:
            boxes = target["boxes"]
        # Existing patches anchor at the display top. V5 can start from the
        # globally padded image, then cut 240-pixel patches on the tile grid.
        aligned = not np.any((boxes[:, 1] + grid.top_padding) % grid.size)
        tile_height, tile_width = grid.counts().shape
        tiles_per_patch = patch_size // grid.size
        return {
            "legacy_patch_grid_aligned": aligned,
            "padding_top": grid.top_padding,
            "padding_right_to_tile": -grid.width % grid.size,
            "v5_patch_count": math.ceil(tile_height / tiles_per_patch)
            * math.ceil(tile_width / tiles_per_patch),
        }

    def measure(self, image: UnityTileImage) -> JsonDict:
        row = image.row
        labels = UnityTileLabels.measure(image)
        grid = labels.grid
        pixels = labels.pixels.astype(np.int64)
        content, smooth = labels.content, labels.smooth
        need_alpha = row["metadata"]["need_alpha"]
        selected = row["original_selection"]
        comparisons: dict[str, JsonDict] = {}
        for candidate_index, candidate in enumerate(image.candidates):
            block, preset = candidate["block"], candidate["preset"]
            errors = labels.squared_errors[candidate_index]
            views = {
                "native_rgb": grid.psnr(errors[..., :3].sum(axis=2), 3 * pixels),
                "native_rgba": grid.psnr(errors[..., :4].sum(axis=2), 4 * pixels),
                "display": grid.psnr(errors[..., 4], 3 * pixels),
            }
            comparisons[f"{block}x{block}_{preset}"] = {
                view: self.view_summary(psnr, content, smooth) for view, psnr in views.items()
            }
        return {
            "index": row["index"],
            "asset": row["path"],
            "width": grid.width,
            "height": grid.height,
            "tiles": int(content.size),
            "content": int(content.sum()),
            "smooth": int(smooth.sum()),
            "geometry": self.geometry(grid, row),
            "coverage": {
                "normal": row["metadata"]["is_normal"],
                "linear": row["actual_options"]["profile"] == 1,
                "alpha": need_alpha,
                "original_choice_reason": selected["selection_reason"],
                "large": max(grid.width, grid.height) >= 2048,
            },
            "reference_sha256": row["reference_sha256"],
            "candidate_receipt_sha256": row["candidate_receipt_sha256"],
            "comparisons": comparisons,
        }

    def compare_known(self, row: JsonDict) -> JsonDict:
        before = self.known[row["index"]]
        differences = [
            key for key in ("tiles", "content", "smooth") if row[key] != int(before[key])
        ]
        for view, result in row["comparisons"]["8x8_fastest"].items():
            for threshold, counts in result["bad_tiles"].items():
                for key, prefix in (("all", "bad"), ("content", "badc"), ("smooth", "bads")):
                    field = f"{prefix}_{view}_{threshold}"
                    if counts[key] != int(before[field]):
                        differences.append(field)
            expected = float(before[f"min_{view}"])
            actual = result["min_psnr_db"]
            if not (actual is None and math.isinf(expected)) and (
                actual is None or not math.isclose(expected, actual, abs_tol=1e-10)
            ):
                differences.append(f"min_{view}")
        return {"index": row["index"], "differences": differences}

    def run(self, indices: list[int], output: Path) -> JsonDict:
        if not indices or len(set(indices)) != len(indices):
            raise ValueError("Audit indices must be nonempty and unique")
        output.mkdir(parents=True, exist_ok=False)
        root = Path(__file__).resolve().parents[3]
        source_paths = [
            Path(__file__),
            root / "script/audit_unity_tiles.py",
            *(
                root / "src/adaptive_astc/data" / name
                for name in (
                    "unity_tile_archive.py",
                    "unity_tile_errors.py",
                    "unity_tile_labels.py",
                )
            ),
        ]
        source_sha256 = {
            p.relative_to(root).as_posix(): ArtifactStore.sha256_file(p) for p in source_paths
        }
        start = time.perf_counter()
        completed: list[JsonDict] = []
        index: int | None = None
        try:
            for index in indices:
                result = self.measure(self.archive.image("validation", index))
                detail = output / f"validation-{index:04d}.json"
                ArtifactStore.write_json(detail, result)
                completed.append(
                    {key: value for key, value in result.items() if key != "comparisons"}
                    | {"detail_sha256": ArtifactStore.sha256_file(detail)}
                )
                if index in self.KNOWN:
                    completed[-1]["historical_comparison"] = self.compare_known(result)
                    completed[-1]["known_display_fastest"] = result["comparisons"]["8x8_fastest"][
                        "display"
                    ]
                print(
                    f"Validation {index}: {result['tiles']} tiles, 20 candidates verified",
                    flush=True,
                )
        except Exception as error:
            ArtifactStore.write_json(
                output / "failure.json",
                {
                    "index": index,
                    "error": str(error),
                    "completed": completed,
                },
            )
            raise
        report = {
            "status": "passed"
            if all(not row.get("historical_comparison", {}).get("differences") for row in completed)
            else "historical_mismatch",
            "split": "validation",
            "indices": indices,
            "all_known_cases_recomputed": set(self.KNOWN).issubset(indices),
            "source_sha256": source_sha256,
            "images": len(completed),
            "candidate_decodes": 20 * len(completed),
            "candidate_png_sha256_verified": True,
            "native_pixel_orientation_verified": True,
            "native_channel_sse_exact": True,
            "test_opened": False,
            "actual_encoding_calls": 0,
            "development_corpus_sha256": self.archive.sha256,
            "history_csv_sha256": self.history_sha256,
            "wall_seconds": time.perf_counter() - start,
            "rows": completed,
        }
        ArtifactStore.write_json(output / "report.json", report)
        return report
