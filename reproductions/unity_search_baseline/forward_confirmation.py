"""Prepare and execute the frozen forward-search confirmation protocol."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import psutil
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_evaluation import UnityConfirmationEvaluation
from reproductions.unity_search_baseline.deployment import (
    UnityDeploymentResult,
    UnityDeploymentTrial,
)
from reproductions.unity_search_baseline.forward_capture_output import (
    UnityForwardCaptureOutputAudit as O,
)
from reproductions.unity_search_baseline.forward_deployment import UnityForwardSearchTrial
from reproductions.unity_search_baseline.forward_system_evidence import UnityForwardSystemEvidence
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class UnityForwardConfirmationEvaluation(UnityConfirmationEvaluation):
    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/forward_system_evidence.py",
            "reproductions/unity_search_baseline/forward_capture_output.py",
            "reproductions/unity_search_baseline/forward_confirmation.py",
            "reproductions/unity_search_baseline/forward_deployment.py",
            "reproductions/unity_search_baseline/system_variant_policy.py",
            "src/adaptive_astc/data/splitting.py",
            "script/evaluate_unity_forward_confirmation.py",
        ]
        return UnityConfirmationEvaluation.execution_sources(root) | {
            name: A.sha256_file(root / name) for name in names
        }

    @staticmethod
    def validate_config(config: JsonDict) -> None:
        UnityConfirmationEvaluation.validate_config(config)
        if (
            config["schema"] != "unity-forward-confirmation-v1"
            or config["evaluation_object"] != "frozen_prediction_forward_search_system"
            or config["inference_scope"] != "whole_cohort"
            or config["fixed8_preset"] != "medium"
            or type(config["confirmation_execution_authorized"]) is not bool
        ):
            raise ValueError(
                "Require the frozen whole-cohort forward system and explicit execution scope"
            )

    def __init__(self, root: Path, path: Path) -> None:
        self.root, self.path = root.resolve(), path.resolve()
        config_bytes = self.path.read_bytes()
        self.config = json.loads(config_bytes.decode("utf-8-sig"))
        self.evidence = UnityForwardSystemEvidence(self.root, self.config["system"])
        self.evidence.bind(self.path, hashlib.sha256(config_bytes).hexdigest())
        self.validate_config(self.config)
        self.protocol_sha256 = A.fingerprint(
            {
                key: value
                for key, value in self.config.items()
                if key not in {"output", "report", "preparation_report"}
            }
        )
        self.output, self.report = (
            Path(self.config["output"]).resolve(),
            Path(self.config["report"]).resolve(),
        )
        local, public = self.root / "experiment report/.local", self.root / "experiment report"
        if (
            not self.output.is_relative_to(local)
            or self.output == local
            or not self.report.is_relative_to(public)
            or self.report.is_relative_to(local)
            or self.output.exists()
            or self.report.exists()
        ):
            raise ValueError("Use fresh local artifacts and a separate public report")
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Forward confirmation sources changed or are incomplete")
        for name, digest in self.config["sources_sha256"].items():
            self.evidence.bind(self.root / name, digest)

    def prepare(self) -> JsonDict:
        """Inspect development evidence and source bindings before cohort access."""
        report = Path(self.config["preparation_report"]).resolve()
        if report.exists() or report == self.report or report.is_relative_to(self.output):
            raise ValueError("Use a fresh separate preparation report")
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        state: JsonDict = {
            "status": "preparing",
            "training_updates": 0,
            "model_forward_calls": 0,
            "actual_encoding_calls": 0,
            "test_opened": False,
            "formal_confirmation_executed": False,
        }
        started = time.perf_counter()
        try:
            training = self.evidence.model(self.config["training"])
            self.quality_binding()
            self.evidence.verify()
            state.update(
                status="passed_development_protocol_preparation",
                system_admission=self.evidence.admission,
                checkpoint_sha256=training["checkpoint_sha256"],
                protocol_sha256=self.protocol_sha256,
                execution_authorized=self.config["confirmation_execution_authorized"],
                formal_confirmation_ready=False,
                pending=[
                    "Approved cohort/pixel/capture evidence",
                    "Future confirmation execution authorization",
                ],
                sources_sha256=self.config["sources_sha256"],
                inputs_sha256=self.evidence.files,
                inference_scope="Whole cohort, patch batch16, artifact chunks up to8",
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state

    def run(self) -> JsonDict:
        if self.config["confirmation_execution_authorized"] is not True:
            raise PermissionError("Confirmation remains sealed for protocol preparation")
        if not isinstance(self.config["pixel_audit"], dict):
            raise ValueError("Approved complete cohort pixel/capture evidence is required")
        return super().run()

    def quality_binding(self) -> JsonDict:
        freeze = self.evidence.bound(self.config["system"]["validation_freeze"])
        quality_path = str(Path(self.config["quality_build"]["path"]).resolve())
        if (
            freeze["identity"]["files_sha256"].get(quality_path)
            != self.config["quality_build"]["sha256"]
        ):
            raise ValueError("Quality build differs from the frozen validation system")
        receipt = self.evidence.bound(self.config["quality_build"])
        self.evidence.bind(Path(receipt["dll"]), receipt["dll_sha256"])
        return receipt

    def quality(self) -> UnityQuality:
        self.quality_binding()
        return super().quality()

    def preserve_failed_pair(self, repeat: int, measured: dict[str, UnityDeploymentResult]) -> None:
        for arm, result in measured.items():
            folder = self.output / f"partial-{repeat}-{arm}"
            folder.mkdir(parents=True, exist_ok=False)
            A.write_json(
                folder / "choices.json", {"rows": result.choices, "timings": result.timings}
            )
            for index, container in enumerate(result.containers):
                (folder / f"{index:05d}.astc").write_bytes(container)
            if result.predictions is not None:
                np.savez_compressed(
                    folder / "predictions.npz",
                    channel_mse=result.predictions["channel_mse"],
                    channel_zero=result.predictions["channel_zero"],
                    zero_probability=result.predictions["zero_probability"],
                    image_quality=result.predictions["image_quality"],
                )

    @staticmethod
    def slice_result(result: UnityDeploymentResult, start: int, stop: int) -> UnityDeploymentResult:
        choices = result.choices[start:stop]
        predictions = None
        if result.predictions is not None:
            predictions = {name: value[start:stop] for name, value in result.predictions.items()}
        calls = (
            sum(choice["candidates_measured"] for choice in choices)
            if predictions is not None
            else len(choices)
        )
        return UnityDeploymentResult(
            result.containers[start:stop],
            choices,
            predictions,
            {
                "encoding_calls": calls,
                "images": len(choices),
                "scope": "Artifact slice of a completed whole-cohort timed arm",
            },
        )

    def evaluate(
        self,
        rows: list[JsonDict],
        indices: list[int],
        predictor: UnityQualityInference,
        backends: list[UnityASTCBackend],
        quality: UnityQuality,
        state: JsonDict,
    ) -> JsonDict:
        if not rows:
            raise ValueError("Require a nonempty captured cohort")
        split = rows[0]["source_split"]
        if split not in {"validation", "confirmation"} or any(
            row["source_split"] != split for row in rows
        ):
            raise ValueError("Require one explicit capture split")
        if split == "confirmation" and (
            len(rows) != 2000 or self.config["confirmation_execution_authorized"] is not True
        ):
            raise PermissionError("Complete confirmation execution requires explicit authorization")
        if split == "validation" and len(rows) > 8:
            raise ValueError("Development protocol smoke is bounded to8 images")
        if len(indices) != len(rows):
            raise ValueError("Capture policy coverage differs")
        # Retain both paired arms while auditing their outputs in bounded chunks.
        payload_bound = sum(
            ((row["width"] + 5) // 6) * ((row["height"] + 5) // 6) * 16 for row in rows
        )
        largest_rgba = max(row["width"] * row["height"] * 4 for row in rows)
        if psutil.virtual_memory().available < max(
            2 * 1024**3, payload_bound * 4 + largest_rgba * 8
        ):
            raise RuntimeError("Insufficient memory for whole-cohort paired outputs")
        adapter = UnityCaptureInputAdapter(rows, split)
        policies = [self.evidence.policies[index].policy for index in indices]
        libraries = [backends[index] for index in indices]
        forward = UnityForwardSearchTrial(
            adapter.textures,
            policies,
            libraries,
            [quality] * len(rows),
            predictor,
            240,
            list(range(len(rows))),
        )
        fixed = UnityDeploymentTrial(
            adapter.textures, policies, libraries, predictor, 240, "medium"
        )
        original_state = {
            name: value.detach().cpu().clone()
            for name, value in predictor.model.state_dict().items()
        }
        signatures: dict[str, str] = {}
        baseline: dict[str, np.ndarray] | None = None
        chunks: list[JsonDict] = []
        repetitions: list[JsonDict] = []
        state.update(status="evaluating", test_opened=split == "confirmation", chunks_completed=0)
        for repeat in range(4):
            order = ["prediction", "fixed8"] if repeat % 2 == 0 else ["fixed8", "prediction"]
            measured: dict[str, UnityDeploymentResult] = {}
            state["active_measurement"] = {
                "repetition": repeat,
                "warmup": repeat == 0,
                "order": order,
                "arms": {},
            }
            try:
                for arm in order:
                    state.update(active_arm=arm, active_stage="timed_trial")
                    A.write_json(self.report, state)
                    try:
                        measured[arm] = (
                            forward.run() if arm == "prediction" else fixed.run(predicted=False)
                        )
                    except BaseException:
                        state["failure_progress"] = (
                            forward.progress_state()
                            if arm == "prediction"
                            else {
                                "encoding_attempts": None,
                                "scope": "Fixed8 aggregate counters unavailable before return",
                            }
                        )
                        raise
                    state["active_measurement"]["arms"][arm] = {
                        "timings": measured[arm].timings,
                        "status": "timed_pending_audit",
                    }
                    A.write_json(self.report, state)
                state.update(active_arm="prediction", active_stage="prediction_repeat_check")
                A.write_json(self.report, state)
                prediction = measured["prediction"].predictions
                assert prediction is not None
                if baseline is None:
                    baseline = {name: value.copy() for name, value in prediction.items()}
                else:
                    for name, value in prediction.items():
                        np.testing.assert_array_equal(value, baseline[name])
                combined: dict[str, list[JsonDict]] = {"prediction": [], "fixed8": []}
                size = self.config["image_chunk_size"]
                for start in range(0, len(rows), size):
                    stop = min(start + size, len(rows))
                    record: JsonDict = {
                        "repeat": repeat,
                        "start": start,
                        "images": stop - start,
                        "warmup": repeat == 0,
                        "order": order,
                        "arms": {},
                    }
                    chunk_adapter = UnityCaptureInputAdapter(rows[start:stop], split)
                    for arm in order:
                        state.update(active_arm=arm, active_stage="post_trial_audit")
                        A.write_json(self.report, state)
                        sliced = self.slice_result(measured[arm], start, stop)
                        folder = self.output / f"repeat-{repeat}/{start:05d}-{arm}"
                        before = time.perf_counter()
                        outcome = O.run(
                            chunk_adapter,
                            policies[start:stop],
                            libraries[start:stop],
                            [quality] * (stop - start),
                            [row["selection"] for row in rows[start:stop]],
                            sliced,
                            folder,
                            offset=start,
                        )
                        for offset, row in enumerate(outcome["rows"]):
                            key = f"{arm}:{start + offset}"
                            signature = A.fingerprint(
                                {
                                    "choice": O.signature(sliced.choices[offset]),
                                    "astc": row["astc_sha256"],
                                }
                            )
                            if key in signatures and signatures[key] != signature:
                                raise ValueError(
                                    "Repeated system choices, measured queries or ASTC differ"
                                )
                            signatures[key] = signature
                        combined[arm].extend(outcome["rows"])
                        record["arms"][arm] = {
                            "actual_encoding_calls": sliced.timings["encoding_calls"],
                            "timing_scope": "Whole-cohort timings recorded by repetition",
                            "summary": outcome["summary"],
                            "outputs_sha256": outcome["outputs_sha256"],
                            "audit_and_write_seconds": time.perf_counter() - before,
                        }
                    receipt = self.output / f"repeat-{repeat}/{start:05d}-receipt.json"
                    A.write_json(receipt, record)
                    chunks.append({"path": str(receipt), "sha256": A.sha256_file(receipt)})
                    state.update(
                        chunks_completed=state["chunks_completed"] + 1,
                        repetition=repeat,
                        completed_images_this_repetition=stop,
                    )
                    A.write_json(self.report, state)
                for arm, outcomes in combined.items():
                    if [row["path"] for row in outcomes] != [row["path"] for row in rows] or sum(
                        row["candidates_measured"] for row in outcomes
                    ) != measured[arm].timings["encoding_calls"]:
                        raise ValueError(
                            "Whole-cohort output order or actual encoding count differs"
                        )
                repetitions.append(
                    {
                        "repetition": repeat,
                        "warmup": repeat == 0,
                        "arms": {
                            arm: {
                                "summary": O.summarize(combined[arm]),
                                "timings": result.timings,
                                "end_to_end_seconds": result.timings["end_to_end_seconds"],
                                "encoding_calls": result.timings["encoding_calls"],
                            }
                            for arm, result in measured.items()
                        },
                    }
                )
                state.pop("active_measurement")
                A.write_json(self.output / "repetitions.json", {"rows": repetitions})
                A.write_json(self.report, state)
            except BaseException:
                try:
                    self.preserve_failed_pair(repeat, measured)
                except BaseException as persistence_error:
                    state["failure_artifact_error"] = repr(persistence_error)
                raise
        for name, value in predictor.model.state_dict().items():
            if not torch.equal(value.detach().cpu(), original_state[name]):
                raise ValueError("Frozen model parameters or buffers changed")
        repetitions_path = self.output / "repetitions.json"
        manifest = {
            "chunks": chunks,
            "repetitions": {
                "path": str(repetitions_path),
                "sha256": A.sha256_file(repetitions_path),
            },
        }
        self.verify_outputs(manifest, len(rows))
        manifest_path = self.output / "outputs.json"
        A.write_json(manifest_path, manifest)
        self.evidence.verify()
        return {
            "outputs_manifest": {
                "path": str(manifest_path),
                "sha256": A.sha256_file(manifest_path),
            },
            "repetitions": repetitions,
            "system_admission": self.evidence.admission,
            "evaluation_object": "frozen_prediction_forward_search_system",
            "inference_scope": "Whole cohort per arm. Artifact chunks up to8.",
            "model_parameters_and_buffers_unchanged": True,
            "repeated_prediction_arrays_exact": True,
            "summary": {
                arm: {
                    **repetitions[-1]["arms"][arm]["summary"],
                    "median_end_to_end_seconds": float(
                        np.median(
                            [
                                record["arms"][arm]["end_to_end_seconds"]
                                for record in repetitions[1:]
                            ]
                        )
                    ),
                    "measured_encoding_calls": sum(
                        record["arms"][arm]["encoding_calls"] for record in repetitions[1:]
                    ),
                    "warmup_encoding_calls": repetitions[0]["arms"][arm]["encoding_calls"],
                }
                for arm in ["prediction", "fixed8"]
            },
        }
