"""Development integration of sealed prediction, one encoding, and capture-only scoring."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal
from reproductions.unity_search_baseline.capture_output import UnityCaptureOutputAudit
from reproductions.unity_search_baseline.deployment import UnityDeploymentTrial
from reproductions.unity_search_baseline.quality import UnityQuality, UnityQualityBuild
from reproductions.unity_search_baseline.sealed_inference import UnitySealedInferenceSmoke
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class UnityCaptureDeploymentSmoke(UnitySealedInferenceSmoke):
    """Development2 only. The reusable scorer has no dependency on candidate archives."""

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/capture_output.py",
            "reproductions/unity_search_baseline/capture_deployment.py",
            "reproductions/unity_search_baseline/deployment.py",
            "reproductions/unity_search_baseline/quality.py",
            "reproductions/unity_search_baseline/native/quality_wrapper.cpp",
            "reproductions/unity_search_baseline/native/CMakeLists.txt",
            "script/benchmark_unity_capture_deployment.py",
        ]
        return UnitySealedInferenceSmoke.execution_sources(root) | {
            name: A.sha256_file(root / name) for name in names
        }

    def quality_backend(self) -> UnityQuality:
        receipt = self.bound_json(self.config["quality_build"])
        binding = receipt["binding"]
        engine = self.bind(Path(binding["engine_source"]), binding["engine_source_sha256"])
        extracted = UnityQualityBuild.extract(engine.read_text(encoding="utf-8-sig"))
        native = self.root / "reproductions/unity_search_baseline/native"
        if (
            hashlib.sha256(extracted.encode()).hexdigest() != binding["extracted_sha256"]
            or A.sha256_file(native / "quality_wrapper.cpp") != binding["wrapper_sha256"]
            or A.sha256_file(native / "CMakeLists.txt") != binding["cmake_sha256"]
        ):
            raise ValueError("Native quality build does not match current extracted engine metrics")
        self.bind(Path(receipt["dll"]), receipt["dll_sha256"])
        return UnityQuality(Path(self.config["quality_build"]["path"]))

    def run(self) -> JsonDict:
        started = time.perf_counter()
        config = self.config
        output, report = Path(config["output"]).resolve(), Path(config["report"]).resolve()
        local, public = self.root / "experiment report/.local", self.root / "experiment report"
        if (
            not output.is_relative_to(local)
            or not report.is_relative_to(public)
            or report.is_relative_to(local)
            or output.exists()
            or report.exists()
            or any(type(config[k]) is not int or config[k] < 1 for k in ["warmups", "repetitions"])
            or config["fixed8_preset"] not in UnityASTCBackend.PRESETS
        ):
            raise ValueError(
                "Require fresh output/report and explicit positive paired trial counts"
            )
        adapter, policy, training = self.prepare()
        identity = A.read_json(Path(policy.binding["capture_run"]) / "identity.json")
        dll = self.bind(
            policy.baseline.project / "Assets/Editor/Astc/Plugins/astcenc-avx2-shared.dll",
            identity["encoder_dlls"]["astcenc-avx2-shared.dll"],
        )
        backend = UnityASTCBackend(dll, identity["encoder_dlls"][dll.name])
        quality = self.quality_backend()
        manifest = A.read_json(Path(self.bound_json(config["series_report"])["manifest"]))
        selections = [row["selection"] for row in manifest["splits"]["validation"]]
        if any(Path(name).is_relative_to(output) or report == Path(name) for name in self.inputs):
            raise ValueError("Deployment output overlaps its input evidence")
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        state: JsonDict = {
            "status": "preparing",
            "config_sha256": A.sha256_file(self.path),
            "evidence_and_backend_seconds": time.perf_counter() - started,
            "measurements": [],
            "test_opened": False,
            "training_updates": 0,
            "scope": "Observed validation2; mip0 only; confirmation evaluator pending",
        }
        try:
            settings = training["config"]
            before = time.perf_counter()
            device = ExperimentRuntime.configure(settings["seed"])
            if device.type != "cuda" or torch.cuda.mem_get_info(device)[0] < 2 * 1024**3:
                raise RuntimeError("CUDA with2GiB free VRAM is required")
            checkpoint = torch.load(
                Path(settings["output"]) / "best.pt", map_location="cpu", weights_only=False
            )
            self.verify_checkpoint(checkpoint, training)
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            torch.cuda.synchronize(device)
            state["model_load_and_cuda_seconds"] = time.perf_counter() - before
            predictor = UnityQualityInference(
                model,
                device,
                settings["validation_batch_size"],
                settings["zero_probability_threshold"],
            )
            trial = UnityDeploymentTrial(
                adapter.textures,
                [policy.policy] * len(adapter.textures),
                [backend] * len(adapter.textures),
                predictor,
                240,
                config["fixed8_preset"],
            )
            contract = {
                "schema": "unity_native_inference_v1",
                "split": "validation",
                "cohort_fingerprint": adapter.fingerprint,
                "inputs_fingerprint": adapter.fingerprint,
                "policies_fingerprint": A.fingerprint([policy.binding]),
                "model": {
                    "checkpoint_sha256": training["checkpoint_sha256"],
                    "epoch": checkpoint["epoch"],
                },
                "decision": {
                    "patch_size": 240,
                    "batch_size": predictor.batch_size,
                    "zero_probability_threshold": predictor.zero_threshold,
                    "fixed8_preset": config["fixed8_preset"],
                    "warmups": config["warmups"],
                    "repetitions": config["repetitions"],
                    "policy": "original_native_search_order",
                },
                "runtime": {
                    "torch": torch.__version__,
                    "numpy": np.__version__,
                    "device": str(device),
                },
                "files_sha256": self.inputs,
            }
            seal = UnityEvaluationSeal(output / "validation-seal", contract)
            state.update(
                seal=seal.acquire(),
                seal_path=str(seal.path),
                status="sealed_before_forward",
                parameters=sum(p.numel() for p in model.parameters()),
                weights_bytes=sum(
                    t.numel() * t.element_size() for t in model.state_dict().values()
                ),
                checkpoint_sha256=training["checkpoint_sha256"],
                gpu=torch.cuda.get_device_name(device),
            )
            A.write_json(report, state)
            first_outputs: dict[str, list[str]] = {}
            for repeat in range(config["warmups"] + config["repetitions"]):
                order = ["prediction", "fixed8"] if repeat % 2 == 0 else ["fixed8", "prediction"]
                # Both measured arms finish before reading labels for scoring or writing outputs.
                results = {}
                for arm in order:
                    seal.verify()
                    results[arm] = (
                        seal.forward(lambda: trial.run(predicted=True))
                        if arm == "prediction"
                        else trial.run(predicted=False)
                    )
                record: JsonDict = {
                    "repetition": repeat,
                    "warmup": repeat < config["warmups"],
                    "order": order,
                    "arms": {},
                }
                for arm, result in results.items():
                    before = time.perf_counter()
                    audit = UnityCaptureOutputAudit.run(
                        adapter,
                        [policy.policy] * len(adapter.textures),
                        [backend] * len(adapter.textures),
                        [quality] * len(adapter.textures),
                        selections,
                        result,
                        output / f"{repeat:02d}-{arm}",
                    )
                    signatures = [A.fingerprint(row) for row in result.choices]
                    signatures += [row["astc_sha256"] for row in audit["rows"]]
                    if arm in first_outputs and signatures != first_outputs[arm]:
                        raise ValueError("Repeated native deployment changed choices or ASTC bytes")
                    first_outputs[arm] = signatures
                    record["arms"][arm] = {
                        "timings": result.timings,
                        "audit": audit,
                        "audit_and_write_seconds": time.perf_counter() - before,
                    }
                state["measurements"].append(record)
                A.write_json(report, state)
            policy.verify()
            adapter.verify_references()
            seal.verify()
            measured = [row for row in state["measurements"] if not row["warmup"]]
            state.update(
                status="passed",
                summary={
                    arm: {
                        **measured[-1]["arms"][arm]["audit"]["summary"],
                        "median_end_to_end_seconds": float(
                            np.median(
                                [
                                    row["arms"][arm]["timings"]["end_to_end_seconds"]
                                    for row in measured
                                ]
                            )
                        ),
                        "measured_encoding_calls": sum(
                            row["arms"][arm]["timings"]["encoding_calls"] for row in measured
                        ),
                        "warmup_encoding_calls": config["warmups"] * len(adapter.textures),
                    }
                    for arm in ["prediction", "fixed8"]
                },
                inputs_sha256=self.inputs,
                original_search_seconds=sum(row["search_ms"] for row in selections) / 1000,
                original_select_and_encode_seconds=sum(
                    row["select_and_encode_ms"] for row in selections
                )
                / 1000,
                latency_scope=(
                    "Warm model/DLL, reference PNG to mip0 ASTC memory; audit/writes excluded; "
                    "original import timing is separate and not a paired speedup"
                ),
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(output / "receipt.json", state)
            A.write_json(report, state)
        return state
