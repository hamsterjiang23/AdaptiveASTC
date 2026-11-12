"""Audited paired native prediction/encoding measurements on frozen development inputs."""

from __future__ import annotations

import hashlib
import os
import time
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
from reproductions.unity_search_baseline.deployment import (
    UnityDeploymentResult,
    UnityDeploymentTrial,
)
from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding
from reproductions.unity_search_baseline.inference_benchmark import UnityInferenceBenchmark
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P
from reproductions.unity_search_baseline.policy import UnitySearchPolicy


class UnityDeploymentBenchmark:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.config_path = root.resolve(), config_path.resolve()
        self.config = A.read_json(config_path)

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        return UnityInferenceBenchmark.execution_sources(root) | {
            str((root / name).resolve()): A.sha256_file(root / name)
            for name in [
                "reproductions/unity_search_baseline/deployment.py",
                "reproductions/unity_search_baseline/deployment_benchmark.py",
                "script/benchmark_unity_deployment.py",
            ]
        }

    def verify_sources(self, config_sha: str) -> None:
        if A.sha256_file(self.config_path) != config_sha or self.config[
            "sources_sha256"
        ] != self.execution_sources(self.root):
            raise ValueError("Deployment configuration or execution sources changed")

    @staticmethod
    def audit(
        binding: UnityFinalEncoding,
        result: UnityDeploymentResult,
        rows: list[JsonDict],
        decisions: list[JsonDict],
        policies: list[UnitySearchPolicy],
        baseline: dict[str, np.ndarray],
        output: Path,
    ) -> JsonDict:
        """All truth access, decompression, quality checks and writes are outside trial timing."""
        predicted = result.predictions is not None
        if predicted:
            assert result.predictions is not None
            for key, value in result.predictions.items():
                if value.dtype == np.bool_:
                    np.testing.assert_array_equal(value, baseline[key])
                else:
                    np.testing.assert_allclose(value, baseline[key], rtol=0, atol=1e-5)
            if result.choices != [row["predicted_decision"] for row in decisions]:
                raise ValueError("Fresh deployment choices differ from the saved checkpoint audit")
        output.mkdir()
        outcomes = []
        for i, (row, decision, policy, choice, container) in enumerate(
            zip(rows, decisions, policies, result.choices, result.containers, strict=True)
        ):
            candidates, archive, backend, quality = binding.candidate_source(row)
            candidate = candidates[choice["selected_index"]]
            block, preset = candidate["block"], candidate["preset"]
            stem = f"{block}x{block}_{preset}"
            archived = binding.bind(archive / f"{stem}.astc", candidate["astc_sha256"])
            if container != archived.read_bytes():
                raise ValueError("Fresh deployment ASTC differs from the measured native candidate")
            texture = UnityTextureInput.from_row(row)
            with Image.open(row["reference"]) as image:
                rgba = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
            decoded, decode_seconds = backend.decode_payload(
                container[16:], texture.width, texture.height, block, srgb=texture.srgb
            )
            image_path = binding.bind(archive / f"{stem}.png", candidate["decoded_png_sha256"])
            with Image.open(image_path) as image:
                np.testing.assert_array_equal(decoded[::-1], np.asarray(image.convert("RGBA")))
            metrics = quality.measure(
                rgba,
                decoded,
                need_alpha=texture.need_alpha,
                compute_ssim=texture.srgb and not texture.normal,
                normal=texture.normal,
                mip_count=row["metadata"]["mip_count"] if texture.normal else 1,
            )
            binding.verify_metrics(metrics, candidate["metrics"])
            strict = UnityQualityPrediction.strict_quality(
                policy, texture, metrics, decision["original_decision"]["effective_psnr_threshold"]
            )
            if predicted and strict != decision["actual_strict_quality_met"]:
                raise ValueError("Final deployment quality differs from the saved prediction audit")
            path = output / f"{i:05d}.astc"
            path.write_bytes(container)
            if len(container) - 16 != candidate["payload_bytes"]:
                raise ValueError("Final deployment payload size differs")
            outcomes.append(
                {
                    "path": row["path"],
                    "selected_index": choice["selected_index"],
                    "block": block,
                    "preset": preset,
                    "payload_bytes": len(container) - 16,
                    "container_bytes": len(container),
                    "strict_quality_met": strict,
                    "metrics": metrics,
                    "decode_audit_seconds": decode_seconds,
                    "astc_sha256": A.sha256_file(path),
                    "candidate_bytes_and_pixels_match": True,
                }
            )
        if predicted:
            assert result.predictions is not None
            np.savez_compressed(
                output / "predictions.npz",
                channel_mse=result.predictions["channel_mse"],
                channel_zero=result.predictions["channel_zero"],
                zero_probability=result.predictions["zero_probability"],
                image_quality=result.predictions["image_quality"],
            )
        A.write_json(output / "choices.json", {"rows": result.choices})
        return {
            "rows": outcomes,
            "payload_bytes": sum(row["payload_bytes"] for row in outcomes),
            "strict_quality_pass_rate": sum(row["strict_quality_met"] for row in outcomes)
            / len(rows),
            "outputs_sha256": {p.name: A.sha256_file(p) for p in output.iterdir() if p.is_file()},
        }

    def run(self) -> JsonDict:
        config = self.config
        output, report = Path(config["output"]).resolve(), Path(config["report"]).resolve()
        if not output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Deployment artifacts belong in the local experiment directory")
        if report.exists() or report.is_relative_to(output):
            raise FileExistsError("Use a fresh deployment identity and separate report")
        if any(type(config[k]) is not int or config[k] < 1 for k in ["warmups", "repetitions"]):
            raise ValueError("Explicit positive warmup and measured repetitions required")
        if not isinstance(config["dependencies"], list) or not config["dependencies"]:
            raise ValueError("Deployment benchmark requires bound CUDA job dependencies")
        config_sha = A.sha256_file(self.config_path)
        if A.read_json(self.config_path) != config:
            raise ValueError("Deployment configuration changed before measurement")
        self.verify_sources(config_sha)
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        state: JsonDict = {
            "status": "waiting_dependencies",
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
            self.verify_sources(config_sha)
            if psutil.virtual_memory().available < 4 * 1024**3:
                raise RuntimeError("Insufficient RAM for deployment smoke")
            encoding_path = Path(config["encoding_config"])
            if A.sha256_file(encoding_path) != config["encoding_config_sha256"]:
                raise ValueError("Deployment encoding binding changed")
            binding = UnityFinalEncoding(self.root, encoding_path)
            rows, decisions, policies, training = binding.prepare()
            settings = training["config"]
            for path, digest in settings["source_sha256"].items():
                binding.bind(Path(path), digest)
            specs, backends = [], []
            for row in rows:
                binding.bind(Path(row["reference"]), row["reference_sha256"])
                candidates, archive, backend, _ = binding.candidate_source(row)
                for candidate in candidates:
                    stem = f"{candidate['block']}x{candidate['block']}_{candidate['preset']}"
                    binding.bind(archive / f"{stem}.astc", candidate["astc_sha256"])
                    binding.bind(archive / f"{stem}.png", candidate["decoded_png_sha256"])
                spec = UnityInferenceTexture(
                    Path(row["reference"]),
                    row["import_metadata"]["srgb"],
                    row["metadata"]["is_normal"],
                    row["metadata"]["need_alpha"],
                    row["metadata"]["mip_count"] if row["metadata"]["is_normal"] else 1,
                )
                with Image.open(spec.reference) as image:
                    pixels = np.asarray(image.convert("RGBA"), dtype=np.uint8)
                rgba = np.ascontiguousarray(pixels[::-1])
                options = row["actual_options"]
                if (
                    hashlib.sha256(rgba.tobytes()).hexdigest() != options["rgba_sha256"]
                    or options["need_alpha"] is not spec.need_alpha
                    or options["profile"] != (0 if spec.srgb else 1)
                    or options["normal_pack"] is not False
                    or options["channel"] != 4
                ):
                    raise ValueError("Deployment encoder inputs differ from original capture")
                if UnityDeploymentTrial.texture_input(pixels, spec) != UnityTextureInput.from_row(
                    row
                ):
                    raise ValueError("Pixel-derived deployment policy inputs differ from training")
                specs.append(spec)
                backends.append(backend)
            state["binding_and_backend_load_seconds"] = time.perf_counter() - active_started
            before = time.perf_counter()
            device = ExperimentRuntime.configure(settings["seed"])
            if device.type != "cuda":
                raise RuntimeError("Native deployment measurement requires CUDA")
            free, total = torch.cuda.mem_get_info(device)
            if free < 2 * 1024**3:
                raise RuntimeError("Insufficient VRAM for deployment smoke")
            checkpoint = torch.load(
                Path(settings["output"]) / "best.pt", map_location="cpu", weights_only=False
            )
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            torch.cuda.synchronize(device)
            state.update(
                status="running",
                config=config,
                checkpoint_sha256=training["checkpoint_sha256"],
                model_load_and_cuda_init_seconds=time.perf_counter() - before,
                gpu=torch.cuda.get_device_name(device),
                free_vram_before_bytes=free,
                total_vram_bytes=total,
                parameters=sum(p.numel() for p in model.parameters()),
                checkpoint_bytes=(Path(settings["output"]) / "best.pt").stat().st_size,
                validation_images=len(rows),
                source_files_sha256=config["sources_sha256"],
            )
            predictor = UnityQualityInference(
                model,
                device,
                settings["validation_batch_size"],
                settings["zero_probability_threshold"],
            )
            trial = UnityDeploymentTrial(
                specs,
                policies,
                backends,
                predictor,
                A.read_json(Path(settings["corpus"]) / "corpus.json")["config"]["patch_size"],
                binding.config["fixed8_preset"],
            )
            with np.load(
                Path(settings["output"]) / "best-validation.npz", allow_pickle=False
            ) as saved:
                baseline = {key: saved[key].copy() for key in saved.files}
            torch.cuda.reset_peak_memory_stats(device)
            for repeat in range(config["warmups"] + config["repetitions"]):
                order = ["prediction", "fixed8"] if repeat % 2 == 0 else ["fixed8", "prediction"]
                record: JsonDict = {
                    "repetition": repeat,
                    "warmup": repeat < config["warmups"],
                    "order": order,
                    "arms": {},
                }
                # Complete both timed arms before any truth audit or artifact writes.
                results = {arm: trial.run(predicted=arm == "prediction") for arm in order}
                for arm, result in results.items():
                    before = time.perf_counter()
                    outcome = self.audit(
                        binding,
                        result,
                        rows,
                        decisions,
                        policies,
                        baseline,
                        output / f"{repeat:02d}-{arm}",
                    )
                    record["arms"][arm] = {
                        "timings": result.timings,
                        "audit": outcome,
                        "audit_and_write_seconds": time.perf_counter() - before,
                    }
                state["measurements"].append(record)
                A.write_json(report, state)
            for path, digest in binding.inputs.items():
                binding.bind(Path(path), digest)
            fresh = UnityFinalEncoding(self.root, encoding_path)
            _, fresh_decisions, _, _ = fresh.prepare()
            if fresh_decisions != decisions or fresh.resolver.origins != binding.resolver.origins:
                raise ValueError("Original policy changed during deployment measurement")
            self.verify_sources(config_sha)
            measured = [row for row in state["measurements"] if not row["warmup"]]
            state.update(
                status="passed",
                wall_seconds=time.perf_counter() - started,
                active_seconds=time.perf_counter() - active_started,
                peak_vram_bytes=torch.cuda.max_memory_allocated(device),
                inputs_sha256=binding.inputs,
                summary={
                    arm: {
                        "median_end_to_end_seconds": float(
                            np.median(
                                [r["arms"][arm]["timings"]["end_to_end_seconds"] for r in measured]
                            )
                        ),
                        "measured_encoding_calls": sum(
                            r["arms"][arm]["timings"]["encoding_calls"] for r in measured
                        ),
                        "warmup_encoding_calls": config["warmups"] * len(rows),
                        "payload_bytes": measured[-1]["arms"][arm]["audit"]["payload_bytes"],
                        "strict_quality_pass_rate": measured[-1]["arms"][arm]["audit"][
                            "strict_quality_pass_rate"
                        ],
                    }
                    for arm in ["prediction", "fixed8"]
                },
                scope=(
                    "Development mip0 smoke; warm model/DLL and filesystem; "
                    "no production or equal-quality speedup claim"
                ),
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
