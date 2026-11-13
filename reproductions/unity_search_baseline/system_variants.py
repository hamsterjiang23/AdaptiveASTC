"""Validation-only system variant evaluation from SHA-bound saved predictions."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.data.splitting import DatasetSplitter
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.system_variant_policy import (
    VariantOutcome,
    VariantSpec,
    replay_variant,
)
from script.attribute_unity_errors import grouped_metrics
from script.diagnose_unity_rules import UnityRuleDiagnostics


class FrozenInputs:
    def __init__(self) -> None:
        self.sources: dict[str, str] = {}
        self.documents: dict[str, JsonDict] = {}

    def bind(self, path: Path, expected: str | None = None) -> bytes:
        path = path.resolve()
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if expected is not None and actual != expected:
            raise ValueError(f"SHA-256 mismatch for {path}")
        previous = self.sources.setdefault(str(path), actual)
        if previous != actual:
            raise ValueError(f"Frozen input changed: {path}")
        return raw

    def read(self, path: Path, expected: str | None = None) -> JsonDict:
        key = str(path.resolve())
        if key in self.documents:
            if expected is not None and self.sources[key] != expected:
                raise ValueError(f"SHA-256 mismatch for {path}")
            return self.documents[key]
        raw = self.bind(path, expected)
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("Require a JSON object")
        self.documents[str(path.resolve())] = document
        return document

    def verify(self) -> None:
        for path, expected in self.sources.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Frozen input changed: {path}")


def offline_contract() -> JsonDict:
    return {
        "model_forward_calls": 0,
        "training_updates": 0,
        "test_opened": False,
        "actual_encoding_calls": 0,
    }


def variant_specs() -> list[VariantSpec]:
    variants = [
        VariantSpec("0_pure_model", "pure"),
        VariantSpec("original_search", "original"),
        VariantSpec("normal_native_search", "pure", normal_native=True),
    ]
    for normal_native in (False, True):
        prefix = "normal_native_search+" if normal_native else ""
        for start in ("candidate_idx", "block_start"):
            variants.append(
                VariantSpec(
                    prefix + "B1_" + start,
                    "forward",
                    start_mode=start,
                    normal_native=normal_native,
                )
            )
            for probe in ("predicted_preset", "canonical_block"):
                for budget in (None, 2, 3, 5):
                    suffix = "unlimited" if budget is None else f"K{budget}"
                    name = prefix + f"B2_{start}_{probe}_{suffix}"
                    variants.append(
                        VariantSpec(
                            name,
                            "bidirectional",
                            start_mode=start,
                            probe_mode=probe,
                            budget=budget,
                            normal_native=normal_native,
                        )
                    )
    return variants


def pareto_frontier(points: list[JsonDict]) -> list[JsonDict]:
    return [
        point
        for point in points
        if not any(
            other["accuracy"] >= point["accuracy"]
            and other["mean_candidates_measured"] <= point["mean_candidates_measured"]
            and (
                other["accuracy"] > point["accuracy"]
                or other["mean_candidates_measured"] < point["mean_candidates_measured"]
            )
            for other in points
        )
    ]


class UnitySystemVariants:
    def __init__(self, config_path: Path) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.config_path = config_path.resolve()
        self.frozen = FrozenInputs()
        self.config = self.frozen.read(self.config_path)
        if type(self.config["smoke"]) is not bool:
            raise ValueError("Require an explicit smoke flag")
        for relative, expected in self.config["execution_sources_sha256"].items():
            self.frozen.bind(self.root / relative, expected)
        self.diagnostics = UnityRuleDiagnostics(self.config_path)
        if self.diagnostics.config != self.config:
            raise ValueError("Configuration changed during initialization")

    def load_entries(self) -> tuple[list[JsonDict], list[int]]:
        config = self.config
        corpus = self.frozen.read(Path(config["corpus"]), config["corpus_sha256"])
        if (
            corpus["status"] != "passed"
            or corpus["coverage"] != "complete"
            or corpus["test_opened"] is not False
            or set(corpus["splits"]) != {"train", "validation"}
            or corpus["counts"] != {"train": 10000, "validation": 1000}
            or len(corpus["splits"]["validation"]) != 1000
        ):
            raise ValueError("Require the complete frozen development corpus")
        rows = corpus["splits"]["validation"]
        if any(row["split"] != "validation" for row in rows):
            raise ValueError("System variants are restricted to validation")
        for row in rows:
            source = row["source_shard"]
            shard = self.frozen.read(Path(source["corpus"]), source["sha256"])
            shard_config = shard["config"]
            manifest = self.frozen.read(
                Path(shard_config["candidate_manifest"]),
                shard_config["candidate_manifest_sha256"],
            )
            original = manifest["splits"]["validation"][source["index"]]
            if original["path"] != row["path"] or original["source_split"] != "validation":
                raise ValueError("Candidate archive belongs to a different validation input")
            candidate_path = Path(original["candidate_directory"]) / "candidates.json"
            candidates = json.loads(
                self.frozen.bind(candidate_path, row["candidate_receipt_sha256"])
            )
            if (
                original["candidate_receipt_sha256"] != row["candidate_receipt_sha256"]
                or [(item["block"], item["preset"]) for item in candidates]
                != list(UnityQualityPrediction.GRID)
                or [item["metrics"] for item in candidates] != row["image_quality"]
                or [item["payload_bytes"] for item in candidates] != row["payload_bytes"]
            ):
                raise ValueError("Canonical candidate metrics or payload differ from the corpus")
            for item in candidates:
                for name in ("encode_seconds", "decode_seconds", "quality_seconds"):
                    value = item["timings"][name]
                    if type(value) not in {float, int} or not math.isfinite(value) or value < 0:
                        raise ValueError("Archived candidate timing must be finite and nonnegative")
            row["system_variant_timings"] = [item["timings"] for item in candidates]
            batch = self.frozen.read(Path(original["candidate_directory"]).parent / "receipt.json")
            run = Path(batch["config"]["capture_run"])
            phase = batch["config"]["capture_phase"]
            identity = self.frozen.read(run / "identity.json")
            phase_config = self.frozen.read(run / f"{phase}-config.json")
            cache = (
                Path(identity["project"])
                / phase_config["cacheDirectory"]
                / "parameter_cache_detail.jsonl"
            )
            if str(cache.resolve()) not in self.frozen.sources:
                self.frozen.bind(cache)
        entries = self.diagnostics.prepare(rows)
        for entry in entries:
            entry["timings"] = entry["row"].pop("system_variant_timings")
        indices = list(range(1000))
        if config["smoke"]:
            indices = config["smoke_indices"]
            if (
                not indices
                or indices != sorted(set(indices))
                or any(not 0 <= i < 1000 for i in indices)
            ):
                raise ValueError("Require unique ordered validation smoke indices")
        return entries, indices

    def load_model(
        self, model: JsonDict, entries: list[JsonDict]
    ) -> tuple[JsonDict, JsonDict, JsonDict, float]:
        training = self.frozen.read(Path(model["training_report"]), model["training_report_sha256"])
        settings = training["config"]
        audit = training["checkpoint_audit"]
        if (
            training["status"] != "completed"
            or training["test_opened"] is not False
            or audit["status"] != "passed"
            or audit["test_opened"] is not False
            or settings["smoke"] is not False
            or settings["train_image_indices"]
            or settings["train_images"] != 10000
            or settings["validation_images"] != 1000
            or settings["corpus_sha256"] != self.config["corpus_sha256"]
            or Path(settings["corpus"]).resolve() / "corpus.json"
            != Path(self.config["corpus"]).resolve()
            or audit["selected_artifacts_sha256"] != training["best_artifacts_sha256"]
        ):
            raise ValueError("Require a completed selected model on the frozen development corpus")
        archive = Path(model["training_source_archive"])
        self.frozen.bind(
            archive / "manifest.json", model["training_source_archive_manifest_sha256"]
        )
        binding = PatchNormalizationAudit.bind_training_sources(
            {"source_files_sha256": settings["source_sha256"]},
            self.root,
            archive,
        )
        for source in binding["sources"]:
            self.frozen.bind(Path(source["verified_source"]), source["training_sha256"])
        output = Path(settings["output"])
        artifacts: dict[str, bytes] = {}
        for name, expected in training["best_artifacts_sha256"].items():
            raw = self.frozen.bind(output / name, expected)
            if name != "best.pt":
                artifacts[name] = raw
        if (
            self.frozen.read(output / "config.json") != settings
            or self.frozen.read(output / "checkpoint-audit.json") != audit
            or training["checkpoint_sha256"] != training["best_artifacts_sha256"]["best.pt"]
        ):
            raise ValueError("Frozen selected checkpoint evidence changed")
        with np.load(io.BytesIO(artifacts["best-validation.npz"]), allow_pickle=False) as saved:
            predictions = {name: saved[name].copy() for name in saved.files}
        np.testing.assert_array_equal(
            predictions["channel_zero"],
            predictions["zero_probability"] >= settings["zero_probability_threshold"],
        )
        metrics, replayed = UnityQualityPrediction.score(
            [entry["row"] for entry in entries],
            [entry["policy"] for entry in entries],
            predictions["channel_mse"],
            predictions["channel_zero"],
            predictions["image_quality"],
        )
        recorded = json.loads(artifacts["best-decisions.json"])
        if recorded["rows"] != replayed or metrics["accuracy"] != audit["metrics"]["accuracy"]:
            raise ValueError("Saved raw prediction decisions did not reproduce the selected model")
        calibration = self.frozen.read(
            Path(model["calibration_report"]),
            model["calibration_report_sha256"],
        )
        if (
            calibration["status"] != "completed"
            or calibration["test_opened"] is not False
            or calibration["training_updates"] != 0
            or calibration["model_forward_calls"] != 0
            or calibration["validation_images"] != 1000
        ):
            raise ValueError("Require completed validation-only frozen calibration")
        attribution = self.frozen.read(
            Path(calibration["config"]["attribution_report"]),
            calibration["config"]["attribution_report_sha256"],
        )
        if (
            attribution["config"]["training_report_sha256"] != model["training_report_sha256"]
            or Path(attribution["config"]["training_report"]).resolve()
            != Path(model["training_report"]).resolve()
        ):
            raise ValueError("Calibration belongs to a different frozen model")
        saved_calibration = self.frozen.read(
            Path(calibration["decisions"]),
            calibration["decisions_sha256"],
        )
        calibration["frozen_selected_rows"] = saved_calibration["rows"]
        cost = self.frozen.read(
            Path(model["inference_cost_report"]), model["inference_cost_report_sha256"]
        )
        if (
            cost["status"] != "passed"
            or cost["validation_images"] != 1000
            or cost["test_opened"] is not False
            or cost["training_updates"] != 0
            or cost["encoding_calls"] != 0
            or cost["checkpoint_sha256"] != training["checkpoint_sha256"]
        ):
            raise ValueError("Inference timing must bind the same frozen selected model")
        for entry in entries:
            row = entry["row"]
            if cost["inputs_sha256"].get(row["reference"]) != row["reference_sha256"]:
                raise ValueError("Inference timing used different validation PNG identities")
        model_ms = 1000 * cost["amortized_preprocess_inference_decision_seconds_per_image"]
        if not math.isfinite(model_ms) or model_ms < 0:
            raise ValueError("Inference cost must be finite and nonnegative")
        return training, predictions, calibration, model_ms

    @staticmethod
    def predictions(
        entries: list[JsonDict], arrays: JsonDict, parameters: JsonDict
    ) -> tuple[list[list[JsonDict]], list[JsonDict]]:
        candidates_by_image, decisions = [], []
        for index, entry in enumerate(entries):
            zero = arrays["zero_probability"][index] >= parameters["zero_probability_threshold"]
            candidates = UnityQualityPrediction.candidates(
                entry["texture"],
                arrays["channel_mse"][index],
                zero,
                arrays["image_quality"][index],
            )
            for candidate in candidates:
                metrics = candidate["metrics"]
                metrics["psnr"] -= parameters["psnr_margin_db"]
                if entry["texture"].normal:
                    metrics["normal_mean_deg"] += parameters["mean_angle_margin_deg"]
                    metrics["normal_p95_deg"] += parameters["p95_angle_margin_deg"]
                elif entry["texture"].srgb:
                    metrics["ms_ssim_db"] -= parameters["ssim_margin_db"]
            texture = entry["texture"]
            decision = entry["policy"].select(
                candidates,
                width=texture.width,
                height=texture.height,
                srgb=texture.srgb,
                normal=texture.normal,
            )
            candidates_by_image.append(candidates)
            decisions.append(asdict(decision))
        return candidates_by_image, decisions

    @staticmethod
    def summarize(
        entries: list[JsonDict],
        outcomes: list[VariantOutcome],
        model_ms: float,
    ) -> tuple[JsonDict, list[JsonDict]]:
        metrics = UnityRuleDiagnostics.summarize(
            entries,
            [outcome.selected_index for outcome in outcomes],
        )
        confusion = np.zeros((4, 4), dtype=np.int64)
        classes = [6, 8, 10, 12]
        observations = []
        families: dict[str, list[bool]] = defaultdict(list)
        estimated_ms, archive_reference_ms, historical_reference_ms = [], [], []
        archive_matched_ms = []
        encode_ms, quality_ms = [], []
        for entry, outcome in zip(entries, outcomes, strict=True):
            row, original = entry["row"], entry["decision"]
            block, preset = UnityQualityPrediction.GRID[outcome.selected_index]
            original_block = UnityQualityPrediction.GRID[original.selected_index][0]
            confusion[classes.index(original_block), classes.index(block)] += 1
            observation = {
                "path": row["path"],
                "predicted_decision": {
                    "selected_index": outcome.selected_index,
                    "block_size": f"{block}x{block}",
                    "preset": preset,
                },
                "original_decision": asdict(original),
                "footprint_match": block == original_block,
                "full_choice_match": outcome.selected_index == original.selected_index,
                "actual_strict_quality_met": bool(entry["strict"][outcome.selected_index]),
                **asdict(outcome),
            }
            observations.append(observation)
            family = DatasetSplitter.asset_group(row["path"].replace("\\", "/")).casefold()
            families[family].append(observation["footprint_match"])
            timings = entry["timings"]
            encoded = sum(timings[index]["encode_seconds"] for index in outcome.measured_indices)
            checked = sum(
                timings[index]["decode_seconds"] + timings[index]["quality_seconds"]
                for index in outcome.quality_checked_indices
            )
            encode_ms.append(1000 * encoded)
            quality_ms.append(1000 * checked)
            archive_cost_ms = 1000 * (encoded + checked) + model_ms * outcome.model_used
            archive_matched_ms.append(archive_cost_ms)
            archive_reference_ms.append(
                1000
                * sum(
                    sum(
                        timings[index][name]
                        for name in (
                            "encode_seconds",
                            "decode_seconds",
                            "quality_seconds",
                        )
                    )
                    for index in range(original.candidates_measured)
                )
            )
            historical = row["original_selection"]["search_ms"]
            if not math.isfinite(historical) or historical <= 0:
                raise ValueError("Original search timing must be finite and positive")
            historical_reference_ms.append(historical)
            estimated_ms.append(historical if outcome.native_routed else archive_cost_ms)
        groups = grouped_metrics([entry["row"] for entry in entries], observations)
        groups["direct_parent_macro"] = groups.pop("asset_group_macro")
        groups["asset_family_macro"] = {
            "groups": len(families),
            "accuracy": sum(sum(items) / len(items) for items in families.values()) / len(families),
        }
        per_class = {}
        recalls = []
        for index, block in enumerate(classes):
            support = int(confusion[index].sum())
            predicted = int(confusion[:, index].sum())
            correct = int(confusion[index, index])
            recall = correct / support if support else None
            if recall is not None:
                recalls.append(recall)
            per_class[f"{block}x{block}"] = {
                "support": support,
                "predicted": predicted,
                "precision": correct / predicted if predicted else None,
                "recall": recall,
            }
        counts = [len(outcome.measured_indices) for outcome in outcomes]
        native_counts = [entry["decision"].candidates_measured for entry in entries]
        mean_ms = float(np.mean(estimated_ms))
        metrics.update(
            actual_quality_pass_rate=metrics["actual_strict_quality_pass_rate"],
            balanced_accuracy=float(np.mean(recalls)),
            confusion_matrix=confusion.tolist(),
            per_class=per_class,
            groups=groups,
            candidates_measured={
                "mean": float(np.mean(counts)),
                "median": float(np.median(counts)),
                "p95": float(np.percentile(counts, 95)),
                "max": max(counts),
                "total": sum(counts),
            },
            original_candidates_measured={
                "mean": float(np.mean(native_counts)),
                "median": float(np.median(native_counts)),
                "p95": float(np.percentile(native_counts, 95)),
            },
            budget_exhausted_images=sum(outcome.budget_exhausted for outcome in outcomes),
            fallback_needs_prefix_backfill_images=sum(
                outcome.needs_prefix_backfill for outcome in outcomes
            ),
            model_routed_images=sum(outcome.model_used for outcome in outcomes),
            native_routed_images=sum(outcome.native_routed for outcome in outcomes),
            max_model_route_candidates_measured=max(
                (len(outcome.measured_indices) for outcome in outcomes if outcome.model_used),
                default=0,
            ),
            encoding_cost_estimate={
                "estimated_total_mean_ms": mean_ms,
                "estimated_total_median_ms": float(np.median(estimated_ms)),
                "estimated_total_p95_ms": float(np.percentile(estimated_ms, 95)),
                "mean_archived_encode_ms": float(np.mean(encode_ms)),
                "mean_archived_decode_and_quality_ms": float(np.mean(quality_ms)),
                "amortized_model_ms_per_model_routed_image": model_ms,
                "original_historical_search_mean_ms": float(np.mean(historical_reference_ms)),
                "original_archive_replay_mean_ms": float(np.mean(archive_reference_ms)),
                "archive_matched_total_mean_ms": float(np.mean(archive_matched_ms)),
                "estimated_speedup_vs_original_search": float(np.mean(historical_reference_ms))
                / mean_ms,
                "estimated_speedup_vs_archive_replay": float(np.mean(archive_reference_ms))
                / float(np.mean(archive_matched_ms)),
            },
            reaches_validation90=metrics["accuracy"] >= 0.9,
        )
        return metrics, observations

    def run(self) -> JsonDict:
        started = time.perf_counter()
        all_entries, indices = self.load_entries()
        entries = [all_entries[index] for index in indices]
        specs = variant_specs()
        output = Path(self.config["output"]).resolve()
        report = Path(self.config["report"]).resolve()
        if (
            not output.is_relative_to(self.root / "experiment report/.local")
            or report.is_relative_to(output)
            or output.exists()
            or report.exists()
        ):
            raise ValueError("Require fresh private output and an external report")
        controls = {"full_canonical_original_replay_images": 0, "zero_extra_budget_arms": 0}
        canonical = VariantSpec("canonical_control", "forward", budget=20)
        for entry in all_entries:
            result = replay_variant(entry, entry["candidates"], 0, canonical)
            original = entry["decision"]
            if (
                result.selected_index != original.selected_index
                or len(result.measured_indices) != original.candidates_measured
                or result.reason != original.selection_reason
            ):
                raise ValueError("Full canonical budget differs from original native search")
            controls["full_canonical_original_replay_images"] += 1
        self.frozen.verify()
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            stream.write('{"status":"running"}\n')
        state: JsonDict = {
            "status": "running",
            "config": self.config,
            **offline_contract(),
            "validation_images": len(entries),
            "ordered_validation_indices": indices,
            "variants": [asdict(spec) for spec in specs],
            "models": {},
            "scope": "Frozen development validation predictions and archived candidate metrics",
            "calibration_scope": "Already-fitted margins from the same validation1000",
            "encoding_count_scope": (
                "Projected unique encodes including the final selected ASTC. "
                "Selected measured results are reused"
            ),
            "budget_scope": (
                "K limits all unique encodes on model-routed images. "
                "Normal-native routes retain the original search count"
            ),
            "probe_preset_rule": (
                "First predicted strict preset within a block, "
                "otherwise first maximum predicted float32 PSNR"
            ),
            "budget_exhaustion_rule": (
                "Retain a measured strict incumbent, else last measured PSNR-pass "
                "in a locked block, else first measured highest PSNR"
            ),
            "large_rule": (
                "Preserve the native measured cross-block lookahead "
                "before the locked-block boundary check"
            ),
            "timing_scope": (
                "Native-routed images use their historical Unity search_ms. Model-routed "
                "images use archived encode/decode/quality durations plus measured "
                "batch-amortized PNG/input/inference/policy cost. The archive-matched "
                "estimate uses archived candidate durations on every route"
            ),
            "controls": controls,
        }
        points: list[JsonDict] = []
        try:
            with gzip.open(output / "decisions.jsonl.gz", "xt", encoding="utf-8") as trace:
                for model in self.config["models"]:
                    training, arrays, calibration, model_ms = self.load_model(model, all_entries)
                    raw_parameters = {
                        "zero_probability_threshold": training["config"][
                            "zero_probability_threshold"
                        ],
                        "psnr_margin_db": 0.0,
                        "ssim_margin_db": 0.0,
                        "mean_angle_margin_deg": 0.0,
                        "p95_angle_margin_deg": 0.0,
                    }
                    model_result: JsonDict = {"raw": {}, "calibrated": {}}
                    for mode, parameters in (
                        ("raw", raw_parameters),
                        ("calibrated", calibration["best_parameters"]),
                    ):
                        candidates, predicted = self.predictions(all_entries, arrays, parameters)
                        if mode == "calibrated":
                            expected = calibration["frozen_selected_rows"]
                            if any(
                                saved["path"] != entry["row"]["path"] or saved["decision"] != choice
                                for saved, entry, choice in zip(
                                    expected, all_entries, predicted, strict=True
                                )
                            ):
                                raise ValueError("Frozen calibrated predictions did not replay")
                        expected_accuracy = (
                            calibration["best_accuracy"]
                            if mode == "calibrated"
                            else training["checkpoint_audit"]["metrics"]["accuracy"]
                        )
                        accuracy = (
                            sum(
                                choice["selected_index"] // 5
                                == entry["decision"].selected_index // 5
                                for choice, entry in zip(predicted, all_entries, strict=True)
                            )
                            / 1000
                        )
                        if accuracy != expected_accuracy:
                            raise ValueError("Frozen raw/calibrated validation accuracy changed")
                        selected_predictions = [predicted[index] for index in indices]
                        selected_candidates = [candidates[index] for index in indices]
                        zero = VariantSpec("zero_control", "bidirectional", budget=0)
                        if any(
                            replay_variant(
                                entry, predicted_candidates, decision["selected_index"], zero
                            ).selected_index
                            != decision["selected_index"]
                            for entry, predicted_candidates, decision in zip(
                                entries, selected_candidates, selected_predictions, strict=True
                            )
                        ):
                            raise ValueError("Zero extra budget changed the pure model decision")
                        controls["zero_extra_budget_arms"] += 1
                        for spec in specs:
                            outcomes = [
                                replay_variant(
                                    entry, predicted_candidates, decision["selected_index"], spec
                                )
                                for entry, predicted_candidates, decision in zip(
                                    entries, selected_candidates, selected_predictions, strict=True
                                )
                            ]
                            if spec.budget is not None and any(
                                len(outcome.measured_indices) > spec.budget
                                for outcome in outcomes
                                if outcome.model_used
                            ):
                                raise ValueError("Model-routed query budget exceeded")
                            metrics, observations = self.summarize(entries, outcomes, model_ms)
                            model_result[mode][spec.name] = metrics
                            trace.write(
                                json.dumps(
                                    {
                                        "model": model["name"],
                                        "prediction_mode": mode,
                                        "variant": spec.name,
                                        "rows": observations,
                                    },
                                    ensure_ascii=False,
                                    allow_nan=False,
                                )
                                + "\n"
                            )
                            points.append(
                                {
                                    "model": model["name"],
                                    "prediction_mode": mode,
                                    "variant": spec.name,
                                    "accuracy": metrics["accuracy"],
                                    "mean_candidates_measured": metrics["candidates_measured"][
                                        "mean"
                                    ],
                                    "estimated_total_mean_ms": metrics["encoding_cost_estimate"][
                                        "estimated_total_mean_ms"
                                    ],
                                    "reaches_validation90": metrics["reaches_validation90"],
                                }
                            )
                    state["models"][model["name"]] = model_result
                    print(
                        {
                            "model": model["name"],
                            "raw_accuracy": training["checkpoint_audit"]["metrics"]["accuracy"],
                            "variants": len(specs),
                        },
                        flush=True,
                    )
            self.frozen.verify()
            eligible = [point for point in points if point["reaches_validation90"]]
            minimum = min((point["mean_candidates_measured"] for point in eligible), default=None)
            state.update(
                status="passed_smoke" if self.config["smoke"] else "completed",
                pareto_frontier=pareto_frontier(points),
                validation90_solutions=eligible,
                minimum_mean_candidates_at90=minimum,
                minimum_encoding_solutions_at90=[
                    point
                    for point in pareto_frontier(eligible)
                    if point["mean_candidates_measured"] == minimum
                ],
                policy_origins=self.diagnostics.resolver.origins,
                decisions_archive=str(output / "decisions.jsonl.gz"),
                decisions_archive_sha256=A.sha256_file(output / "decisions.jsonl.gz"),
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["sources_sha256"] = self.frozen.sources
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
        return state
