"""Archive and remeasure already encoded Unity normal candidates without re-encoding."""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCFile
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import (
    UnityASTCBackend,
    UnitySupplementalCapture,
)


class UnityNormalCandidateAudit:
    def __init__(self, config: Path) -> None:
        self.config_path = config
        self.config = ArtifactStore.read_json(config)

    @staticmethod
    def table(text: str) -> tuple[list[JsonDict], float, float]:
        thresholds = re.search(
            r"Target Normal Angular .*mean<=([\d.]+) deg, p95<=([\d.]+) deg", text
        )
        if thresholds is None:
            raise ValueError("Native normal thresholds are missing")
        matches = re.findall(
            r"^\s*(\d+x\d+)\s*\|\s*(\w+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)"
            r"\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([^\r\n]+)",
            text,
            re.MULTILINE,
        )
        expected = [
            (f"{block}x{block}", preset)
            for block in UnityASTCBackend.BLOCKS
            for preset in UnityASTCBackend.PRESETS
        ]
        if [(row[0], row[1]) for row in matches] != expected:
            raise ValueError("Normal audit requires all20 original candidates in native order")
        return (
            [
                {
                    "block_size": row[0],
                    "preset": row[1],
                    "psnr": float(row[2]),
                    "ms_ssim_db": float(row[3]),
                    "normal_mean_deg": float(row[4]),
                    "normal_p95_deg": float(row[5]),
                    "payload_kib": float(row[6]),
                    "status": row[7].strip(),
                }
                for row in matches
            ],
            float(thresholds[1]),
            float(thresholds[2]),
        )

    @staticmethod
    def native_status_valid(status: str) -> bool:
        base = status.removesuffix(" [BEST]")
        if base not in {"Valid", "Below Target"}:
            raise ValueError(f"Unknown native candidate status: {status}")
        return base == "Valid"

    @staticmethod
    def native_thresholds(
        policy: JsonDict, configured: JsonDict, reported: tuple[float, float]
    ) -> tuple[float, float]:
        result = []
        for key, configured_key, rounded in zip(
            ["targetNormalMeanDeg", "targetNormalP95Deg"],
            ["normal_mean", "normal_p95"],
            reported,
            strict=True,
        ):
            threshold = float(np.float32(policy[key]))
            if (
                not np.isfinite(threshold)
                or threshold < 0
                or threshold != float(np.float32(configured[configured_key]))
                or float(f"{threshold:.2f}") != rounded
            ):
                raise ValueError("Native normal thresholds disagree with capture/report")
            result.append(threshold)
        return result[0], result[1]

    def run(self) -> JsonDict:
        config = self.config
        archive, capture = Path(config["capture"]), Path(config["capture_run"])
        receipt = ArtifactStore.read_json(archive / "receipt.json")
        if (
            receipt["status"] != "passed"
            or ArtifactStore.sha256_file(archive / "receipt.json")
            != config["capture_receipt_sha256"]
        ):
            raise ValueError("Frozen reference capture changed")
        manifest = ArtifactStore.read_json(archive / "manifest.json")
        if ArtifactStore.sha256_file(archive / "manifest.json") != receipt[
            "manifest_sha256"
        ] or not set(manifest["splits"]).issubset({"train", "validation"}):
            raise ValueError("Normal audit requires frozen development references")
        provenance = UnitySupplementalCapture.verify_capture_provenance(config, receipt)
        options = UnitySupplementalCapture.read_actual_options(config, receipt)
        index = config["index"]
        if type(index) is not int or not 0 <= index < len(receipt["rows"]):
            raise ValueError("Normal audit index outside reference cohort")
        reference, observed = receipt["rows"][index], options["rows"][index]
        if (
            reference["path"] != config["path"]
            or reference["texture_type"] != "NormalMap"
            or observed["profile"] != 1
            or observed["channel"] != 4
        ):
            raise ValueError("Normal audit requires observed Linear LDR RGBA32 NormalMap")
        identity = ArtifactStore.read_json(capture / "identity.json")
        project = Path(identity["project"])
        UnitySearchBaseline(
            project, project, Path(identity["editor"]), Path(identity["manifest"])
        ).require_project_closed()
        imports_path = capture / f"{config['capture_phase']}-imports.jsonl"
        imports = UnitySearchBaseline._read_lines(imports_path)
        if len(imports) != len(receipt["rows"]) or any(
            UnitySearchBaseline._asset_key(imported["asset"])
            != UnitySearchBaseline._asset_key(row["path"])
            for imported, row in zip(imports, receipt["rows"], strict=True)
        ):
            raise ValueError("Import identities changed")
        imported = imports[index]
        if (
            not imported["success"]
            or imported["mipmaps"]
            or imported["texture_type"] != "NormalMap"
            or imported["srgb"]
        ):
            raise ValueError("Current normal audit supports captured mip0-only Linear NormalMap")
        debug = Path(imported["reference_directory"]).resolve()
        if not debug.is_relative_to((project / "ASTC_Cache").resolve()):
            raise ValueError("Native candidate directory escaped project cache")
        folder = archive / f"{index:05d}"
        for name in ["original.png", "unity.astc", "unity-native.png", "parameter_test_report.txt"]:
            if ArtifactStore.sha256_file(folder / name) != reference["artifacts_sha256"][name]:
                raise ValueError("Archived reference artifact changed")
        for name in ["original.png", "parameter_test_report.txt"]:
            if ArtifactStore.sha256_file(debug / name) != reference["artifacts_sha256"][name]:
                raise ValueError("Live candidate directory belongs to a different capture")
        table, mean_gate, p95_gate = self.table(
            (folder / "parameter_test_report.txt").read_text(encoding="utf-8-sig")
        )
        phase_config = ArtifactStore.read_json(capture / f"{config['capture_phase']}-config.json")
        cache_directory = (project / phase_config["cacheDirectory"]).resolve()
        if not cache_directory.is_relative_to((project / "ASTC_Cache").resolve()):
            raise ValueError("Native parameter cache escaped project cache")
        cache_path = cache_directory / "parameter_cache_detail.jsonl"
        policy = UnitySearchBaseline.read_parameter_cache(cache_path)[0]["tableConfig"]
        policy_binding = {
            "tableConfig": policy,
            "source_sha256": {
                str(path): ArtifactStore.sha256_file(path)
                for path in [cache_path, cache_path.with_suffix(".json")]
                if path.exists()
            },
        }
        mean_gate, p95_gate = self.native_thresholds(
            policy, identity["quality"], (mean_gate, p95_gate)
        )
        if (
            sorted([[row["block_size"], row["preset"]] for row in table])
            != observed["candidate_keys"]
        ):
            raise ValueError("Original table and observed callbacks differ")
        with Image.open(folder / "original.png") as image:
            original = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
        if hashlib.sha256(original.tobytes()).hexdigest() != observed["rgba_sha256"]:
            raise ValueError("Normal reference bytes differ from actual encoder input")
        height, width = original.shape[:2]
        output = Path(config["output"])
        if output.exists() and any(output.iterdir()):
            raise FileExistsError("Use a new native audit identity")
        if Path(config["report"]).exists():
            raise FileExistsError("Use a new native audit report")
        backend = UnityASTCBackend(Path(config["encoder_dll"]), config["encoder_dll_sha256"])
        quality = UnityQuality(Path(config["quality_build_receipt"]))
        output.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        state: JsonDict = {
            "status": "running",
            "config": config,
            "config_sha256": ArtifactStore.sha256_file(self.config_path),
            "capture_binding": provenance,
            "input_options": observed,
            "imports_sha256": ArtifactStore.sha256_file(imports_path),
            "quality_build": quality.receipt,
            "native_thresholds": {"mean": mean_gate, "p95": p95_gate},
            "native_policy_binding": policy_binding,
            "native_mip_evidence": (
                "import mipmaps=false; mip_count1 checked against original angular metrics"
            ),
            "source_files_sha256": {
                str(path): ArtifactStore.sha256_file(path)
                for path in [
                    Path(__file__),
                    Path(__file__).with_name("supplement.py"),
                    Path(__file__).with_name("quality.py"),
                ]
            },
            "original_selection": reference["selection"],
            "rows": [],
            "encoded_candidates": 0,
            "scope": (
                "Archive original normal candidates; fresh decode and metrics only; "
                "no search or label changes"
            ),
            "test_opened": False,
        }
        try:
            ArtifactStore.write_json(output / "native-policy.json", policy_binding)
            shutil.copy2(folder / "original.png", output / "original.png")
            shutil.copy2(folder / "parameter_test_report.txt", output / "parameter_test_report.txt")
            for expected in table:
                prefix = f"{expected['block_size']}_{expected['preset']}"
                for suffix in [".astc", "_decompressed.png"]:
                    shutil.copy2(debug / f"{prefix}{suffix}", output / f"{prefix}{suffix}")
                astc_path, png_path = (
                    output / f"{prefix}.astc",
                    output / f"{prefix}_decompressed.png",
                )
                astc = ASTCFile.read(astc_path)
                block = int(expected["block_size"].split("x")[0])
                if (astc.width, astc.height, astc.depth, astc.footprint) != (
                    width,
                    height,
                    1,
                    (block, block),
                ):
                    raise ValueError("Original candidate ASTC header differs")
                if abs(astc.payload_bytes / 1024 - expected["payload_kib"]) > 0.00501:
                    raise ValueError("Original candidate payload differs from rounded report")
                decoded, decode_seconds = backend.decode_payload(
                    astc_path.read_bytes()[16:], width, height, block, srgb=False
                )
                with Image.open(png_path) as image:
                    if not np.array_equal(decoded, np.asarray(image.convert("RGBA"))):
                        raise ValueError("Fresh decode differs from original candidate PNG")
                metric_started = time.perf_counter()
                metrics = quality.measure(
                    original,
                    decoded,
                    need_alpha=observed["need_alpha"],
                    compute_ssim=False,
                    normal=True,
                    mip_count=1,
                )
                metric_seconds = time.perf_counter() - metric_started
                differences = {
                    name: abs(metrics[name] - expected[name])
                    for name in ["psnr", "normal_mean_deg", "normal_p95_deg"]
                }
                if max(differences.values()) > 0.00501:
                    raise ValueError(f"Original normal metrics differ: {prefix}: {differences}")
                valid = (
                    metrics["normal_mean_deg"] <= mean_gate
                    and metrics["normal_p95_deg"] <= p95_gate
                )
                if self.native_status_valid(expected["status"]) != valid:
                    raise ValueError("Normal angular gate differs from native report")
                state["rows"].append(
                    {
                        **expected,
                        "metrics": metrics,
                        "differences": differences,
                        "valid": valid,
                        "payload_bytes": astc.payload_bytes,
                        "decode_seconds": decode_seconds,
                        "quality_seconds": metric_seconds,
                        "astc_sha256": ArtifactStore.sha256_file(astc_path),
                        "native_png_sha256": ArtifactStore.sha256_file(png_path),
                    }
                )
                ArtifactStore.write_json(output / "receipt.json", state)
            winner = reference["selection"]
            selected_path = output / f"{winner['block_size']}_{winner['preset']}.astc"
            if (
                ArtifactStore.sha256_file(selected_path)
                != reference["artifacts_sha256"]["unity.astc"]
            ):
                raise ValueError("Selected payload differs from sealed native winner")
            state["quality_passing_candidates"] = sum(row["valid"] for row in state["rows"])
            if not state["quality_passing_candidates"]:
                best = max(state["rows"], key=lambda row: row["metrics"]["psnr"])
                if (best["block_size"], best["preset"]) != (winner["block_size"], winner["preset"]):
                    raise ValueError("Highest-PSNR fallback differs from native winner")
            state["status"] = "passed"
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            ArtifactStore.write_json(output / "receipt.json", state)
            ArtifactStore.write_json(
                Path(config["report"]),
                {**state, "raw_receipt_sha256": ArtifactStore.sha256_file(output / "receipt.json")},
            )
        return state
