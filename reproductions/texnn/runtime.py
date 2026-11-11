"""Exchange predicted configurations and partition-only features with the native codec."""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.texnn.data import TexNNLabelCollector
from reproductions.texnn.reference import TexNNReference


@dataclass(frozen=True)
class TexNNConfiguration:
    partition_count: int
    partition_index: int
    block_mode: int = -1
    dual_component: int = -1
    endpoint_modes: tuple[int, int, int, int] = (0, 0, 0, 0)

    @classmethod
    def from_teacher(cls, row: dict[str, Any]) -> TexNNConfiguration:
        count = int(row["partition_count"])
        if count < 1 or count > 4 or row["constant"] or row["error"]:
            raise ValueError("A constant/error block has no learned configuration target")
        canonical = {1: 0, 5: 4, 9: 8, 13: 12}
        formats = [canonical.get(int(value), int(value)) for value in row["endpoint_modes"]]
        if len(formats) != count:
            raise ValueError("Endpoint modes do not match the teacher partition count")
        padded = formats + [formats[-1]] * (4 - len(formats))
        return cls(
            count,
            int(row["partition_index"]),
            int(row["block_mode"]),
            int(row["dual_component"]),
            (padded[0], padded[1], padded[2], padded[3]),
        )

    @property
    def joint_label(self) -> tuple[int, int, int, int, int, int]:
        return (self.block_mode, self.dual_component, *self.endpoint_modes)


@dataclass(frozen=True)
class TexNNPartitionFeatures:
    block_index: int
    candidate_index: int
    endpoints: tuple[float, ...]


class TexNNNativeBackend:
    def __init__(self, root: Path) -> None:
        reference = TexNNReference(root)
        commit = reference.verify()
        self.build = json.loads(
            (reference.artifact_dir / "build-receipt.json").read_text(encoding="utf-8")
        )
        if self.build["commit"] != commit:
            raise ValueError("Prediction backend build uses another upstream revision")
        if self.build.get("feature_protocol") != "partition_single_plane_rgb24_v2":
            raise ValueError("Build the partition-only TexNN feature backend before inference")
        self.executable = Path(self.build["prediction_executable"])
        self.expected_sha256 = self.build["prediction_sha256"]
        self.encoder = ASTCEncoder(self.executable, threads=1)
        self.verify_binary()

    def verify_binary(self) -> None:
        if TexNNLabelCollector.sha256(self.executable) != self.expected_sha256:
            raise ValueError("TexNN prediction backend binary changed")

    @staticmethod
    def blocks(pixels: Path, footprint: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
        with Image.open(pixels) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)[::-1]
        block_x, block_y = footprint
        height, width, _ = rgb.shape
        padded = np.pad(
            rgb,
            ((0, (-height) % block_y), (0, (-width) % block_x), (0, 0)),
            mode="edge",
        )
        rows = padded.reshape(
            padded.shape[0] // block_y, block_y, padded.shape[1] // block_x, block_x, 3
        ).transpose(0, 2, 1, 3, 4)
        rows = rows.reshape(-1, block_x * block_y, 3)
        constant = np.all(rows == rows[:, :1, :], axis=(1, 2))
        return rows.reshape(-1, block_x * block_y * 3).astype(np.float32) / 255, constant

    @staticmethod
    def write_predictions(
        path: Path,
        pixels: Path,
        footprint: tuple[int, int],
        blocks: list[list[TexNNConfiguration]],
    ) -> None:
        if footprint not in {(4, 4), (6, 6), (8, 8)}:
            raise ValueError("Unsupported TexNN prediction footprint")
        with Image.open(pixels) as image:
            width, height = image.size
        expected = math.ceil(width / footprint[0]) * math.ceil(height / footprint[1])
        if len(blocks) != expected:
            raise ValueError("Prediction count differs from the image block grid")
        with path.open("xb") as output:
            output.write(struct.pack("<8s5I", b"TXNP0001", width, height, *footprint, expected))
            for candidates in blocks:
                if len(candidates) > 1024:
                    raise ValueError("Too many predicted configurations for one block")
                output.write(struct.pack("<I", len(candidates)))
                for candidate in candidates:
                    output.write(
                        struct.pack(
                            "<8i",
                            candidate.partition_count,
                            candidate.partition_index,
                            candidate.block_mode,
                            candidate.dual_component,
                            *candidate.endpoint_modes,
                        )
                    )

    @staticmethod
    def environment(predictions: Path) -> dict[str, str]:
        environment = os.environ.copy()
        for key in [
            "TEXNN_LABELS",
            "TEXNN_CATALOG",
            "TEXNN_PREDICTIONS",
            "TEXNN_FEATURE_OUTPUT",
            "TEXNN_DECISIONS",
        ]:
            environment.pop(key, None)
        environment["TEXNN_PREDICTIONS"] = str(predictions.resolve())
        return environment

    def features(
        self, pixels: Path, predictions: Path, output: Path, footprint: tuple[int, int], preset: str
    ) -> float:
        if output.exists():
            raise FileExistsError(output)
        self.verify_binary()
        environment = self.environment(predictions)
        environment["TEXNN_FEATURE_OUTPUT"] = str(output.resolve())
        started = time.perf_counter()
        result = subprocess.run(
            [
                str(self.executable),
                "-cl",
                str(pixels.resolve()),
                str(output.with_suffix(".astc").resolve()),
                f"{footprint[0]}x{footprint[1]}",
                f"-{preset}",
                "-j",
                "1",
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        elapsed = time.perf_counter() - started
        output.with_suffix(".txt").write_text(result.stdout, encoding="utf-8")
        if not output.exists():
            output.write_text("", encoding="utf-8")
        self.verify_binary()
        return elapsed

    @staticmethod
    def iter_features(path: Path) -> Iterator[TexNNPartitionFeatures]:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                endpoints = tuple(float(value) for value in row["ideal_endpoints"])
                if (
                    row["feature_protocol"] != 2
                    or len(endpoints) != 24
                    or not all(math.isfinite(value) for value in endpoints)
                    or row["block"] < 0
                    or row["candidate"] < 0
                ):
                    raise ValueError("Invalid native partition-only inference feature")
                yield TexNNPartitionFeatures(row["block"], row["candidate"], endpoints)

    def encode(
        self,
        pixels: Path,
        predictions: Path,
        output: Path,
        footprint: tuple[int, int],
        preset: str,
        decisions: Path | None = None,
    ) -> tuple[ASTCFile, float, str]:
        self.verify_binary()
        environment = self.environment(predictions)
        if decisions is not None:
            if decisions.exists():
                raise FileExistsError(decisions)
            environment["TEXNN_DECISIONS"] = str(decisions.resolve())
        result = self.encoder.encode(pixels, output, footprint, preset, environment=environment)
        self.verify_binary()
        return result
