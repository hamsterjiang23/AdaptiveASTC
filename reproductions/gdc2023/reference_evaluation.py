"""Measure the frozen classifier and one final encode on Unity's captured mip0 RGB pixels."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from adaptive_astc.config import CLASSES
from adaptive_astc.models import ASTCClassifier
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.common.cohort import EvaluationCohort
from reproductions.common.encoder import ASTCEncoder
from reproductions.common.upstream import BaselineGate
from reproductions.gdc2023.evaluation import GDCCompressionEvaluation


class GDCReferenceEvaluation(GDCCompressionEvaluation):
    def evaluate_reference(self, capture: Path, output: Path, images: int = 64) -> dict[str, Any]:
        if output.exists():
            raise FileExistsError(output)
        BaselineGate.require(
            self.root
            / "experiment report/.local/unity-search-baseline-lite-rdo-off/full-receipt.json"
        )
        started = time.perf_counter()
        capture = capture.resolve()
        descriptor = ArtifactStore.read_json(capture / "receipt.json")
        capture_sha = ArtifactStore.sha256_file(capture / "receipt.json")
        frozen, cohort = EvaluationCohort.unity64(
            self.root / "experiment report/.local/unity-search-baseline-lite-rdo-off"
        )
        if (
            descriptor["status"] != "passed"
            or descriptor["images"] != len(frozen)
            or [row["path"] for row in descriptor["rows"]] != frozen
            or not 1 <= images <= len(frozen)
            or ArtifactStore.sha256_file(capture / "manifest.json") != descriptor["manifest_sha256"]
        ):
            raise ValueError("Unity reference evaluation requires the frozen complete64 capture")
        manifest = ArtifactStore.read_json(self.run / "manifest.json")
        fingerprint = dict(manifest)
        expected_fingerprint = fingerprint.pop("fingerprint")
        if ArtifactStore.fingerprint(fingerprint) != expected_fingerprint or manifest[
            "classes"
        ] != list(CLASSES):
            raise ValueError("GDC training manifest changed")
        training = self.completed_training(self.run, self.initialization, manifest)
        complete = ArtifactStore.read_json(
            self.run / self.initialization / "training_complete.json"
        )
        train = {row["path"]: row for row in manifest["splits"]["train"]}
        rows = descriptor["rows"][:images]
        for index, row in enumerate(rows):
            if train[row["path"]]["fileHash"] != row["source_md4"]:
                raise ValueError("Unity reference is outside the original training cohort")
            for name, digest in row["artifacts_sha256"].items():
                if (
                    Path(name).name != name
                    or ArtifactStore.sha256_file(capture / f"{index:05d}" / name) != digest
                ):
                    raise ValueError("Unity reference artifact changed")
        checkpoint = self.run / self.initialization / "best.pt"
        model_sha = ArtifactStore.sha256_file(checkpoint)
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        if (
            state["data_fingerprint"] != expected_fingerprint
            or state["initialization"] != self.initialization
            or state["epoch"] != complete["best_epoch"]
        ):
            raise ValueError("Reference classifier differs from its training identity")
        device = ExperimentRuntime.configure(manifest["seed"])
        model = ASTCClassifier(self.initialization, pretrained=False).to(device)
        model.load_state_dict(state["model"], strict=True)
        model.eval()
        with (
            torch.inference_mode(),
            torch.autocast(
                device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"
            ),
        ):
            model(torch.zeros(1, 3, 224, 224, device=device)).cpu()
        build = ArtifactStore.read_json(
            self.root
            / "experiment report/.local/reproduction-binaries/nah2022_psnr_search"
            / "build-receipt.json"
        )
        protocol = ArtifactStore.read_json(self.run / "protocol.json")
        if (
            ArtifactStore.sha256_file(self.run / "protocol.json")
            != manifest["label_protocol_sha256"]
        ):
            raise ValueError("GDC reference evaluation protocol changed from the trained dataset")
        encoder = ASTCEncoder(Path(build["executable"]), threads=1)
        if ArtifactStore.sha256_file(encoder.executable) != protocol["encoder_sha256"]:
            raise ValueError("Reference encoding uses a different binary from GDC labels")
        output.mkdir(parents=True)
        binding = {
            "capture_sha256": capture_sha,
            "capture_directory": str(capture),
            "cohort": cohort,
            "data_fingerprint": expected_fingerprint,
            "checkpoint_sha256": model_sha,
            "training_files_sha256": training,
            "initialization": self.initialization,
            "encoder_sha256": protocol["encoder_sha256"],
        }
        ArtifactStore.write_json(output / "binding.json", binding)
        setup_seconds = time.perf_counter() - started
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        measured = []
        loop_started = time.perf_counter()
        for index, row in enumerate(rows):
            folder = output / f"{index:05d}"
            folder.mkdir()
            rgb_started = time.perf_counter()
            with Image.open(capture / f"{index:05d}/input.png") as original:
                rgb = original.convert("RGB")
                rgb.save(folder / "input.png")
            rgb_seconds = time.perf_counter() - rgb_started
            integrity_started = time.perf_counter()
            if (
                ArtifactStore.sha256_file(folder / "input.png")
                != row["artifacts_sha256"]["input.png"]
            ):
                raise ValueError("GDC reference RGB pixels differ from the captured input")
            integrity_seconds = time.perf_counter() - integrity_started
            prepare_started = time.perf_counter()
            resized = np.asarray(rgb.resize((224, 224), Image.Resampling.BILINEAR)).copy()
            features = torch.from_numpy(resized).permute(2, 0, 1).float().div_(255)
            features = ((features - mean) / std).unsqueeze(0)
            prepare_seconds = time.perf_counter() - prepare_started
            inference_started = time.perf_counter()
            with (
                torch.inference_mode(),
                torch.autocast(
                    device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"
                ),
            ):
                scores = model(features.to(device)).float().cpu()
            if not torch.isfinite(scores).all():
                raise ValueError("Non-finite reference classifier output")
            predicted = int(scores.argmax(dim=1).item())
            inference_seconds = time.perf_counter() - inference_started
            footprint = tuple(int(value) for value in CLASSES[predicted].split("x"))
            selected, seconds, text = encoder.encode(
                folder / "input.png",
                folder / "selected.astc",
                (footprint[0], footprint[1]),
                protocol["preset"],
            )
            (folder / "selected.txt").write_text(text, encoding="utf-8")
            fixed, fixed_seconds, text = encoder.encode(
                folder / "input.png", folder / "fixed8.astc", (8, 8), protocol["preset"]
            )
            (folder / "fixed8.txt").write_text(text, encoding="utf-8")
            verification_started = time.perf_counter()
            quality = {}
            for name in ["selected", "fixed8"]:
                encoder.decode(folder / f"{name}.astc", folder / f"{name}.png")
                value = encoder.psnr_rgb(folder / "input.png", folder / f"{name}.png")
                quality[name] = {
                    "rgb_psnr": value if math.isfinite(value) else None,
                    "lossless": math.isinf(value),
                    "target_met": value > 35.0,
                }
            result = {
                "path": row["path"],
                "source_md4": row["source_md4"],
                "predicted_class": predicted,
                "footprint": list(footprint),
                "logits": scores[0].tolist(),
                "quality": quality,
                "payload_bytes": selected.payload_bytes,
                "fixed8_payload_bytes": fixed.payload_bytes,
                "timings": {
                    "preprocessing_seconds": prepare_seconds,
                    "source_rgb_seconds": rgb_seconds,
                    "inference_seconds": inference_seconds,
                    "final_encode_seconds": seconds,
                    "model_pipeline_seconds": rgb_seconds
                    + prepare_seconds
                    + inference_seconds
                    + seconds,
                    "fixed8_pipeline_seconds": rgb_seconds + fixed_seconds,
                    "verification_seconds": integrity_seconds
                    + time.perf_counter()
                    - verification_started,
                },
                "artifacts_sha256": {
                    path.name: ArtifactStore.sha256_file(path)
                    for path in folder.iterdir()
                    if path.is_file()
                },
            }
            ArtifactStore.write_json(folder / "receipt.json", result)
            measured.append(
                {**result, "receipt_sha256": ArtifactStore.sha256_file(folder / "receipt.json")}
            )
            print(f"GDC Unity reference compression {index + 1}/{images}", flush=True)
        if (
            ArtifactStore.sha256_file(checkpoint) != model_sha
            or ArtifactStore.sha256_file(encoder.executable) != binding["encoder_sha256"]
            or ArtifactStore.sha256_file(capture / "receipt.json") != capture_sha
            or any(
                ArtifactStore.sha256_file(self.run / self.initialization / name) != digest
                for name, digest in training.items()
            )
        ):
            raise ValueError("Reference model or source changed during evaluation")
        receipt = {
            "schema": "gdc_unity_reference_v1",
            "status": "passed",
            "scope": "Unity mip0 RGB training-cohort diagnostic",
            "images": images,
            "binding": binding,
            "setup_seconds": setup_seconds,
            "wall_seconds": time.perf_counter() - loop_started,
            "per_image": measured,
            "profile": "Linear LDR RGB8, one encoding thread, no mip/RDO",
            "encoder_preset": protocol["preset"],
            "model_target_psnr": protocol["target_psnr"],
            "evaluation_target_psnr": 35.0,
        }
        ArtifactStore.write_json(output / "receipt.json", receipt)
        return {"status": "passed", "images": images, "receipt": str(output / "receipt.json")}
