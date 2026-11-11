"""Archive native Unity reference pixels and selected ASTCs for common-input evaluation."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline


class UnityReferenceCapture:
    def __init__(self, baseline: UnitySearchBaseline) -> None:
        self.baseline = baseline

    def collect(self, phase: str) -> dict[str, Any]:
        baseline = self.baseline
        completed = ArtifactStore.read_json(baseline.run_dir / f"{phase}-receipt.json")
        if (
            completed["status"] != "passed"
            or completed["process_exit_code"] != 0
            or completed["metadata_restore_conflicts"] != []
            or baseline.summarize(phase)["status"] != "passed"
        ):
            raise ValueError("Reference capture requires a complete successful import phase")
        baseline.audit(phase)
        config = ArtifactStore.read_json(baseline.run_dir / f"{phase}-config.json")
        if config.get("captureReferences") is not True:
            raise ValueError("Reference capture requires a frozen disk-debug configuration")
        imports = baseline._read_lines(baseline.run_dir / f"{phase}-imports.jsonl")
        expected = [baseline._asset_key(row["path"]) for row in config["assets"]]
        if (
            not expected
            or len(expected) != len(set(expected))
            or [baseline._asset_key(row["asset"]) for row in imports] != expected
            or not all(row["success"] for row in imports)
        ):
            raise ValueError("Reference imports differ from the complete frozen input cohort")
        native = {
            row["asset"].casefold(): row
            for row in baseline._read_lines(baseline.run_dir / f"{phase}-native.jsonl")
        }
        original = {
            row["path"].casefold(): row
            for row in ArtifactStore.read_json(baseline.manifest)["splits"][baseline.source_split]
        }
        output = baseline.run_dir / "references" / f"normalized-{phase}"
        receipt_path = output / "receipt.json"
        if receipt_path.exists():
            cached = ArtifactStore.read_json(receipt_path)
            if ArtifactStore.sha256_file(output / "manifest.json") != cached["manifest_sha256"]:
                raise ValueError("Archived reference manifest changed")
            manifest = ArtifactStore.read_json(output / "manifest.json")
            mirrored = manifest["splits"][baseline.source_split]
            if (
                cached["status"] != "passed"
                or cached["images"] != len(expected)
                or len(cached["rows"]) != len(expected)
                or manifest["reference_capture"] != cached["rows"]
                or [baseline._asset_key(row["path"]) for row in cached["rows"]] != expected
                or [baseline._asset_key(row["path"]) for row in mirrored] != expected
            ):
                raise ValueError("Archived reference identity or coverage changed")
            for index, row in enumerate(cached["rows"]):
                for name, digest in row["artifacts_sha256"].items():
                    if ArtifactStore.sha256_file(output / f"{index:05d}" / name) != digest:
                        raise ValueError("Archived reference pixels changed")
                source = (output / "project" / mirrored[index]["path"]).resolve()
                if (
                    not source.is_relative_to((output / "project").resolve())
                    or MD4.new(source.read_bytes()).hexdigest() != mirrored[index]["fileHash"]
                    or ArtifactStore.sha256_file(source) != row["artifacts_sha256"]["input.png"]
                ):
                    raise ValueError("Mirrored reference pixels changed")
            return cached
        output.mkdir(parents=True, exist_ok=True)
        rows = []
        adapted = []
        for index, imported in enumerate(imports):
            path = imported["asset"]
            folder = output / f"{index:05d}"
            folder.mkdir(exist_ok=True)
            debug = Path(imported["reference_directory"]).resolve()
            if not debug.is_relative_to((baseline.project / "ASTC_Cache").resolve()):
                raise ValueError("Unity reference output escaped its debug directory")
            selected = native[path.casefold()]
            prefix = f"{selected['block_size']}_{selected['preset']}"
            for source, destination in [
                (debug / "original.png", folder / "original.png"),
                (debug / f"{prefix}.astc", folder / "unity.astc"),
                (debug / f"{prefix}_decompressed.png", folder / "unity-native.png"),
                (debug / "parameter_test_report.txt", folder / "parameter_test_report.txt"),
            ]:
                if destination.exists() and ArtifactStore.sha256_file(
                    source
                ) != ArtifactStore.sha256_file(destination):
                    raise ValueError("An archived Unity reference artifact changed")
                shutil.copy2(source, destination)
            source = baseline.project / path
            if MD4.new(source.read_bytes()).hexdigest() != original[path.casefold()]["fileHash"]:
                raise ValueError("Unity reference source changed from the frozen cohort")
            with Image.open(folder / "original.png") as image:
                reference = image.convert("RGB")
                reference.save(folder / "input.png")
            with Image.open(source) as image:
                rgb = image.convert("RGB")
                equal = rgb.size == reference.size and rgb.tobytes() == reference.tobytes()
            with Image.open(folder / "unity-native.png") as image:
                if image.width < reference.width or image.height < reference.height:
                    raise ValueError("Native decoded Unity pixels are smaller than the reference")
                image.convert("RGB").transpose(Image.Transpose.FLIP_TOP_BOTTOM).crop(
                    (0, 0, *reference.size)
                ).save(folder / "unity.png")
            astc = ASTCFile.read(folder / "unity.astc")
            if "x".join(str(value) for value in astc.footprint) != selected["block_size"]:
                raise ValueError("Native reference ASTC differs from its selected footprint")
            quality = ASTCEncoder.psnr_rgb(folder / "input.png", folder / "unity.png")
            mirrored = output / "project" / path
            if not mirrored.resolve().is_relative_to(output.resolve()):
                raise ValueError("Reference image path escaped the capture directory")
            mirrored.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(folder / "input.png", mirrored)
            adapted.append({"path": path, "fileHash": MD4.new(mirrored.read_bytes()).hexdigest()})
            rows.append(
                {
                    "path": path,
                    "source_md4": original[path.casefold()]["fileHash"],
                    "source_split": baseline.source_split,
                    "reference_rgb_sha256": hashlib.sha256(reference.tobytes()).hexdigest(),
                    "source_rgb_equal": equal,
                    "native_png_orientation": "bottom row first, normalized by vertical flip",
                    "width": reference.width,
                    "height": reference.height,
                    "unity_payload_bytes": astc.payload_bytes,
                    "unity_rgb_psnr": quality if quality != float("inf") else None,
                    "unity_lossless": quality == float("inf"),
                    "selection": selected,
                    "srgb": imported["srgb"],
                    "texture_type": imported["texture_type"],
                    "artifacts_sha256": {
                        item.name: ArtifactStore.sha256_file(item)
                        for item in folder.iterdir()
                        if item.is_file()
                    },
                }
            )
        manifest = {"splits": {baseline.source_split: adapted}, "reference_capture": rows}
        ArtifactStore.write_json(output / "manifest.json", manifest)
        result = {
            "status": "passed",
            "images": len(rows),
            "source_rgb_equal": sum(row["source_rgb_equal"] for row in rows),
            "manifest_sha256": ArtifactStore.sha256_file(output / "manifest.json"),
            "capture_provenance": baseline.audit(phase),
            "rows": rows,
        }
        ArtifactStore.write_json(output / "receipt.json", result)
        return result
