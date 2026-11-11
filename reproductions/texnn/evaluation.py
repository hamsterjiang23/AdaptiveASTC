"""Encode and decode learned TexNN predictions alongside a fixed-footprint reference."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.environment import RunEnvironment
from reproductions.common.encoder import ASTCEncoder
from reproductions.common.upstream import BaselineGate
from reproductions.texnn.inference import TexNNPredictor


class TexNNEvaluation:
    def __init__(self, root: Path, run_dir: Path, size: int, *, device: str = "cpu") -> None:
        BaselineGate.require(
            root / "experiment report/.local/unity-search-baseline-lite-rdo-off/full-receipt.json"
        )
        self.predictor = TexNNPredictor(root, run_dir, size, device=device)
        self.size = size

    def evaluate(
        self,
        source: Path,
        output: Path,
        *,
        partition_topk: int = 1,
        joint_topk: int = 1,
        preset: str = "exhaustive",
        scope: str = "pipeline_smoke",
    ) -> dict[str, Any]:
        output.mkdir(parents=True, exist_ok=False)
        source_hash = ArtifactStore.sha256_file(source)
        pixels = output / "input.png"
        input_started = time.perf_counter()
        with Image.open(source) as image:
            image.convert("RGB").save(pixels)
            width, height = image.size
        input_seconds = time.perf_counter() - input_started
        selected = self.predictor.predict(
            pixels,
            output / "inference",
            partition_topk=partition_topk,
            joint_topk=joint_topk,
            preset=preset,
        )
        backend = self.predictor.backend
        decisions_path = output / "decisions.jsonl"
        encoded, encode_seconds, stdout = backend.encode(
            pixels,
            Path(selected["predictions"]),
            output / "selected.astc",
            (self.size, self.size),
            preset,
            decisions_path,
        )
        (output / "selected.txt").write_text(stdout, encoding="utf-8")
        reference = ASTCEncoder(Path(backend.build["executable"]), threads=1)
        if ArtifactStore.sha256_file(reference.executable) != backend.build["sha256"]:
            raise ValueError("Historical reference encoder changed since its build")
        control, reference_seconds, stdout = reference.encode(
            pixels, output / "reference.astc", (self.size, self.size), preset
        )
        (output / "reference.txt").write_text(stdout, encoding="utf-8")
        verification_started = time.perf_counter()
        selected_decode = reference.decode(output / "selected.astc", output / "selected.tga")
        reference_decode = reference.decode(output / "reference.astc", output / "reference.tga")
        quality = reference.psnr_rgb(pixels, output / "selected.tga")
        reference_quality = reference.psnr_rgb(pixels, output / "reference.tga")
        seen: set[tuple[int, int]] = set()
        counts = {key: 0 for key in ["blocks", "constant", "predicted", "fallback"]}
        with decisions_path.open(encoding="utf-8") as stream:
            for line in stream:
                decision = json.loads(line)
                point = (decision["x"], decision["y"])
                if (
                    point in seen
                    or decision["error"]
                    or not 0 <= point[0] < width
                    or not 0 <= point[1] < height
                    or point[0] % self.size
                    or point[1] % self.size
                    or sum(int(decision[key]) for key in ["constant", "predicted", "fallback"]) != 1
                ):
                    raise ValueError("Invalid TexNN native encoding decision")
                seen.add(point)
                counts["blocks"] += 1
                for key in ["constant", "predicted", "fallback"]:
                    counts[key] += int(decision[key])
        if (
            counts["blocks"] != selected["blocks"]
            or counts["constant"] != selected["constant_blocks"]
            or encoded != control
        ):
            raise ValueError("Learned and reference encoding dimensions or block coverage differ")
        if ArtifactStore.sha256_file(source) != source_hash:
            raise ValueError("Evaluation source changed during encoding")
        backend.verify_binary()
        if ArtifactStore.sha256_file(reference.executable) != backend.build["sha256"]:
            raise ValueError("Reference encoder changed during evaluation")
        verification_seconds = time.perf_counter() - verification_started
        total = input_seconds + selected["timings"]["prediction_pipeline_seconds"] + encode_seconds
        receipt = {
            "status": "passed",
            "scope": scope,
            "width": width,
            "height": height,
            "source": str(source.resolve()),
            "source_sha256": source_hash,
            "footprint": [self.size, self.size],
            "preset": preset,
            "color_profile": "source RGB8, Linear LDR, no mipmaps",
            "encoder_threads": 1,
            "feature_protocol": self.predictor.manifest["feature_protocol"],
            "predictions": selected,
            "native_decisions": counts,
            "rgb_psnr": quality if math.isfinite(quality) else None,
            "lossless": math.isinf(quality),
            "reference_rgb_psnr": reference_quality if math.isfinite(reference_quality) else None,
            "reference_lossless": math.isinf(reference_quality),
            "psnr_delta_db": quality - reference_quality
            if math.isfinite(quality) and math.isfinite(reference_quality)
            else None,
            "payload_bytes": encoded.payload_bytes,
            "container_bytes": encoded.container_bytes,
            "timings": {
                "source_rgb_preparation_seconds": input_seconds,
                **selected["timings"],
                "final_encode_seconds": encode_seconds,
                "learned_pipeline_seconds": total,
                "reference_encode_seconds": reference_seconds,
                "reference_pipeline_seconds": input_seconds + reference_seconds,
                "relative_time": total / (input_seconds + reference_seconds),
                "selected_decode_seconds": selected_decode,
                "reference_decode_seconds": reference_decode,
                "verification_seconds": verification_seconds,
            },
            "model_setup_in_pipeline": False,
            "environment": RunEnvironment.capture(),
            "binaries": {
                "reference": backend.build["sha256"],
                "prediction": backend.expected_sha256,
            },
            "artifacts_sha256": {
                str(path.relative_to(output)): ArtifactStore.sha256_file(path)
                for path in sorted(output.rglob("*"))
                if path.is_file()
            },
        }
        ArtifactStore.write_json(output / "receipt.json", receipt)
        return receipt


class TexNNBatchEvaluation:
    def __init__(self, root: Path, project: Path, manifest: Path, run_dir: Path) -> None:
        self.root, self.project, self.manifest, self.run_dir = root, project, manifest, run_dir

    def run(
        self,
        output: Path,
        *,
        images: int = 8,
        patch_size: int = 128,
        settings: tuple[tuple[int, int], ...] = ((1, 1), (3, 10)),
        device: str = "cpu",
    ) -> dict[str, Any]:
        if images < 1 or patch_size < 8:
            raise ValueError("Positive validation sample count and patch size are required")
        frozen = ArtifactStore.read_json(self.manifest)
        training_protocol = ArtifactStore.read_json(self.run_dir / "protocol.json")
        if training_protocol["manifest_sha256"] != ArtifactStore.sha256_file(self.manifest):
            raise ValueError("Evaluation manifest differs from the model training corpus manifest")
        validation = sorted(frozen["splits"]["validation"], key=lambda row: row["path"])[:images]
        if len(validation) != images:
            raise ValueError("Insufficient validation images in the frozen manifest")
        training_paths = {row["path"].casefold() for row in frozen["splits"]["train"]}
        if any(row["path"].casefold() in training_paths for row in validation):
            raise ValueError("Image-level training and validation paths overlap")
        output.mkdir(parents=True, exist_ok=False)
        protocol = {
            "scope": "project_validation_crops",
            "split": "validation",
            "images": images,
            "patch_size": patch_size,
            "crop": "center crop without resizing, RGB8",
            "footprints": [4, 6, 8],
            "topk_settings": settings,
            "preset": "exhaustive",
            "device": device,
            "threads": 1,
            "mipmaps": False,
            "manifest_sha256": ArtifactStore.sha256_file(self.manifest),
            "inputs": [{"path": row["path"], "fileHash": row["fileHash"]} for row in validation],
        }
        ArtifactStore.write_json(output / "protocol.json", protocol)
        started = time.perf_counter()
        prepared = []
        for index, row in enumerate(validation):
            source = (self.project / row["path"]).resolve()
            if not source.is_relative_to((self.project / "Assets").resolve()):
                raise ValueError("Validation source escaped project Assets")
            if MD4.new(source.read_bytes()).hexdigest() != row["fileHash"].lower():
                raise ValueError("Validation source differs from frozen manifest")
            pixels = output / f"input-{index:04d}.png"
            with Image.open(source) as image:
                width, height = min(image.width, patch_size), min(image.height, patch_size)
                left, top = (image.width - width) // 2, (image.height - height) // 2
                box = (left, top, left + width, top + height)
                image.convert("RGB").crop(box).save(pixels)
                source_size = image.size
            if MD4.new(source.read_bytes()).hexdigest() != row["fileHash"].lower():
                raise ValueError("Validation source changed while preparing the crop")
            prepared.append(
                {
                    "index": index,
                    "asset": row["path"],
                    "fileHash": row["fileHash"],
                    "source_size": source_size,
                    "crop_box": box,
                    "pixels": str(pixels),
                    "pixels_sha256": ArtifactStore.sha256_file(pixels),
                }
            )
        ArtifactStore.write_json(output / "inputs.json", {"assets": prepared})
        preparation_seconds = time.perf_counter() - started
        results = []
        setups = {}
        for size in [4, 6, 8]:
            evaluator = TexNNEvaluation(self.root, self.run_dir, size, device=device)
            setups[str(size)] = evaluator.predictor.setup_seconds
            for partition_topk, joint_topk in settings:
                for row in prepared:
                    directory = (
                        output
                        / f"{size}x{size}"
                        / f"top{partition_topk}x{joint_topk}"
                        / f"{row['index']:04d}"
                    )
                    try:
                        receipt = evaluator.evaluate(
                            Path(row["pixels"]),
                            directory,
                            partition_topk=partition_topk,
                            joint_topk=joint_topk,
                            scope="project_validation_crops",
                        )
                        result = {
                            "index": row["index"],
                            "asset": row["asset"],
                            "size": size,
                            "partition_topk": partition_topk,
                            "joint_topk": joint_topk,
                            "status": "passed",
                            "receipt": str(directory / "receipt.json"),
                            "receipt_sha256": ArtifactStore.sha256_file(directory / "receipt.json"),
                            "rgb_psnr": receipt["rgb_psnr"],
                            "reference_rgb_psnr": receipt["reference_rgb_psnr"],
                            "timings": receipt["timings"],
                            "counts": receipt["native_decisions"],
                        }
                    except Exception as error:
                        result = {
                            "index": row["index"],
                            "asset": row["asset"],
                            "size": size,
                            "partition_topk": partition_topk,
                            "joint_topk": joint_topk,
                            "status": "failed",
                            "error": repr(error),
                        }
                    results.append(result)
                    print(
                        f"TexNN validation {len(results)}/{images * 3 * len(settings)} "
                        f"{result['status']}",
                        flush=True,
                    )
                    ArtifactStore.write_json(output / "progress.json", {"results": results})
        receipt = {
            "status": "passed" if all(row["status"] == "passed" for row in results) else "failed",
            "protocol_sha256": ArtifactStore.sha256_file(output / "protocol.json"),
            "inputs_sha256": ArtifactStore.sha256_file(output / "inputs.json"),
            "crop_preparation_seconds": preparation_seconds,
            "model_setup_seconds": setups,
            "wall_seconds": time.perf_counter() - started,
            "results": results,
        }
        ArtifactStore.write_json(output / "receipt.json", receipt)
        return receipt
