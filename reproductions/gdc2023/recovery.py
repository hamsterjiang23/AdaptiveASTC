"""Admit complete, immutable per-image results when continuing an interrupted evaluation."""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from adaptive_astc.config import CLASSES
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCEncoder, ASTCFile


class EvaluationRecovery:
    @staticmethod
    def anchors(output: Path) -> dict[int, str]:
        try:
            recorded = ArtifactStore.read_json(output / "progress.json")["results"]
            anchors = {row["index"]: row["receipt_sha256"] for row in recorded}
            if len(anchors) != len(recorded) or any(
                type(index) is not int
                or index < 0
                or not isinstance(digest, str)
                or len(digest) != 64
                for index, digest in anchors.items()
            ):
                raise ValueError("Invalid evaluation progress entries")
            return anchors
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    @staticmethod
    def prepare(output: Path, binding: dict[str, Any], resume: bool) -> None:
        if output.exists():
            if not resume or (output / "receipt.json").exists():
                raise FileExistsError(output)
            if ArtifactStore.read_json(output / "binding.json") != binding:
                raise ValueError("Evaluation resume binding changed")
        else:
            output.mkdir(parents=True)
            ArtifactStore.write_json(output / "binding.json", binding)

    @staticmethod
    def validate(
        sample: Path, index: int, row: dict[str, Any], label: dict[str, Any], target: float
    ) -> None:
        measured = ArtifactStore.read_json(sample / "receipt.json")
        predicted = measured["predicted_class"]
        if (
            measured["status"] != "passed"
            or measured["index"] != index
            or measured["path"] != row["path"]
            or measured["fileHash"] != row["fileHash"]
            or type(predicted) is not int
            or not 0 <= predicted < len(CLASSES)
            or measured["predicted_footprint"] != CLASSES[predicted]
            or measured["label_class"] != row["class_id"]
            or CLASSES[row["class_id"]] != label["selected"]["name"]
            or measured["label_target_met"] != label["target_met"]
            or measured["label_payload_bytes"] != label["selected"]["payload_bytes"]
            or not 0 <= measured["confidence"] <= 1
        ):
            raise ValueError("Cached evaluation identity or prediction changed")
        name = CLASSES[predicted]
        artifacts = measured["artifacts_sha256"]
        expected = {
            "input.png",
            "selected.astc",
            "selected.png",
            "selected.txt",
            "fixed8.astc",
            "fixed8.png",
            "fixed8.txt",
        }
        if set(artifacts) != expected:
            raise ValueError("Cached evaluation artifacts incomplete")
        for file, digest in artifacts.items():
            if ArtifactStore.sha256_file(sample / file) != digest:
                raise ValueError("Cached evaluation artifact changed")
        for file, native in [
            ("input.png", "input.png"),
            ("selected.astc", f"{name}.astc"),
            ("selected.png", f"{name}.png"),
            ("fixed8.astc", "8x8.astc"),
            ("fixed8.png", "8x8.png"),
        ]:
            if artifacts[file] != label["artifacts_sha256"][native]:
                raise ValueError("Cached evaluation differs from frozen offline candidate")
        with Image.open(sample / "input.png") as image:
            dimensions = image.size
        for kind, footprint, metric, lossless, size, passed in [
            ("selected", name, "rgb_psnr", "lossless", "payload_bytes", "target_met"),
            (
                "fixed8",
                "8x8",
                "fixed8_rgb_psnr",
                "fixed8_lossless",
                "fixed8_payload_bytes",
                "fixed8_target_met",
            ),
        ]:
            actual = ASTCFile.read(sample / f"{kind}.astc")
            quality = ASTCEncoder.psnr_rgb(sample / "input.png", sample / f"{kind}.png")
            recorded = math.inf if measured[lossless] else measured[metric]
            if (
                actual.footprint != tuple(int(value) for value in footprint.split("x"))
                or (actual.width, actual.height) != dimensions
                or actual.depth != 1
                or actual.payload_bytes != measured[size]
                or (measured[lossless] and measured[metric] is not None)
                or recorded is None
                or not math.isclose(quality, recorded, abs_tol=1e-8)
                or measured[passed] != (quality > target)
            ):
                raise ValueError("Cached evaluation payload or quality changed")
        timings = measured["timings"]
        required = {
            "source_rgb_seconds",
            "classifier_preprocessing_seconds",
            "inference_seconds",
            "final_encode_seconds",
            "model_pipeline_seconds",
            "fixed8_encode_seconds",
            "fixed8_pipeline_seconds",
            "verification_seconds",
        }
        if set(timings) != required or any(
            not math.isfinite(value) or value <= 0 for value in timings.values()
        ):
            raise ValueError("Cached evaluation timings invalid")
        model = sum(
            timings[key]
            for key in [
                "source_rgb_seconds",
                "classifier_preprocessing_seconds",
                "inference_seconds",
                "final_encode_seconds",
            ]
        )
        fixed = timings["source_rgb_seconds"] + timings["fixed8_encode_seconds"]
        if not math.isclose(
            model, timings["model_pipeline_seconds"], abs_tol=1e-8
        ) or not math.isclose(fixed, timings["fixed8_pipeline_seconds"], abs_tol=1e-8):
            raise ValueError("Cached evaluation pipeline accounting changed")

    @classmethod
    def reuse(
        cls,
        output: Path,
        index: int,
        row: dict[str, Any],
        label: dict[str, Any],
        target: float,
        expected_receipt_sha256: str | None = None,
    ) -> bool:
        sample = output / f"{index:05d}"
        if not sample.exists():
            return False
        if sample.is_symlink() or not sample.resolve().is_relative_to(output.resolve()):
            raise ValueError("Evaluation recovery path escaped output directory")
        try:
            if (
                expected_receipt_sha256 is not None
                and ArtifactStore.sha256_file(sample / "receipt.json") != expected_receipt_sha256
            ):
                raise ValueError("Cached evaluation differs from the prior progress receipt hash")
            cls.validate(sample, index, row, label, target)
            return True
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            archive = output / "attempts" / f"{index:05d}-{uuid.uuid4().hex}"
            archive.parent.mkdir(exist_ok=True)
            if not archive.resolve().is_relative_to(output.resolve()):
                raise ValueError("Evaluation recovery archive escaped output directory") from error
            sample.rename(archive)
            ArtifactStore.write_json(archive / "recovery-error.json", {"error": repr(error)})
            return False
