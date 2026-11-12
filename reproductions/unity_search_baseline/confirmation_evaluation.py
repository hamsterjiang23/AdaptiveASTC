"""Evaluate a fixed native model on the complete reserved confirmation cohort."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

import numpy as np
import psutil
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal
from reproductions.unity_search_baseline.capture_deployment import UnityCaptureDeploymentSmoke as D
from reproductions.unity_search_baseline.capture_output import UnityCaptureOutputAudit as O
from reproductions.unity_search_baseline.confirmation_evidence import UnityConfirmationEvidence as E
from reproductions.unity_search_baseline.deployment import UnityDeploymentTrial
from reproductions.unity_search_baseline.pixel_audit_pipeline import UnityPixelAuditPipeline as I
from reproductions.unity_search_baseline.quality import UnityQuality, UnityQualityBuild
from reproductions.unity_search_baseline.sealed_inference import UnitySealedInferenceSmoke as S
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class UnityConfirmationEvaluation:
    """No candidate search, model tuning or automatic removal of confirmation samples."""

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/confirmation_evidence.py",
            "reproductions/unity_search_baseline/confirmation_evaluation.py",
            "src/adaptive_astc/evaluation/patch_normalization.py",
            "script/evaluate_unity_confirmation.py",
        ]
        return (
            D.execution_sources(root)
            | I.execution_sources(root)
            | {name: A.sha256_file(root / name) for name in names}
        )

    def __init__(self, root: Path, path: Path) -> None:
        self.root, self.path = root.resolve(), path.resolve()
        self.evidence = E(self.root)
        self.config = self.evidence.read(self.path)
        # Output locations identify an attempt, not a new model/decision protocol.
        self.protocol_sha256 = A.fingerprint(
            {key: value for key, value in self.config.items() if key not in {"output", "report"}}
        )
        self.output, self.report = (
            Path(self.config["output"]).resolve(),
            Path(self.config["report"]).resolve(),
        )
        self.validate_config(self.config)
        local, public = self.root / "experiment report/.local", self.root / "experiment report"
        if (
            not self.output.is_relative_to(local)
            or self.output == local
            or not self.report.is_relative_to(public)
            or self.report.is_relative_to(local)
            or self.output.exists()
            or self.report.exists()
        ):
            raise ValueError("Use fresh local artifacts and a separate new public report")
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Confirmation evaluator sources changed or are incomplete")
        for name, digest in self.config["sources_sha256"].items():
            self.evidence.bind(self.root / name, digest)

    def seal_files(self) -> dict[str, str | None]:
        # The current attempt config remains checked by evidence.verify() and its SHA
        # is saved in the report. All its non-location values are sealed separately.
        return {
            name: digest for name, digest in self.evidence.files.items() if name != str(self.path)
        }

    def verify_outputs(self, manifest: JsonDict, images: int) -> None:
        expected = [
            (repeat, start)
            for repeat in range(4)
            for start in range(0, images, self.config["image_chunk_size"])
        ]
        for item, (repeat, start) in zip(manifest["chunks"], expected, strict=True):
            receipt = self.output / f"repeat-{repeat}/{start:05d}-receipt.json"
            if Path(item["path"]) != receipt or A.sha256_file(receipt) != item["sha256"]:
                raise ValueError("Confirmation chunk receipt changed or coverage differs")
            record = A.read_json(receipt)
            if (record["repeat"], record["start"], record["images"], record["warmup"]) != (
                repeat,
                start,
                min(self.config["image_chunk_size"], images - start),
                repeat == 0,
            ) or set(record["arms"]) != {"prediction", "fixed8"}:
                raise ValueError("Confirmation chunk membership differs")
            for arm, data in record["arms"].items():
                folder = self.output / f"repeat-{repeat}/{start:05d}-{arm}"
                for name, digest in data["outputs_sha256"].items():
                    path = (folder / name).resolve()
                    if not path.is_relative_to(folder.resolve()) or A.sha256_file(path) != digest:
                        raise ValueError("Confirmation compressed output or predictions changed")
        repetitions = manifest["repetitions"]
        if (
            Path(repetitions["path"]) != self.output / "repetitions.json"
            or A.sha256_file(Path(repetitions["path"])) != repetitions["sha256"]
        ):
            raise ValueError("Confirmation repetitions changed")

    @staticmethod
    def validate_config(config: JsonDict) -> None:
        if (
            config["split"] != "confirmation"
            or type(config["images"]) is not int
            or config["images"] != 2000
            or config["warmups"] != 1
            or type(config["warmups"]) is not int
            or config["repetitions"] != 3
            or type(config["repetitions"]) is not int
            or type(config["image_chunk_size"]) is not int
            or not 1 <= config["image_chunk_size"] <= 8
            or config["fixed8_preset"] not in UnityASTCBackend.PRESETS
        ):
            raise ValueError(
                "Require all2000 confirmation images, one warmup, three repeats and bounded chunks"
            )

    def quality(self) -> UnityQuality:
        receipt = self.evidence.bound(self.config["quality_build"])
        binding = receipt["binding"]
        engine = self.evidence.bind(Path(binding["engine_source"]), binding["engine_source_sha256"])
        extracted = UnityQualityBuild.extract(engine.read_text(encoding="utf-8-sig"))
        native = self.root / "reproductions/unity_search_baseline/native"
        if (
            hashlib.sha256(extracted.encode()).hexdigest() != binding["extracted_sha256"]
            or A.sha256_file(native / "quality_wrapper.cpp") != binding["wrapper_sha256"]
            or A.sha256_file(native / "CMakeLists.txt") != binding["cmake_sha256"]
        ):
            raise ValueError("Quality library source differs from the frozen engine metrics")
        self.evidence.bind(Path(receipt["dll"]), receipt["dll_sha256"])
        return UnityQuality(Path(self.config["quality_build"]["path"]))

    def evaluate(
        self,
        rows: list[JsonDict],
        indices: list[int],
        predictor: UnityQualityInference,
        backends: list[UnityASTCBackend],
        quality: UnityQuality,
        state: JsonDict,
    ) -> JsonDict:
        results: list[JsonDict] = []
        chunks: list[JsonDict] = []
        signatures: dict[str, str] = {}
        size = self.config["image_chunk_size"]
        count = len(rows)
        state.update(status="evaluating", test_opened=True, chunks_completed=0)
        A.write_json(self.report, state)
        for repeat in range(4):
            combined: dict[str, list[JsonDict]] = {"prediction": [], "fixed8": []}
            elapsed: dict[str, float] = {"prediction": 0.0, "fixed8": 0.0}
            encode_calls = {"prediction": 0, "fixed8": 0}
            for start in range(0, count, size):
                chunk = rows[start : start + size]
                adapter = UnityCaptureInputAdapter(chunk, "confirmation")
                selected_indices = indices[start : start + size]
                policies = [self.evidence.policies[i].policy for i in selected_indices]
                libraries = [backends[i] for i in selected_indices]
                trial = UnityDeploymentTrial(
                    adapter.textures,
                    policies,
                    libraries,
                    predictor,
                    240,
                    self.config["fixed8_preset"],
                )
                order = (
                    ["prediction", "fixed8"]
                    if (repeat + start // size) % 2 == 0
                    else ["fixed8", "prediction"]
                )
                # No quality results feed back into the model or its choices.
                measured = {arm: trial.run(predicted=arm == "prediction") for arm in order}
                record: JsonDict = {
                    "repeat": repeat,
                    "start": start,
                    "images": len(chunk),
                    "warmup": repeat == 0,
                    "order": order,
                    "arms": {},
                }
                for arm, actual in measured.items():
                    folder = self.output / f"repeat-{repeat}" / f"{start:05d}-{arm}"
                    before = time.perf_counter()
                    outcome = O.run(
                        adapter,
                        policies,
                        libraries,
                        [quality] * len(chunk),
                        [row["selection"] for row in chunk],
                        actual,
                        folder,
                    )
                    for offset, row in enumerate(outcome["rows"]):
                        key = f"{arm}:{start + offset}"
                        signature = A.fingerprint(
                            {"choice": actual.choices[offset], "astc": row["astc_sha256"]}
                        )
                        if key in signatures and signatures[key] != signature:
                            raise ValueError(
                                "Fixed confirmation model produced inconsistent repeated outputs"
                            )
                        signatures[key] = signature
                    combined[arm].extend(outcome["rows"])
                    elapsed[arm] += actual.timings["end_to_end_seconds"]
                    encode_calls[arm] += actual.timings["encoding_calls"]
                    record["arms"][arm] = {
                        "timings": actual.timings,
                        "summary": outcome["summary"],
                        "outputs_sha256": outcome["outputs_sha256"],
                        "audit_and_write_seconds": time.perf_counter() - before,
                    }
                receipt = self.output / f"repeat-{repeat}" / f"{start:05d}-receipt.json"
                A.write_json(receipt, record)
                chunks.append({"path": str(receipt), "sha256": A.sha256_file(receipt)})
                state.update(
                    chunks_completed=state["chunks_completed"] + 1,
                    repetition=repeat,
                    completed_images_this_repetition=start + len(chunk),
                    latest_chunk_receipt=str(receipt),
                    latest_chunk_sha256=A.sha256_file(receipt),
                )
                A.write_json(self.report, state)
            for arm in combined:
                if [row["path"] for row in combined[arm]] != [
                    row["path"] for row in rows
                ] or encode_calls[arm] != count:
                    raise ValueError("Final confirmation coverage or single-encoding count differs")
            results.append(
                {
                    "repetition": repeat,
                    "warmup": repeat == 0,
                    "arms": {
                        arm: {
                            "summary": O.summarize(combined[arm]),
                            "end_to_end_seconds": elapsed[arm],
                            "encoding_calls": encode_calls[arm],
                        }
                        for arm in combined
                    },
                }
            )
            A.write_json(self.output / "repetitions.json", {"rows": results})
        repetitions = self.output / "repetitions.json"
        manifest = {
            "chunks": chunks,
            "repetitions": {"path": str(repetitions), "sha256": A.sha256_file(repetitions)},
        }
        self.verify_outputs(manifest, count)
        manifest_path = self.output / "outputs.json"
        A.write_json(manifest_path, manifest)
        self.evidence.verify()
        return {
            "outputs_manifest": {
                "path": str(manifest_path),
                "sha256": A.sha256_file(manifest_path),
            },
            "repetitions": results,
            "summary": {
                arm: {
                    **results[-1]["arms"][arm]["summary"],
                    "median_end_to_end_seconds": float(
                        np.median([row["arms"][arm]["end_to_end_seconds"] for row in results[1:]])
                    ),
                    "measured_encoding_calls": sum(
                        row["arms"][arm]["encoding_calls"] for row in results[1:]
                    ),
                    "warmup_encoding_calls": count,
                }
                for arm in ["prediction", "fixed8"]
            },
        }

    def run(self) -> JsonDict:
        started = time.perf_counter()
        training = self.evidence.model(self.config["training"])
        pipeline, pixels = self.evidence.pixel_audit(self.config["pixel_audit"])
        rows, indices = self.evidence.captures(pipeline, pixels)
        adapter = UnityCaptureInputAdapter(rows, "confirmation")
        backends = []
        for policy in self.evidence.policies:
            identity = self.evidence.read(policy.baseline.run_dir / "identity.json")
            dll = policy.baseline.project / "Assets/Editor/Astc/Plugins/astcenc-avx2-shared.dll"
            digest = identity["encoder_dlls"][dll.name]
            self.evidence.bind(dll, digest)
            backends.append(UnityASTCBackend(dll, digest))
        quality = self.quality()
        if any(
            Path(name).is_relative_to(self.output) or self.report == Path(name)
            for name in self.evidence.files
        ):
            raise ValueError("Evaluation output overlaps bound evidence")
        required_disk = max(10 * 1024**3, sum(row["width"] * row["height"] for row in rows) * 4 * 8)
        if (
            psutil.virtual_memory().available < 8 * 1024**3
            or shutil.disk_usage(self.root).free < required_disk
        ):
            raise RuntimeError("Insufficient memory or disk for complete confirmation evaluation")
        self.output.mkdir(parents=True, exist_ok=False)
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        state: JsonDict = {
            "status": "preparing",
            "test_opened": False,
            "training_updates": 0,
            "config_sha256": A.sha256_file(self.path),
            "config": str(self.path),
            "protocol_sha256": self.protocol_sha256,
            "evidence_seconds": time.perf_counter() - started,
            "images": len(rows),
            "cohort_isolation_scope": (
                "Reserved asset groups and source hashes; current native cohorts exact RGBA "
                "and aligned same-size near pixels. No historical resized/cropped semantic "
                "isolation claim"
            ),
            "cost_scope": (
                "Reference PNG through mip0 ASTC; audits/writes outside paired timing; "
                "full mip-chain import integration remains separate"
            ),
        }
        try:
            settings = training["config"]
            before = time.perf_counter()
            device = ExperimentRuntime.configure(settings["seed"])
            if device.type != "cuda" or torch.cuda.mem_get_info(device)[0] < 2 * 1024**3:
                raise RuntimeError("CUDA with2GiB free VRAM required")
            checkpoint = torch.load(
                Path(settings["output"]) / "best.pt", map_location="cpu", weights_only=False
            )
            S.verify_checkpoint(checkpoint, training)
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            torch.cuda.synchronize(device)
            state["model_load_and_cuda_seconds"] = time.perf_counter() - before
            predictor = UnityQualityInference(
                model,
                device,
                settings["validation_batch_size"],
                settings["zero_probability_threshold"],
            )
            assert pipeline.confirmation is not None
            contract = {
                "schema": "unity_native_inference_v1",
                "split": "confirmation",
                "cohort_fingerprint": A.fingerprint(
                    {
                        "reservation": pipeline.confirmation.smoke.reservation["manifest_sha256"],
                        "split": "confirmation",
                    }
                ),
                "inputs_fingerprint": adapter.fingerprint,
                "policies_fingerprint": A.fingerprint(
                    [policy.binding for policy in self.evidence.policies]
                ),
                "model": {
                    "checkpoint_sha256": training["checkpoint_sha256"],
                    "epoch": checkpoint["epoch"],
                },
                "decision": {
                    "evaluation_config_sha256": self.protocol_sha256,
                    "patch_size": 240,
                    "batch_size": predictor.batch_size,
                    "zero_probability_threshold": predictor.zero_threshold,
                    "image_chunk_size": self.config["image_chunk_size"],
                    "fixed8_preset": self.config["fixed8_preset"],
                    "warmups": 1,
                    "repetitions": 3,
                    "policy": "original_native_search_order",
                },
                "runtime": {
                    "torch": torch.__version__,
                    "numpy": np.__version__,
                    "device": str(device),
                },
                "files_sha256": self.seal_files(),
            }
            # Shared across all run names, keyed by the reserved primary cohort, never by model.
            seal = UnityEvaluationSeal(
                self.root / "experiment report/.local/unity-confirmation-seals", contract
            )
            state.update(
                seal=seal.acquire(),
                seal_path=str(seal.path),
                status="sealed_before_forward",
                checkpoint_sha256=training["checkpoint_sha256"],
                validation_metrics=training["checkpoint_audit"]["metrics"],
                parameters=sum(p.numel() for p in model.parameters()),
                weights_bytes=sum(
                    t.numel() * t.element_size() for t in model.state_dict().values()
                ),
            )
            A.write_json(self.report, state)
            result = seal.forward(
                lambda: self.evaluate(rows, indices, predictor, backends, quality, state)
            )
            seal.verify()
            state.update(
                status="passed",
                **result,
                inputs_sha256=self.evidence.files,
                accuracy90_met=result["summary"]["prediction"]["footprint_accuracy"] >= 0.90,
                original_search_seconds=sum(row["selection"]["search_ms"] for row in rows) / 1000,
                original_select_and_encode_seconds=sum(
                    row["selection"]["select_and_encode_ms"] for row in rows
                )
                / 1000,
                original_import_wall_seconds=sum(
                    row["import_metadata"]["import_wall_ms"] for row in rows
                )
                / 1000,
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(self.output / "receipt.json", state)
            A.write_json(self.report, state)
        return state
