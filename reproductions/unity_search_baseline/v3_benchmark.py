"""Pair real V3 native encodings with independent throughput and latency measurements."""

from __future__ import annotations

import gzip
import hashlib
import json
import statistics
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceTexture
from adaptive_astc.data.unity_v3_input import SourceTextureSpec
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.unity_search_baseline.deployment import UnityDeploymentResult
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.v3_deployment import UnityV3DeploymentTrial
from reproductions.unity_search_baseline.v3_experiment import UnityV3Experiment
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy


class UnityV3Benchmark:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root = root.resolve()
        self.config_path = config_path.resolve()
        self.config = A.read_json(config_path)
        if self.config.get("schema") != "unity-v3-benchmark-v1":
            raise ValueError("Require an explicit V3 development benchmark schema")
        if type(self.config["smoke"]) is not bool:
            raise ValueError("Explicit smoke scope required")
        if self.config.get("confirmation_execution_authorized") is not False:
            raise ValueError("V3 development benchmark does not open confirmation")
        self.experiment = UnityV3Experiment(root)
        self.evidence = self.experiment.evidence
        self.output = Path(self.config["output"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        if not self.output.is_relative_to(self.experiment.private):
            raise ValueError("V3 runtime artifacts belong to its private experiment directory")
        self.bindings = dict(self.evidence["files_sha256"])
        self.bindings[str(self.config_path)] = A.sha256_file(self.config_path)
        for name, digest in self.config["execution_sources_sha256"].items():
            self.bindings[str(self.root / name)] = digest

    def verify(self) -> None:
        for name, digest in self.bindings.items():
            if A.sha256_file(Path(name)) != digest:
                raise ValueError(f"V3 benchmark input or execution source changed: {name}")

    def prepare(self) -> None:
        self.verify()
        self.entries, self.indices = self.experiment.entries(smoke=self.config["smoke"])
        source_path = Path(self.config["source_manifest"]["path"])
        self.bindings[str(source_path)] = self.config["source_manifest"]["sha256"]
        self.verify()
        source = A.read_json(source_path)
        if source["status"] != "passed" or source["test_opened"]:
            raise ValueError("Require successful development-only source audit")
        lookup = {row["asset"]: row for row in source["splits"]["validation"]}
        self.textures: list[UnityInferenceTexture] = []
        self.specs: list[SourceTextureSpec] = []
        for entry in self.entries:
            row = entry["row"]
            spec = lookup[row["path"]]
            path = Path(spec["source"])
            self.bindings[str(path)] = spec["source_sha256"]
            self.bindings[row["reference"]] = row["reference_sha256"]
            self.textures.append(
                UnityInferenceTexture(
                    Path(row["reference"]),
                    spec["srgb"],
                    spec["normal"],
                    spec["need_alpha"],
                    spec["normal_metric_mips"],
                )
            )
            self.specs.append(
                SourceTextureSpec(
                    path,
                    spec["source_width"],
                    spec["source_height"],
                    spec["target_width"],
                    spec["target_height"],
                    spec["srgb"],
                    spec["normal"],
                    spec["need_alpha"],
                    spec["normal_metric_mips"],
                    spec["asset"],
                )
            )
        self.verify()
        binaries = self.evidence["binaries"]
        dll = Path(binaries["astcenc-avx2-shared.dll"])
        self.backend = UnityASTCBackend(dll, self.bindings[str(dll)])
        self.quality = UnityQuality(Path(binaries["build-receipt.json"]))
        checkpoint = Path(self.config.get("checkpoint", self.evidence["artifacts"]["best.pt"]))
        expected = self.config.get("checkpoint_sha256") or self.bindings.get(str(checkpoint))
        if A.sha256_file(checkpoint) != expected:
            raise ValueError("Selected V3 benchmark checkpoint changed")
        self.bindings[str(checkpoint)] = expected
        device = ExperimentRuntime.configure(20261112)
        if device.type != "cuda":
            raise RuntimeError("Formal V3 model benchmarks require CUDA")
        data = torch.load(checkpoint, map_location="cpu", weights_only=False)
        model = UnityQualityRegressor.from_checkpoint(data, device)
        self.predictor = UnityQualityInference(model, device, 16, 0.5)

    def trial(self, case: JsonDict, indices: list[int]) -> UnityV3DeploymentTrial:
        textures = [self.textures[i] for i in indices]
        return UnityV3DeploymentTrial(
            textures,
            [self.entries[i]["policy"] for i in indices],
            [self.backend] * len(indices),
            [self.quality] * len(indices),
            self.predictor,
            candidate_set=NativeCandidateSet.from_name(case["candidate_set"]),
            input_mode=case["input_mode"],
            source_specs=[self.specs[i] for i in indices],
        )

    def measure(self, case: JsonDict, scope: str, mode: str) -> UnityDeploymentResult:
        if scope == "files":
            return self.trial(case, list(range(len(self.entries)))).run(
                case["arm"], single_image=mode == "single"
            )
        # Bounded chunks make buffers-ready timing independent of total source image bytes.
        results: list[UnityDeploymentResult] = []
        for offset in range(0, len(self.entries), 8):
            indices = list(range(offset, min(offset + 8, len(self.entries))))
            references = []
            for index in indices:
                with Image.open(self.textures[index].reference) as image:
                    references.append(np.asarray(image.convert("RGBA"), dtype=np.uint8))
            sources = None
            if case["input_mode"] != "unity" and case["arm"] in {"pure", "forward"}:
                sources = [self.specs[i].decoded_pixels() for i in indices]
            result = self.trial(case, indices).run(
                case["arm"],
                single_image=mode == "single",
                reference_pixels=references,
                source_pixels=sources,
            )
            results.append(result)
        timings: JsonDict = {
            "end_to_end_seconds": sum(r.timings["end_to_end_seconds"] for r in results),
            "encoding_calls": sum(r.timings["encoding_calls"] for r in results),
            "scope": "Independent pixels-ready measurements; buffers prepared outside the interval",
            "chunk_images": 8,
            "measurements": [r.timings for r in results],
        }
        if mode == "single":
            timings["single_image_latencies_seconds"] = [
                value for r in results for value in r.timings["single_image_latencies_seconds"]
            ]
        return UnityDeploymentResult(
            [b for r in results for b in r.containers],
            [c for r in results for c in r.choices],
            None,
            timings,
        )

    def audit(self, result: UnityDeploymentResult, case: JsonDict, destination: Path) -> JsonDict:
        destination.mkdir(parents=True, exist_ok=False)
        set_ = NativeCandidateSet.from_name(case["candidate_set"])
        for index, (entry, choice, container) in enumerate(
            zip(self.entries, result.choices, result.containers, strict=True)
        ):
            selected = choice["selected_index"]
            if selected not in set_.active_ids or any(
                i not in set_.active_ids for i in choice["measured_indices"]
            ):
                raise ValueError("Runtime used an excluded candidate")
            spec = self.textures[index]
            with Image.open(spec.reference) as image:
                reference = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
            block, _ = set_.candidate(selected)
            decoded, _ = self.backend.decode_payload(
                container[16:],
                entry["texture"].width,
                entry["texture"].height,
                block,
                srgb=spec.srgb,
            )
            metrics = self.quality.measure(
                reference,
                decoded,
                need_alpha=spec.need_alpha,
                compute_ssim=spec.srgb and not spec.normal,
                normal=spec.normal,
                mip_count=spec.normal_metric_mips,
            )
            expected = entry["candidates"][selected]["metrics"]
            for key, value in metrics.items():
                if value is not None and expected.get(key) is not None:
                    if not np.isclose(value, expected[key], rtol=0, atol=2e-4):
                        raise ValueError(f"Actual selected quality differs from archive: {key}")
            if len(container) - 16 != entry["row"]["payload_bytes"][selected]:
                raise ValueError("Actual ASTC byte count differs from candidate grid")
            policy = UnityV3Policy(entry["policy"], set_)
            if case["arm"] in {"original", "forward"}:
                start = choice["starting_decision"]
                replay = policy.search(
                    lambda i: entry["candidates"][i]["metrics"],
                    entry["texture"],
                    start["selected_index"] if start is not None else None,
                )
                if (
                    replay.decision.selected_index != selected
                    or list(replay.measured_indices) != choice["measured_indices"]
                ):
                    raise ValueError("Actual query trace differs from offline replay")
            choice["post_audit_metrics"] = metrics
            choice["post_audit_strict_quality_met"] = policy.strict_quality(
                metrics, entry["texture"]
            )
            (destination / f"{index:04}.astc").write_bytes(container)
            Image.fromarray(decoded[::-1]).save(destination / f"{index:04}.png")
        return self.experiment.summary(self.entries, result.choices)

    def run(self) -> JsonDict:
        if self.report.exists() or self.output.exists():
            raise FileExistsError("Use a fresh benchmark identity")
        self.output.mkdir(parents=True)
        started = time.perf_counter()
        state: JsonDict = {"status": "preparing", "test_opened": False, "results": {}}
        A.write_json(self.report, state)
        try:
            self.prepare()
            state.update(
                status="running", images=len(self.entries), validation_indices=self.indices
            )
            for case in self.config["cases"]:
                name = case["name"]
                print(json.dumps({"case": name, "stage": "warmup"}), flush=True)
                for _ in range(self.config["warmups"]):
                    self.trial(case, list(range(min(8, len(self.entries))))).run(case["arm"])
                record: JsonDict = {"case": case, "measurements": []}
                state["results"][name] = record
                for scope in self.config["scopes"]:
                    for mode in self.config["measurement_modes"]:
                        hashes: list[str] | None = None
                        seconds: list[float] = []
                        for repeat in range(self.config["repetitions"]):
                            print(
                                json.dumps(
                                    {"case": name, "scope": scope, "mode": mode, "repeat": repeat}
                                ),
                                flush=True,
                            )
                            self.verify()
                            result = self.measure(case, scope, mode)
                            actual = [hashlib.sha256(b).hexdigest() for b in result.containers]
                            if hashes is not None and actual != hashes:
                                raise ValueError(
                                    "Repeated trial outputs differ within a timing mode"
                                )
                            folder = self.output / name / f"{scope}-{mode}-{repeat}"
                            if repeat == 0:
                                metrics = self.audit(result, case, folder)
                                hashes = actual
                            else:
                                metrics = self.experiment.summary(self.entries, result.choices)
                            archive = self.output / f"{name}-{scope}-{mode}-{repeat}.json.gz"
                            with gzip.open(archive, "xt", encoding="utf-8") as stream:
                                json.dump(
                                    {
                                        "choices": result.choices,
                                        "astc_sha256": actual,
                                        "timings": result.timings,
                                    },
                                    stream,
                                )
                            seconds.append(result.timings["end_to_end_seconds"])
                            record["measurements"].append(
                                {
                                    "scope": scope,
                                    "mode": mode,
                                    "repeat": repeat,
                                    "timings": result.timings,
                                    "metrics": metrics,
                                    "trace_archive": str(archive),
                                    "trace_sha256": A.sha256_file(archive),
                                }
                            )
                            A.write_json(self.report, state)
                        record[f"{scope}_{mode}_median_seconds"] = statistics.median(seconds)
                A.write_json(self.report, state)
            self.verify()
            state.update(
                status="passed",
                files_sha256=self.bindings,
                wall_seconds=time.perf_counter() - started,
                confirmation_execution_authorized=False,
            )
        except BaseException as error:
            state.update(
                status="failed", error=repr(error), wall_seconds=time.perf_counter() - started
            )
            A.write_json(self.report, state)
            raise
        A.write_json(self.report, state)
        return state
