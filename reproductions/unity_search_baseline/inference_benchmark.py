"""Measure input-only native CUDA inference after a frozen training job exits."""

from __future__ import annotations

import os
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import psutil
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


class UnityInferenceBenchmark:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.config_path = root.resolve(), config_path.resolve()
        self.config = A.read_json(config_path)

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "src/adaptive_astc/data/unity_inference.py",
            "src/adaptive_astc/evaluation/unity_inference.py",
            "src/adaptive_astc/data/unity_patch_dataset.py",
            "src/adaptive_astc/data/patch_targets.py",
            "src/adaptive_astc/models/unity_quality.py",
            "src/adaptive_astc/utils/runtime.py",
            "reproductions/unity_search_baseline/inference_benchmark.py",
            "reproductions/unity_search_baseline/native_data_pipeline.py",
            "script/benchmark_unity_inference.py",
        ]
        return UnityFinalEncoding.execution_sources(root) | {
            str((root / name).resolve()): A.sha256_file(root / name) for name in names
        }

    def run(self) -> JsonDict:
        config = self.config
        output, report = Path(config["output"]).resolve(), Path(config["report"]).resolve()
        if not output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Inference artifacts belong in the local experiment directory")
        if report.exists() or report.is_relative_to(output):
            raise FileExistsError("Use a fresh inference measurement identity")
        if type(config["repetitions"]) is not int or config["repetitions"] < 1:
            raise ValueError("Positive measured repetitions required")
        if type(config["warmups"]) is not int or config["warmups"] < 1:
            raise ValueError("At least one explicit warmup required")
        if not isinstance(config["dependencies"], list) or not config["dependencies"]:
            raise ValueError("Inference measurement requires a bound training dependency")
        if A.read_json(self.config_path) != config:
            raise ValueError("Inference configuration changed before measurement")
        if config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Inference source bindings changed or are incomplete")
        config_sha = A.sha256_file(self.config_path)
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        state: JsonDict = {
            "status": "waiting_training",
            "measurements": [],
            "test_opened": False,
            "training_updates": 0,
        }
        initial = output / "initial.json"
        A.write_json(initial, state)
        os.link(initial, report)
        initial.unlink()
        started = time.perf_counter()
        try:
            while True:
                state["dependencies"] = [
                    P.dependency_status(item) for item in config["dependencies"]
                ]
                A.write_json(report, state)
                if all(item["status"] == "passed" for item in state["dependencies"]):
                    break
                time.sleep(15)
            state["dependency_wait_seconds"] = time.perf_counter() - started
            active_started = time.perf_counter()
            if A.sha256_file(self.config_path) != config_sha or config[
                "sources_sha256"
            ] != self.execution_sources(self.root):
                raise ValueError(
                    "Inference configuration or execution sources changed while waiting"
                )
            if psutil.virtual_memory().available < 4 * 1024**3:
                raise RuntimeError("Insufficient RAM for isolated inference smoke")
            encoding_config = Path(config["encoding_config"])
            if A.sha256_file(encoding_config) != config["encoding_config_sha256"]:
                raise ValueError("Saved prediction binding changed")
            binding = UnityFinalEncoding(self.root, encoding_config)
            rows, decisions, policies, training = binding.prepare()
            settings = training["config"]
            for path, digest in settings["source_sha256"].items():
                binding.bind(Path(path), digest)
            for row in rows:
                binding.bind(Path(row["reference"]), row["reference_sha256"])
                binding.bind(Path(row["targets"]), row["target_sha256"])
            specs = [
                UnityInferenceTexture(
                    Path(row["reference"]),
                    row["import_metadata"]["srgb"],
                    row["metadata"]["is_normal"],
                    row["metadata"]["need_alpha"],
                    row["metadata"]["mip_count"] if row["metadata"]["is_normal"] else 1,
                )
                for row in rows
            ]
            expected_dataset = UnityPatchDataset(
                Path(settings["corpus"]), "validation", expected_sha256=settings["corpus_sha256"]
            )
            inputs = UnityInferenceInput(specs, expected_dataset.patch_size)
            for i in range(len(inputs)):
                actual, expected = inputs[i], expected_dataset[i]
                for key, value in actual.items():
                    torch.testing.assert_close(value, expected[key], rtol=0, atol=0)
            np.testing.assert_array_equal(inputs.input_metadata, expected_dataset.input_metadata)
            state["input_parity_patches"] = len(inputs)
            state["input_binding_audit_seconds"] = time.perf_counter() - active_started
            device = ExperimentRuntime.configure(settings["seed"])
            if device.type != "cuda":
                raise RuntimeError("Native inference latency measurement requires CUDA")
            free, total = torch.cuda.mem_get_info(device)
            if free < 2 * 1024**3:
                raise RuntimeError("Insufficient free VRAM for native inference smoke")
            before = time.perf_counter()
            checkpoint = torch.load(
                Path(settings["output"]) / "best.pt", map_location="cpu", weights_only=False
            )
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            torch.cuda.synchronize(device)
            state.update(
                status="running",
                config=config,
                checkpoint_sha256=training["checkpoint_sha256"],
                model_load_seconds=time.perf_counter() - before,
                gpu=torch.cuda.get_device_name(device),
                free_vram_before_bytes=free,
                total_vram_bytes=total,
                source_files_sha256=config["sources_sha256"],
                scope=(
                    "Saved smoke validation inputs; fresh CUDA inference only; "
                    "encoding and independent test pending"
                ),
            )
            predictor = UnityQualityInference(
                model,
                device,
                settings["validation_batch_size"],
                settings["zero_probability_threshold"],
            )
            torch.cuda.reset_peak_memory_stats(device)
            with np.load(
                Path(settings["output"]) / "best-validation.npz", allow_pickle=False
            ) as saved:
                baseline = {key: saved[key].copy() for key in saved.files}
            for repetition in range(config["warmups"] + config["repetitions"]):
                before = time.perf_counter()
                dataset = UnityInferenceInput(specs, expected_dataset.patch_size)
                preparation = time.perf_counter() - before
                predictions, phases = predictor.run(dataset)
                policy_start = time.perf_counter()
                predicted = [
                    asdict(
                        UnityQualityPrediction.select(
                            policy,
                            UnityTextureInput.from_row(row),
                            predictions["channel_mse"][i],
                            predictions["channel_zero"][i],
                            predictions["image_quality"][i],
                        )
                    )
                    for i, (row, policy) in enumerate(zip(rows, policies, strict=True))
                ]
                policy_seconds = time.perf_counter() - policy_start
                total_seconds = time.perf_counter() - before
                differences = {}
                for key, value in predictions.items():
                    if value.dtype == np.bool_:
                        np.testing.assert_array_equal(value, baseline[key])
                        differences[key] = 0.0
                    else:
                        np.testing.assert_allclose(value, baseline[key], rtol=0, atol=1e-5)
                        differences[key] = float(np.max(np.abs(value - baseline[key])))
                if predicted != [row["predicted_decision"] for row in decisions]:
                    raise ValueError("Fresh CUDA choices differ from the saved checkpoint audit")
                record = {
                    "repetition": repetition,
                    "warmup": repetition < config["warmups"],
                    "reference_and_metadata_seconds": preparation,
                    "inference": phases,
                    "policy_seconds": policy_seconds,
                    "preprocess_inference_decision_seconds": total_seconds,
                    "max_abs_prediction_difference": differences,
                    "choices_match": True,
                }
                state["measurements"].append(record)
                A.write_json(report, state)
            np.savez_compressed(
                output / "predictions.npz",
                channel_mse=predictions["channel_mse"],
                channel_zero=predictions["channel_zero"],
                zero_probability=predictions["zero_probability"],
                image_quality=predictions["image_quality"],
            )
            A.write_json(output / "decisions.json", {"rows": predicted})
            for path, digest in binding.inputs.items():
                binding.bind(Path(path), digest)
            fresh_binding = UnityFinalEncoding(self.root, encoding_config)
            _, fresh_decisions, _, _ = fresh_binding.prepare()
            if (
                fresh_decisions != decisions
                or fresh_binding.resolver.origins != binding.resolver.origins
            ):
                raise ValueError("Native policy origin changed during inference measurement")
            if A.sha256_file(self.config_path) != config_sha or config[
                "sources_sha256"
            ] != self.execution_sources(self.root):
                raise ValueError("Inference configuration or execution sources changed")
            measured = [row for row in state["measurements"] if not row["warmup"]]
            state.update(
                status="passed",
                wall_seconds=time.perf_counter() - started,
                active_seconds=time.perf_counter() - active_started,
                peak_vram_bytes=torch.cuda.max_memory_allocated(device),
                median_preprocess_inference_decision_seconds=float(
                    np.median([row["preprocess_inference_decision_seconds"] for row in measured])
                ),
                deployment_end_to_end_seconds=None,
                encoding_calls=0,
                inputs_sha256=binding.inputs,
                outputs_sha256={
                    name: A.sha256_file(output / name)
                    for name in ["predictions.npz", "decisions.json"]
                },
            )
        except BaseException as error:
            state.update(
                status="failed", error=repr(error), wall_seconds=time.perf_counter() - started
            )
            A.write_json(output / "receipt.json", state)
            A.write_json(report, state)
            raise
        A.write_json(output / "receipt.json", state)
        A.write_json(report, state)
        return state
