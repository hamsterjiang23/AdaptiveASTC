"""Summarize complete real V4 development measurements and bind future test protocols."""

from __future__ import annotations

import csv
import gzip
import json
import statistics
from bisect import bisect_right
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.v3_policy import UnityV3Policy
from reproductions.unity_search_baseline.v4_experiment import UnityV4Experiment


class UnityV4Report:
    def __init__(self, root: Path, attempt: str) -> None:
        self.experiment = UnityV4Experiment(root)
        self.directory = self.experiment.public / f"benchmark1000-{attempt}"

    def build(self) -> JsonDict:
        self.experiment.prepare()
        result_path = self.directory / "result.json"
        result = A.read_json(result_path)
        if (
            result["status"] != "passed"
            or result["images"] != 1000
            or not result["model_parameters_and_buffers_unchanged"]
        ):
            raise ValueError("V4 report requires complete successful native measurements")
        measurements = result["measurements"]
        if len(measurements) != 108:
            raise ValueError("All nine controls and twelve measurement cells are required")
        baseline_cell = next(
            row
            for row in measurements
            if row["case"]["name"] == "v3_baseline"
            and (row["scope"], row["mode"], row["repeat"]) == ("files", "batch", 0)
        )
        with gzip.open(baseline_cell["trace"], "rt", encoding="utf-8") as stream:
            primary_baseline = json.load(stream)["choices"]
        outputs: JsonDict = {}
        rows = []
        distances: dict[str, list[float]] = {}
        for entry in self.experiment.entries:
            policy, texture = UnityV3Policy(entry["policy"]), entry["texture"]
            thresholds = {"psnr": policy.effective_threshold(texture)}
            if texture.normal:
                thresholds = {
                    "normal_mean_deg": policy.table["targetNormalMeanDeg"],
                    "normal_p95_deg": policy.table["targetNormalP95Deg"],
                }
            elif texture.srgb:
                thresholds["ms_ssim_db"] = policy.table["targetMsSsimDb"]
            for candidate in entry["candidates"]:
                for metric, threshold in thresholds.items():
                    distances.setdefault(metric, []).append(
                        candidate["metrics"][metric] - threshold
                    )
        A.write_json(
            self.experiment.public / "threshold-distances.json",
            {
                metric: {
                    "unit": "degrees" if metric.startswith("normal_") else "dB",
                    "count": len(values),
                    "signed_distance_percentiles": np.percentile(
                        values, [0, 5, 25, 50, 75, 95, 100]
                    ).tolist(),
                    "absolute_distance_within": {
                        str(limit): sum(abs(v) <= limit for v in values)
                        for limit in [0.25, 0.5, 1.0, 2.0]
                    },
                }
                for metric, values in distances.items()
            },
        )
        bindings = {str(result_path): A.sha256_file(result_path)}
        for case in A.read_json(self.experiment.public / "offline.json")["controls"]:
            name = case["name"]
            cells = [r for r in measurements if r["case"]["name"] == name]
            if len({(r["scope"], r["mode"], r["repeat"]) for r in cells}) != 12:
                raise ValueError("A V4 case has missing or duplicate timing cells")
            mode_hashes: dict[tuple[str, str], list[str]] = {}
            for cell in cells:
                for key in ["trace", "predictions"]:
                    path = Path(cell[key])
                    if A.sha256_file(path) != cell[f"{key}_sha256"]:
                        raise ValueError("A measurement archive changed")
                    bindings[str(path)] = cell[f"{key}_sha256"]
                mode = (cell["scope"], cell["mode"])
                if cell["astc_sha256"] != mode_hashes.setdefault(mode, cell["astc_sha256"]):
                    raise ValueError("Outputs differ between independent timing cells")
            with gzip.open(cells[0]["trace"], "rt", encoding="utf-8") as stream:
                trace = json.load(stream)
            choices = trace["choices"]
            file_singles = [r for r in cells if (r["scope"], r["mode"]) == ("files", "single")]
            latencies = (
                np.median(
                    np.asarray(
                        [r["timings"]["single_image_latencies_seconds"] for r in file_singles]
                    ),
                    axis=0,
                )
                * 1000
            )
            metrics = self.experiment.summarize(choices, baseline_rows=primary_baseline)
            metrics["max_strict_regressions_vs_v3_across_cells"] = max(
                cell["metrics"]["strict_regressions_vs_v3"] for cell in cells
            )
            metrics["frozen_prediction_difference_counts"] = [
                {
                    "scope": cell["scope"],
                    "mode": cell["mode"],
                    "repeat": cell["repeat"],
                    "images": len(cell["output_audit"]["frozen_prediction_differences"]),
                }
                for cell in cells
            ]
            classes = [6, 8, 10, 12]
            confusion = np.zeros((4, 4), dtype=np.int64)
            for entry, choice in zip(self.experiment.entries, choices, strict=True):
                original_block = entry["candidates"][entry["decision"].selected_index]["block"]
                selected_block = entry["candidates"][choice["selected_index"]]["block"]
                confusion[classes.index(original_block), classes.index(selected_block)] += 1
            metrics["classes"] = classes
            metrics["confusion"] = confusion.tolist()
            metrics["per_class_recall"] = {
                str(block): float(confusion[i, i] / confusion[i].sum())
                if confusion[i].sum()
                else None
                for i, block in enumerate(classes)
            }
            timing = {}
            for scope in ["files", "pixels_ready"]:
                for mode in ["batch", "single"]:
                    parts = [
                        r["timings"] for r in cells if (r["scope"], r["mode"]) == (scope, mode)
                    ]
                    timing[f"{scope}_{mode}"] = {
                        "median_total_seconds": statistics.median(
                            p["end_to_end_seconds"] for p in parts
                        ),
                        "median_mean_ms": statistics.median(p["end_to_end_seconds"] for p in parts),
                        "repetitions": parts,
                    }
                    # Every complete measurement has 1000 images, so total seconds equals mean ms.
            group_indices: dict[str, list[int]] = {}
            gate_changes = []
            for i, (entry, choice) in enumerate(zip(self.experiment.entries, choices, strict=True)):
                texture, selected = entry["texture"], choice["selected_index"]
                baseline = primary_baseline[i]["selected_index"]
                quality = choice["selected_metrics"]
                original = entry["decision"].selected_index
                row = {
                    "case": name,
                    "asset": entry["row"]["path"],
                    "width": texture.width,
                    "height": texture.height,
                    "srgb": texture.srgb,
                    "normal": texture.normal,
                    "need_alpha": texture.need_alpha,
                    "original_start": choice["original_start"],
                    "adjusted_start": choice["adjusted_start"],
                    "original_unity_index": original,
                    "v3_index": baseline,
                    "final_index": selected,
                    "block_size": choice["block_size"],
                    "quality": choice["preset"],
                    "selection_reason": choice["selection_reason"],
                    "strict_pass": choice["strict_quality_met"],
                    "v3_strict_pass": entry["strict"][baseline],
                    "payload_bytes": entry["row"]["payload_bytes"][selected],
                    "payload_ratio_to_v3": entry["row"]["payload_bytes"][selected]
                    / entry["row"]["payload_bytes"][baseline],
                    "encoding_count": len(choice["measured_indices"]),
                    "files_single_ms_median3": float(latencies[i]),
                    **quality,
                }
                baseline_quality = entry["candidates"][baseline]["metrics"]
                for metric in ["psnr", "ms_ssim_db", "normal_mean_deg", "normal_p95_deg"]:
                    value, old = quality.get(metric), baseline_quality.get(metric)
                    row[f"delta_{metric}_vs_v3"] = (
                        value - old if value is not None and old is not None else None
                    )
                rows.append(row)
                kind = (
                    "normal"
                    if texture.normal
                    else "linear"
                    if not texture.srgb
                    else "srgb_large"
                    if choice["size_first"]
                    else "srgb_small"
                )
                groups = [
                    kind,
                    f"alpha_{texture.need_alpha}",
                    f"preset_{choice['preset']}",
                    f"encodes_{len(choice['measured_indices'])}",
                    f"branch_{choice['selection_reason']}",
                ]
                side = max(texture.width, texture.height)
                size_labels = ("<512", "512-1023", "1024-2047", "2048-4095", ">=4096")
                groups.append(
                    f"max_side_{size_labels[bisect_right((512, 1024, 2048, 4096), side)]}"
                )
                if side in [2048, 4096]:
                    groups.append(f"max_side_exact_{side}")
                if (texture.width, texture.height) == (1780, 1000):
                    groups.append("resolution_1780x1000")
                for group in groups:
                    group_indices.setdefault(group, []).append(i)
                for gate in choice["gate_events"]:
                    if gate["skipped"]:
                        exhaustive = entry["candidates"][gate["candidate"]]["metrics"]
                        gate_changes.append(
                            {
                                "asset": row["asset"],
                                "candidate": gate["candidate"],
                                "skipped_exhaustive_strict_pass": entry["strict"][
                                    gate["candidate"]
                                ],
                                "final_minus_exhaustive_psnr_db": quality["psnr"]
                                - exhaustive["psnr"],
                                "final_minus_exhaustive_ms_ssim_db": quality["ms_ssim_db"]
                                - exhaustive["ms_ssim_db"],
                            }
                        )
                event = choice["unlock_event"]
                if (
                    event
                    and event["replaced"]
                    and 2 * row["payload_bytes"] > 3 * event["before_payload_bytes"]
                ):
                    raise ValueError("An actual unlock output violates the per-image budget")
            groups = {}
            for group, indices in group_indices.items():
                groups[group] = {
                    "metrics": self.experiment.summarize(
                        [choices[i] for i in indices],
                        indices,
                        baseline_rows=[primary_baseline[i] for i in indices],
                    ),
                    "mean_ms": float(np.mean(latencies[indices])),
                    "median_ms": float(np.median(latencies[indices])),
                    "p95_ms": float(np.percentile(latencies[indices], 95)),
                    "aggregation": "per-image median of three files/single repeats, then grouped",
                }
            for required in ["max_side_exact_2048", "max_side_exact_4096", "resolution_1780x1000"]:
                groups.setdefault(required, {"images": 0, "coverage": "missing_in_validation"})
            outputs[name] = {
                "options": case["options"],
                "metrics": metrics,
                "timing": timing,
                "groups": groups,
                "gate_quality_changes": gate_changes,
            }
        compatible_names = self.experiment.matrix["recommendations"]["compatibility"][
            "eligible_controls"
        ]
        compatible = [
            name
            for name in compatible_names
            if outputs[name]["metrics"]["accuracy"] >= 0.9
            and outputs[name]["metrics"]["max_strict_regressions_vs_v3_across_cells"] == 0
        ]
        eligible_quality = [
            name
            for name in outputs
            if outputs[name]["metrics"]["max_strict_regressions_vs_v3_across_cells"] == 0
        ]

        def change_count(name: str) -> int:
            options = outputs[name]["options"]
            return sum(
                [
                    options["start_mode"] != "original",
                    options["remove_lookahead"],
                    options["gate_margin_db"] is not None,
                    options["unlock"],
                ]
            )

        def duration(name: str) -> float:
            return outputs[name]["timing"]["files_single"]["median_mean_ms"]

        compatibility = min(
            compatible,
            key=lambda name: (
                -outputs[name]["metrics"]["accuracy"],
                -outputs[name]["metrics"]["full_choice_accuracy"],
                duration(name),
                outputs[name]["metrics"]["payload_bytes"],
                change_count(name),
            ),
        )
        quality = min(
            eligible_quality,
            key=lambda name: (
                -outputs[name]["metrics"]["actual_strict_quality_pass_rate"],
                duration(name),
                outputs[name]["metrics"]["payload_bytes"],
                change_count(name),
            ),
        )
        recommendations = {"compatibility": compatibility, "quality": quality}
        for label, name in recommendations.items():
            protocol = {
                "schema": "unity-v4-future-confirmation-protocol-v1",
                "status": "prepared_pending_new_cohort",
                "system": name,
                "options": outputs[name]["options"],
                "checkpoint": self.experiment.evidence["artifacts"]["checkpoint"],
                "binaries": self.experiment.evidence["binaries"],
                "execution_binding": str(self.directory / "execution-binding.json"),
                "execution_binding_sha256": A.sha256_file(
                    self.directory / "execution-binding.json"
                ),
                "candidate_set": self.experiment.matrix["candidate_set"],
                "quality_policy": "same_frozen_per-image_protocol",
                "timing": self.experiment.matrix["timing"],
                "development_evidence": str(result_path),
                "development_result_sha256": A.sha256_file(result_path),
                "new_cohort": None,
                "confirmation_execution_authorized": False,
                "cohort_requirements": [
                    "new_reserved_assets",
                    "unity_capture",
                    "pixel_isolation_audit",
                    "freeze_before_forward",
                ],
            }
            A.write_json(self.experiment.public / f"confirmation-protocol-{label}.json", protocol)
        csv_path = self.experiment.public / "per-image-results.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        summary = {
            "status": "completed_development",
            "images": 1000,
            "controls": outputs,
            "recommendations": recommendations,
            "training_updates": 0,
            "independent_confirmation": "pending_new_cohort",
            "config_aliases": {},
            "source_result": str(result_path),
            "source_result_sha256": A.sha256_file(result_path),
        }
        A.write_json(self.experiment.public / "summary.json", summary)
        lines = [
            "# V4开发实验报告",
            "",
            "本报告使用1000张开发验证图，参数选择与评价使用同一开发集。"
            "后续独立确认使用新资产。`[verified: summary.json images、independent_confirmation]`",
            "",
            "| 方案 | 块匹配 | 完整配置匹配 | 严格通过 | 相对V3回退 | 编码次数／图 | 平均ms |",
            "|---|---|---|---|---|---|---|",
        ]
        for name, control in outputs.items():
            m = control["metrics"]
            lines.append(
                f"| {name} | {m['accuracy']:.2%} | {m['full_choice_accuracy']:.2%} | "
                f"{m['actual_strict_quality_pass_rate']:.2%} | {m['strict_regressions_vs_v3']} | "
                f"{m['mean_encoding_count']:.3f} | {duration(name):.2f}。"
                f"`[verified: summary.json controls.{name}]` |"
            )
        lines += [
            "",
            f"原规则兼容推荐为{compatibility}，质量提升推荐为{quality}。"
            "`[verified: summary.json recommendations]`",
            "",
            "门控跳过样本的连续质量变化、分组指标和时间见summary.json，"
            "逐图信息见per-image-results.csv。"
            "`[verified: summary.json controls；per-image-results.csv]`",
            "",
            "真实计时包含新推理、编码、解码和质量门控。"
            "文件输入与像素就绪分别测量批量及逐图三轮，"
            "表中时间取文件逐图三轮平均值的中位数。"
            "`[verified: benchmark result.json measurements]`",
            "",
            "后续确认协议分别见confirmation-protocol-compatibility.json"
            "与confirmation-protocol-quality.json。`[verified: 对应协议status、new_cohort]`",
            "",
        ]
        (self.experiment.public / "README.md").write_text("\n".join(lines), encoding="utf-8")
        A.write_json(
            self.experiment.public / "verification.json",
            {
                "status": "passed",
                "cells": 108,
                "images_per_cell": 1000,
                "model_unchanged": True,
                "per_image_unlock_budget_checked": True,
                "source_archives_sha256": bindings,
                "summary_sha256": A.sha256_file(self.experiment.public / "summary.json"),
                "per_image_csv_sha256": A.sha256_file(csv_path),
            },
        )
        A.write_json(
            self.experiment.public / "progress.json",
            {
                "status": "completed_development",
                "summary": str(self.experiment.public / "summary.json"),
                "recommendations": recommendations,
                "training_updates": 0,
            },
        )
        return summary
