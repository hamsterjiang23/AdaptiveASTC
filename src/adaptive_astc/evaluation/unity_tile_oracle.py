"""Verify the historical smooth-gradient observation from the exact V5 label corpus."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_tile_archive import UnityTileArchive, UnityTileImage
from adaptive_astc.data.unity_tile_corpus import UnityTileCorpus
from adaptive_astc.data.unity_tile_errors import UnityTileGrid, UnityTileViews
from adaptive_astc.utils.artifacts import ArtifactStore as A

type TileObservation = tuple[int, np.ndarray, np.ndarray, np.ndarray]


class UnityTileOracle:
    def __init__(self, archive: UnityTileArchive, corpus: Path, manifest: JsonDict) -> None:
        self.archive = archive
        self.folder = corpus.parent
        self.candidate = archive.GRID.index((8, "fastest"))
        if (
            manifest["status"] != "passed"
            or manifest["test_opened"] is not False
            or manifest["counts"] != {"train": 10000, "validation": 1000}
            or manifest["candidate_images"] != 220000
        ):
            raise ValueError("Oracle confirmation needs the complete V5 development label corpus")
        self.records = {record["index"]: record for record in manifest["splits"]["validation"]}
        if set(self.records) != set(range(1000)):
            raise ValueError("V5 validation label identities are incomplete")

    def compare_known_pool(self, step_scores: list[JsonDict]) -> JsonDict:
        return self.summarize(self.label_observations(step_scores))

    @staticmethod
    def pool(
        archive: UnityTileArchive, step_scores: list[JsonDict]
    ) -> Iterator[tuple[int, UnityTileImage, JsonDict]]:
        candidate_index = archive.GRID.index((8, "fastest"))
        for row in step_scores:
            if row["native_psnr"] < 35:
                continue
            index = row["index"]
            image = archive.image("validation", index)
            candidate = image.candidates[candidate_index]
            if (
                row["asset"] != image.row["path"]
                or row["decoded_sha256"] != candidate["decoded_png_sha256"]
                or row["reference_sha256"] != image.row["reference_sha256"]
                or row["native_psnr"] != candidate["metrics"]["psnr"]
            ):
                raise ValueError("Exact oracle or native PSNR source changed in validation")
            yield index, image, candidate

    def label_observations(self, step_scores: list[JsonDict]) -> Iterator[TileObservation]:
        for index, image, _ in self.pool(self.archive, step_scores):
            record = self.records[index]
            if (
                record["asset"] != image.row["path"]
                or record["candidate_receipt_sha256"] != image.row["candidate_receipt_sha256"]
                or record["target"] != f"validation/{index:05d}.npz"
            ):
                raise ValueError("Exact tile label provenance differs from archived validation")
            target = self.folder / record["target"]
            if A.sha256_file(target) != record["target_sha256"]:
                raise ValueError(f"Exact tile label changed: {target}")
            labels = UnityTileCorpus.read_labels(target, image)
            yield (
                index,
                labels.content,
                labels.smooth,
                self.bad_tiles(labels.squared_errors[self.candidate, ..., 4], labels.pixels),
            )

    @classmethod
    def decode_observations(
        cls, archive: UnityTileArchive, step_scores: list[JsonDict]
    ) -> Iterator[TileObservation]:
        for index, image, candidate in cls.pool(archive, step_scores):
            reference, decoded = image.reference(), image.decode(candidate)
            grid = UnityTileGrid(image.row["height"], image.row["width"])
            pixels = grid.counts()
            alpha = image.row["metadata"]["need_alpha"]
            display = UnityTileViews.display(reference, alpha)
            decoded_display = UnityTileViews.display(decoded, alpha)
            maximum = grid.reduce(display.max(axis=2), np.maximum)
            minimum = grid.reduce(display.min(axis=2), np.minimum)
            content = maximum - minimum >= 2
            smooth = 2 * grid.reduce(UnityTileViews.smooth_mask(display), np.add) >= pixels
            sse = grid.squared_errors(display, decoded_display).sum(axis=2, dtype=np.uint32)
            yield index, content, smooth, cls.bad_tiles(sse, pixels)

    @staticmethod
    def bad_tiles(sse: np.ndarray, pixels: np.ndarray) -> np.ndarray:
        return sse > pixels.astype(np.float64) * 3 * 255**2 * 10 ** (-28 / 10)

    @staticmethod
    def summarize(observations: Iterable[TileObservation]) -> JsonDict:
        counts = dict.fromkeys(
            (
                "tiles",
                "content_tiles",
                "smooth_tiles",
                "smooth_content_tiles",
                "bad_tiles",
                "bad_content_tiles",
                "bad_smooth_tiles",
                "bad_smooth_content_tiles",
            ),
            0,
        )
        measured: list[int] = []
        for index, content, smooth, bad in observations:
            smooth_content = smooth & content
            counts["tiles"] += bad.size
            counts["content_tiles"] += int(np.count_nonzero(content))
            counts["smooth_tiles"] += int(np.count_nonzero(smooth))
            counts["smooth_content_tiles"] += int(np.count_nonzero(smooth_content))
            counts["bad_tiles"] += int(np.count_nonzero(bad))
            counts["bad_content_tiles"] += int(np.count_nonzero(bad & content))
            counts["bad_smooth_tiles"] += int(np.count_nonzero(bad & smooth))
            counts["bad_smooth_content_tiles"] += int(np.count_nonzero(bad & smooth_content))
            measured.append(index)
        if not measured or len(set(measured)) != len(measured):
            raise ValueError("Expected nonempty unique fixed8 historical comparison scope")
        other_content = counts["content_tiles"] - counts["smooth_content_tiles"]
        other_bad = counts["bad_content_tiles"] - counts["bad_smooth_content_tiles"]
        return {
            "images": len(measured),
            "indices": measured,
            "candidate": [8, "fastest"],
            "native_psnr_min_db": 35,
            "display_tile_psnr_below_db": 28,
            "counts": counts,
            "smooth_fraction_of_content": (
                counts["smooth_content_tiles"] / counts["content_tiles"]
                if counts["content_tiles"]
                else None
            ),
            "smooth_bad_fraction": (
                counts["bad_smooth_tiles"] / counts["smooth_tiles"]
                if counts["smooth_tiles"]
                else None
            ),
            "other_content_bad_fraction": other_bad / other_content if other_content else None,
            "bad_tile_fraction_in_smooth": (
                counts["bad_smooth_tiles"] / counts["bad_tiles"] if counts["bad_tiles"] else None
            ),
        }
