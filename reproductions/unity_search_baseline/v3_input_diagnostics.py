"""Save full validation quality predictions for the five V3 model/input controls."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import cast

import numpy as np
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.data.unity_v3_input import (
    SourceInputMode,
    SourceTextureSpec,
    UnityV3InferenceInput,
)
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_v3_trainer import UnityV3Prediction
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.v3_policy import UnityV3Policy


class UnityV3InputDiagnostics:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.public = root / "experiment report/unity-v3-20261113"
        self.output = root / "experiment report/.local/unity-v3-20261113/input-diagnostics"

    def pixel_differences(
        self,
        entries: list[JsonDict],
        specs: list[SourceTextureSpec],
        textures: list[UnityInferenceTexture],
    ) -> list[JsonDict]:
        """Compare target-aligned decoded sources to their bound Unity reference pixels."""
        differences = []
        for entry, spec, texture in zip(entries, specs, textures, strict=True):
            if A.sha256_file(texture.reference) != entry["row"]["reference_sha256"]:
                raise ValueError("Pixel diagnostics require the original Unity reference")
            pixels = spec.decoded_pixels()
            image = Image.fromarray(pixels)
            size_changed = image.size != (spec.target_width, spec.target_height)
            if size_changed:
                image = image.resize(
                    (spec.target_width, spec.target_height), Image.Resampling.BICUBIC
                )
            aligned = np.asarray(image, dtype=np.uint8)
            with Image.open(texture.reference) as reference_image:
                reference = np.asarray(reference_image.convert("RGBA"), dtype=np.uint8)
            if reference.shape != aligned.shape:
                raise ValueError("Aligned source and Unity target dimensions differ")
            delta = aligned.astype(np.float32) - reference.astype(np.float32)
            differences.append(
                {
                    "asset": spec.asset,
                    "source_size_changed": size_changed,
                    "aligned_rgb_changed": not np.array_equal(aligned[..., :3], reference[..., :3]),
                    "aligned_alpha_changed": not np.array_equal(aligned[..., 3], reference[..., 3]),
                    "aligned_channel_rmse_255": np.sqrt(
                        np.mean(delta * delta, axis=(0, 1), dtype=np.float64)
                    ).tolist(),
                    "aligned_channel_max_error_255": np.max(np.abs(delta), axis=(0, 1)).tolist(),
                    "aligned_rgba_sha256": hashlib.sha256(aligned.tobytes()).hexdigest(),
                    "reference_rgba_sha256": hashlib.sha256(reference.tobytes()).hexdigest(),
                    "normal": spec.normal,
                    "srgb": spec.srgb,
                    "need_alpha": spec.need_alpha,
                }
            )
        return differences

    @staticmethod
    def group_indices(differences: list[JsonDict]) -> dict[str, list[int]]:
        groups = {
            "all": list(range(len(differences))),
            "normal": [i for i, row in enumerate(differences) if row["normal"]],
            "linear_color": [
                i for i, row in enumerate(differences) if not row["normal"] and not row["srgb"]
            ],
            "srgb_color": [
                i for i, row in enumerate(differences) if not row["normal"] and row["srgb"]
            ],
        }
        for name in [
            "source_size_changed",
            "aligned_rgb_changed",
            "aligned_alpha_changed",
            "need_alpha",
        ]:
            for flag in [False, True]:
                groups[f"{name}={str(flag).lower()}"] = [
                    i for i, row in enumerate(differences) if row[name] == flag
                ]
        return {name: indices for name, indices in groups.items() if indices}

    def run(self, entries: list[JsonDict], controls: list[JsonDict]) -> JsonDict:
        setup_started = time.perf_counter()
        device = ExperimentRuntime.configure(20261112)
        if device.type != "cuda":
            raise RuntimeError("V3 complete-image diagnostics require CUDA")
        torch.cuda.synchronize(device)
        runtime_setup_seconds = time.perf_counter() - setup_started
        self.output.mkdir(parents=True, exist_ok=False)
        manifest_path = self.output.parent / "source-manifest.json"
        manifest = A.read_json(manifest_path)
        lookup = {row["asset"]: row for row in manifest["splits"]["validation"]}
        specs: list[SourceTextureSpec] = []
        textures: list[UnityInferenceTexture] = []
        for entry in entries:
            row = lookup[entry["row"]["path"]]
            specs.append(
                SourceTextureSpec(
                    Path(row["source"]),
                    row["source_width"],
                    row["source_height"],
                    row["target_width"],
                    row["target_height"],
                    row["srgb"],
                    row["normal"],
                    row["need_alpha"],
                    row["normal_metric_mips"],
                    row["asset"],
                    row["source_sha256"],
                )
            )
            textures.append(
                UnityInferenceTexture(
                    Path(entry["row"]["reference"]),
                    row["srgb"],
                    row["normal"],
                    row["need_alpha"],
                    row["normal_metric_mips"],
                )
            )
        differences = self.pixel_differences(entries, specs, textures)
        groups = self.group_indices(differences)
        evidence = A.read_json(self.root / "experiment plan/V3/evidence.json")
        encoder = Path(evidence["binaries"]["astcenc-avx2-shared.dll"])
        quality_receipt = Path(evidence["binaries"]["build-receipt.json"])
        started = time.perf_counter()
        UnityASTCBackend(encoder, evidence["files_sha256"][str(encoder)])
        encoder_setup_seconds = time.perf_counter() - started
        started = time.perf_counter()
        UnityQuality(quality_receipt)
        quality_setup_seconds = time.perf_counter() - started
        reports = []
        seen: set[tuple[str, str]] = set()
        for control in controls:
            key = (control["checkpoint"], control["input_mode"])
            if key in seen or control["arm"] != "pure":
                continue
            seen.add(key)
            started = time.perf_counter()
            expected = control["checkpoint_sha256"]
            if A.sha256_file(Path(key[0])) != expected:
                raise ValueError("A diagnostic checkpoint changed after its real benchmark")
            checkpoint_started = time.perf_counter()
            checkpoint = torch.load(key[0], map_location="cpu", weights_only=False)
            checkpoint_read_seconds = time.perf_counter() - checkpoint_started
            if A.sha256_file(Path(key[0])) != expected:
                raise ValueError("A diagnostic checkpoint changed while loading")
            torch.cuda.synchronize(device)
            model_started = time.perf_counter()
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            torch.cuda.synchronize(device)
            model_construct_and_device_seconds = time.perf_counter() - model_started
            predictor = UnityQualityInference(model, device, 16)
            if key[1] == "unity":
                dataset = UnityInferenceInput(textures)
                contexts = [entry["texture"] for entry in entries]
            else:
                source = UnityV3InferenceInput(specs, cast(SourceInputMode, key[1]))
                dataset = cast(UnityInferenceInput, source)
                contexts = source.decision_inputs
            predictions, timings = predictor.run(dataset)
            metrics, observations = UnityV3Prediction.score(
                [entry["row"] for entry in entries],
                [entry["policy"] for entry in entries],
                predictions["channel_mse"],
                predictions["channel_zero"],
                predictions["image_quality"],
                contexts,
            )
            if control["candidate_set"] != "full20" or any(
                metrics[name] != control["metrics"][name]
                for name in ["accuracy", "full_choice_accuracy"]
            ):
                raise ValueError("Fresh quality predictions differ from the real full20 benchmark")
            target = np.array(
                [
                    [
                        [
                            q[name] if q[name] is not None else np.nan
                            for name in ["ms_ssim_db", "normal_mean_deg", "normal_p95_deg"]
                        ]
                        for q in entry["row"]["image_quality"]
                    ]
                    for entry in entries
                ]
            )
            errors: JsonDict = {}
            for column, name in enumerate(["ms_ssim_db", "normal_mean_deg", "normal_p95_deg"]):
                valid = np.isfinite(target[:, :, column])
                values = predictions["image_quality"][:, :, column] - target[:, :, column]
                errors[name] = float(np.sqrt(np.mean(values[valid] ** 2))) if valid.any() else None
            archive = self.output / f"{len(reports):02}-{key[1]}.npz"
            np.savez_compressed(
                archive,
                channel_mse=predictions["channel_mse"],
                channel_zero=predictions["channel_zero"],
                zero_probability=predictions["zero_probability"],
                image_quality=predictions["image_quality"],
            )
            reports.append(
                {
                    "checkpoint": key[0],
                    "checkpoint_sha256": A.sha256_file(Path(key[0])),
                    "input_mode": key[1],
                    "model_setup_seconds": {
                        "checkpoint_read": checkpoint_read_seconds,
                        "construct_and_device": model_construct_and_device_seconds,
                        "scope": "Diagnostic-process measurements, Python imports excluded",
                    },
                    "metrics": metrics,
                    "quality_rmse": errors,
                    "groups": {
                        name: {
                            "images": len(indices),
                            "accuracy": float(
                                np.mean([observations[i]["footprint_match"] for i in indices])
                            ),
                            "full_choice_accuracy": float(
                                np.mean([observations[i]["full_choice_match"] for i in indices])
                            ),
                            "strict_quality_pass_rate": float(
                                np.mean(
                                    [observations[i]["actual_strict_quality_met"] for i in indices]
                                )
                            ),
                        }
                        for name, indices in groups.items()
                    },
                    "input_context_differences": {
                        "black_pixel_ratio_changed": sum(
                            a.black_pixel_ratio != e["texture"].black_pixel_ratio
                            for a, e in zip(contexts, entries, strict=True)
                        ),
                        "alpha_constant_changed": sum(
                            a.alpha_constant != e["texture"].alpha_constant
                            for a, e in zip(contexts, entries, strict=True)
                        ),
                        "effective_psnr_threshold_changed": sum(
                            UnityV3Policy(e["policy"]).effective_threshold(a)
                            != UnityV3Policy(e["policy"]).effective_threshold(e["texture"])
                            for a, e in zip(contexts, entries, strict=True)
                        ),
                    },
                    "predictions": str(archive),
                    "predictions_sha256": A.sha256_file(archive),
                    "inference_timings": timings,
                    "wall_seconds": time.perf_counter() - started,
                }
            )
        result = {
            "status": "passed",
            "images": len(entries),
            "controls": reports,
            "pixel_differences": differences,
            "group_indices": groups,
            "binary_setup_seconds": {
                "encoder_constructor_and_identity_checks": encoder_setup_seconds,
                "quality_constructor_and_identity_checks": quality_setup_seconds,
                "scope": "Separate final diagnostic process, Python imports excluded",
            },
            "test_opened": False,
            "training_updates": 0,
            "runtime_and_cuda_context_setup_seconds": runtime_setup_seconds,
            "source_manifest_sha256": A.sha256_file(manifest_path),
            "execution_source_sha256": A.sha256_file(Path(__file__)),
            "scope": "Fresh complete-image quality prediction diagnostics; no encoding timing",
        }
        A.write_json(self.public / "input-diagnostics.json", result)
        return result
