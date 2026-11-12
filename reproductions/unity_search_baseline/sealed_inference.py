"""Exercise the native inference seal with completed development captures and CUDA."""

from __future__ import annotations

import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal
from reproductions.unity_search_baseline.capture_policy import (
    UnityCapturePolicyAudit,
    UnityCapturePolicyBinding,
)
from reproductions.unity_search_baseline.collection import UnityReferenceSeries
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


class UnitySealedInferenceSmoke:
    """Development-only integration; final confirmation evaluation is a separate caller."""

    def __init__(self, root: Path, path: Path) -> None:
        self.root, self.path = root.resolve(), path.resolve()
        self.config = A.read_json(self.path)
        self.inputs: dict[str, str | None] = {}
        self.bind(self.path)
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Sealed inference execution sources changed")
        for name, digest in self.config["sources_sha256"].items():
            self.bind(self.root / name, digest)
        if self.config["split"] != "validation" or self.config["images"] != 2:
            raise ValueError(
                "This integration entry is restricted to the two validation smoke images"
            )

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "src/adaptive_astc/data/unity_capture_input.py",
            "src/adaptive_astc/data/unity_inference.py",
            "src/adaptive_astc/data/patch_targets.py",
            "src/adaptive_astc/data/unity_patch_dataset.py",
            "src/adaptive_astc/evaluation/unity_inference.py",
            "src/adaptive_astc/evaluation/unity_quality.py",
            "src/adaptive_astc/models/unity_quality.py",
            "src/adaptive_astc/utils/runtime.py",
            "src/adaptive_astc/utils/unity_evaluation_seal.py",
            "reproductions/unity_search_baseline/sealed_inference.py",
            "script/verify_unity_sealed_inference.py",
        ]
        return UnityCapturePolicyAudit.execution_sources(root) | {
            name: A.sha256_file(root / name) for name in names
        }

    def bind(self, path: Path, expected: str | None = None) -> Path:
        path = path.resolve()
        digest = A.sha256_file(path)
        if (expected is not None and digest != expected) or (
            str(path) in self.inputs and self.inputs[str(path)] != digest
        ):
            raise ValueError(f"Sealed inference evidence changed: {path}")
        self.inputs[str(path)] = digest
        return path

    def bound_json(self, item: JsonDict) -> JsonDict:
        return A.read_json(self.bind(Path(item["path"]), item["sha256"]))

    @staticmethod
    def verify_checkpoint(checkpoint: JsonDict, training: JsonDict) -> None:
        # Torch keeps tuples; JSON restores lists. Match the trainer's canonical audit.
        if (
            A.fingerprint(checkpoint["config"]) != A.fingerprint(training["config"])
            or checkpoint["epoch"] != training["checkpoint_audit"]["epoch"]
        ):
            raise ValueError("Selected checkpoint settings or epoch changed")

    def prepare(self) -> tuple[UnityCaptureInputAdapter, UnityCapturePolicyBinding, JsonDict]:
        job = self.config["training_job"]
        if P.dependency_status(job)["status"] != "passed":
            raise ValueError("Sealed inference requires a successfully exited training process")
        job_path = self.bind(Path(job["job_config"]), job["sha256"])
        self.bind(job_path.with_name("receipt.json"))
        training = self.bound_json(self.config["training_report"])
        settings, audit = training["config"], training["checkpoint_audit"]
        if (
            training["status"] not in {"passed_smoke", "completed"}
            or audit["status"] != "passed"
            or training["test_opened"] is not False
            or training["checkpoint_sha256"] != audit["checkpoint_sha256"]
            or training["best_artifacts_sha256"] != audit["selected_artifacts_sha256"]
        ):
            raise ValueError("Training result lacks a completed selected-checkpoint audit")
        command = A.read_json(job_path)["command"]
        if len(command) != 5 or command[:4] != [
            sys.executable,
            "-u",
            "script/train_unity_quality.py",
            "--config",
        ]:
            raise ValueError("Training job does not run the native trainer")
        trained_config = A.read_json(self.bind(Path(command[-1])))
        if any(settings.get(key) != value for key, value in trained_config.items()):
            raise ValueError("Training report settings differ from the launched configuration")
        if (
            Path(trained_config["report"]).resolve()
            != Path(self.config["training_report"]["path"]).resolve()
        ):
            raise ValueError("Training job does not produce the supplied training report")
        for name, digest in settings["source_sha256"].items():
            self.bind(Path(name), digest)
        for name, digest in training["best_artifacts_sha256"].items():
            self.bind(Path(settings["output"]) / name, digest)
        if A.read_json(self.bind(Path(settings["output"]) / "config.json")) != settings:
            raise ValueError("Training configuration differs from the saved selected model")

        self.bound_json(self.config["series_config"])
        series = UnityReferenceSeries(self.root, Path(self.config["series_config"]["path"]))
        _, batches = series.validate()
        report = self.bound_json(self.config["series_report"])
        if (
            report["status"] != "passed"
            or report["counts"] != {"train": 64, "validation": 2}
            or report["configuration_sha256"] != self.config["series_config"]["sha256"]
            or Path(report["manifest"]).resolve() != (series.output / "manifest.json").resolve()
            or Path(series.report).resolve() != Path(self.config["series_report"]["path"]).resolve()
        ):
            raise ValueError("Require the completed frozen development66 series")
        manifest = A.read_json(self.bind(Path(report["manifest"]), report["manifest_sha256"]))
        selected = [b for b in batches if b["split"] == "validation"]
        if len(selected) != 1:
            raise ValueError("Validation smoke must have one original capture batch")
        batch = selected[0]
        self.bind(Path(batch["path"]), batch["config_sha256"])
        baseline = series.baseline(batch["config"])
        phase = batch["config"]["phase"]
        if not (baseline.run_dir / f"references/normalized-{phase}/receipt.json").is_file():
            raise FileNotFoundError("Require already archived development pixels")
        rows, binding = series.verify_batch(batch)
        if rows != manifest["splits"]["validation"] or binding not in report["batches"]:
            raise ValueError("Validation capture differs from the completed development manifest")
        self.bind(Path(binding["options_receipt"]), binding["options_sha256"])
        policy = UnityCapturePolicyBinding(
            baseline,
            phase,
            reference_sha256=binding["reference_receipt_sha256"],
            phase_sha256=binding["phase_receipt_sha256"],
        )
        for name, digest in policy.inputs.items():
            if name in self.inputs and self.inputs[name] != digest:
                raise ValueError("Conflicting native policy file bindings")
            self.inputs[name] = digest
        adapter = UnityCaptureInputAdapter(rows, "validation")
        expected = A.read_json(Path(settings["output"]) / "best-decisions.json")
        if [row["path"] for row in expected["rows"]] != [row["path"] for row in adapter.bindings]:
            raise ValueError("Captured validation order differs from the model selection data")
        for row in adapter.bindings:
            self.bind(Path(row["reference_png"]), row["reference_sha256"])
        return adapter, policy, training

    def run(self) -> JsonDict:
        preparation_started = time.perf_counter()
        output, report = (
            Path(self.config["output"]).resolve(),
            Path(self.config["report"]).resolve(),
        )
        local, public = self.root / "experiment report/.local", self.root / "experiment report"
        if (
            not output.is_relative_to(local)
            or not report.is_relative_to(public)
            or report.is_relative_to(local)
            or output.exists()
            or report.exists()
        ):
            raise ValueError("Require a fresh local output and public report")
        adapter, policy, training = self.prepare()
        preparation_seconds = time.perf_counter() - preparation_started
        # All sources exist after prepare: an existing upstream file cannot be an output.
        if any(Path(name).is_relative_to(output) or report == Path(name) for name in self.inputs):
            raise ValueError("Inference output overlaps its input evidence")
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        started = time.perf_counter()
        state: JsonDict = {
            "status": "preparing",
            "test_opened": False,
            "training_updates": 0,
            "evidence_preparation_seconds": preparation_seconds,
            "scope": "Development validation2 sealed CUDA inference; "
            "no final encoding or confirmation test",
        }
        try:
            settings = training["config"]
            device = ExperimentRuntime.configure(settings["seed"])
            if device.type != "cuda" or torch.cuda.mem_get_info(device)[0] < 2 * 1024**3:
                raise RuntimeError("CUDA with2GiB free VRAM is required")
            before = time.perf_counter()
            checkpoint = torch.load(
                Path(settings["output"]) / "best.pt", map_location="cpu", weights_only=False
            )
            self.verify_checkpoint(checkpoint, training)
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            torch.cuda.synchronize(device)
            state["model_load_seconds"] = time.perf_counter() - before
            predictor = UnityQualityInference(
                model,
                device,
                settings["validation_batch_size"],
                settings["zero_probability_threshold"],
            )
            identity = {
                "schema": "unity_native_inference_v1",
                "split": "validation",
                "cohort_fingerprint": A.fingerprint(
                    {"split": "validation", "inputs": adapter.bindings}
                ),
                "inputs_fingerprint": adapter.fingerprint,
                "policies_fingerprint": A.fingerprint([policy.binding]),
                "model": {
                    "checkpoint_sha256": training["checkpoint_sha256"],
                    "epoch": checkpoint["epoch"],
                    "training_report_sha256": self.config["training_report"]["sha256"],
                },
                "decision": {
                    "patch_size": 240,
                    "batch_size": predictor.batch_size,
                    "zero_probability_threshold": predictor.zero_threshold,
                    "policy": "original_native_search_order",
                    "augmentation": "none",
                },
                "runtime": {
                    "torch": torch.__version__,
                    "numpy": np.__version__,
                    "device": str(device),
                },
                "files_sha256": self.inputs,
            }
            # Validation is development data: separate runs may test different models.
            # The confirmation caller must use a shared cohort registry, not a run directory.
            registry = output / "validation-seal"
            seal = UnityEvaluationSeal(registry, identity)
            state["seal"] = seal.acquire()
            state["seal_path"] = str(seal.path)
            state["status"] = "sealed_before_forward"
            A.write_json(report, state)
            before = time.perf_counter()
            dataset = adapter.dataset()
            state["input_preparation_seconds"] = time.perf_counter() - before
            predictions, timings = seal.forward(lambda: predictor.run(dataset))
            decisions = [
                asdict(
                    UnityQualityPrediction.select(
                        policy.policy,
                        texture,
                        predictions["channel_mse"][i],
                        predictions["channel_zero"][i],
                        predictions["image_quality"][i],
                    )
                )
                for i, texture in enumerate(adapter.decision_inputs)
            ]
            with np.load(
                Path(settings["output"]) / "best-validation.npz", allow_pickle=False
            ) as saved:
                differences = {}
                for key, actual in predictions.items():
                    if actual.dtype == np.bool_:
                        np.testing.assert_array_equal(actual, saved[key])
                        differences[key] = 0.0
                    else:
                        np.testing.assert_allclose(actual, saved[key], rtol=0, atol=1e-5)
                        differences[key] = float(np.max(np.abs(actual - saved[key])))
            expected = A.read_json(Path(settings["output"]) / "best-decisions.json")
            if decisions != [row["predicted_decision"] for row in expected["rows"]]:
                raise ValueError(
                    "Sealed capture-only decisions differ from the training reload audit"
                )
            np.savez_compressed(
                output / "predictions.npz",
                channel_mse=predictions["channel_mse"],
                channel_zero=predictions["channel_zero"],
                zero_probability=predictions["zero_probability"],
                image_quality=predictions["image_quality"],
            )
            A.write_json(output / "decisions.json", {"rows": decisions})
            policy.verify()
            adapter.verify_references()
            seal.verify()
            state.update(
                status="passed",
                images=len(adapter.textures),
                patches=len(dataset),
                timings=timings,
                max_abs_prediction_difference=differences,
                choices_match=True,
                parameters=sum(p.numel() for p in model.parameters()),
                checkpoint_sha256=training["checkpoint_sha256"],
                outputs_sha256={
                    name: A.sha256_file(output / name)
                    for name in ["predictions.npz", "decisions.json"]
                },
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state
