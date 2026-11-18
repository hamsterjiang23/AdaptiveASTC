"""Development-only V4 preparation, quality reachability and frozen-prediction replay."""

from __future__ import annotations

import gzip
import itertools
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.v3_policy import UnityV3Policy
from reproductions.unity_search_baseline.v4_policy import UnityV4Policy, V4Options
from script.diagnose_unity_rules import UnityRuleDiagnostics


class UnityV4Experiment:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.plan = self.root / "experiment plan/V4"
        self.public = self.root / "experiment report/unity-v4-20261117"
        self.private = self.root / "experiment report/.local/unity-v4-20261117"
        self.matrix = A.read_json(self.plan / "matrix.json")
        self.evidence = A.read_json(self.plan / "evidence.json")
        self.public.mkdir(parents=True, exist_ok=True)
        self.private.mkdir(parents=True, exist_ok=True)

    def verify(self) -> None:
        for name, record in self.evidence["files"].items():
            if A.sha256_file(Path(name)) != record["sha256"]:
                raise ValueError(f"V4 source identity changed: {name}")

    def prepare(self) -> None:
        self.verify()
        corpus = A.read_json(Path(self.evidence["artifacts"]["corpus"]["path"]))
        if {key: len(rows) for key, rows in corpus["splits"].items()} != {
            "train": 10000,
            "validation": 1000,
        }:
            raise ValueError("V4 requires the complete development splits")
        diagnostics = UnityRuleDiagnostics(self.root / "experiment plan/V3/evidence.json")
        self.entries = diagnostics.prepare(corpus["splits"]["validation"])
        prediction_path = Path(self.evidence["artifacts"]["validation_predictions"]["path"])
        with np.load(prediction_path, allow_pickle=False) as data:
            arrays = {
                key: data[key].copy() for key in ["channel_mse", "channel_zero", "image_quality"]
            }
        self.predictions = [
            UnityQualityPrediction.candidates(
                entry["texture"],
                arrays["channel_mse"][i],
                arrays["channel_zero"][i],
                arrays["image_quality"][i],
            )
            for i, entry in enumerate(self.entries)
        ]
        self.baselines = self.replay(V4Options())
        metrics = self.summarize(self.baselines)
        for key in [
            "accuracy",
            "full_choice_accuracy",
            "actual_strict_quality_pass_rate",
            "payload_bytes",
        ]:
            if metrics[key] != self.evidence["development_baseline"]["metrics"][key]:
                raise ValueError(f"V4 frozen V3 reproduction changed: {key}")
        self.smoke_indices = self.select_smoke()

    def select_smoke(self) -> list[int]:
        # This development image exposed a start change between batch and single inference.
        chosen: list[int] = [901]
        checks = {
            "normal": lambda e: e["texture"].normal,
            "linear": lambda e: not e["texture"].srgb and not e["texture"].normal,
            "alpha": lambda e: e["texture"].need_alpha,
            "color": lambda e: e["texture"].srgb and not e["texture"].normal,
            "relaxed": lambda e: e["decision"].selection_reason == "size_first_relaxed",
            "fallback": lambda e: e["decision"].selection_reason == "highest_psnr_fallback",
            "large": lambda e: max(e["texture"].width, e["texture"].height) >= 2048,
            "small": lambda e: max(e["texture"].width, e["texture"].height) < 128,
        }
        coverage = {}
        for name, condition in checks.items():
            available = [i for i, entry in enumerate(self.entries) if condition(entry)]
            coverage[name] = len(available)
            if available and not any(i in chosen for i in available):
                chosen.append(available[0])
        chosen += [i for i in range(1000) if i not in chosen][: 32 - len(chosen)]
        chosen.sort()
        A.write_json(
            self.public / "smoke-selection.json",
            {
                "indices": chosen,
                "coverage_in_validation": coverage,
                "assets": [self.entries[i]["row"]["path"] for i in chosen],
            },
        )
        return chosen

    def replay(self, options: V4Options) -> list[JsonDict]:
        records = []
        for entry, prediction in zip(self.entries, self.predictions, strict=True):
            base = UnityV3Policy(entry["policy"])

            def actual(index: int) -> JsonDict:
                return entry["candidates"][index]["metrics"]

            result = UnityV4Policy(base, options).search(actual, entry["texture"], prediction)
            row = result.record()
            row["selected_metrics"] = actual(result.decision.selected_index)
            records.append(row)
        return records

    def summarize(
        self,
        rows: list[JsonDict],
        indices: list[int] | None = None,
        *,
        baseline_rows: list[JsonDict] | None = None,
    ) -> JsonDict:
        indices = list(range(len(self.entries))) if indices is None else indices
        entries = [self.entries[i] for i in indices]
        result = UnityRuleDiagnostics.summarize(entries, [row["selected_index"] for row in rows])
        baseline = baseline_rows
        if baseline is None:
            baseline = [self.baselines[i] for i in indices] if hasattr(self, "baselines") else rows
        result.update(
            strict_regressions_vs_v3=sum(
                old["strict_quality_met"] and not new["strict_quality_met"]
                for old, new in zip(baseline, rows, strict=True)
            ),
            new_strict_pass_vs_v3=sum(
                not old["strict_quality_met"] and new["strict_quality_met"]
                for old, new in zip(baseline, rows, strict=True)
            ),
            queries=sum(len(row["measured_indices"]) for row in rows),
            exhaustive_queries=sum(i % 5 == 4 for row in rows for i in row["measured_indices"]),
            mean_encoding_count=float(np.mean([len(row["measured_indices"]) for row in rows])),
            gate_events=sum(len(row["gate_events"]) for row in rows),
            skipped_exhaustive=sum(
                event["skipped"] for row in rows for event in row["gate_events"]
            ),
            unlock_replacements=sum(
                bool(row["unlock_event"] and row["unlock_event"]["replaced"]) for row in rows
            ),
        )
        return result

    def reachability(self) -> JsonDict:
        rows = []
        errors: dict[str, list[float]] = {}
        false_pass: Counter[str] = Counter()
        false_fail: Counter[str] = Counter()
        for i, (entry, predicted) in enumerate(zip(self.entries, self.predictions, strict=True)):
            selected = self.baselines[i]["selected_index"]
            block = selected // 5
            passing = [k for k in range(20) if entry["strict"][k]]
            budget = [
                k
                for k in passing
                if 2 * entry["row"]["payload_bytes"][k]
                <= 3 * entry["row"]["payload_bytes"][selected]
            ]
            rows.append(
                {
                    "asset": entry["row"]["path"],
                    "baseline_index": selected,
                    "baseline_pass": entry["strict"][selected],
                    "passing_candidates": passing,
                    "same_block_pass": any(k // 5 == block for k in passing),
                    "other_block_pass": any(k // 5 != block for k in passing),
                    "skipped_prefix_pass": any(
                        k < self.baselines[i]["adjusted_start"] for k in passing
                    ),
                    "within_payload_budget_pass": bool(budget),
                    "budget_candidates": budget,
                }
            )
            policy, texture = UnityV3Policy(entry["policy"]), entry["texture"]
            thresholds = {"psnr": policy.effective_threshold(texture)}
            if texture.normal:
                thresholds = {
                    "normal_mean_deg": policy.table["targetNormalMeanDeg"],
                    "normal_p95_deg": policy.table["targetNormalP95Deg"],
                }
            elif texture.srgb:
                thresholds["ms_ssim_db"] = policy.table["targetMsSsimDb"]
            for actual, prediction in zip(entry["candidates"], predicted, strict=True):
                for metric, threshold in thresholds.items():
                    value, estimate = actual["metrics"][metric], prediction["metrics"][metric]
                    errors.setdefault(metric, []).append(estimate - value)
                    lower = metric.startswith("normal_")
                    true_pass = value <= threshold if lower else value >= threshold
                    pred_pass = estimate <= threshold if lower else estimate >= threshold
                    false_pass[metric] += pred_pass and not true_pass
                    false_fail[metric] += true_pass and not pred_pass
        archive = self.private / "reachability-rows.json"
        A.write_json(archive, {"rows": rows})
        return {
            "images": len(rows),
            "rows": str(archive),
            "rows_sha256": A.sha256_file(archive),
            "counts": {
                key: sum(bool(row[key]) for row in rows)
                for key in [
                    "baseline_pass",
                    "same_block_pass",
                    "other_block_pass",
                    "skipped_prefix_pass",
                    "within_payload_budget_pass",
                ]
            },
            "no_passing_candidate": sum(not row["passing_candidates"] for row in rows),
            "prediction_metrics": {
                key: {
                    "count": len(values),
                    "bias": float(np.mean(values)),
                    "rmse": float(np.sqrt(np.mean(np.square(values)))),
                    "false_pass": false_pass[key],
                    "false_fail": false_fail[key],
                }
                for key, values in errors.items()
            },
        }

    def offline(self) -> JsonDict:
        report = self.public / "offline.json"
        if report.exists():
            raise FileExistsError("Keep the existing V4 offline result identity")
        started = time.perf_counter()
        self.prepare()
        original_policy_checks = 0
        for entry, prediction, expected in zip(
            self.entries, self.predictions, self.baselines, strict=True
        ):
            policy = UnityV3Policy(entry["policy"])
            start = policy.select(prediction, entry["texture"]).selected_index
            actual = policy.search(
                lambda i: entry["candidates"][i]["metrics"], entry["texture"], start
            )
            if (
                asdict(actual.decision) != {k: expected[k] for k in asdict(actual.decision)}
                or list(actual.measured_indices) != expected["measured_indices"]
            ):
                raise ValueError("V4 baseline does not reproduce the frozen V3 search")
            original_policy_checks += 1
        configs = [
            V4Options(start_mode=mode)
            for mode in ["original", "back_one", "back_two", "same_block_fastest"]
        ]
        configs += [
            V4Options("margin", psnr, ssim)
            for psnr, ssim in itertools.product([0.0, 0.25, 0.5, 1.0], repeat=2)
            if psnr or ssim
        ]
        starts = []
        for options in configs:
            rows = self.replay(options)
            starts.append({"options": asdict(options), "metrics": self.summarize(rows)})
        selected_start = max(
            enumerate(starts),
            key=lambda pair: (
                pair[1]["metrics"]["accuracy"],
                pair[1]["metrics"]["full_choice_accuracy"],
                -pair[1]["metrics"]["queries"],
                -sum(pair[1]["options"][k] for k in ["psnr_margin_db", "ms_ssim_margin_db"]),
                -pair[0],
            ),
        )[1]
        gates = []
        for margin in [0.0, 0.5, 1.0, 2.0]:
            options = V4Options(gate_margin_db=margin)
            rows = self.replay(options)
            gates.append({"options": asdict(options), "metrics": self.summarize(rows)})
        eligible = [r for r in gates if r["metrics"]["strict_regressions_vs_v3"] == 0]
        selected_gate = (
            max(
                eligible,
                key=lambda r: (
                    r["metrics"]["actual_strict_quality_pass_rate"],
                    -r["metrics"]["exhaustive_queries"],
                    -r["metrics"]["queries"],
                    r["options"]["gate_margin_db"],
                ),
            )["options"]["gate_margin_db"]
            if eligible
            else None
        )
        controls, traces = [], {}
        for control in self.matrix["controls"]:
            options = (
                dict(selected_start["options"])
                if control["start"] == "selected"
                else asdict(V4Options())
            )
            options.update(
                remove_lookahead=control["remove_lookahead"],
                gate_margin_db=selected_gate if control["gate"] == "selected" else None,
                unlock=control["unlock"],
            )
            rows = self.replay(V4Options(**options))
            controls.append(
                {"name": control["name"], "options": options, "metrics": self.summarize(rows)}
            )
            traces[control["name"]] = rows
        archive = self.private / "offline-traces.json.gz"
        with gzip.open(archive, "xt", encoding="utf-8") as stream:
            json.dump(traces, stream)
        result = {
            "status": "passed",
            "images": 1000,
            "original_policy_checks": original_policy_checks,
            "reachability": self.reachability(),
            "start_scan": starts,
            "gate_scan": gates,
            "selected_start": selected_start,
            "selected_gate_margin_db": selected_gate,
            "controls": controls,
            "trace_archive": str(archive),
            "trace_sha256": A.sha256_file(archive),
            "training_updates": 0,
            "model_forward_calls": 0,
            "actual_encoding_calls": 0,
            "wall_seconds": time.perf_counter() - started,
            "selection_split": "validation",
        }
        self.verify()
        A.write_json(report, result)
        return result
