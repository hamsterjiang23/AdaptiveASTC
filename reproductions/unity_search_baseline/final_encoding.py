"""Encode frozen native validation predictions once and audit actual ASTC outcomes."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.encoder import ASTCFile
from reproductions.unity_search_baseline.candidate_completion import UnityCandidateCompletion
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.prediction_audit import UnityPredictionAudit
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import (
    UnityASTCBackend,
    UnitySupplementalCapture,
)


class UnityFinalEncoding:
    """Development-only encoding audit; saved inference has no new latency measurement."""

    def __init__(self, root: Path, config_path: Path) -> None:
        self.root = root.resolve()
        self.config_path = config_path.resolve()
        self.config = A.read_json(self.config_path)
        self.inputs: dict[str, str] = {}
        self.backends: dict[str, tuple[UnityASTCBackend, UnityQuality]] = {}
        self.resolver = UnityPredictionAudit(root, config_path)

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/final_encoding.py",
            "reproductions/unity_search_baseline/supplement.py",
            "reproductions/unity_search_baseline/quality.py",
            "reproductions/unity_search_baseline/candidate_completion.py",
            "reproductions/unity_search_baseline/policy.py",
            "reproductions/unity_search_baseline/policy_audit.py",
            "reproductions/unity_search_baseline/prediction_audit.py",
            "reproductions/common/encoder.py",
            "src/adaptive_astc/evaluation/unity_quality.py",
            "script/encode_unity_predictions.py",
        ]
        return {str((root / name).resolve()): A.sha256_file(root / name) for name in names}

    def bind(self, path: Path, expected: str | None = None) -> Path:
        path = path.resolve()
        digest = A.sha256_file(path)
        if expected is not None and digest != expected:
            raise ValueError(f"Final encoding input changed: {path}")
        if str(path) in self.inputs and self.inputs[str(path)] != digest:
            raise ValueError(f"Final encoding input changed during audit: {path}")
        self.inputs[str(path)] = digest
        return path

    def prepare(self) -> tuple[list[JsonDict], list[JsonDict], list[UnitySearchPolicy], JsonDict]:
        self.bind(self.config_path)
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Final encoding execution sources changed or are incomplete")
        for name, digest in self.config["sources_sha256"].items():
            self.bind(Path(name), digest)
        training_path = self.bind(
            Path(self.config["training_report"]), self.config["training_report_sha256"]
        )
        training = A.read_json(training_path)
        if training["status"] not in {"passed_smoke", "completed"} or training["test_opened"]:
            raise ValueError("Require completed native development training and checkpoint audit")
        settings = training["config"]
        run = Path(settings["output"])
        if A.read_json(self.bind(run / "config.json")) != settings:
            raise ValueError("Training config differs from the completed report")
        expected = training["best_artifacts_sha256"]
        if set(expected) != {"best.pt", "best-validation.npz", "best-decisions.json"}:
            raise ValueError("Require bound checkpoint, predictions and decisions")
        for name, digest in expected.items():
            self.bind(run / name, digest)
        audit = A.read_json(self.bind(run / "checkpoint-audit.json"))
        if (
            audit != training["checkpoint_audit"]
            or audit["status"] != "passed"
            or audit["test_opened"]
            or audit["selected_artifacts_sha256"] != expected
            or audit["checkpoint_sha256"] != expected["best.pt"]
            or training["checkpoint_sha256"] != expected["best.pt"]
        ):
            raise ValueError("Checkpoint reload audit does not bind the selected prediction")
        corpus = A.read_json(
            self.bind(Path(settings["corpus"]) / "corpus.json", settings["corpus_sha256"])
        )
        if corpus["status"] != "passed" or corpus["test_opened"]:
            raise ValueError("Require verified development corpus")
        rows = corpus["splits"]["validation"]
        if not rows or any(row["split"] != "validation" for row in rows):
            raise ValueError("Final encoding audit is restricted to development validation")
        policies = [self.resolver.policy_for(row) for row in rows]
        for row in rows:
            shard = A.read_json(
                self.bind(Path(row["source_shard"]["corpus"]), row["source_shard"]["sha256"])
            )
            self.bind(
                Path(shard["config"]["candidate_manifest"]),
                shard["config"]["candidate_manifest_sha256"],
            )
        with np.load(run / "best-validation.npz", allow_pickle=False) as saved:
            metrics, decisions = UnityQualityPrediction.score(
                rows, policies, saved["channel_mse"], saved["channel_zero"], saved["image_quality"]
            )
        recorded = A.read_json(run / "best-decisions.json")
        if decisions != recorded["rows"] or any(
            recorded["metrics"][key] != value for key, value in metrics.items()
        ):
            raise ValueError("Saved native decisions do not reproduce the frozen predictions")
        return rows, decisions, policies, training

    def candidate_source(
        self, row: JsonDict
    ) -> tuple[list[JsonDict], Path, UnityASTCBackend, UnityQuality]:
        shard = Path(row["source_shard"]["corpus"]).resolve()
        origin = self.resolver.sources[shard]["splits"]["validation"][row["source_shard"]["index"]]
        if origin["actual_options"] != row["actual_options"]:
            raise ValueError("Model and candidate encoder options differ")
        folder = Path(origin["candidate_directory"])
        raw_path = folder.parent / "receipt.json"
        raw = A.read_json(raw_path)
        config = raw["config"]
        public = A.read_json(self.bind(Path(config["report"]), origin["candidate_report_sha256"]))
        self.bind(raw_path, public["raw_receipt_sha256"])
        if (
            raw["status"] != "passed"
            or public["status"] != "passed"
            or raw["test_opened"]
            or public["test_opened"]
            or public["config"] != config
            or public["config_sha256"] != raw["config_sha256"]
        ):
            raise ValueError("Candidate archive has not completed or changed identity")
        candidates_path = self.bind(folder / "candidates.json", row["candidate_receipt_sha256"])
        candidates: list[JsonDict] = json.loads(candidates_path.read_text("utf-8"))
        if (
            [(item["block"], item["preset"]) for item in candidates] != UnityQualityPrediction.GRID
            or [item["metrics"] for item in candidates] != row["image_quality"]
            or [item["payload_bytes"] for item in candidates] != row["payload_bytes"]
        ):
            raise ValueError("Candidate grid or native targets changed")
        key = str(folder.parent.resolve())
        if key not in self.backends:
            capture = A.read_json(
                self.bind(
                    Path(config["capture"]) / "receipt.json", config["capture_receipt_sha256"]
                )
            )
            UnitySupplementalCapture.verify_capture_provenance(config, capture)
            UnityCandidateCompletion.verify_actual_options(config, capture)
            phase = config["capture_phase"]
            run = Path(config["capture_run"])
            for name in ["protocol-lock.json", "identity.json", f"{phase}-config.json"]:
                self.bind(run / name)
            phase_config = A.read_json(run / f"{phase}-config.json")
            identity = A.read_json(run / "identity.json")
            self.bind(
                Path(identity["project"])
                / phase_config["cacheDirectory"]
                / "parameter_cache_detail.jsonl"
            )
            self.bind(Path(config["options_receipt"]), config["options_receipt_sha256"])
            self.bind(run / f"{phase}-imports.jsonl", config["imports_sha256"])
            dll = self.bind(Path(config["encoder_dll"]), config["encoder_dll_sha256"])
            quality_receipt = self.bound_quality_receipt(raw)
            self.backends[key] = (
                UnityASTCBackend(dll, config["encoder_dll_sha256"]),
                UnityQuality(quality_receipt),
            )
        return candidates, folder, *self.backends[key]

    def bound_quality_receipt(self, raw: JsonDict) -> Path:
        path = self.bind(Path(raw["config"]["quality_build_receipt"]))
        binding = A.read_json(path)
        if binding != raw["quality_build"]:
            raise ValueError("Quality build differs from the original frozen candidate measurement")
        self.bind(Path(binding["dll"]), binding["dll_sha256"])
        return path

    @staticmethod
    def verify_metrics(actual: JsonDict, expected: JsonDict) -> None:
        if actual.keys() != expected.keys():
            raise ValueError("Native quality metric schema differs")
        for key, value in expected.items():
            if value is None or type(value) is bool or key == "mip_count":
                if actual[key] != value:
                    raise ValueError(f"Native metric scope differs: {key}")
            elif not np.isfinite(actual[key]) or abs(actual[key] - value) > 1e-5:
                raise ValueError(f"Re-encoded native quality differs: {key}")

    def encode_image(
        self, row: JsonDict, decision: JsonDict, policy: UnitySearchPolicy, output: Path
    ) -> JsonDict:
        candidates, archive, backend, quality = self.candidate_source(row)
        texture = UnityTextureInput.from_row(row)
        reference_path = self.bind(Path(row["reference"]), row["reference_sha256"])
        started = time.perf_counter()
        with Image.open(reference_path) as image:
            rgba = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
        preprocessing = time.perf_counter() - started
        if rgba.shape != (texture.height, texture.width, 4):
            raise ValueError("Reference dimensions differ from the model input")
        options = row["actual_options"]
        if (
            hashlib.sha256(rgba.tobytes()).hexdigest() != options["rgba_sha256"]
            or options["need_alpha"] is not texture.need_alpha
            or options["profile"] != (0 if texture.srgb else 1)
            or options["normal_pack"] is not False
            or options["channel"] != 4
        ):
            raise ValueError("Final encoder inputs differ from original captured options")
        output.mkdir()
        arms = {}
        fixed = UnityQualityPrediction.GRID.index((8, self.config["fixed8_preset"]))
        for name, index in [
            ("prediction", decision["predicted_decision"]["selected_index"]),
            ("fixed8", fixed),
        ]:
            candidate = candidates[index]
            block, preset = candidate["block"], candidate["preset"]
            stem = f"{block}x{block}_{preset}"
            archived_astc = self.bind(archive / f"{stem}.astc", candidate["astc_sha256"])
            archived_png = self.bind(archive / f"{stem}.png", candidate["decoded_png_sha256"])
            started = time.perf_counter()
            payload, decoded, timings = backend.encode_decode(
                rgba, block, preset, srgb=texture.srgb, need_alpha=texture.need_alpha
            )
            timings["encode_decode_wrapper_seconds"] = time.perf_counter() - started
            started = time.perf_counter()
            metrics = quality.measure(
                rgba,
                decoded,
                need_alpha=texture.need_alpha,
                compute_ssim=texture.srgb and not texture.normal,
                normal=texture.normal,
                mip_count=row["metadata"]["mip_count"] if texture.normal else 1,
            )
            timings["quality_seconds"] = time.perf_counter() - started
            self.verify_metrics(metrics, candidate["metrics"])
            container = backend.container(payload, texture.width, texture.height, block)
            if container != archived_astc.read_bytes():
                raise ValueError(
                    "Predicted/fixed8 ASTC differs from the corresponding measured candidate"
                )
            with Image.open(archived_png) as image:
                if not np.array_equal(np.asarray(image.convert("RGBA")), decoded[::-1]):
                    raise ValueError("Decoded pixels or orientation differ from measured candidate")
            astc_path, png_path = output / f"{name}.astc", output / f"{name}.png"
            astc_path.write_bytes(container)
            Image.fromarray(decoded[::-1]).save(png_path)
            astc = ASTCFile.read(astc_path)
            if astc.payload_bytes != candidate["payload_bytes"]:
                raise ValueError("Final payload differs from selected candidate geometry")
            strict = UnityQualityPrediction.strict_quality(
                policy, texture, metrics, decision["original_decision"]["effective_psnr_threshold"]
            )
            if name == "prediction" and strict != decision["actual_strict_quality_met"]:
                raise ValueError("Actual strict quality differs from prediction audit")
            arms[name] = {
                "block": block,
                "preset": preset,
                "encoding_calls": 1,
                "payload_bytes": astc.payload_bytes,
                "container_bytes": astc.container_bytes,
                "strict_quality_met": strict,
                "metrics": metrics,
                "timings": timings,
                "astc_sha256": A.sha256_file(astc_path),
                "decoded_png_sha256": A.sha256_file(png_path),
                "candidate_astc_matches": True,
                "candidate_decoded_pixels_match": True,
            }
        return {"path": row["path"], "reference_load_seconds": preprocessing, "arms": arms}

    def run(self) -> JsonDict:
        output, report = (
            Path(self.config["output"]).resolve(),
            Path(self.config["report"]).resolve(),
        )
        if not output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Final ASTC outputs belong under experiment report/.local")
        if report.exists() or report.is_relative_to(output):
            raise FileExistsError("Use a fresh, separate final-encoding report")
        if self.config["fixed8_preset"] not in UnityASTCBackend.PRESETS:
            raise ValueError("Invalid explicitly configured fixed8 preset")
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        state: JsonDict = {
            "status": "preparing",
            "rows": [],
            "test_opened": False,
            "training_updates": 0,
        }
        initial = output / "initial.json"
        A.write_json(initial, state)
        os.link(initial, report)
        initial.unlink()
        started = time.perf_counter()
        try:
            rows, decisions, policies, training = self.prepare()
            state.update(
                status="running",
                config=self.config,
                preparation_seconds=time.perf_counter() - started,
                checkpoint_sha256=training["checkpoint_sha256"],
                training_scope=training["status"],
                validation_images=len(rows),
                model_inference_seconds=None,
                end_to_end_seconds=None,
                timing_scope=(
                    "Saved validation predictions; native mip0 encoding/decode/quality only; "
                    "no inference or deployment speedup"
                ),
                policy_origins=self.resolver.origins,
            )
            for index, (row, decision, policy) in enumerate(
                zip(rows, decisions, policies, strict=True)
            ):
                state["rows"].append(
                    self.encode_image(row, decision, policy, output / f"{index:05d}")
                )
                A.write_json(report, state)
            for name, digest in list(self.inputs.items()):
                self.bind(Path(name), digest)
            state.update(
                status="passed",
                inputs_sha256=self.inputs,
                wall_seconds=time.perf_counter() - started,
                summary={
                    name: {
                        "images": len(rows),
                        "encoding_calls": len(rows),
                        "payload_bytes": sum(
                            r["arms"][name]["payload_bytes"] for r in state["rows"]
                        ),
                        "strict_quality_pass_rate": sum(
                            r["arms"][name]["strict_quality_met"] for r in state["rows"]
                        )
                        / len(rows),
                        "encode_seconds": sum(
                            r["arms"][name]["timings"]["encode_seconds"] for r in state["rows"]
                        ),
                    }
                    for name in ["prediction", "fixed8"]
                },
            )
        except BaseException as error:
            state.update(
                status="failed",
                error=repr(error),
                inputs_sha256=self.inputs,
                wall_seconds=time.perf_counter() - started,
            )
            A.write_json(output / "receipt.json", state)
            A.write_json(report, state)
            raise
        A.write_json(output / "receipt.json", state)
        A.write_json(report, state)
        return state
