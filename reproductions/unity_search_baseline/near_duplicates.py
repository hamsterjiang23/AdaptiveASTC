"""Screen aligned same-size native RGBA images by full-resolution pixel RMSE."""

from __future__ import annotations

import hashlib
import io
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import scipy
from numpy.typing import NDArray
from PIL import Image
from scipy.spatial import KDTree

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityAlignedPixelDistance:
    """Cell means give an RMSE lower bound; accepted pairs use every RGBA sample."""

    @staticmethod
    def validate(pixels: NDArray[np.uint8]) -> None:
        if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 4:
            raise ValueError("Expected native RGBA8 pixels")
        if not pixels.shape[0] or not pixels.shape[1]:
            raise ValueError("Native image dimensions must be positive")

    @classmethod
    def descriptor(cls, pixels: NDArray[np.uint8], grid: int) -> NDArray[np.float64]:
        cls.validate(pixels)
        if type(grid) is not int or not 1 <= grid <= 16:
            raise ValueError("Cell grid must be an integer in1..16")
        height, width, _ = pixels.shape
        ys = np.linspace(0, height, min(grid, height) + 1, dtype=np.int64)
        xs = np.linspace(0, width, min(grid, width) + 1, dtype=np.int64)
        # Integer sums avoid a full-image float copy and preserve all original samples.
        sums = np.add.reduceat(pixels, ys[:-1], axis=0, dtype=np.uint64)
        sums = np.add.reduceat(sums, xs[:-1], axis=1, dtype=np.uint64)
        counts = np.diff(ys)[:, None] * np.diff(xs)[None, :]
        weights = np.sqrt(counts.astype(np.float64) * (height * width * 4))
        return (sums / weights[..., None]).reshape(-1)

    @classmethod
    def measure(cls, left: NDArray[np.uint8], right: NDArray[np.uint8]) -> JsonDict:
        cls.validate(left)
        cls.validate(right)
        if left.shape != right.shape:
            raise ValueError("Aligned pixel comparison requires equal dimensions")
        sums = np.zeros(4, dtype=np.int64)
        maximum = 0
        for start in range(0, left.shape[0], 64):
            difference = np.subtract(
                left[start : start + 64], right[start : start + 64], dtype=np.int16
            )
            squared = np.square(difference, dtype=np.int32)
            sums += squared.sum(axis=(0, 1), dtype=np.int64)
            maximum = max(maximum, int(np.abs(difference).max()))
        pixels = left.shape[0] * left.shape[1]
        return {
            "rgba_rmse_8bit": math.sqrt(int(sums.sum()) / (pixels * 4)),
            "channel_rmse_8bit": np.sqrt(sums / pixels).tolist(),
            "maximum_absolute_error_8bit": maximum,
        }

    @staticmethod
    def candidates(
        descriptors: NDArray[np.float64], threshold: float, maximum: int
    ) -> NDArray[np.int64]:
        if not math.isfinite(threshold) or not 0 < threshold <= 255 or maximum < 1:
            raise ValueError("Invalid near-duplicate threshold or candidate limit")
        # Rounding guard only affects retrieval; final full-resolution threshold is unchanged.
        radius = threshold + 1e-9
        tree = KDTree(descriptors)
        counts = tree.query_ball_point(descriptors, radius, eps=0, workers=1, return_length=True)
        total = (int(np.sum(counts)) - len(descriptors)) // 2
        if total > maximum:
            raise ValueError(f"Candidate budget exceeded: {total}>{maximum}; no partial pass")
        pairs = np.asarray(tree.query_pairs(radius, eps=0, output_type="ndarray"), dtype=np.int64)
        if len(pairs):
            pairs = pairs[np.lexsort((pairs[:, 1], pairs[:, 0]))]
        return pairs


class UnityNearDuplicateAudit:
    """Use frozen pixel identities; never consult labels, modify splits or open model tests."""

    def __init__(self, root: Path, path: Path) -> None:
        self.root, self.path = root.resolve(), path.resolve()
        self.config_sha = A.sha256_file(self.path)
        self.config = A.read_json(self.path)
        self.inputs: dict[str, str] = {str(self.path): self.config_sha}
        self.pngs: dict[str, str] = {}
        self.verify()
        self.threshold = self.config["rgba_rmse_8bit"]
        self.grid = self.config["cell_grid"]
        self.maximum = self.config["max_candidate_pairs"]
        if type(self.threshold) not in {int, float} or not 0 < self.threshold <= 255:
            raise ValueError("RMSE threshold must be finite and within0..255")
        if type(self.grid) is not int or not 1 <= self.grid <= 16:
            raise ValueError("Cell grid must be an integer in1..16")
        if type(self.maximum) is not int or self.maximum < 1:
            raise ValueError("Candidate limit must be a positive integer")

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/near_duplicates.py",
            "src/adaptive_astc/utils/artifacts.py",
            "script/audit_unity_near_duplicates.py",
            "pyproject.toml",
            "uv.lock",
        ]
        return {name: A.sha256_file(root / name) for name in names}

    @staticmethod
    def runtime() -> dict[str, str]:
        return {"numpy": np.__version__, "scipy": scipy.__version__, "pillow": Image.__version__}

    def verify(self) -> None:
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Near-duplicate execution sources changed")
        if self.config["runtime"] != self.runtime():
            raise ValueError("Near-duplicate runtime differs from frozen configuration")
        for name, digest in self.inputs.items():
            if A.sha256_file(Path(name)) != digest:
                raise ValueError("Frozen near-duplicate evidence changed")
        for name, digest in self.pngs.items():
            if A.sha256_file(Path(name)) != digest:
                raise ValueError("Native PNG changed during the near-duplicate audit")

    def bound_json(self, path: Path, digest: str) -> JsonDict:
        path = path.resolve()
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Frozen pixel audit input changed")
        if str(path) in self.inputs and self.inputs[str(path)] != digest:
            raise ValueError("Conflicting pixel audit evidence")
        self.inputs[str(path)] = digest
        return json.loads(raw.decode("utf-8-sig"))

    def rows(self) -> tuple[list[JsonDict], JsonDict]:
        source = self.config["pixel_identity_report"]
        report = self.bound_json(Path(source["path"]), source["sha256"])
        if report["status"] != "passed" or report["splits_modified"] is not False:
            raise ValueError("A completed unchanged pixel identity audit is required")
        details = self.bound_json(Path(report["details"]), report["details_sha256"])
        for name, digest in report["inputs_sha256"].items():
            self.bound_json(Path(name), digest)
        fields = [
            "path",
            "source_split",
            "reference",
            "reference_sha256",
            "width",
            "height",
            "rgba_identity",
            "rgba_sha256",
            "observed_options",
        ]
        rows = [{field: row[field] for field in fields} for row in details["rows"]]
        counts = dict(Counter(row["source_split"] for row in rows))
        keys = [row["path"].replace("\\", "/").casefold() for row in rows]
        if (
            not rows
            or len(set(keys)) != len(keys)
            or not set(counts) <= {"train", "validation", "confirmation"}
            or counts != report["counts"]
            or counts != self.config["expected_counts"]
        ):
            raise ValueError("Frozen pixel audit membership or coverage differs")
        return rows, report

    def load(self, row: JsonDict) -> NDArray[np.uint8]:
        path = Path(row["reference"]).resolve()
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["reference_sha256"]:
            raise ValueError("Native PNG differs from its frozen pixel audit")
        self.pngs[str(path)] = row["reference_sha256"]
        with Image.open(io.BytesIO(raw)) as image:
            if image.size != (row["width"], row["height"]):
                raise ValueError("Native dimensions differ from pixel identity")
            pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8)
        digest = hashlib.sha256(pixels.tobytes()).hexdigest()
        if (
            digest != row["rgba_sha256"]
            or A.fingerprint(["RGBA8", row["width"], row["height"], digest]) != row["rgba_identity"]
        ):
            raise ValueError("Decoded native pixels differ from pixel identity")
        return pixels

    def run(self) -> JsonDict:
        self.verify()
        report_path = Path(self.config["report"]).resolve()
        output = Path(self.config["output"]).resolve()
        public, local = self.root / "experiment report", self.root / "experiment report/.local"
        if (
            not report_path.is_relative_to(public)
            or report_path.is_relative_to(local)
            or not output.is_relative_to(local)
        ):
            raise ValueError("Audit report must be public and raw output must be under.local")
        if output.exists() or report_path.exists():
            raise FileExistsError("Use a fresh near-duplicate output and report")
        output.mkdir(parents=True, exist_ok=False)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        started = time.perf_counter()
        state: JsonDict = {
            "status": "running",
            "config_sha256": self.config_sha,
            "sources_sha256": self.config["sources_sha256"],
            "runtime": self.runtime(),
            "rgba_rmse_8bit": self.threshold,
            "cell_grid": self.grid,
            "test_opened": False,
            "training_updates": 0,
            "model_forward_calls": 0,
            "splits_modified": False,
            "independent_test_isolation_proven": False,
            "scope": "Same native dimensions and pixel alignment, RGBA8 RMSE only; "
            "no resize/crop/rotation/semantic invariance, no label-based filtering",
        }
        try:
            rows, source = self.rows()
            identities: dict[str, list[int]] = defaultdict(list)
            for index, row in enumerate(rows):
                identities[row["rgba_identity"]].append(index)
            groups = list(identities.values())
            dimensions: dict[tuple[int, int], list[int]] = defaultdict(list)
            descriptors = {}
            state.update(
                phase="loading_pixels", unique_rgba_identities=len(groups), loaded_identities=0
            )
            for index, members in enumerate(groups):
                row = rows[members[0]]
                pixels = self.load(row)
                descriptors[index] = UnityAlignedPixelDistance.descriptor(pixels, self.grid)
                dimensions[(row["width"], row["height"])].append(index)
                for duplicate in members[1:]:
                    self.load(rows[duplicate])
                state["loaded_identities"] = index + 1
                if (index + 1) % 128 == 0:
                    A.write_json(report_path, state)
            near = []
            candidates = 0
            compared = 0
            state["phase"] = "comparing_pixels"
            A.write_json(report_path, state)
            for dimension, indices in sorted(dimensions.items()):
                matrix = np.stack([descriptors[i] for i in indices])
                pairs = UnityAlignedPixelDistance.candidates(matrix, self.threshold, self.maximum)
                candidates += len(pairs)
                if candidates > self.maximum:
                    raise ValueError("Total candidate budget exceeded; no partial pass")
                for first, second in pairs:
                    left, right = groups[indices[int(first)]], groups[indices[int(second)]]
                    metrics = UnityAlignedPixelDistance.measure(
                        self.load(rows[left[0]]), self.load(rows[right[0]])
                    )
                    compared += 1
                    state["measured_candidate_pairs"] = compared
                    if compared % 128 == 0:
                        A.write_json(report_path, state)
                    if metrics["rgba_rmse_8bit"] <= self.threshold:
                        near.append(
                            {
                                "left_row_indices": left,
                                "right_row_indices": right,
                                "dimensions": list(dimension),
                                **metrics,
                                "cross_split": len({rows[i]["source_split"] for i in left + right})
                                > 1,
                            }
                        )
            self.verify()
            details_path = output / "near-duplicates.json"
            A.write_json(details_path, {"rows": rows, "near_pairs": near})
            state.update(
                status="passed",
                phase="complete",
                counts=source["counts"],
                unique_rgba_identities=len(groups),
                exact_duplicate_groups=sum(len(group) > 1 for group in groups),
                eligible_identity_pairs=sum(
                    len(ids) * (len(ids) - 1) // 2 for ids in dimensions.values()
                ),
                all_identity_pairs=len(groups) * (len(groups) - 1) // 2,
                retrieved_candidate_pairs=candidates,
                measured_candidate_pairs=compared,
                near_identity_pairs=len(near),
                near_image_pairs=sum(
                    len(p["left_row_indices"]) * len(p["right_row_indices"]) for p in near
                ),
                cross_split_near_identity_pairs=sum(p["cross_split"] for p in near),
                exact_cross_split_groups=source["rgba"]["cross_split_groups"],
                details=str(details_path),
                details_sha256=A.sha256_file(details_path),
                inputs_sha256=self.inputs,
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report_path, state)
        return state
