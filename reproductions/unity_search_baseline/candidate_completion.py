"""Complete archived color and mip0 normal candidates without opening Unity."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCFile
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import (
    UnityASTCBackend,
    UnitySupplementalCapture,
)


class UnityCandidateCompletion(UnitySupplementalCapture):
    """Keep original choices; add complete measurements under captured options."""

    def __init__(self, config: Path) -> None:
        super().__init__(config)
        if self.config["completion_source_sha256"] != ArtifactStore.sha256_file(Path(__file__)):
            raise ValueError("Candidate completion implementation changed")

    @staticmethod
    def normal_table(text: str) -> dict[tuple[str, str], tuple[float, float]]:
        matches = re.findall(
            r"^\s*(\d+x\d+)\s*\|\s*(\w+)\s*\|\s*[\d.]+\s*\|\s*[\d.]+"
            r"\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|",
            text,
            re.MULTILINE,
        )
        rows = {(block, preset): (float(mean), float(p95)) for block, preset, mean, p95 in matches}
        if not rows or len(rows) != len(matches):
            raise ValueError("Normal candidate metrics are absent or duplicated")
        if set(rows) != set(UnitySupplementalCapture.search_table(text)):
            raise ValueError("Normal and PSNR candidate coverage differ")
        return rows

    @staticmethod
    def verify_normal_imports(config: JsonDict, receipt: JsonDict) -> None:
        path = Path(config["capture_run"]) / f"{config['capture_phase']}-imports.jsonl"
        if ArtifactStore.sha256_file(path) != config["imports_sha256"]:
            raise ValueError("Captured import metadata changed")
        imports = [json.loads(line) for line in path.read_text("utf-8-sig").splitlines() if line]
        if len(imports) != len(receipt["rows"]):
            raise ValueError("Import metadata does not cover the frozen cohort")
        for imported, reference in zip(imports, receipt["rows"], strict=True):
            if imported["asset"] != reference["path"] or not imported["success"]:
                raise ValueError("Import metadata identities or completion changed")
        for item in config["items"]:
            if not item["is_normal"]:
                continue
            imported = imports[item["index"]]
            if (
                imported["texture_type"] != "NormalMap"
                or imported["srgb"]
                or imported["mipmaps"] is not False
                or imported["texture_dimension"] != "Tex2D"
                or type(item.get("mip_count")) is not int
                or item["mip_count"] != 1
            ):
                raise ValueError("Normal completion requires captured mip0-only Linear Tex2D")

    @staticmethod
    def verify_actual_options(config: JsonDict, receipt: JsonDict) -> JsonDict:
        options = UnitySupplementalCapture.read_actual_options(config, receipt)
        color_items = []
        for item in config["items"]:
            reference = receipt["rows"][item["index"]]
            observed = options["rows"][item["index"]]
            if type(item["is_normal"]) is not bool or item["is_normal"] != (
                reference["texture_type"] == "NormalMap"
            ):
                raise ValueError("Normal target flag disagrees with captured texture usage")
            if not item["is_normal"]:
                color_items.append(item)
                continue
            if (
                item["path"] != reference["path"]
                or item["is_hdr"] is not False
                or type(item["need_alpha"]) is not bool
                or item["need_alpha"] is not observed["need_alpha"]
                or observed["profile"] != 1
                or observed["normal_pack"] is not False
                or observed["channel"] != 4
                or reference["srgb"]
                or not item["metadata_source"]
            ):
                raise ValueError("Normal completion disagrees with actual encoder options")
        binding = UnitySupplementalCapture.verify_actual_options(
            {**config, "items": color_items}, receipt
        )
        UnityCandidateCompletion.verify_normal_imports(config, receipt)
        return {
            **binding,
            "imports_sha256": config["imports_sha256"],
            "completion_source_sha256": config["completion_source_sha256"],
            "normal_scope": "Linear RGBA8, normal_pack=false, mip0 only",
        }

    def collect_image(
        self,
        archive: Path,
        receipt: JsonDict,
        item: JsonDict,
        output: Path,
        backend: UnityASTCBackend,
        quality: UnityQuality,
    ) -> JsonDict:
        if not item["is_normal"]:
            return super().collect_image(archive, receipt, item, output, backend, quality)
        index = item["index"]
        reference = receipt["rows"][index]
        folder = archive / f"{index:05d}"
        for name in ["original.png", "unity.astc", "unity-native.png", "parameter_test_report.txt"]:
            if ArtifactStore.sha256_file(folder / name) != reference["artifacts_sha256"][name]:
                raise ValueError("Frozen normal reference artifact changed")
        with Image.open(folder / "original.png") as image:
            original = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
        height, width = original.shape[:2]
        expected = ASTCFile.read(folder / "unity.astc")
        if (width, height) != (reference["width"], reference["height"]) or (
            expected.width,
            expected.height,
            expected.depth,
        ) != (width, height, 1):
            raise ValueError("Normal reference and ASTC dimensions differ")
        text = (folder / "parameter_test_report.txt").read_text("utf-8-sig")
        angles, psnr = self.normal_table(text), self.search_table(text)
        selection = reference["selection"]
        selected_key = selection["block_size"], selection["preset"]
        if expected.footprint != tuple(int(value) for value in selected_key[0].split("x")):
            raise ValueError("Original normal ASTC footprint differs from its selected label")
        results: list[JsonDict] = []
        destination = output / f"{index:05d}"
        destination.mkdir()
        winner_matches = False
        for block in backend.BLOCKS:
            for preset in backend.PRESETS:
                payload, decoded, timings = backend.encode_decode(
                    original, block, preset, srgb=False, need_alpha=item["need_alpha"]
                )
                started = time.perf_counter()
                metrics = quality.measure(
                    original,
                    decoded,
                    need_alpha=item["need_alpha"],
                    compute_ssim=False,
                    normal=True,
                    mip_count=1,
                )
                timings["quality_seconds"] = time.perf_counter() - started
                key = f"{block}x{block}", preset
                name = f"{key[0]}_{preset}"
                astc_path, png_path = destination / f"{name}.astc", destination / f"{name}.png"
                astc_path.write_bytes(backend.container(payload, width, height, block))
                ASTCFile.read(astc_path)
                Image.fromarray(decoded[::-1]).save(png_path)
                if key in angles:
                    expected_metrics = (psnr[key][0], *angles[key])
                    measured = (
                        metrics["psnr"],
                        metrics["normal_mean_deg"],
                        metrics["normal_p95_deg"],
                    )
                    if any(
                        abs(a - b) > 0.00501
                        for a, b in zip(measured, expected_metrics, strict=True)
                    ):
                        raise ValueError(
                            f"Normal candidate differs from original rounded metrics: {name}"
                        )
                if key == selected_key:
                    with Image.open(folder / "unity-native.png") as image:
                        winner_matches = np.array_equal(np.asarray(image.convert("RGBA")), decoded)
                    if (
                        not winner_matches
                        or (folder / "unity.astc").read_bytes() != astc_path.read_bytes()
                    ):
                        raise ValueError(
                            "Normal winner payload or decode differs from original search"
                        )
                results.append(
                    {
                        "block": block,
                        "preset": preset,
                        "payload_bytes": len(payload),
                        "metrics": metrics,
                        "timings": timings,
                        "measured_in_original_search": key in angles,
                        "astc_sha256": ArtifactStore.sha256_file(astc_path),
                        "decoded_png_sha256": ArtifactStore.sha256_file(png_path),
                    }
                )
                ArtifactStore.write_json(destination / "candidates.json", results)
        if not winner_matches or sum(row["measured_in_original_search"] for row in results) != len(
            angles
        ):
            raise ValueError("Original normal candidate coverage was not reproduced")
        result = {
            "index": index,
            "path": reference["path"],
            "metadata": item,
            "original_selection": selection,
            "candidate_count": len(results),
            "original_search_candidates": len(angles),
            "new_candidates": len(results) - len(angles),
            "selected_payload_and_decode_match": winner_matches,
            "native_metric_comparisons": len(angles),
            "native_record_tolerance_db": 0.00501,
            "cost": {
                name: sum(row["timings"][name] for row in results)
                for name in ["encode_seconds", "decode_seconds", "quality_seconds"]
            },
            "candidates": results,
            "candidate_receipt_sha256": ArtifactStore.sha256_file(destination / "candidates.json"),
        }
        ArtifactStore.write_json(destination / "receipt.json", result)
        return result
