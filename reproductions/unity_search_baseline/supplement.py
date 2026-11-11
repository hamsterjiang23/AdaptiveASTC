"""Offline candidate measurements, separate from original Unity search and labels."""

from __future__ import annotations

import ctypes
import re
import time
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCFile
from reproductions.unity_search_baseline.quality import UnityQuality


class UnityASTCBackend:
    PRESETS = {"fastest": 0, "fast": 10, "medium": 60, "thorough": 98, "exhaustive": 100}
    BLOCKS = (12, 10, 8, 6)

    def __init__(self, dll: Path, expected_sha256: str) -> None:
        if ArtifactStore.sha256_file(dll) != expected_sha256:
            raise ValueError("Unity encoder DLL differs from the frozen capture")
        self.library = ctypes.CDLL(str(dll.resolve()))
        self.encode_function = self.library.armastc_encode
        self.encode_function.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_float,
            ctypes.c_bool,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_bool,
            ctypes.c_char_p,
            ctypes.c_bool,
            ctypes.c_bool,
            ctypes.c_float,
            ctypes.c_int,
        ]
        self.encode_function.restype = None
        self.decode_function = self.library.armastc_decompress_from_memory
        self.decode_function.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_bool,
            ctypes.c_char_p,
            ctypes.c_bool,
        ]
        self.decode_function.restype = None

    def encode_decode(
        self, rgba: NDArray[np.uint8], block: int, preset: str, *, srgb: bool, need_alpha: bool
    ) -> tuple[bytes, NDArray[np.uint8], JsonDict]:
        if rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4:
            raise ValueError("Unity supplemental encoding requires RGBA8")
        height, width = rgba.shape[:2]
        if (
            min(width, height) < 1
            or width * height > 536870911
            or block not in self.BLOCKS
            or preset not in self.PRESETS
        ):
            raise ValueError("Invalid image dimensions or candidate")
        reference = np.array(rgba, dtype=np.uint8, order="C", copy=True)
        payload = np.zeros(
            ((width + block - 1) // block) * ((height + block - 1) // block) * 16, dtype=np.uint8
        )
        profile = 0 if srgb else 1
        started = time.perf_counter()
        self.encode_function(
            reference.ctypes.data,
            width,
            height,
            self.PRESETS[preset],
            False,
            block,
            payload.ctypes.data,
            profile,
            False,
            None,
            need_alpha,
            False,
            0.0,
            0,
        )
        encode_seconds = time.perf_counter() - started
        if not payload.any():
            raise RuntimeError("Unity encoder returned an empty payload")
        decoded = np.zeros((height, width, 4), dtype=np.uint8)
        started = time.perf_counter()
        self.decode_function(
            payload.ctypes.data,
            payload.size,
            width,
            height,
            block,
            decoded.ctypes.data,
            profile,
            False,
            None,
            False,
        )
        decode_seconds = time.perf_counter() - started
        return (
            payload.tobytes(),
            decoded,
            {
                "encode_seconds": encode_seconds,
                "decode_seconds": decode_seconds,
            },
        )

    @staticmethod
    def container(payload: bytes, width: int, height: int, block: int) -> bytes:
        return (
            bytes.fromhex("13aba15c")
            + bytes([block, block, 1])
            + width.to_bytes(3, "little")
            + height.to_bytes(3, "little")
            + (1).to_bytes(3, "little")
            + payload
        )


class UnitySupplementalCapture:
    def __init__(self, config: Path) -> None:
        self.config_path = config
        self.config = ArtifactStore.read_json(config)

    @staticmethod
    def verify_capture_provenance(config: JsonDict, receipt: JsonDict) -> JsonDict:
        run = Path(config["capture_run"])
        phase = config["capture_phase"]
        if not phase or Path(phase).name != phase or phase in {".", ".."}:
            raise ValueError("Capture phase must be one file-name component")
        lock_path = run / "protocol-lock.json"
        protocol_sha = ArtifactStore.sha256_file(lock_path)
        if protocol_sha != receipt["capture_provenance"]["protocol_sha256"]:
            raise ValueError("Reference capture belongs to a different native protocol")
        lock = ArtifactStore.read_json(lock_path)
        for name in ["identity.json", f"{phase}-config.json"]:
            if ArtifactStore.sha256_file(run / name) != lock[name]:
                raise ValueError("Frozen capture identity or phase changed")
        identity = ArtifactStore.read_json(run / "identity.json")
        expected_dll = identity["encoder_dlls"]["astcenc-avx2-shared.dll"]
        if config["encoder_dll_sha256"] != expected_dll:
            raise ValueError("Supplemental encoder is not the original capture DLL")
        original_config = ArtifactStore.read_json(run / f"{phase}-config.json")
        expected_paths = [
            row["path"].replace("\\", "/").casefold() for row in original_config["assets"]
        ]
        actual_paths = [row["path"].replace("\\", "/").casefold() for row in receipt["rows"]]
        if not original_config.get("captureReferences") or expected_paths != actual_paths:
            raise ValueError("Reference rows do not match the frozen native capture cohort")
        return {
            "protocol_sha256": protocol_sha,
            "identity_sha256": lock["identity.json"],
            "phase_config_sha256": lock[f"{phase}-config.json"],
            "encoder_dll_sha256": expected_dll,
        }

    @staticmethod
    def search_table(text: str) -> dict[tuple[str, str], tuple[float, float]]:
        rows = re.findall(
            r"^\s*(\d+x\d+)\s*\|\s*(\w+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|",
            text,
            re.MULTILINE,
        )
        if not rows or len({(r[0], r[1]) for r in rows}) != len(rows):
            raise ValueError("Native search table is empty or duplicated")
        return {(block, preset): (float(psnr), float(ssim)) for block, preset, psnr, ssim in rows}

    def run(self) -> JsonDict:
        config = self.config
        archive = Path(config["capture"])
        source_receipt = ArtifactStore.read_json(archive / "receipt.json")
        if (
            source_receipt["status"] != "passed"
            or ArtifactStore.sha256_file(archive / "receipt.json")
            != config["capture_receipt_sha256"]
        ):
            raise ValueError("Frozen Unity reference capture changed")
        manifest_path = archive / "manifest.json"
        if ArtifactStore.sha256_file(manifest_path) != source_receipt["manifest_sha256"]:
            raise ValueError("Frozen Unity reference manifest changed")
        source_manifest = ArtifactStore.read_json(manifest_path)
        if not set(source_manifest["splits"]).issubset({"train", "validation"}):
            raise ValueError("Development supplemental collection excludes calibration and test")
        provenance = self.verify_capture_provenance(config, source_receipt)
        indexes = [item["index"] for item in config["items"]]
        if (
            not indexes
            or len(set(indexes)) != len(indexes)
            or any(
                type(index) is not int or index < 0 or index >= len(source_receipt["rows"])
                for index in indexes
            )
        ):
            raise ValueError("Require unique, nonnegative capture indexes within the frozen cohort")
        output = Path(config["output"])
        if output.exists() and any(output.iterdir()):
            raise FileExistsError("Use a new supplemental identity; keep prior attempts")
        backend = UnityASTCBackend(Path(config["encoder_dll"]), config["encoder_dll_sha256"])
        quality = UnityQuality(Path(config["quality_build_receipt"]))
        output.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        state = {
            "status": "running",
            "config": config,
            "config_sha256": ArtifactStore.sha256_file(self.config_path),
            "quality_build": quality.receipt,
            "capture_binding": provenance,
            "source_files_sha256": {
                str(path): ArtifactStore.sha256_file(path)
                for path in [Path(__file__), Path(__file__).with_name("quality.py")]
            },
            "rows": [],
            "test_opened": False,
        }
        try:
            for item in config["items"]:
                state["rows"].append(
                    self.collect_image(archive, source_receipt, item, output, backend, quality)
                )
                ArtifactStore.write_json(output / "receipt.json", state)
        except BaseException as error:
            state.update(
                status="failed", error=repr(error), wall_seconds=time.perf_counter() - started
            )
            ArtifactStore.write_json(output / "receipt.json", state)
            raise
        state.update(status="passed", wall_seconds=time.perf_counter() - started)
        ArtifactStore.write_json(output / "receipt.json", state)
        public = {
            **state,
            "rows": [{k: v for k, v in row.items() if k != "candidates"} for row in state["rows"]],
            "raw_receipt": str(output / "receipt.json"),
            "raw_receipt_sha256": ArtifactStore.sha256_file(output / "receipt.json"),
        }
        ArtifactStore.write_json(Path(config["report"]), public)
        return public

    def collect_image(
        self,
        archive: Path,
        receipt: JsonDict,
        item: JsonDict,
        output: Path,
        backend: UnityASTCBackend,
        quality: UnityQuality,
    ) -> JsonDict:
        index = item["index"]
        row = receipt["rows"][index]
        if row["path"] != item["path"]:
            raise ValueError("Supplemental sample identity changed")
        if row["texture_type"] != "Default" or item["is_hdr"] or item["is_normal"]:
            raise ValueError("Current supplemental pilot supports LDR Default textures only")
        if type(item["need_alpha"]) is not bool or not item["metadata_source"]:
            raise ValueError("Explicit Alpha contract and provenance required")
        folder = archive / f"{index:05d}"
        for name in ["original.png", "unity.astc", "unity-native.png", "parameter_test_report.txt"]:
            if ArtifactStore.sha256_file(folder / name) != row["artifacts_sha256"][name]:
                raise ValueError("Frozen Unity reference artifact changed")
        with Image.open(folder / "original.png") as image:
            rgba = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
        height, width = rgba.shape[:2]
        expected = ASTCFile.read(folder / "unity.astc")
        if (width, height) != (row["width"], row["height"]) or (width, height, 1) != (
            expected.width,
            expected.height,
            expected.depth,
        ):
            raise ValueError("Reference and native ASTC dimensions differ")
        selected = row["selection"]
        best_key = (selected["block_size"], selected["preset"])
        table = self.search_table(
            (folder / "parameter_test_report.txt").read_text(encoding="utf-8-sig")
        )
        results = []
        destination = output / f"{index:05d}"
        destination.mkdir()
        winner_matches = False
        for block in backend.BLOCKS:
            for preset in backend.PRESETS:
                payload, decoded, timings = backend.encode_decode(
                    rgba, block, preset, srgb=row["srgb"], need_alpha=item["need_alpha"]
                )
                measure_started = time.perf_counter()
                metrics = quality.measure(
                    rgba, decoded, need_alpha=item["need_alpha"], compute_ssim=row["srgb"]
                )
                timings["quality_seconds"] = time.perf_counter() - measure_started
                name = f"{block}x{block}_{preset}"
                astc_path = destination / f"{name}.astc"
                astc_path.write_bytes(backend.container(payload, width, height, block))
                ASTCFile.read(astc_path)
                png_path = destination / f"{name}.png"
                Image.fromarray(decoded[::-1]).save(png_path)
                key = (f"{block}x{block}", preset)
                measured_in_search = key in table
                if measured_in_search:
                    native_psnr, native_ssim = table[key]
                    if abs(metrics["psnr"] - native_psnr) > 0.00501 or (
                        native_ssim > 0 and abs(metrics["ms_ssim_db"] - native_ssim) > 0.00501
                    ):
                        raise ValueError(
                            f"Supplemental candidate disagrees with original native metrics: {name}"
                        )
                if key == best_key:
                    winner_matches = (folder / "unity.astc").read_bytes()[16:] == payload
                    if not winner_matches or expected.payload_bytes != len(payload):
                        raise ValueError(
                            "Selected candidate payload did not reproduce original Unity output"
                        )
                    with Image.open(folder / "unity-native.png") as image:
                        if not np.array_equal(np.asarray(image.convert("RGBA")), decoded):
                            raise ValueError(
                                "Selected candidate decoding differs from original Unity output"
                            )
                results.append(
                    {
                        "block": block,
                        "preset": preset,
                        "payload_bytes": len(payload),
                        "metrics": metrics,
                        "timings": timings,
                        "measured_in_original_search": measured_in_search,
                        "astc_sha256": ArtifactStore.sha256_file(astc_path),
                        "decoded_png_sha256": ArtifactStore.sha256_file(png_path),
                    }
                )
                ArtifactStore.write_json(destination / "candidates.json", results)
        if not winner_matches or sum(r["measured_in_original_search"] for r in results) != len(
            table
        ):
            raise ValueError("Native search candidate coverage could not be reproduced")
        result = {
            "index": index,
            "path": row["path"],
            "metadata": item,
            "original_selection": selected,
            "candidate_count": len(results),
            "original_search_candidates": len(table),
            "new_candidates": len(results) - len(table),
            "selected_payload_and_decode_match": winner_matches,
            "native_metric_comparisons": len(table),
            "native_record_tolerance_db": 0.00501,
            "cost": {
                name: sum(r["timings"][name] for r in results)
                for name in ["encode_seconds", "decode_seconds", "quality_seconds"]
            },
            "candidates": results,
            "candidate_receipt_sha256": ArtifactStore.sha256_file(destination / "candidates.json"),
        }
        ArtifactStore.write_json(destination / "receipt.json", result)
        return result
