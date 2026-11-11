"""Run a pinned astcenc CLI and inspect the actual ASTC output header."""

from __future__ import annotations

import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ASTCFile:
    footprint: tuple[int, int]
    width: int
    height: int
    depth: int
    payload_bytes: int
    container_bytes: int

    @classmethod
    def read(cls, path: Path) -> ASTCFile:
        contents = path.read_bytes()
        if len(contents) < 16 or contents[:4] != bytes.fromhex("13aba15c"):
            raise ValueError(f"Invalid ASTC header: {path}")
        block_x, block_y, block_z = contents[4:7]
        width = int.from_bytes(contents[7:10], "little")
        height = int.from_bytes(contents[10:13], "little")
        depth = int.from_bytes(contents[13:16], "little")
        if min(block_x, block_y, block_z, width, height, depth) < 1:
            raise ValueError(f"Zero-sized ASTC dimension: {path}")
        payload = 16 * math.ceil(width / block_x) * math.ceil(height / block_y)
        payload *= math.ceil(depth / block_z)
        if len(contents) != payload + 16:
            raise ValueError(f"ASTC payload size mismatch: {path}")
        return cls((block_x, block_y), width, height, depth, payload, len(contents))


class ASTCEncoder:
    def __init__(self, executable: Path, threads: int = 1) -> None:
        self.executable = executable.resolve()
        self.threads = threads
        if threads < 1:
            raise ValueError("Encoder thread count must be positive")

    def encode(
        self,
        source: Path,
        output: Path,
        footprint: tuple[int, int],
        preset: str,
        srgb: bool = False,
        target_psnr: float | None = None,
        *,
        environment: dict[str, str] | None = None,
    ) -> tuple[ASTCFile, float, str]:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(output)
        command = [
            str(self.executable),
            "-cs" if srgb else "-cl",
            str(source),
            str(output),
            f"{footprint[0]}x{footprint[1]}",
            f"-{preset}",
            "-j",
            str(self.threads),
        ]
        if target_psnr is not None:
            command.extend(["-dbtarget", str(target_psnr)])
        started = time.perf_counter()
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, env=environment
        )
        elapsed = time.perf_counter() - started
        return ASTCFile.read(output), elapsed, result.stdout

    def decode(self, source: Path, output: Path, srgb: bool = False) -> float:
        if output.exists():
            raise FileExistsError(output)
        started = time.perf_counter()
        subprocess.run(
            [str(self.executable), "-ds" if srgb else "-dl", str(source), str(output)],
            capture_output=True,
            text=True,
            check=True,
        )
        return time.perf_counter() - started

    @staticmethod
    def psnr_rgb(reference: Path, decoded: Path) -> float:
        """Conventional byte-domain RGB MSE, separate from Unity's channel averaging."""
        return ASTCEncoder._psnr(reference, decoded, "RGB")

    @staticmethod
    def psnr_rgba(reference: Path, decoded: Path) -> float:
        """Byte-domain RGBA MSE, matching the reference CLI's expanded PNG channels."""
        return ASTCEncoder._psnr(reference, decoded, "RGBA")

    @staticmethod
    def _psnr(reference: Path, decoded: Path, mode: Literal["RGB", "RGBA"]) -> float:
        with Image.open(reference) as image:
            original = np.asarray(image.convert(mode), dtype=np.float64)
        with Image.open(decoded) as image:
            reconstructed = np.asarray(image.convert(mode), dtype=np.float64)
        if original.shape != reconstructed.shape:
            raise ValueError("Reference and decoded dimensions differ")
        mse = float(np.mean((original - reconstructed) ** 2))
        return float("inf") if mse == 0 else 10 * math.log10(255**2 / mse)
