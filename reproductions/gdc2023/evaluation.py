"""Measure a frozen ResNet decision followed by one real final ASTC encoding."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.config import CLASSES
from adaptive_astc.models import ASTCClassifier
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.checkpoints import CheckpointStore
from adaptive_astc.utils.environment import RunEnvironment
from adaptive_astc.utils.evaluation_seal import EvaluationSeal
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.common.cohort import EvaluationCohort
from reproductions.common.encoder import ASTCEncoder
from reproductions.common.upstream import BaselineGate
from reproductions.gdc2023.dataset import GDCMeasuredDataset


class GDCCompressionEvaluation:
    def __init__(self, root: Path, run: Path, initialization: str) -> None:
        self.root, self.run = root.resolve(), run.resolve()
        self.initialization = initialization
        if initialization not in {"pretrained", "scratch"}:
            raise ValueError("Unknown GDC initialization")

    @staticmethod
    def completed_training(
        run: Path, initialization: str, manifest: dict[str, Any]
    ) -> dict[str, str]:
        CheckpointStore.require_completed(run, initialization, manifest)
        directory = run / initialization
        complete = ArtifactStore.read_json(directory / "training_complete.json")
        config = ArtifactStore.read_json(directory / "config.json")
        history = ArtifactStore.read_json(directory / "history.json")["epochs"]
        last = torch.load(directory / "last.pt", map_location="cpu", weights_only=False)
        epochs = complete["completed_epochs"]
        if (
            complete["config"] != config
            or epochs != config["epochs_target"]
            or len(history) != epochs
            or last["epoch"] != epochs
            or [item["epoch"] for item in history] != list(range(1, epochs + 1))
            or last["history"] != history
            or last["data_fingerprint"] != manifest["fingerprint"]
            or last["initialization"] != initialization
            or not 1 <= complete["best_epoch"] <= epochs
            or last["best_key"][2] != complete["best_epoch"]
        ):
            raise ValueError("Training state is incomplete or differs from its completion receipt")
        names = ["training_complete.json", "config.json", "history.json", "last.pt"]
        if (directory / "wall-clock.json").exists():
            names.append("wall-clock.json")
        return {name: ArtifactStore.sha256_file(directory / name) for name in names}

    def preflight_inputs(
        self,
        manifest: dict[str, Any],
        protocol: dict[str, Any],
        split: str,
        indices: dict[tuple[str, str], int],
        protocol_fingerprint: str,
        selected_rows: list[dict[str, Any]] | None = None,
    ) -> list[tuple[Path, dict[str, Any]]]:
        result = []
        for row in manifest["splits"][split] if selected_rows is None else selected_rows:
            source = (Path(manifest["image_root"]) / row["path"]).resolve()
            if not source.is_relative_to((Path(manifest["image_root"]) / "Assets").resolve()):
                raise ValueError("GDC evaluation source escaped project Assets")
            if MD4.new(source.read_bytes()).hexdigest() != row["fileHash"].lower():
                raise ValueError("GDC source changed before compression evaluation")
            native_index = indices[(split, row["path"])]
            label_folder = self.run / "labels" / f"{native_index:05d}"
            label = ArtifactStore.read_json(label_folder / "receipt.json")
            if (
                ArtifactStore.sha256_file(label_folder / "receipt.json")
                != row["label_receipt_sha256"]
            ):
                raise ValueError("GDC label changed before compression evaluation")
            GDCMeasuredDataset.validate_receipt(
                label_folder,
                label,
                native_index,
                protocol["inputs"][native_index],
                protocol,
                protocol_fingerprint,
            )
            result.append((source, label))
        if not result:
            raise ValueError("GDC evaluation split is empty")
        return result

    def evaluate(
        self,
        output: Path,
        split: str = "test",
        cohort_paths: list[str] | None = None,
        cohort_name: str | None = None,
    ) -> dict[str, Any]:
        if output.exists():
            raise FileExistsError(output)
        BaselineGate.require(
            self.root
            / "experiment report/.local/unity-search-baseline-lite-rdo-off/full-receipt.json"
        )
        setup_started = time.perf_counter()
        manifest = ArtifactStore.read_json(self.run / "manifest.json")
        content = dict(manifest)
        fingerprint = content.pop("fingerprint")
        if ArtifactStore.fingerprint(content) != fingerprint or manifest["classes"] != list(
            CLASSES
        ):
            raise ValueError("GDC classifier manifest changed or uses incompatible classes")
        selected_rows = EvaluationCohort.rows(manifest, split, cohort_paths)
        protocol = ArtifactStore.read_json(self.run / "protocol.json")
        if manifest["label_protocol_sha256"] != ArtifactStore.sha256_file(
            self.run / "protocol.json"
        ) or manifest["label_collection_sha256"] != ArtifactStore.sha256_file(
            self.run / "collection.json"
        ):
            raise ValueError("GDC measured-label provenance changed")
        training_hashes = self.completed_training(self.run, self.initialization, manifest)
        checkpoint = self.run / self.initialization / "best.pt"
        checkpoint_sha256 = ArtifactStore.sha256_file(checkpoint)
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        complete = ArtifactStore.read_json(
            self.run / self.initialization / "training_complete.json"
        )
        if (
            state["data_fingerprint"] != fingerprint
            or state["initialization"] != self.initialization
            or state["epoch"] != complete["best_epoch"]
        ):
            raise ValueError("GDC checkpoint differs from its training source/initialization")
        device = ExperimentRuntime.configure(manifest["seed"])
        model = ASTCClassifier(self.initialization, pretrained=False).to(device)
        model.load_state_dict(state["model"], strict=True)
        model.eval()
        warmup_started = time.perf_counter()
        with (
            torch.inference_mode(),
            torch.autocast(
                device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"
            ),
        ):
            model(torch.zeros(1, 3, 224, 224, device=device)).cpu()
        warmup_seconds = time.perf_counter() - warmup_started
        encoder_build = ArtifactStore.read_json(
            self.root
            / "experiment report/.local/reproduction-binaries/nah2022_psnr_search"
            / "build-receipt.json"
        )
        encoder = ASTCEncoder(Path(encoder_build["executable"]), threads=1)
        if (
            encoder_build["sha256"] != protocol["encoder_sha256"]
            or ArtifactStore.sha256_file(encoder.executable) != protocol["encoder_sha256"]
        ):
            raise ValueError("GDC final encoder differs from its measured-label encoder")
        protocol_fingerprint = ArtifactStore.fingerprint(protocol)
        indices = {
            (item["split"], item["path"]): index for index, item in enumerate(protocol["inputs"])
        }
        binding = {
            "data_fingerprint": fingerprint,
            "checkpoint_sha256": checkpoint_sha256,
            "initialization": self.initialization,
            "split": split,
            "training_files_sha256": training_hashes,
        }
        if cohort_paths is not None:
            binding["cohort_paths"] = [row["path"] for row in selected_rows]
        if cohort_name is not None:
            if cohort_name != "unity64" or split != "train":
                raise ValueError("Named Unity64 comparison requires the training diagnostic")
            frozen_paths, identity = EvaluationCohort.unity64(
                self.root / "experiment report/.local/unity-search-baseline-lite-rdo-off"
            )
            if binding.get("cohort_paths") != frozen_paths:
                raise ValueError("Named Unity64 inputs differ from the frozen cohort")
            binding["cohort_identity"] = identity
        verified_inputs = self.preflight_inputs(
            manifest, protocol, split, indices, protocol_fingerprint, selected_rows
        )
        output.mkdir(parents=True, exist_ok=False)
        ArtifactStore.write_json(output / "binding.json", binding)
        setup_seconds = time.perf_counter() - setup_started
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        started = time.perf_counter()
        results = []
        for index, row in enumerate(selected_rows):
            sample = output / f"{index:05d}"
            sample.mkdir()
            source, label = verified_inputs[index]
            rgb_started = time.perf_counter()
            pixels = sample / "input.png"
            with Image.open(source) as image:
                rgb = image.convert("RGB")
                rgb.save(pixels)
            rgb_seconds = time.perf_counter() - rgb_started
            if ArtifactStore.sha256_file(pixels) != label["artifacts_sha256"]["input.png"]:
                raise ValueError("GDC production RGB pixels differ from measured-label input")
            prepare_started = time.perf_counter()
            resized = np.asarray(
                rgb.resize((224, 224), Image.Resampling.BILINEAR), dtype=np.uint8
            ).copy()
            features = torch.from_numpy(resized).permute(2, 0, 1).float().div_(255)
            features = ((features - mean) / std).unsqueeze(0)
            prepare_seconds = time.perf_counter() - prepare_started
            if split == "test" and index == 0:
                EvaluationSeal.compression(
                    self.run, fingerprint, self.initialization, checkpoint_sha256
                )
            prediction_started = time.perf_counter()
            with (
                torch.inference_mode(),
                torch.autocast(
                    device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"
                ),
            ):
                logits = model(features.to(device))
            scores = logits.float().cpu()
            if not torch.isfinite(scores).all():
                raise ValueError("Non-finite GDC model prediction")
            predicted = int(scores.argmax(dim=1).item())
            confidence = float(scores.softmax(dim=1).max().item())
            inference_seconds = time.perf_counter() - prediction_started
            name = CLASSES[predicted]
            x, y = (int(value) for value in name.split("x"))
            selected, encoding_seconds, stdout = encoder.encode(
                pixels, sample / "selected.astc", (x, y), "medium"
            )
            (sample / "selected.txt").write_text(stdout, encoding="utf-8")
            fixed8, fixed8_seconds, stdout = encoder.encode(
                pixels, sample / "fixed8.astc", (8, 8), "medium"
            )
            (sample / "fixed8.txt").write_text(stdout, encoding="utf-8")
            verification_started = time.perf_counter()
            if ArtifactStore.sha256_file(pixels) != label["artifacts_sha256"]["input.png"]:
                raise ValueError("GDC production RGB pixels differ from measured-label input")
            if (
                ArtifactStore.sha256_file(sample / "selected.astc")
                != label["artifacts_sha256"][f"{name}.astc"]
            ):
                raise ValueError("GDC final encoded payload differs from its frozen candidate")
            if (
                ArtifactStore.sha256_file(sample / "fixed8.astc")
                != label["artifacts_sha256"]["8x8.astc"]
            ):
                raise ValueError("GDC fixed8 control differs from its frozen candidate")
            encoder.decode(sample / "selected.astc", sample / "selected.png")
            encoder.decode(sample / "fixed8.astc", sample / "fixed8.png")
            if (
                ArtifactStore.sha256_file(sample / "selected.png")
                != label["artifacts_sha256"][f"{name}.png"]
                or ArtifactStore.sha256_file(sample / "fixed8.png")
                != label["artifacts_sha256"]["8x8.png"]
            ):
                raise ValueError("Fresh GDC decode differs from the frozen reconstruction")
            quality = encoder.psnr_rgb(pixels, sample / "selected.png")
            fixed_quality = encoder.psnr_rgb(pixels, sample / "fixed8.png")
            if MD4.new(source.read_bytes()).hexdigest() != row["fileHash"].lower():
                raise ValueError("GDC original source changed during evaluation")
            receipt = {
                "status": "passed",
                "index": index,
                "path": row["path"],
                "fileHash": row["fileHash"],
                "predicted_class": predicted,
                "predicted_footprint": name,
                "confidence": confidence,
                "label_class": row["class_id"],
                "label_target_met": label["target_met"],
                "label_payload_bytes": label["selected"]["payload_bytes"],
                "rgb_psnr": quality if math.isfinite(quality) else None,
                "lossless": math.isinf(quality),
                "target_met": quality > protocol["target_psnr"],
                "fixed8_rgb_psnr": fixed_quality if math.isfinite(fixed_quality) else None,
                "fixed8_lossless": math.isinf(fixed_quality),
                "fixed8_target_met": fixed_quality > protocol["target_psnr"],
                "payload_bytes": selected.payload_bytes,
                "fixed8_payload_bytes": fixed8.payload_bytes,
                "timings": {
                    "source_rgb_seconds": rgb_seconds,
                    "classifier_preprocessing_seconds": prepare_seconds,
                    "inference_seconds": inference_seconds,
                    "final_encode_seconds": encoding_seconds,
                    "model_pipeline_seconds": rgb_seconds
                    + prepare_seconds
                    + inference_seconds
                    + encoding_seconds,
                    "fixed8_encode_seconds": fixed8_seconds,
                    "fixed8_pipeline_seconds": rgb_seconds + fixed8_seconds,
                    "verification_seconds": time.perf_counter() - verification_started,
                },
                "artifacts_sha256": {
                    path.name: ArtifactStore.sha256_file(path)
                    for path in sorted(sample.iterdir())
                    if path.is_file()
                },
            }
            ArtifactStore.write_json(sample / "receipt.json", receipt)
            results.append(
                {
                    "index": index,
                    "receipt_sha256": ArtifactStore.sha256_file(sample / "receipt.json"),
                }
            )
            ArtifactStore.write_json(output / "progress.json", {"results": results})
            print(f"GDC final compression {index + 1}/{len(selected_rows)}", flush=True)
        if (
            ArtifactStore.sha256_file(checkpoint) != checkpoint_sha256
            or ArtifactStore.sha256_file(encoder.executable) != protocol["encoder_sha256"]
        ):
            raise ValueError("GDC model or codec changed during evaluation")
        if any(
            ArtifactStore.sha256_file(self.run / self.initialization / name) != digest
            for name, digest in training_hashes.items()
        ):
            raise ValueError("GDC training state changed during evaluation")
        receipt = {
            "status": "passed",
            "binding": binding,
            "images": len(results),
            "results": results,
            "setup_seconds": setup_seconds,
            "model_warmup_seconds": warmup_seconds,
            "wall_seconds": time.perf_counter() - started,
            "protocol_sha256": manifest["label_protocol_sha256"],
            "encoder_sha256": protocol["encoder_sha256"],
            "inference_device": str(device),
            "environment": RunEnvironment.capture(),
            "scope": "source RGB project four-square talk reconstruction",
            "data_use": "training diagnostic" if split == "train" else "held-out " + split,
            "quality_audit_excluded_from_model_time": True,
        }
        ArtifactStore.write_json(output / "receipt.json", receipt)
        return receipt
