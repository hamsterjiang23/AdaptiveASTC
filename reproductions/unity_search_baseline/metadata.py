"""Capture actual managed/native encoder arguments while preserving source bytes."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.unity_reference import UnityReferenceCapture
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.supplement import (
    UnityASTCBackend,
    UnitySupplementalCapture,
)


class ManagedCaptureHook:
    MARKER = "RecordASTCTrainingOptions"
    METHOD = "    unsafe static void HandleOptimizeCompress("

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    @staticmethod
    def instrument(original: bytes) -> bytes:
        bom = original.startswith(b"\xef\xbb\xbf")
        source = original.decode("utf-8-sig")
        if ManagedCaptureHook.MARKER in source or source.count(ManagedCaptureHook.METHOD) != 1:
            raise ValueError("Managed capture source is already patched or its signature changed")
        start = source.index(ManagedCaptureHook.METHOD)
        brace = source.index("{", start)
        signature = source[start:brace]
        required = [
            "byte* srcdata",
            "bool needAlpha",
            "int astc3rd_quality",
            "bool astc3rd_packnormal",
            "int astcenc_profile",
            "bool bSaveASTC",
            "string outputASTCfilename",
            "bool rdoEnabled",
            "float rdoQualityScalar",
            "int rdoLookback",
        ]
        if not all(value in signature for value in required):
            raise ValueError("Managed encoder callback signature changed")
        newline = "\r\n" if "\r\n" in source else "\n"
        helper = Path(__file__).with_name("native").joinpath("capture_options.cs.txt").read_text()
        helper = helper.replace("\n", newline)
        call = (
            newline + "        RecordASTCTrainingOptions(srcdata, width, height, channel, format, "
            "needAlpha, astc3rd_quality, astc3rd_packnormal, astcenc_profile, bSaveASTC, "
            "outputASTCfilename, rdoEnabled, rdoQualityScalar, rdoLookback);" + newline
        )
        patched = source[:start] + helper + source[start : brace + 1] + call + source[brace + 1 :]
        return (b"\xef\xbb\xbf" if bom else b"") + patched.encode("utf-8")

    @staticmethod
    def replace_bytes(path: Path, payload: bytes) -> None:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=path.name + ".", suffix=".astccapture.tmp", delete=False
        ) as target:
            temporary = Path(target.name)
            try:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            except BaseException:
                target.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def install(self, source: Path) -> JsonDict:
        if self.folder.exists() and any(self.folder.iterdir()):
            raise FileExistsError("Use a fresh hook journal; retain previous captures")
        original = source.read_bytes()
        patched = self.instrument(original)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.replace_bytes(self.folder / "original.cs", original)
        self.replace_bytes(self.folder / "instrumented.cs", patched)
        receipt = {
            "status": "prepared",
            "source": str(source.resolve()),
            "original_sha256": hashlib.sha256(original).hexdigest(),
            "instrumented_sha256": hashlib.sha256(patched).hexdigest(),
        }
        ArtifactStore.write_json(self.folder / "receipt.json", receipt)
        if source.read_bytes() != original:
            raise ValueError("Managed source changed before instrumentation")
        self.replace_bytes(source, patched)
        receipt["status"] = "installed"
        ArtifactStore.write_json(self.folder / "receipt.json", receipt)
        return receipt

    def restore(self) -> JsonDict:
        receipt = ArtifactStore.read_json(self.folder / "receipt.json")
        source = Path(receipt["source"])
        original = self.folder / "original.cs"
        if ArtifactStore.sha256_file(original) != receipt["original_sha256"]:
            raise ValueError("Managed source backup changed")
        current = ArtifactStore.sha256_file(source)
        if current not in {receipt["original_sha256"], receipt["instrumented_sha256"]}:
            raise ValueError("Managed source changed independently; refusing to overwrite it")
        if current != receipt["original_sha256"]:
            self.replace_bytes(source, original.read_bytes())
        receipt["status"] = "restored"
        receipt["restored_sha256"] = ArtifactStore.sha256_file(source)
        ArtifactStore.write_json(self.folder / "receipt.json", receipt)
        return receipt


class UnityOptionCapture:
    def __init__(self, root: Path, config: Path) -> None:
        self.root = root
        self.config = ArtifactStore.read_json(config)

    def reaudit(self, report: Path) -> JsonDict:
        config = self.config
        baseline = UnitySearchBaseline(
            self.root,
            Path(config["project"]),
            Path(config["editor"]),
            Path(config["manifest"]),
            run_id=config["run_id"],
            capture_references=True,
        )
        baseline.require_project_closed()
        previous_path = baseline.run_dir / "options-receipt.json"
        previous = ArtifactStore.read_json(previous_path)
        restoration = previous["managed_source_restoration"]
        if (
            previous["status"] != "passed"
            or restoration["status"] != "restored"
            or restoration["original_sha256"] != restoration["restored_sha256"]
        ):
            raise ValueError("Reaudit requires a successful restored capture")
        captured = UnityReferenceCapture(baseline).collect(config["phase"])
        result = self.audit(baseline, config["phase"], captured)
        result["managed_source_restoration"] = restoration
        result["collection_timing_scope"] = previous["collection_timing_scope"]
        result["previous_receipt_sha256"] = ArtifactStore.sha256_file(previous_path)
        result["scope"] = "Reaudit archived callback records; no new Editor run or encoding"
        ArtifactStore.write_json(report, result)
        return result

    def run(self) -> JsonDict:
        config = self.config
        phase = config["phase"]
        if phase not in {"probe", "smoke1", "smoke2", "smoke3"}:
            raise ValueError("Metadata pilot must pass before full collection")
        baseline = UnitySearchBaseline(
            self.root,
            Path(config["project"]),
            Path(config["editor"]),
            Path(config["manifest"]),
            run_id=config["run_id"],
            capture_references=True,
        )
        if baseline.run_dir.exists() or Path(config["report"]).exists():
            raise FileExistsError("Use a new capture identity and report")
        baseline.require_project_closed()
        baseline.prepare()
        hook = ManagedCaptureHook(baseline.run_dir / "managed-hook")
        source = baseline.project / "Assets/Editor/Astc/astccustom.cs"
        log = baseline.run_dir / f"{phase}-options.jsonl"
        if log.exists():
            raise FileExistsError("Use a new capture identity")
        key = "ASTC_TRAINING_CAPTURE_OPTIONS"
        previous = os.environ.get(key)
        result: JsonDict = {"status": "running", "run_directory": str(baseline.run_dir)}
        implementation_sha256 = {
            path.name: ArtifactStore.sha256_file(path)
            for path in [
                Path(__file__),
                Path(__file__).with_name("native") / "capture_options.cs.txt",
            ]
        }
        try:
            hook.install(source)
            os.environ[key] = str(log)
            result = baseline.run(phase)
            if result["status"] != "passed":
                raise RuntimeError("Unity metadata pilot failed; inspect original phase receipt")
            captured = UnityReferenceCapture(baseline).collect(phase)
            result = self.audit(baseline, phase, captured)
        except BaseException as error:
            result["status"] = "failed"
            result["error"] = repr(error)
            raise
        finally:
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
            try:
                if (hook.folder / "receipt.json").exists():
                    baseline.require_project_closed()
                    result["managed_source_restoration"] = hook.restore()
            except BaseException as error:
                result["status"] = "failed"
                result["restoration_error"] = repr(error)
                raise
            finally:
                result["implementation_sha256"] = implementation_sha256
                result["collection_timing_scope"] = (
                    "Reference export and callback hashing enabled; original search policy "
                    "unchanged; timing is collection cost, not baseline"
                )
                ArtifactStore.write_json(baseline.run_dir / "options-receipt.json", result)
                ArtifactStore.write_json(Path(config["report"]), result)
        return result

    @staticmethod
    def audit(baseline: UnitySearchBaseline, phase: str, captured: JsonDict) -> JsonDict:
        log = baseline.run_dir / f"{phase}-options.jsonl"
        options = baseline._read_lines(log)
        imports = baseline._read_lines(baseline.run_dir / f"{phase}-imports.jsonl")
        rows = []
        all_matched = 0
        for index, (reference, imported) in enumerate(zip(captured["rows"], imports, strict=True)):
            if baseline._asset_key(reference["path"]) != baseline._asset_key(imported["asset"]):
                raise ValueError("Metadata import and archived reference identities differ")
            folder = Path(imported["reference_directory"]).resolve()
            candidates = [
                row for row in options if Path(row["astc_file"]).resolve().parent == folder
            ]
            if not candidates or len(candidates) != reference["selection"]["candidates_attempted"]:
                raise ValueError("Actual encoder argument coverage differs from native attempts")
            image = (
                baseline.run_dir
                / "references"
                / f"normalized-{phase}"
                / f"{index:05d}"
                / "original.png"
            )
            with Image.open(image) as pixels:
                rgba = np.ascontiguousarray(np.asarray(pixels.convert("RGBA"))[::-1])
            expected_sha = hashlib.sha256(rgba.tobytes()).hexdigest()
            signatures = set()
            keys = set()
            for row in candidates:
                if (
                    row["rgba_sha256"] != expected_sha
                    or row["channel"] != 4
                    or (row["width"], row["height"]) != (reference["width"], reference["height"])
                ):
                    raise ValueError("Callback RGBA bytes differ from the archived reference PNG")
                match = re.fullmatch(
                    r"(\d+x\d+)_(fastest|fast|medium|thorough|exhaustive)\.astc",
                    Path(row["astc_file"]).name,
                )
                if match is None or row["quality"] != UnityASTCBackend.PRESETS[match[2]]:
                    raise ValueError("Callback candidate/preset mapping differs")
                candidate_key = (match[1], match[2])
                formats = {"6x6": 50, "8x8": 51, "10x10": 52, "12x12": 53}
                if (
                    match[1] not in formats
                    or row["format_value"] != formats[match[1]]
                    or row["format_name"] != f"kTexFormatASTC_{match[1]}"
                    or row["profile"] not in {0, 1}
                ):
                    raise ValueError("Callback footprint/format/profile is not supported LDR")
                if candidate_key in keys or row["rdo"]:
                    raise ValueError("Duplicate candidate or unexpected RDO setting")
                keys.add(candidate_key)
                signatures.add((row["need_alpha"], row["profile"], row["normal_pack"]))
            measured = UnitySupplementalCapture.search_table(
                (image.parent / "parameter_test_report.txt").read_text(encoding="utf-8-sig")
            )
            selection = reference["selection"]
            if (
                not set(measured).issubset(keys)
                or (selection["block_size"], selection["preset"]) not in keys
            ):
                raise ValueError("Callback coverage omits measured candidates or the native winner")
            if len(signatures) != 1:
                raise ValueError("Per-image encoder contract changed across candidates")
            need_alpha, profile, normal_pack = signatures.pop()
            rows.append(
                {
                    "index": index,
                    "path": reference["path"],
                    "need_alpha": need_alpha,
                    "profile": profile,
                    "normal_pack": normal_pack,
                    "channel": 4,
                    "rgba_sha256": expected_sha,
                    "width": reference["width"],
                    "height": reference["height"],
                    "srgb_importer": reference["srgb"],
                    "texture_type_importer": reference["texture_type"],
                    "candidates_recorded": len(candidates),
                    "candidate_keys": sorted([list(key) for key in keys]),
                    "input_hash_ms": sum(row["input_hash_ms"] for row in candidates),
                    "metadata_source": (
                        "actual optimized encoder callback; raw RGBA hash matches archived PNG"
                    ),
                }
            )
            all_matched += len(candidates)
        if all_matched != len(options):
            raise ValueError("Unmatched callback argument records")
        return {
            "status": "passed",
            "images": len(rows),
            "candidate_callbacks": len(options),
            "rows": rows,
            "options_sha256": ArtifactStore.sha256_file(log),
            "audit_source_sha256": ArtifactStore.sha256_file(Path(__file__)),
            "capture_receipt_sha256": ArtifactStore.sha256_file(
                baseline.run_dir / "references" / f"normalized-{phase}" / "receipt.json"
            ),
            "native_provenance": captured["capture_provenance"],
            "run_directory": str(baseline.run_dir),
        }
