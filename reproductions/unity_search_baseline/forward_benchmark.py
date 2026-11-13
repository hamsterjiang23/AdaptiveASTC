"""Paired validation measurements of fresh prediction, real forward search and fixed8."""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import psutil
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.unity_search_baseline.deployment import (
    UnityDeploymentResult,
    UnityDeploymentTrial,
)
from reproductions.unity_search_baseline.deployment_benchmark import UnityDeploymentBenchmark
from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding
from reproductions.unity_search_baseline.forward_deployment import UnityForwardSearchTrial
from reproductions.unity_search_baseline.inference_benchmark import UnityInferenceBenchmark
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P
from reproductions.unity_search_baseline.system_variant_policy import VariantOutcome
from reproductions.unity_search_baseline.system_variants import UnitySystemVariants
from script.diagnose_unity_rules import UnityRuleDiagnostics


class UnityForwardSearchBenchmark:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.config_path = root.resolve(), config_path.resolve()
        self.config_sha256 = A.sha256_file(self.config_path)
        self.config = A.read_json(self.config_path)

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/forward_deployment.py",
            "reproductions/unity_search_baseline/forward_benchmark.py",
            "reproductions/unity_search_baseline/system_variant_policy.py",
            "reproductions/unity_search_baseline/system_variants.py",
            "script/attribute_unity_errors.py",
            "script/diagnose_unity_rules.py",
            "src/adaptive_astc/data/splitting.py",
            "script/benchmark_unity_forward_search.py",
            "experiment report/.local/unity-v2-20261112/run_forward_search_guarded.py",
        ]
        return UnityDeploymentBenchmark.execution_sources(root) | {
            str((root / name).resolve()): A.sha256_file(root / name) for name in names
        }

    def verify_sources(self) -> None:
        if A.sha256_file(self.config_path) != self.config_sha256 or self.config[
            "sources_sha256"
        ] != self.execution_sources(self.root):
            raise ValueError("Forward benchmark configuration or execution sources changed")

    def expected_trace(self, binding: UnityFinalEncoding) -> JsonDict:
        path = binding.bind(
            Path(self.config["offline_report"]), self.config["offline_report_sha256"]
        )
        offline = A.read_json(path)
        if offline["status"] != "completed" or offline["test_opened"] is not False:
            raise ValueError("Require a completed validation-only offline reference")
        trace_path = binding.bind(
            Path(offline["decisions_archive"]), offline["decisions_archive_sha256"]
        )
        with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                if (
                    record["model"] == "imagenet-resnet34-head-sampled4"
                    and record["prediction_mode"] == "raw"
                    and record["variant"] == "B1_candidate_idx"
                ):
                    if len(record["rows"]) != 1000:
                        raise ValueError("Require the full1000 offline forward reference")
                    return record
        raise ValueError("Selected forward-search offline reference missing")

    @staticmethod
    def audit_forward(
        binding: UnityFinalEncoding,
        result: UnityDeploymentResult,
        rows: list[JsonDict],
        indices: list[int],
        baseline: dict[str, np.ndarray],
        pure_decisions: list[JsonDict],
        expected: JsonDict,
    ) -> JsonDict:
        assert result.predictions is not None
        differences = {}
        for name, actual in result.predictions.items():
            if actual.dtype == np.bool_:
                np.testing.assert_array_equal(actual, baseline[name])
            else:
                np.testing.assert_allclose(actual, baseline[name], rtol=0, atol=1e-5)
            differences[name] = float(
                np.max(np.abs(actual.astype(np.float64) - baseline[name].astype(np.float64)))
            )
        query_count = 0
        for row, source_index, choice in zip(rows, indices, result.choices, strict=True):
            saved = expected["rows"][source_index]
            if (
                saved["path"] != row["path"]
                or choice["source_index"] != source_index
                or choice["starting_decision"] != pure_decisions[source_index]["predicted_decision"]
                or choice["selected_index"] != saved["selected_index"]
                or choice["measured_indices"] != saved["measured_indices"]
                or choice["candidates_measured"] != len(saved["measured_indices"])
                or choice["selection_reason"] != saved["reason"]
            ):
                raise ValueError(
                    "Real forward choices/query order differ from the frozen offline replay"
                )
            candidates, archive, _, _ = binding.candidate_source(row)
            if [query["selected_index"] for query in choice["queries"]] != choice[
                "measured_indices"
            ]:
                raise ValueError("Real measurement receipt order differs from the search queries")
            for query in choice["queries"]:
                index = query["selected_index"]
                candidate = candidates[index]
                stem = f"{candidate['block']}x{candidate['block']}_{candidate['preset']}"
                binding.bind(archive / f"{stem}.astc", candidate["astc_sha256"])
                png = binding.bind(archive / f"{stem}.png", candidate["decoded_png_sha256"])
                if query["container_sha256"] != candidate["astc_sha256"]:
                    raise ValueError("Queried real ASTC differs from the frozen native candidate")
                with Image.open(png) as image:
                    pixels = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
                if (
                    hashlib.sha256(pixels.tobytes()).hexdigest()
                    != query["decoded_native_rgba_sha256"]
                ):
                    raise ValueError("Queried real decoded pixels differ from the frozen archive")
                binding.verify_metrics(query["metrics"], candidate["metrics"])
                query_count += 1
        if query_count != result.timings["encoding_calls"]:
            raise ValueError("Real encoding count differs from actual query receipts")
        return {
            "fresh_prediction_max_abs_difference": differences,
            "starting_choices_exact": True,
            "forward_choices_and_query_order_exact": True,
            "actual_queried_candidates_verified": query_count,
            "all_query_payloads_pixels_and_native_quality_match": True,
        }

    def run(self) -> JsonDict:
        config = self.config
        if (
            config["variant"] != "B1_candidate_idx"
            or config["prediction_mode"] != "raw"
            or type(config["smoke"]) is not bool
            or any(
                type(config[name]) is not int or config[name] < 1
                for name in ["warmups", "repetitions"]
            )
            or config["fixed8_preset"] != "medium"
        ):
            raise ValueError(
                "Require frozen raw candidate-start forward search and explicit paired repeats"
            )
        output, report = Path(config["output"]).resolve(), Path(config["report"]).resolve()
        if (
            not output.is_relative_to(self.root / "experiment report/.local")
            or output.exists()
            or report.exists()
            or report.is_relative_to(output)
        ):
            raise FileExistsError("Use a fresh private output and separate public report")
        self.verify_sources()
        output.mkdir(parents=True, exist_ok=False)
        with report.open("x", encoding="utf-8") as stream:
            stream.write('{"status":"preparing"}\n')
        started = time.perf_counter()
        state: JsonDict = {
            "status": "preparing",
            "config": config,
            "measurements": [],
            "training_updates": 0,
            "test_opened": False,
        }
        active_trial: UnityForwardSearchTrial | None = None
        results: dict[str, UnityDeploymentResult] = {}
        try:
            dependencies = [P.dependency_status(item) for item in config["dependencies"]]
            if not dependencies or any(item["status"] != "passed" for item in dependencies):
                raise ValueError("Frozen model dependency has not completed successfully")
            state["dependencies"] = dependencies
            if psutil.virtual_memory().available < 4 * 1024**3:
                raise RuntimeError("Insufficient RAM for forward-search validation")
            binding_path = Path(config["encoding_config"])
            if A.sha256_file(binding_path) != config["encoding_config_sha256"]:
                raise ValueError("Selected prediction binding changed")
            binding = UnityFinalEncoding(self.root, binding_path)
            all_rows, pure_decisions, all_policies, training = binding.prepare()
            settings = training["config"]
            if len(all_rows) != 1000 or any(row["split"] != "validation" for row in all_rows):
                raise ValueError("Runtime forward search is restricted to validation1000")
            if training["checkpoint_sha256"] != config["checkpoint_sha256"]:
                raise ValueError("Selected frozen model changed")
            archived = UnityInferenceBenchmark(self.root, self.config_path).bind_training_sources(
                binding, settings
            )
            expected = self.expected_trace(binding)
            indices = config["encoding_indices"] if config["smoke"] else list(range(1000))
            if config["smoke"] and (len(indices) != 8 or indices != sorted(set(indices))):
                raise ValueError("Pilot requires eight unique ordered encoding indices")
            rows = [all_rows[index] for index in indices]
            policies = [all_policies[index] for index in indices]
            specs, backends, qualities = [], [], []
            for row in all_rows:
                binding.bind(Path(row["reference"]), row["reference_sha256"])
                _, _, backend, quality = binding.candidate_source(row)
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
                    or UnityDeploymentTrial.texture_input(pixels, spec)
                    != UnityTextureInput.from_row(row)
                ):
                    raise ValueError("Real encoder inputs differ from the original capture")
                specs.append(spec)
                backends.append(backend)
                qualities.append(quality)
            corpus_path = Path(settings["corpus"]) / "corpus.json"
            corpus = A.read_json(binding.bind(corpus_path, settings["corpus_sha256"]))
            expected_dataset = UnityPatchDataset(
                Path(settings["corpus"]), "validation", expected_sha256=settings["corpus_sha256"]
            )
            inputs = UnityInferenceInput(specs, expected_dataset.patch_size)
            for index in range(len(inputs)):
                expected_patch = expected_dataset[index]
                for name, value in inputs[index].items():
                    torch.testing.assert_close(value, expected_patch[name], rtol=0, atol=0)
            np.testing.assert_array_equal(inputs.input_metadata, expected_dataset.input_metadata)
            state.update(
                input_parity_patches=len(inputs),
                binding_and_input_audit_seconds=time.perf_counter() - started,
                inference_images=1000,
                encoded_images=len(indices),
                training_source_binding=archived,
            )
            del inputs, expected_dataset
            self.verify_sources()
            before = time.perf_counter()
            device = ExperimentRuntime.configure(settings["seed"])
            if device.type != "cuda":
                raise RuntimeError("Forward-search inference requires CUDA")
            free, total = torch.cuda.mem_get_info(device)
            if free < 2 * 1024**3:
                raise RuntimeError("Insufficient free VRAM for the selected model")
            checkpoint = torch.load(
                Path(settings["output"]) / "best.pt", map_location="cpu", weights_only=False
            )
            if A.fingerprint(checkpoint["config"]) != A.fingerprint(settings):
                raise ValueError("Selected checkpoint settings changed")
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            torch.cuda.synchronize(device)
            predictor = UnityQualityInference(
                model,
                device,
                settings["validation_batch_size"],
                settings["zero_probability_threshold"],
            )
            state.update(
                status="running",
                gpu=torch.cuda.get_device_name(device),
                free_vram_before_bytes=free,
                total_vram_bytes=total,
                model_load_and_cuda_init_seconds=time.perf_counter() - before,
                checkpoint_sha256=training["checkpoint_sha256"],
                parameters=sum(value.numel() for value in model.parameters()),
            )

            def progress(observation: JsonDict) -> None:
                if observation["completed_images"] % 32 == 0 or observation[
                    "completed_images"
                ] == len(indices):
                    state["active_progress"] = observation
                    A.write_json(report, state)

            active_trial = UnityForwardSearchTrial(
                specs,
                all_policies,
                backends,
                qualities,
                predictor,
                corpus["config"]["patch_size"],
                indices,
                progress,
            )
            fixed_trial = UnityDeploymentTrial(
                [specs[index] for index in indices],
                policies,
                [backends[index] for index in indices],
                predictor,
                corpus["config"]["patch_size"],
                config["fixed8_preset"],
            )
            with np.load(
                Path(settings["output"]) / "best-validation.npz", allow_pickle=False
            ) as saved:
                baseline = {name: saved[name].copy() for name in saved.files}
            entries = UnityRuleDiagnostics(self.config_path).prepare(rows)
            for entry in entries:
                candidates, _, _, _ = binding.candidate_source(entry["row"])
                entry["timings"] = [candidate["timings"] for candidate in candidates]
            torch.cuda.reset_peak_memory_stats(device)
            for repetition in range(config["warmups"] + config["repetitions"]):
                order = ["forward", "fixed8"] if repetition % 2 == 0 else ["fixed8", "forward"]
                record: JsonDict = {
                    "repetition": repetition,
                    "warmup": repetition < config["warmups"],
                    "order": order,
                    "arms": {},
                }
                results = {}
                state["active_measurement"] = record
                for arm in order:
                    state["active_stage"] = "timed_trial"
                    state["active_arm"] = {
                        "repetition": repetition,
                        "arm": arm,
                        "warmup": record["warmup"],
                    }
                    A.write_json(report, state)
                    results[arm] = (
                        active_trial.run() if arm == "forward" else fixed_trial.run(predicted=False)
                    )
                    record["arms"][arm] = {
                        "status": "timed_trial_completed_pending_audit",
                        "timings": results[arm].timings,
                    }
                    A.write_json(report, state)
                for arm, result in results.items():
                    state["active_stage"] = "post_trial_audit"
                    state["active_arm"]["arm"] = arm
                    A.write_json(report, state)
                    before = time.perf_counter()
                    query_audit = (
                        self.audit_forward(
                            binding, result, rows, indices, baseline, pure_decisions, expected
                        )
                        if arm == "forward"
                        else None
                    )
                    audit = UnityDeploymentBenchmark.audit(
                        binding,
                        replace(result, predictions=None),
                        rows,
                        [pure_decisions[index] for index in indices],
                        policies,
                        baseline,
                        output / f"{repetition:02d}-{arm}",
                    )
                    if arm == "forward":
                        assert result.predictions is not None
                        np.savez_compressed(
                            output / f"{repetition:02d}-{arm}" / "predictions.npz",
                            channel_mse=result.predictions["channel_mse"],
                            channel_zero=result.predictions["channel_zero"],
                            zero_probability=result.predictions["zero_probability"],
                            image_quality=result.predictions["image_quality"],
                        )
                        audit["outputs_sha256"]["predictions.npz"] = A.sha256_file(
                            output / f"{repetition:02d}-{arm}" / "predictions.npz"
                        )
                    outcomes = (
                        [
                            VariantOutcome(
                                choice["selected_index"],
                                tuple(choice["measured_indices"]),
                                tuple(choice["measured_indices"]),
                                choice["selection_reason"],
                            )
                            for choice in result.choices
                        ]
                        if arm == "forward"
                        else [
                            VariantOutcome(
                                choice["selected_index"],
                                (choice["selected_index"],),
                                (),
                                "fixed8_medium",
                                model_used=False,
                            )
                            for choice in result.choices
                        ]
                    )
                    metrics, _ = UnitySystemVariants.summarize(entries, outcomes, 0.0)
                    metrics.pop("encoding_cost_estimate")
                    if metrics["actual_quality_pass_rate"] != audit["strict_quality_pass_rate"]:
                        raise ValueError(
                            "Real final quality differs from the bound candidate audit"
                        )
                    record["arms"][arm] = {
                        "status": "passed",
                        "timings": result.timings,
                        "validation_metrics": metrics,
                        "audit": audit,
                        "query_audit": query_audit,
                        "audit_and_write_seconds": time.perf_counter() - before,
                    }
                    A.write_json(report, state)
                state["measurements"].append(record)
                state.pop("active_measurement")
                A.write_json(report, state)
            state["active_stage"] = "final_identity_verification"
            for name, value in model.state_dict().items():
                if not torch.equal(value.detach().cpu(), checkpoint["model"][name]):
                    raise ValueError(
                        "Frozen model parameters or buffers changed during measurement"
                    )
            for path, digest in list(binding.inputs.items()):
                binding.bind(Path(path), digest)
            fresh = UnityFinalEncoding(self.root, binding_path)
            _, fresh_decisions, _, _ = fresh.prepare()
            if (
                fresh_decisions != pure_decisions
                or fresh.resolver.origins != binding.resolver.origins
            ):
                raise ValueError("Frozen policy inputs changed during real forward measurement")
            self.verify_sources()
            measured = [record for record in state["measurements"] if not record["warmup"]]
            summary = {}
            for arm in ["forward", "fixed8"]:
                median = float(
                    np.median(
                        [
                            record["arms"][arm]["timings"]["end_to_end_seconds"]
                            for record in measured
                        ]
                    )
                )
                summary[arm] = {
                    "median_reference_to_astc_seconds": median,
                    "batch_amortized_ms_per_image": median * 1000 / len(indices)
                    if len(indices) == 1000
                    else None,
                    "measured_encoding_calls": sum(
                        record["arms"][arm]["timings"]["encoding_calls"] for record in measured
                    ),
                    "warmup_encoding_calls": sum(
                        record["arms"][arm]["timings"]["encoding_calls"]
                        for record in state["measurements"]
                        if record["warmup"]
                    ),
                    "validation_metrics": measured[-1]["arms"][arm]["validation_metrics"],
                }
            state.update(
                status="passed_smoke" if config["smoke"] else "passed",
                summary=summary,
                source_files_sha256=config["sources_sha256"],
                inputs_sha256=binding.inputs,
                model_parameters_and_buffers_unchanged=True,
                peak_vram_bytes=torch.cuda.max_memory_allocated(device),
                scope=(
                    "Validation real forward-search/fixed8 paired mip0 measurement. Warm "
                    "model/DLL and filesystem, fresh1000-image prediction on every forward arm"
                ),
                artifact_scope=(
                    "Selected ASTC outputs and predictions saved per repetition. Every queried "
                    "ASTC/pixel hash and native quality checked against its frozen archive"
                ),
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            if (
                active_trial is not None
                and state.get("active_stage") == "timed_trial"
                and state.get("active_arm", {}).get("arm") == "forward"
            ):
                state["failure_progress"] = active_trial.progress_state()
            elif state.get("active_stage") == "timed_trial":
                state["failure_progress"] = {
                    "encoding_attempts": None,
                    "scope": "Fixed8 trial failed before returning its aggregate counters",
                }
            for arm, result in results.items():
                A.write_json(output / f"partial-{arm}-choices.json", {"rows": result.choices})
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
            A.write_json(output / "receipt.json", state)
        return state
