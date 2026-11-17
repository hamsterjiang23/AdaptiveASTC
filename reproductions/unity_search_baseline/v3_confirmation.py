"""Execute one selected V3 system against the reserved independent cohort."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import statistics
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import psutil
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction as Q
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal
from reproductions.unity_search_baseline.deployment import UnityDeploymentResult
from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding
from reproductions.unity_search_baseline.forward_capture_output import (
    UnityForwardCaptureOutputAudit as OutputSummary,
)
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.revised_confirmation_evidence import (
    UnityRevisedConfirmationEvidence,
)
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.v3_benchmark import UnityV3Benchmark
from reproductions.unity_search_baseline.v3_deployment import UnityV3DeploymentTrial
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy


class UnityV3Confirmation(UnityV3Benchmark):
    """Reuse the frozen V3 trial and measure two timing scopes independently."""

    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.config_path = root.resolve(), config_path.resolve()
        self.config = A.read_json(self.config_path)
        if self.config["schema"] != "unity-v3-confirmation-execution-v1":
            raise ValueError("Explicit V3 confirmation execution contract required")
        if self.config["confirmation_execution_authorized"] is not True:
            raise PermissionError("Formal execution needs the recorded user authorization")
        self.public = Path(self.config["public"])
        self.output = Path(self.config["output"])
        self.report = self.public / "result.json"
        self.contract = A.read_json(Path(self.config["development_contract"]["path"]))
        self.bindings = {
            str(self.config_path): A.sha256_file(self.config_path),
            **self.config["files_sha256"],
        }
        self.verify()
        self.case = {
            "name": "forward-unity-full20",
            "arm": "forward",
            "input_mode": "unity",
            "candidate_set": "full20",
        }
        selected = self.contract["selected_system"]
        if any(
            selected[key] != self.case[key]
            for key in ["name", "arm", "input_mode", "candidate_set"]
        ):
            raise ValueError("Selected system differs from the frozen development contract")
        if (
            selected["metrics"]["accuracy"]
            < self.contract["primary_acceptance"]["system_block_top1_min"]
        ):
            raise ValueError("Selected system has not met development admission")
        self.active_state: JsonDict = {}

    def verify(self) -> None:
        for name, expected in self.bindings.items():
            path = Path(name)
            if expected is None:
                if path.exists():
                    raise ValueError(f"Previously absent bound input appeared: {name}")
            elif A.sha256_file(path) != expected:
                raise ValueError(f"V3 confirmation input or source changed: {name}")

    def prepare_inputs(self) -> JsonDict:
        """Re-audit cohort provenance without constructing or forwarding a model."""
        path = self.output / "prepared-inputs.json"
        if path.exists():
            raise FileExistsError("Preserve the existing input preparation")
        self.output.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        evidence = UnityRevisedConfirmationEvidence(self.root, {})
        head_path = Path(self.config["training_report"])
        head = evidence.read(head_path, self.bindings[str(head_path)])
        if head["status"] != "completed" or head["checkpoint_audit"]["status"] != "passed":
            raise ValueError("Completed V3 training and checkpoint reload audit required")
        corpus = Path(head["config"]["corpus"]) / "corpus.json"
        evidence.corpus = evidence.read(corpus, head["config"]["corpus_sha256"])
        protocol = evidence.read(Path(self.config["cohort_protocol"]))
        pipeline, pixels = evidence.pixel_audit(protocol["pixel_audit"])
        rows, indices = evidence.captures(pipeline, pixels)
        adapter = UnityCaptureInputAdapter(rows, "confirmation")
        if adapter.fingerprint != self.contract["cohort"]["native_input_fingerprint"]:
            raise ValueError("Prepared cohort differs from the frozen V3 input fingerprint")
        if pipeline.confirmation is None:
            raise ValueError("Original cohort reservation is required")
        parent = pipeline.confirmation.smoke.reservation["manifest_sha256"]
        if parent != self.contract["cohort"]["registry_parent_manifest_sha256"]:
            raise ValueError("Shared reserved cohort identity changed")
        expected_dll = self.contract["native_binaries"]["astcenc-avx2-shared.dll"]
        for binding in evidence.policies:
            identity = evidence.read(binding.baseline.run_dir / "identity.json")
            if identity["encoder_dlls"]["astcenc-avx2-shared.dll"] != self.bindings[expected_dll]:
                raise ValueError("Confirmation native encoder differs from the selected V3 DLL")
        evidence.verify()
        prepared = {
            "status": "passed",
            "rows": rows,
            "policy_indices": indices,
            "policy_tables": [item.policy.table for item in evidence.policies],
            "policy_bindings": [item.binding for item in evidence.policies],
            "input_fingerprint": adapter.fingerprint,
            "reservation_sha256": parent,
            "files_sha256": evidence.files,
            "model_forward_calls": 0,
            "training_updates": 0,
            "test_opened": False,
            "wall_seconds": time.perf_counter() - started,
        }
        A.write_json(path, prepared)
        public = {
            key: prepared[key]
            for key in [
                "status",
                "input_fingerprint",
                "reservation_sha256",
                "model_forward_calls",
                "training_updates",
                "test_opened",
                "wall_seconds",
            ]
        }
        public.update(
            images=len(rows),
            native_policy_contexts=len(evidence.policies),
            prepared_inputs={"path": str(path), "sha256": A.sha256_file(path)},
        )
        A.write_json(self.public / "preparation.json", public)
        return public

    def load_inputs(self, smoke: bool) -> None:
        self.smoke = smoke
        if smoke:
            snapshot = A.read_json(Path(self.config["smoke_inputs"]))
            self.rows, indices, tables = (
                snapshot["rows"],
                snapshot["policy_indices"],
                snapshot["policy_tables"],
            )
            split = "validation"
        else:
            preparation = A.read_json(self.public / "preparation.json")
            source = preparation["prepared_inputs"]
            if A.sha256_file(Path(source["path"])) != source["sha256"]:
                raise ValueError("Prepared input snapshot changed")
            self.bindings[source["path"]] = source["sha256"]
            self.bindings[str(self.public / "preparation.json")] = A.sha256_file(
                self.public / "preparation.json"
            )
            snapshot = A.read_json(Path(source["path"]))
            for name, expected in snapshot["files_sha256"].items():
                if name in self.bindings and self.bindings[name] != expected:
                    raise ValueError(f"Conflicting confirmation evidence binding: {name}")
                self.bindings[name] = expected
            self.rows = snapshot["rows"]
            indices, tables = snapshot["policy_indices"], snapshot["policy_tables"]
            split = "confirmation"
            if len(self.rows) != 2000:
                raise ValueError("Formal confirmation requires all2000 reserved images")
        self.adapter = UnityCaptureInputAdapter(self.rows, split)
        self.textures = self.adapter.textures
        self.entries = [
            {"policy": tables[i], "texture": texture}
            for i, texture in zip(indices, self.adapter.decision_inputs, strict=True)
        ]
        self.verify()
        device = ExperimentRuntime.configure(20261112)
        if device.type != "cuda":
            raise RuntimeError("Selected V3 system requires CUDA inference")
        checkpoint_path = Path(self.contract["selected_system"]["checkpoint"])
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
        if checkpoint["config"]["backbone_name"] != "resnet34" or model.image_pooling != "mean":
            raise ValueError("Frozen ResNet34 mean-pooling architecture changed")
        self.predictor = UnityQualityInference(model, device, 16, 0.5)
        binaries = self.contract["native_binaries"]
        dll = Path(binaries["astcenc-avx2-shared.dll"])
        self.backend = UnityASTCBackend(dll, self.bindings[str(dll)])
        self.quality = UnityQuality(Path(binaries["build-receipt.json"]))
        self.input_snapshot = snapshot

    def trial(self, case: JsonDict, indices: list[int]) -> UnityV3DeploymentTrial:
        return UnityV3DeploymentTrial(
            [self.textures[i] for i in indices],
            [self.entries[i]["policy"] for i in indices],
            [self.backend] * len(indices),
            [self.quality] * len(indices),
            self.predictor,
            candidate_set=NativeCandidateSet.full20(),
            input_mode="unity",
            progress=lambda progress: self.progress(progress),
        )

    def progress(self, progress: JsonDict) -> None:
        now = time.monotonic()
        if now - getattr(self, "last_progress", 0.0) >= 10:
            self.last_progress = now
            state = {
                **self.active_state,
                "progress": progress,
                "pid": os.getpid(),
                "rss_bytes": psutil.Process().memory_info().rss,
                "ram_available_bytes": psutil.virtual_memory().available,
            }
            A.write_json(
                self.public / ("smoke-progress.json" if self.smoke else "progress.json"), state
            )

    def measure(self, case: JsonDict, scope: str, mode: str) -> UnityDeploymentResult:
        if scope == "files":
            return super().measure(case, scope, mode)
        results: list[UnityDeploymentResult] = []
        for offset in range(0, len(self.entries), 8):
            indices = list(range(offset, min(offset + 8, len(self.entries))))
            references = []
            for index in indices:
                with Image.open(self.textures[index].reference) as image:
                    references.append(np.asarray(image.convert("RGBA"), dtype=np.uint8))
            result = self.trial(case, indices).run(
                case["arm"], single_image=mode == "single", reference_pixels=references
            )
            for index, choice in enumerate(result.choices):
                choice["source_index"] = offset + index
            results.append(result)
        parts = [result.predictions for result in results]
        if not parts or any(part is None for part in parts):
            raise ValueError("Every selected-system trial must retain real model predictions")
        first = parts[0]
        assert first is not None
        predictions = {
            key: np.concatenate([part[key] for part in parts if part is not None]) for key in first
        }
        timings: JsonDict = {
            "end_to_end_seconds": sum(result.timings["end_to_end_seconds"] for result in results),
            "encoding_calls": sum(result.timings["encoding_calls"] for result in results),
            "scope": "Independent pixels-ready measurements; buffers prepared outside timing",
            "chunk_images": 8,
            "measurements": [result.timings for result in results],
        }
        if mode == "single":
            timings["single_image_latencies_seconds"] = [
                value
                for result in results
                for value in result.timings["single_image_latencies_seconds"]
            ]
        return UnityDeploymentResult(
            [container for result in results for container in result.containers],
            [choice for result in results for choice in result.choices],
            predictions,
            timings,
        )

    @staticmethod
    def signature(choice: JsonDict, container: bytes) -> str:
        return A.fingerprint(
            {
                "selected": choice["selected_index"],
                "start": choice["starting_decision"],
                "measured": choice["measured_indices"],
                "reason": choice["selection_reason"],
                "astc": hashlib.sha256(container).hexdigest(),
            }
        )

    def audit(self, result: UnityDeploymentResult, case: JsonDict, destination: Path) -> JsonDict:
        destination.mkdir(parents=True, exist_ok=False)
        if result.predictions is None:
            raise ValueError("Selected-system output audit requires prediction evidence")
        rows: list[JsonDict] = []
        for index, (captured, spec, texture, choice, container) in enumerate(
            zip(
                self.rows,
                self.textures,
                self.adapter.decision_inputs,
                result.choices,
                result.containers,
                strict=True,
            )
        ):
            policy = UnityV3Policy(self.entries[index]["policy"])
            if choice["source_index"] != index:
                raise ValueError("Captured source order changed during timing aggregation")
            selected = choice["selected_index"]
            block, preset = policy.candidate_set.candidate(selected)
            truth = captured["selection"]
            if (
                truth["asset"].replace("\\", "/").casefold()
                != captured["path"].replace("\\", "/").casefold()
            ):
                raise ValueError("Original label belongs to another asset")
            if case["arm"] == "forward":
                start = choice["starting_decision"]
                if result.predictions is not None:
                    predicted = Q.candidates(
                        texture,
                        result.predictions["channel_mse"][index],
                        result.predictions["channel_zero"][index],
                        result.predictions["image_quality"][index],
                    )
                    if asdict(policy.select(predicted, texture)) != start:
                        raise ValueError("Recorded start differs from current model predictions")
                records = {item["selected_index"]: item for item in choice["queries"]}
                replay = policy.search(
                    lambda candidate: records[candidate]["metrics"],
                    texture,
                    start["selected_index"],
                )
                if (
                    asdict(replay.decision) != {key: choice[key] for key in asdict(replay.decision)}
                    or list(replay.measured_indices) != choice["measured_indices"]
                ):
                    raise ValueError("Real V3 query trace differs from native rule replay")
                if (
                    len(records) != len(choice["queries"])
                    or len(records) != choice["candidates_measured"]
                ):
                    raise ValueError("Actual candidate measurements are duplicated or missing")
                selected_record = records[selected]
                if hashlib.sha256(container).hexdigest() != selected_record["container_sha256"]:
                    raise ValueError("Selected ASTC is not the recorded encoded result")
            elif selected != Q.GRID.index((8, "medium")):
                raise ValueError("Fixed baseline parameter changed")
            payload = (
                ((texture.width + block - 1) // block)
                * ((texture.height + block - 1) // block)
                * 16
            )
            if (
                container[:16] != self.backend.container(b"", texture.width, texture.height, block)
                or len(container) != 16 + payload
            ):
                raise ValueError("Selected ASTC header or payload geometry changed")
            with Image.open(spec.reference) as image:
                reference = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
            if (
                hashlib.sha256(reference.tobytes()).hexdigest()
                != self.adapter.bindings[index]["callback_rgba_sha256"]
            ):
                raise ValueError("Scoring reference differs from captured callback pixels")
            decoded, seconds = self.backend.decode_payload(
                container[16:], texture.width, texture.height, block, srgb=spec.srgb
            )
            metrics = self.quality.measure(
                reference,
                decoded,
                need_alpha=spec.need_alpha,
                compute_ssim=spec.srgb and not spec.normal,
                normal=spec.normal,
                mip_count=spec.normal_metric_mips,
            )
            if case["arm"] == "forward":
                UnityFinalEncoding.verify_metrics(metrics, selected_record["metrics"])
                if (
                    hashlib.sha256(decoded.tobytes()).hexdigest()
                    != selected_record["decoded_native_rgba_sha256"]
                ):
                    raise ValueError("Selected decoded pixels changed")
            original_side = int(truth["block_size"].split("x")[0])
            strict = policy.strict_quality(metrics, texture)
            astc, png = destination / f"{index:05d}.astc", destination / f"{index:05d}.png"
            astc.write_bytes(container)
            Image.fromarray(decoded[::-1]).save(png)
            rows.append(
                {
                    "path": captured["path"],
                    "source_split": self.adapter.split,
                    "width": texture.width,
                    "height": texture.height,
                    "normal": spec.normal,
                    "srgb": spec.srgb,
                    "size_first": not spec.normal
                    and spec.srgb
                    and texture.width * texture.height
                    >= policy.table["sizeFirstMinSideLarge"] ** 2,
                    "selected_index": selected,
                    "block_size": f"{block}x{block}",
                    "preset": preset,
                    "original_selection": truth,
                    "footprint_match": block == original_side,
                    "full_choice_match": (f"{block}x{block}", preset)
                    == (truth["block_size"], truth["preset"]),
                    "effective_psnr_threshold": policy.effective_threshold(texture),
                    "strict_quality_met": strict,
                    "metrics": metrics,
                    "predicted_psnr": None,
                    "payload_bytes": payload,
                    "container_bytes": len(container),
                    "original_payload_bytes": ((texture.width + original_side - 1) // original_side)
                    * ((texture.height + original_side - 1) // original_side)
                    * 16,
                    "fixed8_payload_bytes": ((texture.width + 7) // 8)
                    * ((texture.height + 7) // 8)
                    * 16,
                    "quality_regression": truth["selection_reason"]
                    in {"first_valid", "size_first_strict"}
                    and not strict,
                    "larger_block": block > original_side,
                    "smaller_block": block < original_side,
                    "candidates_measured": choice["candidates_measured"],
                    "decode_audit_seconds": seconds,
                    "astc_sha256": A.sha256_file(astc),
                    "decoded_png_sha256": A.sha256_file(png),
                    "starting_decision": choice["starting_decision"],
                }
            )
        summary = OutputSummary.summarize(rows)
        if case["arm"] == "forward":
            summary["pure_start_block_accuracy"] = sum(
                row["starting_decision"]["block_size"] == row["original_selection"]["block_size"]
                for row in rows
            ) / len(rows)
        A.write_json(destination / "rows.json", {"rows": rows, "complete": True})
        if result.predictions is not None:
            np.savez_compressed(destination / "predictions.npz", **result.predictions)
        files = {
            str(destination / f"{index:05d}.{extension}"): row[field]
            for index, row in enumerate(rows)
            for extension, field in [("astc", "astc_sha256"), ("png", "decoded_png_sha256")]
        }
        for name in ["rows.json", "predictions.npz"]:
            files[str(destination / name)] = A.sha256_file(destination / name)
        manifest = destination / "outputs.json"
        A.write_json(manifest, {"files_sha256": files, "images": len(rows)})
        return {
            "summary": summary,
            "outputs_manifest": {"path": str(manifest), "sha256": A.sha256_file(manifest)},
        }

    @staticmethod
    def verify_outputs(measurements: list[JsonDict]) -> None:
        manifests = {
            record["outputs_manifest"]["path"]: record["outputs_manifest"]["sha256"]
            for record in measurements
        }
        for name, digest in manifests.items():
            path = Path(name)
            if A.sha256_file(path) != digest:
                raise ValueError("Saved output manifest changed")
            manifest = A.read_json(path)
            for output, expected in manifest["files_sha256"].items():
                if A.sha256_file(Path(output)) != expected:
                    raise ValueError(f"Saved confirmation output changed: {output}")
        for record in measurements:
            if A.sha256_file(Path(record["trace"])) != record["trace_sha256"]:
                raise ValueError("Saved actual query trace changed")
            predictions = record["predictions_archive"]
            if A.sha256_file(Path(predictions["path"])) != predictions["sha256"]:
                raise ValueError("Saved repeated model predictions changed")

    def evaluate(self, smoke: bool) -> JsonDict:
        report = self.public / ("smoke-result.json" if smoke else "result.json")
        folder = self.output / ("smoke" if smoke else "formal")
        if report.exists() or folder.exists():
            raise FileExistsError("Preserve the existing evaluation attempt")
        folder.mkdir(parents=True)
        original = {
            key: value.detach().cpu().clone()
            for key, value in self.predictor.model.state_dict().items()
        }
        state: JsonDict = {
            "status": "running",
            "test_opened": not smoke,
            "training_updates": 0,
            "images": len(self.rows),
            "measurements": [],
            "pid": os.getpid(),
            "execution_config_sha256": A.sha256_file(self.config_path),
            "checkpoint_sha256": self.contract["selected_system"]["checkpoint_sha256"],
            "input_fingerprint": self.adapter.fingerprint,
        }
        A.write_json(report, state)
        started = time.perf_counter()
        try:
            for scope in self.config["timing"]["scopes"]:
                for mode in self.config["timing"]["measurement_modes"]:
                    signature: list[str] | None = None
                    summary: JsonDict = {}
                    outputs_manifest: JsonDict = {}
                    self.active_state = {"scope": scope, "mode": mode, "stage": "warmup"}
                    for _ in range(self.config["timing"]["warmups"]):
                        self.trial(self.case, list(range(min(8, len(self.rows))))).run("forward")
                    for repeat in range(self.config["timing"]["repetitions"]):
                        self.active_state = {
                            "scope": scope,
                            "mode": mode,
                            "repeat": repeat,
                            "stage": "timing",
                        }
                        print(json.dumps(self.active_state), flush=True)
                        before = time.perf_counter()
                        result = self.measure(self.case, scope, mode)
                        trial_wall = time.perf_counter() - before
                        current = [
                            self.signature(c, b)
                            for c, b in zip(result.choices, result.containers, strict=True)
                        ]
                        if signature is not None and current != signature:
                            raise ValueError(
                                "Repeated choices, starts, query traces or ASTC differ"
                            )
                        if signature is None:
                            signature = current
                            self.active_state["stage"] = "output_audit"
                            before = time.perf_counter()
                            audit = self.audit(
                                result, self.case, folder / f"{scope}-{mode}-outputs"
                            )
                            summary = audit["summary"]
                            outputs_manifest = audit["outputs_manifest"]
                            audit_seconds = time.perf_counter() - before
                        else:
                            audit_seconds = 0.0
                        trace = folder / f"{scope}-{mode}-{repeat}.json.gz"
                        with gzip.open(trace, "xt", encoding="utf-8") as stream:
                            json.dump(
                                {
                                    "choices": result.choices,
                                    "astc_sha256": [
                                        hashlib.sha256(b).hexdigest() for b in result.containers
                                    ],
                                    "timings": result.timings,
                                },
                                stream,
                            )
                        if result.predictions is None:
                            raise ValueError("A timed prediction trial lost its model outputs")
                        prediction_path = folder / f"{scope}-{mode}-{repeat}-predictions.npz"
                        np.savez_compressed(prediction_path, **result.predictions)
                        state["measurements"].append(
                            {
                                "scope": scope,
                                "mode": mode,
                                "repeat": repeat,
                                "timings": result.timings,
                                "summary": summary,
                                "outputs_manifest": outputs_manifest,
                                "trace": str(trace),
                                "trace_sha256": A.sha256_file(trace),
                                "predictions_archive": {
                                    "path": str(prediction_path),
                                    "sha256": A.sha256_file(prediction_path),
                                },
                                "audit_and_write_seconds": audit_seconds,
                                "whole_trial_wall_seconds": trial_wall,
                            }
                        )
                        A.write_json(report, state)
            for key, value in self.predictor.model.state_dict().items():
                if not torch.equal(value.detach().cpu(), original[key]):
                    raise ValueError("Evaluation changed model parameters or buffers")
            self.verify_outputs(state["measurements"])
            grouped = {}
            for scope in self.config["timing"]["scopes"]:
                for mode in self.config["timing"]["measurement_modes"]:
                    records = [
                        record
                        for record in state["measurements"]
                        if (record["scope"], record["mode"]) == (scope, mode)
                    ]
                    grouped[f"{scope}_{mode}"] = {
                        "summary": records[0]["summary"],
                        "median_end_to_end_seconds": statistics.median(
                            row["timings"]["end_to_end_seconds"] for row in records
                        ),
                        "repetitions": len(records),
                    }
            primary = grouped["files_batch"]["summary"]
            state.update(
                status="passed" if smoke else "audited_pending_seal_verification",
                results=grouped,
                summary=primary,
                accuracy90_met=primary["footprint_accuracy"] >= 0.90,
                model_parameters_and_buffers_unchanged=True,
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state

    def run_confirmation(self) -> JsonDict:
        self.load_inputs(False)
        if (self.public / "smoke-result.json").is_file():
            smoke = A.read_json(self.public / "smoke-result.json")
            smoke_adapter = UnityCaptureInputAdapter(
                A.read_json(Path(self.config["smoke_inputs"]))["rows"], "validation"
            )
            if (
                smoke["status"] != "passed"
                or smoke["test_opened"]
                or smoke["execution_config_sha256"] != A.sha256_file(self.config_path)
                or smoke["checkpoint_sha256"]
                != self.contract["selected_system"]["checkpoint_sha256"]
                or smoke["input_fingerprint"] != smoke_adapter.fingerprint
            ):
                raise ValueError("Development smoke must pass before formal evaluation")
            self.verify_outputs(smoke["measurements"])
            self.bindings[str(self.public / "smoke-result.json")] = A.sha256_file(
                self.public / "smoke-result.json"
            )
        else:
            raise ValueError("Development smoke evidence required")
        registry = self.contract["confirmation_registry"]
        identity = {
            "schema": "unity_native_inference_v1",
            "split": "confirmation",
            "cohort_fingerprint": A.fingerprint(
                {"reservation": self.input_snapshot["reservation_sha256"], "split": "confirmation"}
            ),
            "inputs_fingerprint": self.adapter.fingerprint,
            "policies_fingerprint": A.fingerprint(self.input_snapshot["policy_bindings"]),
            "model": {
                "checkpoint_sha256": self.contract["selected_system"]["checkpoint_sha256"],
                "name": self.case["name"],
            },
            "decision": {
                "case": self.case,
                "patch_size": 240,
                "batch_size": 16,
                "zero_probability_threshold": 0.5,
                "timing": self.config["timing"],
                "evaluation_config_sha256": A.sha256_file(self.config_path),
            },
            "runtime": {
                "torch": torch.__version__,
                "numpy": np.__version__,
                "device": str(self.predictor.device),
                "threads": torch.get_num_threads(),
            },
            "files_sha256": self.bindings,
        }
        if (
            identity["cohort_fingerprint"] != registry["cohort_fingerprint"]
            or identity["inputs_fingerprint"] != self.contract["cohort"]["native_input_fingerprint"]
        ):
            raise ValueError("Formal contract changed the reserved cohort")
        seal = UnityEvaluationSeal(Path(registry["registry"]), identity)
        if seal.path.exists():
            raise FileExistsError("Reserved cohort already has an inference contract")
        seal.acquire()
        A.write_json(
            self.public / "execution-seal.json",
            {
                "path": str(seal.path),
                "fingerprint": seal.fingerprint,
                "checkpoint_sha256": identity["model"]["checkpoint_sha256"],
                "test_opened": False,
            },
        )
        try:
            result = seal.forward(lambda: self.evaluate(False))
            seal.verify()
            result.update(
                status="passed",
                seal_path=str(seal.path),
                seal_fingerprint=seal.fingerprint,
                config_sha256=A.sha256_file(self.config_path),
            )
            A.write_json(self.report, result)
            return result
        except BaseException as error:
            result = A.read_json(self.report) if self.report.exists() else {}
            result.update(
                status="failed",
                error=repr(error),
                seal_path=str(seal.path),
                seal_fingerprint=seal.fingerprint,
            )
            A.write_json(self.report, result)
            raise
