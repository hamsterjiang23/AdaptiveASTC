"""Resumable per-cell real V4 measurements with original archives used only for audit."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import psutil
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceTexture
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.unity_search_baseline.deployment import UnityDeploymentResult
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.v3_policy import UnityV3Policy
from reproductions.unity_search_baseline.v4_experiment import UnityV4Experiment
from reproductions.unity_search_baseline.v4_policy import UnityV4Policy, V4Options
from reproductions.unity_search_baseline.v4_runtime import UnityV4Trial, model_digest


class UnityV4Benchmark:
    def __init__(self, root: Path, *, smoke: bool, attempt: str) -> None:
        if not attempt or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in attempt):
            raise ValueError(
                "Attempt identity requires lowercase letters, digits, dash or underscore"
            )
        self.experiment = UnityV4Experiment(root)
        self.smoke = smoke
        self.name = f"{'smoke32' if smoke else 'benchmark1000'}-{attempt}"
        self.public = self.experiment.public / self.name
        self.private = self.experiment.private / self.name
        self.public.mkdir(parents=True, exist_ok=True)
        self.private.mkdir(parents=True, exist_ok=True)
        self.progress = self.experiment.public / "progress.json"

    def setup(self) -> None:
        self.experiment.prepare()
        self.offline = A.read_json(self.experiment.public / "offline.json")
        if self.offline["status"] != "passed":
            raise ValueError("The complete offline scans must pass first")
        with gzip.open(self.offline["trace_archive"], "rt", encoding="utf-8") as stream:
            if A.sha256_file(Path(self.offline["trace_archive"])) != self.offline["trace_sha256"]:
                raise ValueError("Offline trace identity changed")
            self.expected = json.load(stream)
        self.indices = self.experiment.smoke_indices if self.smoke else list(range(1000))
        self.textures = []
        for entry in self.experiment.entries:
            row, texture = entry["row"], entry["texture"]
            self.textures.append(
                UnityInferenceTexture(
                    Path(row["reference"]),
                    texture.srgb,
                    texture.normal,
                    texture.need_alpha,
                    row["metadata"]["mip_count"] if texture.normal else 1,
                )
            )
            if A.sha256_file(Path(row["reference"])) != row["reference_sha256"]:
                raise ValueError("Unity reference pixels changed")
        source_files = [
            self.experiment.plan / "matrix.json",
            self.experiment.plan / "evidence.json",
            self.experiment.public / "offline.json",
            *sorted((self.experiment.root / "reproductions/unity_search_baseline").glob("v4_*.py")),
            self.experiment.root / "script/run_unity_v4.py",
            self.experiment.root / "script/execute_unity_v4.py",
        ]
        self.binding = {str(path): A.sha256_file(path) for path in source_files}
        self.binding.update(
            {name: record["sha256"] for name, record in self.experiment.evidence["files"].items()}
        )
        self.binding.update(
            {
                str(texture.reference): self.experiment.entries[i]["row"]["reference_sha256"]
                for i, texture in enumerate(self.textures)
            }
        )
        binding_file = self.public / "execution-binding.json"
        if binding_file.exists() and A.read_json(binding_file)["files_sha256"] != self.binding:
            raise ValueError("Resume requires the original execution sources and settings")
        A.write_json(
            binding_file,
            {
                "files_sha256": self.binding,
                "validation_indices": self.indices,
                "frozen_parent_sources": str(self.experiment.plan / "evidence.json"),
            },
        )
        started = time.perf_counter()
        device = ExperimentRuntime.configure(20261112)
        if device.type != "cuda":
            raise RuntimeError("V4 actual model benchmarks require CUDA")
        checkpoint = Path(self.experiment.evidence["artifacts"]["checkpoint"]["path"])
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        self.predictor = UnityQualityInference(
            UnityQualityRegressor.from_checkpoint(state, device), device, 16, 0.5
        )
        self.model_loading_seconds = time.perf_counter() - started
        started = time.perf_counter()
        binaries = self.experiment.evidence["binaries"]
        encoder = binaries["astcenc-avx2-shared.dll"]
        self.backend = UnityASTCBackend(Path(encoder["path"]), encoder["sha256"])
        self.quality = UnityQuality(Path(binaries["build-receipt.json"]["path"]))
        self.binary_loading_seconds = time.perf_counter() - started
        self.before_digest = model_digest(self.predictor)

    def verify(self) -> None:
        for name, digest in self.binding.items():
            if A.sha256_file(Path(name)) != digest:
                raise ValueError(f"V4 execution source changed: {name}")

    def trial(self, indices: list[int], options: V4Options) -> UnityV4Trial:
        return UnityV4Trial(
            [self.textures[i] for i in indices],
            [UnityV3Policy(self.experiment.entries[i]["policy"]) for i in indices],
            self.predictor,
            self.backend,
            self.quality,
            options,
        )

    def measure(self, options: V4Options, scope: str, mode: str) -> UnityDeploymentResult:
        chunk_size = (
            1 if mode == "single" else (8 if scope == "pixels_ready" else len(self.indices))
        )
        results = []
        for offset in range(0, len(self.indices), chunk_size):
            indices = self.indices[offset : offset + chunk_size]
            buffers = None
            if scope == "pixels_ready":
                buffers = []
                for index in indices:
                    with Image.open(self.textures[index].reference) as image:
                        buffers.append(np.asarray(image.convert("RGBA"), dtype=np.uint8))
            result = self.trial(indices, options).run(buffers)
            for index, choice in zip(indices, result.choices, strict=True):
                choice["source_index"] = index
            results.append(result)
        timings: JsonDict = {
            "end_to_end_seconds": sum(r.timings["end_to_end_seconds"] for r in results),
            "encoding_calls": sum(r.timings["encoding_calls"] for r in results),
            "prediction_passes": sum(r.timings["prediction_passes"] for r in results),
            "chunk_images": chunk_size,
            "measurements": [r.timings for r in results],
            "scope": scope,
            "mode": mode,
        }
        if mode == "single":
            timings["single_image_latencies_seconds"] = [
                r.timings["end_to_end_seconds"] for r in results
            ]
        return UnityDeploymentResult(
            [value for r in results for value in r.containers],
            [value for r in results for value in r.choices],
            {
                key: np.concatenate([r.predictions[key] for r in results])
                for key in results[0].predictions
            },
            timings,
        )

    def audit(self, result: UnityDeploymentResult, case: JsonDict, folder: Path) -> JsonDict:
        started = time.perf_counter()
        folder.mkdir(parents=True, exist_ok=False)
        outputs = []
        differences = []
        if result.predictions is None:
            raise ValueError("Replay audit requires this measurement's actual predictions")
        for position, (index, choice, container) in enumerate(
            zip(self.indices, result.choices, result.containers, strict=True)
        ):
            entry = self.experiment.entries[index]
            context = UnityTextureInput(**choice["prediction_context"])
            texture = UnityTextureInput(**choice["gate_context"])
            candidates = UnityQualityPrediction.candidates(
                context,
                result.predictions["channel_mse"][position],
                result.predictions["channel_zero"][position],
                result.predictions["image_quality"][position],
            )
            replay = UnityV4Policy(
                UnityV3Policy(entry["policy"]), V4Options(**case["options"])
            ).search(
                lambda candidate: entry["candidates"][candidate]["metrics"],
                texture,
                candidates,
                prediction_texture=context,
            )
            expected = replay.record()
            frozen = self.expected[case["name"]][index]
            changed = [
                key
                for key in [
                    "selected_index",
                    "measured_indices",
                    "original_start",
                    "adjusted_start",
                ]
                if choice[key] != frozen[key]
            ]
            if changed:
                differences.append(
                    {"index": index, "asset": entry["row"]["path"], "fields": changed}
                )
            choice["frozen_prediction_trace_difference"] = changed
            for key in [
                "selected_index",
                "measured_indices",
                "selection_reason",
                "strict_quality_met",
                "original_start",
                "adjusted_start",
                "gate_events",
                "unlock_event",
            ]:
                if choice[key] != expected[key]:
                    raise ValueError(f"Real execution differs from offline replay: {index} {key}")
            for query in choice["queries"]:
                archived = entry["candidates"][query["selected_index"]]["metrics"]
                for key, value in query["metrics"].items():
                    if (
                        value is not None
                        and archived.get(key) is not None
                        and not np.isclose(value, archived[key], rtol=0, atol=2e-4)
                    ):
                        raise ValueError(
                            f"Real candidate quality differs from archive: {index} {key}"
                        )
            selected = choice["selected_index"]
            block = entry["candidates"][selected]["block"]
            spec = self.textures[index]
            with Image.open(spec.reference) as image:
                reference = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
            decoded, _ = self.backend.decode_payload(
                container[16:],
                entry["texture"].width,
                entry["texture"].height,
                block,
                srgb=spec.srgb,
            )
            measured = self.quality.measure(
                reference,
                decoded,
                need_alpha=spec.need_alpha,
                compute_ssim=spec.srgb and not spec.normal,
                normal=spec.normal,
                mip_count=spec.normal_metric_mips,
            )
            for key, value in measured.items():
                if (
                    value is not None
                    and choice["selected_metrics"].get(key) is not None
                    and not np.isclose(value, choice["selected_metrics"][key], rtol=0, atol=2e-4)
                ):
                    raise ValueError(f"Final ASTC quality audit failed: {index} {key}")
            if len(container) - 16 != entry["row"]["payload_bytes"][selected]:
                raise ValueError("Final payload size differs from canonical geometry")
            astc = folder / f"{index:05d}.astc"
            png = folder / f"{index:05d}.png"
            astc.write_bytes(container)
            Image.fromarray(np.ascontiguousarray(decoded[::-1])).save(png)
            outputs.append(
                {
                    "index": index,
                    "asset": entry["row"]["path"],
                    "astc": str(astc),
                    "astc_sha256": A.sha256_file(astc),
                    "decoded_png": str(png),
                    "decoded_png_sha256": A.sha256_file(png),
                }
            )
        A.write_json(folder / "outputs.json", {"outputs": outputs})
        return {
            "images": len(outputs),
            "manifest": str(folder / "outputs.json"),
            "manifest_sha256": A.sha256_file(folder / "outputs.json"),
            "seconds": time.perf_counter() - started,
            "replay_prediction_source": "this_measurement_fresh_predictions",
            "frozen_prediction_differences": differences,
        }

    def run(self) -> JsonDict:
        lock = self.experiment.private / "native-benchmark.lock"
        if lock.exists():
            owner = A.read_json(lock)
            if psutil.pid_exists(owner["pid"]):
                raise RuntimeError("Another V4 native benchmark is active")
            lock.unlink()
        with lock.open("x", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "attempt": self.name}, stream)
        try:
            return self._run()
        except BaseException as error:
            failure = {
                "status": "failed",
                "error": repr(error),
                "attempt": self.name,
                "utc": datetime.now(UTC).isoformat(),
            }
            A.write_json(self.public / f"failure-{time.time_ns()}.json", failure)
            A.write_json(self.progress, failure)
            raise
        finally:
            lock.unlink()

    def _run(self) -> JsonDict:
        started = time.perf_counter()
        self.setup()
        measurements = []
        scopes = ["files", "pixels_ready"]
        modes = ["batch", "single"]
        repetitions = 1 if self.smoke else 3
        for case in self.offline["controls"]:
            options = V4Options(**case["options"])
            self.trial(self.indices[:8], options).run()
            for scope in scopes:
                for mode in modes:
                    previous_hashes = None
                    for repeat in range(repetitions):
                        unit = f"{case['name']}-{scope}-{mode}-{repeat}"
                        receipt = self.public / f"{unit}.json"
                        if receipt.exists():
                            previous = A.read_json(receipt)
                            if (
                                previous["status"] != "passed"
                                or A.sha256_file(Path(previous["trace"]))
                                != previous["trace_sha256"]
                            ):
                                raise ValueError(
                                    "Preserve failed or changed cells and use a new attempt"
                                )
                            if (
                                A.sha256_file(Path(previous["predictions"]))
                                != previous["predictions_sha256"]
                            ):
                                raise ValueError("Saved predictions changed")
                            manifest = Path(previous["output_audit"]["manifest"])
                            if (
                                A.sha256_file(manifest)
                                != previous["output_audit"]["manifest_sha256"]
                            ):
                                raise ValueError("Saved output manifest changed")
                            for output in A.read_json(manifest)["outputs"]:
                                for key in ["astc", "decoded_png"]:
                                    if A.sha256_file(Path(output[key])) != output[f"{key}_sha256"]:
                                        raise ValueError("Saved native output changed")
                            previous_hashes = previous["astc_sha256"]
                            measurements.append(previous)
                            continue
                        self.verify()
                        A.write_json(
                            self.progress,
                            {
                                "status": "running_smoke" if self.smoke else "running_benchmark",
                                "cell": unit,
                                "completed_cells": len(measurements),
                                "attempt": self.name,
                                "training_updates": 0,
                                "resources": {
                                    "cpu_percent": psutil.cpu_percent(),
                                    "available_ram_bytes": psutil.virtual_memory().available,
                                },
                            },
                        )
                        print(json.dumps({"cell": unit, "status": "running"}), flush=True)
                        result = self.measure(options, scope, mode)
                        hashes = [hashlib.sha256(b).hexdigest() for b in result.containers]
                        if previous_hashes is not None and hashes != previous_hashes:
                            raise ValueError("Repeated native outputs differ")
                        previous_hashes = hashes
                        raw_trace = self.private / f"{unit}-unverified.json.gz"
                        with gzip.open(raw_trace, "xt", encoding="utf-8") as stream:
                            json.dump(
                                {"choices": result.choices, "timings": result.timings}, stream
                            )
                        predictions = self.private / f"{unit}-predictions.npz"
                        if result.predictions is None:
                            raise ValueError("V4 measurement must preserve fresh predictions")
                        np.savez_compressed(
                            predictions,
                            channel_mse=result.predictions["channel_mse"],
                            channel_zero=result.predictions["channel_zero"],
                            zero_probability=result.predictions["zero_probability"],
                            image_quality=result.predictions["image_quality"],
                        )
                        audit = self.audit(result, case, self.private / unit / "outputs")
                        trace = self.private / f"{unit}.json.gz"
                        with gzip.open(trace, "xt", encoding="utf-8") as stream:
                            json.dump(
                                {
                                    "choices": result.choices,
                                    "timings": result.timings,
                                    "astc_sha256": hashes,
                                },
                                stream,
                            )
                        raw_trace.unlink()
                        baseline_choices = result.choices
                        if case["name"] != "v3_baseline":
                            baseline = A.read_json(
                                self.public / f"v3_baseline-{scope}-{mode}-{repeat}.json"
                            )
                            with gzip.open(baseline["trace"], "rt", encoding="utf-8") as stream:
                                baseline_choices = json.load(stream)["choices"]
                        row = {
                            "status": "passed",
                            "case": case,
                            "scope": scope,
                            "mode": mode,
                            "repeat": repeat,
                            "timings": result.timings,
                            "metrics": self.experiment.summarize(
                                result.choices, self.indices, baseline_rows=baseline_choices
                            ),
                            "trace": str(trace),
                            "trace_sha256": A.sha256_file(trace),
                            "astc_sha256": hashes,
                            "predictions": str(predictions),
                            "predictions_sha256": A.sha256_file(predictions),
                            "output_audit": audit,
                        }
                        A.write_json(receipt, row)
                        measurements.append(row)
        self.verify()
        after_digest = model_digest(self.predictor)
        if after_digest != self.before_digest:
            raise ValueError("Model parameters or buffers changed during evaluation")
        report = {
            "status": "passed",
            "smoke": self.smoke,
            "images": len(self.indices),
            "measurements": measurements,
            "model_parameters_and_buffers_unchanged": True,
            "model_digest": after_digest,
            "model_loading_seconds": self.model_loading_seconds,
            "binary_loading_seconds": self.binary_loading_seconds,
            "training_updates": 0,
            "wall_seconds": time.perf_counter() - started,
        }
        A.write_json(self.public / "result.json", report)
        A.write_json(
            self.progress,
            {
                "status": "smoke_passed" if self.smoke else "benchmark_passed",
                "attempt": self.name,
                "result": str(self.public / "result.json"),
                "completed_cells": len(measurements),
                "training_updates": 0,
            },
        )
        return report
