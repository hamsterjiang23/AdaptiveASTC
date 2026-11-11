"""Build and invoke the engine's unchanged PSNR, MS-SSIM and normal metrics."""

from __future__ import annotations

import ctypes
import hashlib
import subprocess
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore


class UnityQualityBuild:
    START = "    static float CalculatePSNR("
    END = "    // Prepare original image data:"

    @staticmethod
    def extract(source: str) -> str:
        if source.count(UnityQualityBuild.START) != 1 or source.count(UnityQualityBuild.END) != 1:
            raise ValueError("Unity metric extraction boundaries changed")
        start = source.index(UnityQualityBuild.START)
        end = source.index(UnityQualityBuild.END, start)
        result = source[start:end]
        for name in ["CalculateMSSSIMDb_Luma", "CalculateNormalAngularErrorMip0To3"]:
            if (
                f"static float {name}(" not in result
                and f"static NormalAngularResult {name}(" not in result
            ):
                raise ValueError(f"Required native metric missing: {name}")
        return result

    @staticmethod
    def build(engine_source: Path, output: Path) -> JsonDict:
        engine_source = engine_source.resolve()
        output = output.resolve()
        native = Path(__file__).with_name("native")
        source = engine_source.read_text(encoding="utf-8-sig")
        extracted = UnityQualityBuild.extract(source)
        prefix = (
            "#include <algorithm>\n#include <cmath>\n#include <utility>\n"
            "#include <vector>\nusing UInt8 = unsigned char;\n"
        )
        generated = prefix + extracted + (native / "quality_wrapper.cpp").read_text()
        binding = {
            "engine_source": str(engine_source),
            "engine_source_sha256": ArtifactStore.sha256_file(engine_source),
            "engine_first_line": source[: source.index(UnityQualityBuild.START)].count("\n") + 1,
            "engine_last_line": source[: source.index(UnityQualityBuild.END)].count("\n"),
            "extracted_sha256": hashlib.sha256(extracted.encode()).hexdigest(),
            "wrapper_sha256": ArtifactStore.sha256_file(native / "quality_wrapper.cpp"),
            "cmake_sha256": ArtifactStore.sha256_file(native / "CMakeLists.txt"),
            "arithmetic": "MSVC fp:precise; unchanged engine functions; parity checked separately",
        }
        receipt_path = output / "build-receipt.json"
        if receipt_path.exists():
            receipt = ArtifactStore.read_json(receipt_path)
            if (
                receipt["binding"] != binding
                or ArtifactStore.sha256_file(Path(receipt["dll"])) != receipt["dll_sha256"]
            ):
                raise ValueError("Native metric build identity changed")
            return receipt
        if output.exists() and any(output.iterdir()):
            raise FileExistsError("Use a new metric build identity; retain failed build logs")
        output.mkdir(parents=True, exist_ok=True)
        (output / "metrics.cpp").write_text(generated, encoding="utf-8")
        commands = [
            [
                "cmake",
                "-S",
                str(native),
                "-B",
                str(output / "build"),
                "-G",
                "Visual Studio 17 2022",
                "-A",
                "x64",
                f"-DMETRICS_SOURCE={(output / 'metrics.cpp').as_posix()}",
            ],
            ["cmake", "--build", str(output / "build"), "--config", "Release", "--parallel", "1"],
        ]
        for index, command in enumerate(commands):
            with (output / f"build-{index}.log").open("wb") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        dll = output / "build/Release/unity_astc_quality.dll"
        receipt = {
            "status": "passed",
            "binding": binding,
            "commands": commands,
            "dll": str(dll),
            "dll_sha256": ArtifactStore.sha256_file(dll),
            "generated_sha256": ArtifactStore.sha256_file(output / "metrics.cpp"),
        }
        ArtifactStore.write_json(receipt_path, receipt)
        return receipt


class UnityQuality:
    def __init__(self, build_receipt: Path) -> None:
        self.receipt = ArtifactStore.read_json(build_receipt)
        dll = Path(self.receipt["dll"])
        if (
            self.receipt["status"] != "passed"
            or ArtifactStore.sha256_file(dll) != self.receipt["dll_sha256"]
        ):
            raise ValueError("Native metric DLL identity changed")
        self.library = ctypes.CDLL(str(dll))
        self.function = self.library.unity_astc_quality
        self.function.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_bool,
            ctypes.c_bool,
            ctypes.c_bool,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        self.function.restype = ctypes.c_int

    def measure(
        self,
        original: NDArray[np.uint8],
        decoded: NDArray[np.uint8],
        *,
        need_alpha: bool,
        compute_ssim: bool,
        normal: bool = False,
        mip_count: int = 1,
    ) -> JsonDict:
        if (
            original.dtype != np.uint8
            or original.ndim != 3
            or original.shape[2] != 4
            or decoded.dtype != np.uint8
            or decoded.shape != original.shape
        ):
            raise ValueError("Native metrics require equal RGBA8 images")
        if not 1 <= mip_count <= 4:
            raise ValueError("Normal metrics support mip0 through mip3")
        original = np.ascontiguousarray(original)
        decoded = np.ascontiguousarray(decoded)
        height, width = original.shape[:2]
        output = np.zeros(5, dtype=np.float32)
        status = self.function(
            original.ctypes.data,
            decoded.ctypes.data,
            width,
            height,
            not need_alpha,
            compute_ssim,
            normal,
            mip_count,
            output.ctypes.data,
        )
        if status or not np.isfinite(output).all():
            raise RuntimeError(f"Native quality failed: {status}")
        return {
            "psnr": float(output[0]),
            "black_pixel_ratio": float(output[1]),
            "ms_ssim_db": float(output[2]) if compute_ssim else None,
            "normal_mean_deg": float(output[3]) if normal else None,
            "normal_p95_deg": float(output[4]) if normal else None,
            "mip_count": mip_count,
            "need_alpha": need_alpha,
        }
