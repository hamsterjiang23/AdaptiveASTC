"""Validate complete candidate grids before reuse or training-corpus assembly."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCFile
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class UnityCandidateArchive:
    @staticmethod
    def verify(
        report: Path, references: list[JsonDict], config_path: Path
    ) -> tuple[list[JsonDict], JsonDict]:
        config = ArtifactStore.read_json(config_path)
        config_sha = ArtifactStore.sha256_file(config_path)
        public = ArtifactStore.read_json(report)
        output = Path(config["output"]).resolve()
        raw_path = output / "receipt.json"
        if (
            public["status"] != "passed"
            or public["test_opened"]
            or public["config"] != config
            or public["config_sha256"] != config_sha
            or Path(public["raw_receipt"]).resolve() != raw_path
            or ArtifactStore.sha256_file(raw_path) != public["raw_receipt_sha256"]
        ):
            raise ValueError("Candidate summary identity or raw receipt changed")
        raw = ArtifactStore.read_json(raw_path)
        if (
            raw["status"] != "passed"
            or raw["config"] != config
            or raw["test_opened"]
            or raw["config_sha256"] != config_sha
        ):
            raise ValueError("Candidate run did not complete the frozen development config")
        if len(raw["rows"]) != len(references) or len(config["items"]) != len(references):
            raise ValueError("Candidate grid does not cover the entire reference batch")
        if public["rows"] != [
            {key: value for key, value in row.items() if key != "candidates"} for row in raw["rows"]
        ]:
            raise ValueError("Candidate public and raw rows differ")
        expected_grid = [
            (block, preset)
            for block in UnityASTCBackend.BLOCKS
            for preset in UnityASTCBackend.PRESETS
        ]
        assembled = []
        for index, (row, reference, item) in enumerate(
            zip(raw["rows"], references, config["items"], strict=True)
        ):
            if (
                row["index"] != index
                or item["index"] != index
                or row["path"] != reference["path"]
                or item["path"] != reference["path"]
                or row["original_selection"] != reference["selection"]
                or row["metadata"] != item
                or not row["selected_payload_and_decode_match"]
                or row["candidate_count"] != 20
            ):
                raise ValueError("Candidate row differs from its original reference or choice")
            folder = output / f"{index:05d}"
            candidates_path = folder / "candidates.json"
            if ArtifactStore.sha256_file(candidates_path) != row["candidate_receipt_sha256"]:
                raise ValueError("Candidate receipt changed")
            candidates: list[JsonDict] = json.loads(candidates_path.read_text("utf-8"))
            if not isinstance(candidates, list) or not all(isinstance(c, dict) for c in candidates):
                raise ValueError("Candidate receipt must contain a list of records")
            if (
                candidates != row["candidates"]
                or [(c["block"], c["preset"]) for c in candidates] != expected_grid
            ):
                raise ValueError("Candidate grid is missing, duplicated or reordered")
            selected = reference["selection"]
            original_count = 0
            for candidate in candidates:
                block, preset = candidate["block"], candidate["preset"]
                name = f"{block}x{block}_{preset}"
                astc_path, png_path = folder / f"{name}.astc", folder / f"{name}.png"
                for path, key in [(astc_path, "astc_sha256"), (png_path, "decoded_png_sha256")]:
                    if ArtifactStore.sha256_file(path) != candidate[key]:
                        raise ValueError("Candidate ASTC or decoded PNG changed")
                astc = ASTCFile.read(astc_path)
                if (
                    (astc.width, astc.height, astc.depth)
                    != (reference["width"], reference["height"], 1)
                    or astc.footprint != (block, block)
                    or astc.payload_bytes != candidate["payload_bytes"]
                ):
                    raise ValueError(
                        "Candidate ASTC dimensions, footprint or real byte count differ"
                    )
                metrics = candidate["metrics"]
                required = ["psnr", "black_pixel_ratio"]
                required += (
                    ["normal_mean_deg", "normal_p95_deg"]
                    if item["is_normal"]
                    else (["ms_ssim_db"] if reference["actual_options"]["profile"] == 0 else [])
                )
                if any(
                    type(metrics[key]) not in {int, float} or not math.isfinite(metrics[key])
                    for key in required
                ):
                    raise ValueError("Candidate quality targets are missing or nonfinite")
                expected_mips = item["mip_count"] if item["is_normal"] else 1
                if (
                    type(expected_mips) is not int
                    or not 1 <= expected_mips <= 4
                    or type(metrics["mip_count"]) is not int
                    or metrics["need_alpha"] is not item["need_alpha"]
                    or metrics["mip_count"] != expected_mips
                ):
                    raise ValueError("Candidate metric Alpha or mip scope changed")
                if type(candidate["measured_in_original_search"]) is not bool:
                    raise ValueError("Candidate original-coverage flag must be boolean")
                original_count += candidate["measured_in_original_search"]
                with Image.open(png_path) as decoded:
                    if (
                        decoded.size != (reference["width"], reference["height"])
                        or decoded.mode != "RGBA"
                    ):
                        raise ValueError("Decoded candidate shape or channels differ")
                    if (f"{block}x{block}", preset) == (selected["block_size"], selected["preset"]):
                        source_folder = (
                            Path(reference["capture_directory"])
                            / f"{reference['capture_index']:05d}"
                        )
                        if astc_path.read_bytes() != (source_folder / "unity.astc").read_bytes():
                            raise ValueError("Candidate winner differs from original complete ASTC")
                        with Image.open(source_folder / "unity-native.png") as original_decoded:
                            if not np.array_equal(
                                np.asarray(decoded),
                                np.asarray(original_decoded.convert("RGBA"))[::-1],
                            ):
                                raise ValueError(
                                    "Candidate winner PNG orientation or pixels differ"
                                )
            if (
                original_count != row["original_search_candidates"]
                or original_count != row["native_metric_comparisons"]
                or row["new_candidates"] != 20 - original_count
            ):
                raise ValueError("Candidate original/new coverage accounting changed")
            assembled.append(
                {
                    **reference,
                    "candidate_directory": str(folder),
                    "candidate_receipt_sha256": row["candidate_receipt_sha256"],
                    "candidate_report_sha256": ArtifactStore.sha256_file(report),
                }
            )
        return assembled, {
            "images": len(assembled),
            "candidates": 20 * len(assembled),
            "new_candidates": sum(row["new_candidates"] for row in raw["rows"]),
            "original_candidates": sum(row["original_search_candidates"] for row in raw["rows"]),
            "normal_images": sum(item["is_normal"] for item in config["items"]),
            "report": str(report),
            "report_sha256": ArtifactStore.sha256_file(report),
            "raw_receipt_sha256": public["raw_receipt_sha256"],
            "wall_seconds": raw["wall_seconds"],
            "cost": {
                key: sum(row["cost"][key] for row in raw["rows"])
                for key in ["encode_seconds", "decode_seconds", "quality_seconds"]
            },
        }
