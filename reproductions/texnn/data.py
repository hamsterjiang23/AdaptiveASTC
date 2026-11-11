"""Collect and verify block labels from the historical native reference encoder."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.common.upstream import BaselineGate
from reproductions.texnn.reference import TexNNReference


class TexNNLabelCollector:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @staticmethod
    def sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def collect(
        self,
        source: Path,
        destination: Path,
        footprint: tuple[int, int],
        preset: str = "exhaustive",
    ) -> dict[str, object]:
        if footprint not in {(4, 4), (6, 6), (8, 8)}:
            raise ValueError("TexNN uses 4x4, 6x6 or 8x8 blocks")
        if preset not in {"veryfast", "fast", "medium", "thorough", "exhaustive"}:
            raise ValueError("Unsupported historical reference preset")
        BaselineGate.require(
            self.root
            / "experiment report/.local/unity-search-baseline-lite-rdo-off/full-receipt.json"
        )
        reference = TexNNReference(self.root)
        commit = reference.verify()
        build = json.loads(
            (reference.artifact_dir / "build-receipt.json").read_text(encoding="utf-8")
        )
        if build["commit"] != commit:
            raise ValueError("TexNN encoder build belongs to another commit")
        binaries = {
            "reference": (Path(build["executable"]), build["sha256"]),
            "labels": (Path(build["labels_executable"]), build["labels_sha256"]),
        }
        for executable, expected_hash in binaries.values():
            if self.sha256(executable) != expected_hash:
                raise ValueError("TexNN encoder executable changed since build")
        source = source.resolve()
        source_hash = self.sha256(source)
        destination = destination.resolve()
        destination.mkdir(parents=True, exist_ok=False)
        pixels = destination / "input.png"
        with Image.open(source) as image:
            image.convert("RGB").save(pixels)
        labels_path = destination / "labels.jsonl"
        environment = os.environ.copy()
        environment["TEXNN_LABELS"] = str(labels_path)
        catalog_path = destination / "catalog.json"
        environment["TEXNN_CATALOG"] = str(catalog_path)
        instrumented = ASTCEncoder(binaries["labels"][0], threads=1)
        encoded, label_seconds, stdout = instrumented.encode(
            pixels, destination / "teacher.astc", footprint, preset, environment=environment
        )
        (destination / "teacher.txt").write_text(stdout, encoding="utf-8")
        original = ASTCEncoder(binaries["reference"][0], threads=1)
        original_environment = os.environ.copy()
        original_environment.pop("TEXNN_LABELS", None)
        _, reference_seconds, stdout = original.encode(
            pixels,
            destination / "reference.astc",
            footprint,
            preset,
            environment=original_environment,
        )
        (destination / "reference.txt").write_text(stdout, encoding="utf-8")
        if self.sha256(destination / "teacher.astc") != self.sha256(destination / "reference.astc"):
            raise ValueError("Label observer changed the reference ASTC output")
        decode_seconds = original.decode(destination / "teacher.astc", destination / "teacher.tga")
        quality = original.psnr_rgb(pixels, destination / "teacher.tga")
        counts = self.verify_labels(labels_path, destination / "teacher.astc", catalog_path, pixels)
        if self.sha256(source) != source_hash:
            raise ValueError("TexNN source image changed during collection")
        for executable, expected_hash in binaries.values():
            if self.sha256(executable) != expected_hash:
                raise ValueError("TexNN encoder executable changed during collection")
        receipt = {
            "status": "passed",
            "commit": commit,
            "source": str(source),
            "source_sha256": source_hash,
            "footprint": footprint,
            "preset": preset,
            "reference_pixels": "source converted to RGB8 at original resolution",
            "color_profile": "Linear LDR",
            "native_origin": "bottom-left, historical stb loader y_flip=1",
            "threads": 1,
            "mipmaps": False,
            "label_export_seconds": label_seconds,
            "reference_encode_seconds": reference_seconds,
            "verification_decode_seconds": decode_seconds,
            "observer_byte_identical": True,
            "rgb_psnr": quality if math.isfinite(quality) else None,
            "lossless": math.isinf(quality),
            "payload_bytes": encoded.payload_bytes,
            "counts": counts,
            "binaries": {key: expected_hash for key, (_, expected_hash) in binaries.items()},
            "artifacts_sha256": {
                name: self.sha256(destination / name)
                for name in [
                    "input.png",
                    "teacher.astc",
                    "teacher.tga",
                    "reference.astc",
                    "labels.jsonl",
                    "catalog.json",
                ]
            },
        }
        (destination / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return receipt

    @staticmethod
    def verify_labels(
        labels_path: Path,
        astc_path: Path,
        catalog_path: Path | None = None,
        pixels_path: Path | None = None,
    ) -> dict[str, object]:
        header = ASTCFile.read(astc_path)
        if header.depth != 1:
            raise ValueError("TexNN image labels require a 2D ASTC file")
        block_x, block_y = header.footprint
        columns = math.ceil(header.width / block_x)
        expected = columns * math.ceil(header.height / block_y)
        original: np.ndarray | None = None
        if pixels_path is not None:
            with Image.open(pixels_path) as image:
                if image.size != (header.width, header.height):
                    raise ValueError("Reference pixels disagree with the ASTC dimensions")
                original = np.asarray(image.convert("RGB"), dtype=np.uint8)
        valid_partitions: set[tuple[int, int]] = set()
        valid_modes: set[int] = set()
        if catalog_path is not None:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            valid_partitions = {tuple(pair) for pair in catalog["partitions"]}
            valid_modes = {mode["block_mode"] for mode in catalog["block_modes"]}
            if tuple(catalog["footprint"]) != header.footprint or len(valid_partitions) > 3069:
                raise ValueError("Native partition catalog disagrees with the Appendix network")
        seen: set[tuple[int, int]] = set()
        constants = 0
        partitions: Counter[int] = Counter()
        with labels_path.open(encoding="utf-8") as labels, astc_path.open("rb") as astc:
            for line in labels:
                row = json.loads(line)
                x, y = row["x"], row["y"]
                if (
                    row["z"] != 0
                    or row["width"] != header.width
                    or row["height"] != header.height
                    or (row["block_x"], row["block_y"]) != header.footprint
                    or (x, y) in seen
                    or not 0 <= x < header.width
                    or not 0 <= y < header.height
                    or x % block_x
                    or y % block_y
                ):
                    raise ValueError("Label coordinates disagree with the ASTC grid")
                seen.add((x, y))
                astc.seek(16 + ((y // block_y) * columns + x // block_x) * 16)
                if astc.read(16).hex() != row["astc_hex"]:
                    raise ValueError("Native label does not match its actual ASTC block")
                if (
                    catalog_path is not None
                    and not row["constant"]
                    and (
                        (row["partition_count"], row["partition_index"]) not in valid_partitions
                        or row["block_mode"] not in valid_modes
                    )
                ):
                    raise ValueError("Teacher configuration is absent from the native catalog")
                rgb = np.asarray(row["rgb"], dtype=np.float32)
                endpoints = np.asarray(row["ideal_endpoints"], dtype=np.float32)
                if (
                    rgb.shape != (block_x * block_y * 3,)
                    or endpoints.shape != (24,)
                    or not np.isfinite(rgb).all()
                    or not np.isfinite(endpoints).all()
                    or np.any(rgb < 0)
                    or np.any(rgb > 1)
                    or row["error"]
                ):
                    raise ValueError("Invalid TexNN pixel or ideal-endpoint features")
                if original is not None:
                    source_y = np.maximum(header.height - 1 - y - np.arange(block_y), 0)
                    source_x = np.minimum(x + np.arange(block_x), header.width - 1)
                    expected_rgb = original[source_y[:, None], source_x[None, :]]
                    expected_rgb = expected_rgb.reshape(-1).astype(np.float32) / 255
                    if not np.allclose(rgb, expected_rgb, rtol=0, atol=1e-7):
                        raise ValueError("Native RGB features differ from reference pixels")
                constants += int(row["constant"])
                partitions[row["partition_count"]] += 1
        if len(seen) != expected:
            raise ValueError(f"Missing native labels: {len(seen)} != {expected}")
        return {
            "blocks": expected,
            "constant_blocks": constants,
            "partition_counts": dict(partitions),
            "valid_partition_labels": len(valid_partitions),
            "valid_block_modes": len(valid_modes),
        }
