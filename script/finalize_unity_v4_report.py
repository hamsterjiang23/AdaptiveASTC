"""Expand the verified V4 development results into the requested interpretation report."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import statistics
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A

LABELS = {
    "v3_baseline": "当前V3",
    "remove_lookahead": "删除跨块前瞻",
    "calibrated_start": "起点校准",
    "exhaustive_gate": "exhaustive门控",
    "bounded_unlock": "50%预算大图解锁",
    "calibrated_start_no_lookahead": "起点校准＋删除前瞻",
    "calibrated_gate_no_lookahead": "起点校准＋删除前瞻＋门控",
    "calibrated_unlock_no_lookahead": "起点校准＋删除前瞻＋解锁",
    "combined": "完整组合",
}


def distribution(values: list[float]) -> JsonDict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "minimum": min(values),
        "median": statistics.median(values),
        "p95": float(np.percentile(values, 95)),
        "maximum": max(values),
    }


def timing_summary(cells: list[JsonDict], images: int) -> JsonDict:
    repetitions = []
    component_keys = [
        "input_preparation_seconds",
        "reference_load_metadata_and_flip_seconds",
        "inference_wall_seconds",
        "policy_and_bookkeeping_seconds",
        "native_encode_seconds",
        "native_decode_seconds",
        "native_quality_seconds",
    ]
    for cell in sorted(cells, key=lambda row: row["repeat"]):
        timing = cell["timings"]
        parts = timing["measurements"]
        repetitions.append(
            {
                "repeat": cell["repeat"],
                "total_seconds": timing["end_to_end_seconds"],
                "mean_ms": timing["end_to_end_seconds"] * 1000 / images,
                "latency_ms": distribution(
                    [value * 1000 for value in timing.get("single_image_latencies_seconds", [])]
                ),
                "component_ms_per_image": {
                    key.removesuffix("_seconds"): sum(part.get(key, 0.0) for part in parts)
                    * 1000
                    / images
                    for key in component_keys
                },
                "encoding_calls": timing["encoding_calls"],
                "output_audit_seconds": cell["output_audit"]["seconds"],
            }
        )
    result: JsonDict = {
        "repetitions": repetitions,
        "median_mean_ms": statistics.median(row["mean_ms"] for row in repetitions),
        "mean_ms_range": [
            min(row["mean_ms"] for row in repetitions),
            max(row["mean_ms"] for row in repetitions),
        ],
        "component_ms_per_image_median3": {
            key: statistics.median(row["component_ms_per_image"][key] for row in repetitions)
            for key in repetitions[0]["component_ms_per_image"]
        },
    }
    if cells[0]["mode"] == "single":
        result["median_latency_ms_median3"] = statistics.median(
            row["latency_ms"]["median"] for row in repetitions
        )
        result["p95_latency_ms_median3"] = statistics.median(
            row["latency_ms"]["p95"] for row in repetitions
        )
    return result


def candidate_cache_reuse(choice: JsonDict, options: JsonDict) -> JsonDict:
    gate_hits = sum(bool(event["probe_cached"]) for event in choice["gate_events"])
    unlock = choice["unlock_event"]
    # A relaxed search crosses into the next block once before stopping, unless
    # lookahead is removed or a gate already returned the relaxed result.
    unlock_hit = int(
        bool(unlock and unlock["rescue_queries"])
        and not options["remove_lookahead"]
        and not any(event["skipped"] for event in choice["gate_events"])
    )
    return {
        "gate_probe_cache_hits": gate_hits,
        "unlock_rescue_cache_hits": unlock_hit,
        "candidate_cache_hits": gate_hits + unlock_hit,
        "selected_payload_reused": choice["selected_encoded_result_reused"],
    }


def finalize(root: Path, attempt: str) -> JsonDict:
    public = root / "experiment report" / "unity-v4-20261117"
    summary = A.read_json(public / "summary.json")
    result = A.read_json(Path(summary["source_result"]))
    audit = A.read_json(public / "complete-artifact-audit.json")
    if (
        summary["status"] != "completed_development"
        or result["status"] != "passed"
        or not result["model_parameters_and_buffers_unchanged"]
        or audit["status"] != "passed"
        or audit["cells"] != 108
        or result["training_updates"] != 0
    ):
        raise ValueError(
            "The interpretation report requires the complete independently audited run"
        )
    expected = public / f"benchmark1000-{attempt}" / "result.json"
    if Path(summary["source_result"]).resolve() != expected.resolve():
        raise ValueError("The selected attempt differs from the reported native result")
    if A.sha256_file(expected) != summary["source_result_sha256"]:
        raise ValueError("The native result identity changed")
    csv_path = public / "per-image-results.csv"
    original_csv_sha256 = A.read_json(public / "verification.json").get(
        "original_per_image_csv_sha256", A.sha256_file(csv_path)
    )
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    if len(csv_rows) != 9000:
        raise ValueError("The report must retain all 1000 images for all nine controls")
    offline = A.read_json(public / "offline.json")
    diagnostic = A.read_json(public / "diagnostic-analysis.json")
    controls: JsonDict = {}
    primary: dict[str, list[JsonDict]] = {}
    baseline_assets = [row["asset"] for row in csv_rows if row["case"] == "v3_baseline"]
    if (
        len(baseline_assets) != 1000
        or len(set(baseline_assets)) != 1000
        or {row["case"] for row in csv_rows} != set(summary["controls"])
    ):
        raise ValueError(
            "The per-image CSV has missing, duplicate or undeclared assets or controls"
        )
    csv_checks = 0
    for name, control in summary["controls"].items():
        cells = [cell for cell in result["measurements"] if cell["case"]["name"] == name]
        modes = {}
        for scope in ["files", "pixels_ready"]:
            for mode in ["batch", "single"]:
                selected = [
                    cell for cell in cells if (cell["scope"], cell["mode"]) == (scope, mode)
                ]
                if len(selected) != 3:
                    raise ValueError("Each timing mode must have three complete repetitions")
                modes[f"{scope}_{mode}"] = timing_summary(selected, result["images"])
        first = next(
            cell
            for cell in cells
            if (cell["scope"], cell["mode"], cell["repeat"]) == ("files", "batch", 0)
        )
        with gzip.open(first["trace"], "rt", encoding="utf-8") as stream:
            primary[name] = json.load(stream)["choices"]
        case_rows = [row for row in csv_rows if row["case"] == name]
        if [row["asset"] for row in case_rows] != baseline_assets:
            raise ValueError("The CSV asset order or complete coverage differs between controls")
        single_cells = sorted(
            [cell for cell in cells if (cell["scope"], cell["mode"]) == ("files", "single")],
            key=lambda cell: cell["repeat"],
        )
        for index, (row, choice) in enumerate(zip(case_rows, primary[name], strict=True)):
            expected_fields = {
                "original_start": choice["original_start"],
                "adjusted_start": choice["adjusted_start"],
                "final_index": choice["selected_index"],
                "encoding_count": len(choice["measured_indices"]),
                "width": choice["gate_context"]["width"],
                "height": choice["gate_context"]["height"],
            }
            if any(int(row[key]) != value for key, value in expected_fields.items()):
                raise ValueError(f"The per-image CSV differs from the actual native trace: {name}")
            if (
                row["strict_pass"] != str(choice["strict_quality_met"])
                or row["quality"] != choice["preset"]
                or row["block_size"] != choice["block_size"]
                or row["selection_reason"] != choice["selection_reason"]
            ):
                raise ValueError("The CSV final decision differs from the actual native trace")
            for metric in ["psnr", "ms_ssim_db", "normal_mean_deg", "normal_p95_deg"]:
                value = choice["selected_metrics"].get(metric)
                csv_value = float(row[metric]) if row[metric] else None
                if csv_value != value:
                    raise ValueError("The CSV quality differs from the final native output")
            latency = (
                statistics.median(
                    cell["timings"]["single_image_latencies_seconds"][index]
                    for cell in single_cells
                )
                * 1000
            )
            if float(row["files_single_ms_median3"]) != latency:
                raise ValueError(
                    "The CSV latency differs from the actual repeated single-image runs"
                )
            for key, value in candidate_cache_reuse(choice, control["options"]).items():
                row[key] = str(value)
            csv_checks += 1
        if (
            sum(int(row["payload_bytes"]) for row in case_rows)
            != control["metrics"]["payload_bytes"]
        ):
            raise ValueError("The CSV total payload differs from the selected system summary")
        skipped = control["gate_quality_changes"]
        rows_by_asset = {row["asset"]: row for row in case_rows}
        controls[name] = {
            "label": LABELS[name],
            "options": control["options"],
            "primary_metrics": control["metrics"],
            "timing": modes,
            "candidate_cache_reuse": {
                key: sum(int(row[key]) for row in case_rows)
                for key in [
                    "gate_probe_cache_hits",
                    "unlock_rescue_cache_hits",
                    "candidate_cache_hits",
                ]
            },
            "selected_payload_reuses": sum(
                row["selected_payload_reused"] == "True" for row in case_rows
            ),
            "skipped_exhaustive": {
                "images": len(skipped),
                "skipped_strict_pass_candidates": sum(
                    row["skipped_exhaustive_strict_pass"] for row in skipped
                ),
                "final_minus_exhaustive_psnr_db": distribution(
                    [row["final_minus_exhaustive_psnr_db"] for row in skipped]
                ),
                "final_minus_exhaustive_ms_ssim_db": distribution(
                    [row["final_minus_exhaustive_ms_ssim_db"] for row in skipped]
                ),
                "final_minus_v3_psnr_db": distribution(
                    [float(rows_by_asset[row["asset"]]["delta_psnr_vs_v3"]) for row in skipped]
                ),
                "final_minus_v3_ms_ssim_db": distribution(
                    [
                        float(rows_by_asset[row["asset"]]["delta_ms_ssim_db_vs_v3"])
                        for row in skipped
                    ]
                ),
            },
            "metric_ranges_across_12_cells": {
                key: [min(c["metrics"][key] for c in cells), max(c["metrics"][key] for c in cells)]
                for key in [
                    "accuracy",
                    "full_choice_accuracy",
                    "actual_strict_quality_pass_rate",
                    "strict_regressions_vs_v3",
                    "mean_encoding_count",
                ]
            },
        }
    baseline = primary["v3_baseline"]
    assets = [row["asset"] for row in csv_rows if row["case"] == "v3_baseline"]
    original_indices = [
        int(row["original_unity_index"]) for row in csv_rows if row["case"] == "v3_baseline"
    ]
    for name, choices in primary.items():
        changed = []
        regressions = []
        unlocks = []
        for index, (old, new) in enumerate(zip(baseline, choices, strict=True)):
            if old["selected_index"] != new["selected_index"]:
                changed.append(index)
            if old["strict_quality_met"] and not new["strict_quality_met"]:
                regressions.append({"index": index, "asset": assets[index], "v3": old, "v4": new})
            event = new["unlock_event"]
            if event:
                unlocks.append({"index": index, "asset": assets[index], "event": event})
        controls[name]["changed_configuration_images"] = len(changed)
        controls[name]["configuration_recovered_vs_v3"] = sum(
            new["selected_index"] == original and old["selected_index"] != original
            for old, new, original in zip(baseline, choices, original_indices, strict=True)
        )
        controls[name]["configuration_matches_lost_vs_v3"] = sum(
            new["selected_index"] != original and old["selected_index"] == original
            for old, new, original in zip(baseline, choices, original_indices, strict=True)
        )
        controls[name]["strict_regression_examples"] = regressions
        controls[name]["unlock_events"] = unlocks
        controls[name]["unlock_outcomes"] = {
            "events": len(unlocks),
            "terminal_6x6": sum(row["event"]["next_block"] is None for row in unlocks),
            "budget_blocked": sum(
                row["event"]["next_block"] is not None and not row["event"]["budget_permitted"]
                for row in unlocks
            ),
            "budget_permitted": sum(row["event"]["budget_permitted"] for row in unlocks),
            "replaced": sum(row["event"]["replaced"] for row in unlocks),
            "allowed_but_unsuccessful": sum(
                row["event"]["budget_permitted"] and not row["event"]["replaced"] for row in unlocks
            ),
        }
    temporary_csv = public / "per-image-results.cache.tmp"
    with temporary_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    temporary_csv.replace(csv_path)
    interpretation = {
        "status": "verified_development_interpretation",
        "images": result["images"],
        "training_updates": result["training_updates"],
        "model_parameters_and_buffers_unchanged": result["model_parameters_and_buffers_unchanged"],
        "primary_metric_scope": "files_batch_repeat0",
        "timing_summary": "median_of_three_independent_repeat_statistics",
        "development_selection_split": offline["selection_split"],
        "offline_start_scan": offline["start_scan"],
        "offline_gate_scan": offline["gate_scan"],
        "highest_block_match_zero_regression_offline_start": min(
            [
                row
                for row in offline["start_scan"]
                if row["metrics"]["strict_regressions_vs_v3"] == 0
            ],
            key=lambda row: (
                -row["metrics"]["accuracy"],
                -row["metrics"]["full_choice_accuracy"],
                row["metrics"]["queries"],
            ),
        ),
        "failed_reachability": diagnostic["failed_reachability"],
        "configuration_mismatch_context": diagnostic["v3_config_mismatch_context"],
        "near_threshold_prediction_diagnostics": {
            metric: values["within_1"]
            for metric, values in diagnostic["threshold_prediction_diagnostics"].items()
        },
        "recommendations": summary["recommendations"],
        "per_image_csv_native_consistency_checks": csv_checks,
        "original_per_image_csv_sha256": original_csv_sha256,
        "cache_reuse_basis": (
            "Gate probe_cached flags and unlock lookahead reuse reconstructed from the "
            "frozen search path. Final selected-payload reuse is counted separately."
        ),
        "controls": controls,
        "separate_costs": {
            "model_loading_seconds": result["model_loading_seconds"],
            "binary_loading_seconds": result["binary_loading_seconds"],
            "entire_benchmark_wall_seconds": result["wall_seconds"],
            "unity_import_and_full_mip_chain": "outside_this_development_measurement",
        },
        "source_bindings": {
            str(public / "summary.json"): A.sha256_file(public / "summary.json"),
            str(expected): A.sha256_file(expected),
            str(public / "complete-artifact-audit.json"): A.sha256_file(
                public / "complete-artifact-audit.json"
            ),
            str(public / "per-image-results.csv"): A.sha256_file(public / "per-image-results.csv"),
            str(public / "diagnostic-analysis.json"): A.sha256_file(
                public / "diagnostic-analysis.json"
            ),
            str(Path(__file__).resolve()): A.sha256_file(Path(__file__).resolve()),
        },
    }
    A.write_json(public / "interpretation.json", interpretation)
    parent_path = (
        root / "experiment report/unity-v3-20261113/benchmark-trained-unity-full1000-v1-config.json"
    )
    parent_sources = A.read_json(parent_path)["execution_sources_sha256"]
    unlock_budget = A.read_json(root / "experiment plan/V4/matrix.json")["unlock"]
    protocol_hashes = {}
    for label, name in summary["recommendations"].items():
        protocol_path = public / f"confirmation-protocol-{label}.json"
        protocol = A.read_json(protocol_path)
        if (
            protocol["system"] != name
            or protocol["options"] != controls[name]["options"]
            or protocol["new_cohort"] is not None
            or protocol["confirmation_execution_authorized"]
        ):
            raise ValueError("The prepared confirmation protocol differs from the frozen selection")
        protocol["inherited_v3_execution_sources_sha256"] = parent_sources
        protocol["inherited_v3_config_sha256"] = A.sha256_file(parent_path)
        protocol["development_artifact_audit"] = {
            "path": str((public / "complete-artifact-audit.json").resolve()),
            "sha256": A.sha256_file(public / "complete-artifact-audit.json"),
        }
        protocol["pending_cohort_binding"] = [
            "ordered_new_asset_manifest_and_source_identities",
            "unity_reference_pixels_and_actual_import_options",
            "original_unity_search_labels_and_per_image_rule_tables",
            "complete_pixel_isolation_audit_against_observed_development_and_confirmation_assets",
            "cohort_assignment_and_shared_seal_contract_before_first_forward",
        ]
        protocol["planned_metrics"] = [
            "block_and_full_configuration_match_against_original_unity_labels",
            "actual_strict_quality_and_paired_v3_regressions_and_new_passes",
            "continuous_quality_changes_and_per_image_unlock_payload_budget",
            "encoding_calls_and_four_timing_modes_with_three_repetitions",
        ]
        protocol["paired_comparison"] = {
            "system": "v3_baseline",
            "options": controls["v3_baseline"]["options"],
            "same_scope_mode_and_repeat": True,
        }
        protocol["unlock_budget"] = unlock_budget
        protocol["test_opened"] = False
        A.write_json(protocol_path, protocol)
        protocol_hashes[str(protocol_path.resolve())] = A.sha256_file(protocol_path)
    write_report(public, interpretation, summary, attempt)
    verification = A.read_json(public / "verification.json")
    verification["original_per_image_csv_sha256"] = original_csv_sha256
    verification["per_image_csv_sha256"] = A.sha256_file(csv_path)
    verification["interpretation"] = {
        "independent_audit": str(public / "complete-artifact-audit.json"),
        "json_sha256": A.sha256_file(public / "interpretation.json"),
        "readme_sha256": A.sha256_file(public / "README.md"),
        "script_sha256": A.sha256_file(Path(__file__).resolve()),
        "csv_rows": len(csv_rows),
        "confirmation_protocols_sha256": protocol_hashes,
    }
    A.write_json(public / "verification.json", verification)
    return {"status": interpretation["status"], "recommendations": summary["recommendations"]}


def write_report(public: Path, analysis: JsonDict, summary: JsonDict, attempt: str) -> None:
    controls = analysis["controls"]
    baseline = controls["v3_baseline"]
    reference = baseline["primary_metrics"]
    lines = [
        "# V4开发实验报告与结论解读",
        "",
        "本轮使用1000张开发验证图，冻结ResNet-34及Unity参考输入，训练更新为0。"
        "参数选择与系统评价使用同一开发集，后续独立确认状态为待准备新资产。"
        "`[verified: summary.json images、training_updates、independent_confirmation]`",
        "",
        "## 怎么做及目的",
        "",
        "先重放原规则并诊断20候选的质量可达性，扫描19种起点和4种门控余量。"
        "固定参数后执行九组对照，每组覆盖文件输入与像素就绪、批量与逐图，共四种口径，"
        "每种独立重复三次。每轮重新推理并实际压缩、解压、检查质量，最终输出另行解码审计。"
        "`[verified: offline.json original_policy_checks、start_scan、gate_scan；"
        "complete-artifact-audit.json cells]`",
        "",
        "每个对照先用固定前8张图预热一次。文件批量口径一次调用1000张图，"
        "像素就绪批量按每组8张图调用，逐图口径每次调用1张图，四种口径独立计时。"
        "`[verified: v4_benchmark.py _run、measure]`",
        "",
        "起点校准检验能否找回跳过的配置，删除跨块前瞻检验能否省去不影响结果的查询，"
        "exhaustive门控检验时间与连续质量的取舍，大图解锁检验单图payload最多增加50%时的质量补救。"
        "`[verified: ../../experiment plan/V4/matrix.json controls、unlock]`",
        "",
        "## 九组结果",
        "",
        "质量与配置指标采用文件输入批量模式第一轮。时间采用三轮文件输入逐图平均值的中位数，"
        "各输入模式的指标范围和每轮数据保存在interpretation.json。"
        "`[verified: interpretation.json primary_metric_scope、timing_summary、controls]`",
        "",
        "块匹配以原Unity搜索标签为参照，完整配置匹配同时要求Blocksize和Quality一致。"
        "严格通过要求最终ASTC实际解码质量满足该图全部适用门槛。"
        "原标签回退统计原Unity选择严格合格而新方案未通过的图片。"
        "V3回退统计同一计时单元中V3通过而新方案未通过的图片，最大值取12个单元。"
        "`[verified: ../../experiment plan/V4/README.md 第4节“两类推荐标准”；"
        "script/diagnose_unity_rules.py summarize；"
        "v4_report.py max_strict_regressions_vs_v3_across_cells]`",
        "",
        "| 方案 | 块匹配 | 完整配置匹配 | 严格通过 | 原标签回退 | V3最大回退 | "
        "编码次数／图 | payload相对V3 | 逐图平均ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, control in controls.items():
        m = control["primary_metrics"]
        lines.append(
            f"| {LABELS[name]} | {m['accuracy']:.2%} | {m['full_choice_accuracy']:.2%} | "
            f"{m['actual_strict_quality_pass_rate']:.2%} | {m['quality_regression_images']} | "
            f"{m['max_strict_regressions_vs_v3_across_cells']} | "
            f"{m['mean_encoding_count']:.3f} | "
            f"{m['payload_bytes'] / reference['payload_bytes'] - 1:+.2%} | "
            f"{control['timing']['files_single']['median_mean_ms']:.2f}。"
            f"`[verified: interpretation.json controls.{name}]` |"
        )
    lines += [
        "",
        "payload按实际宽高补齐ASTC块后计算，每块16字节，完整ASTC容器另含16字节文件头。"
        "解锁的50%上限相对解锁前锁块输出计算，表中体积变化采用整集payload相对V3的比例。"
        "`[verified: supplement.py encode_decode、container；"
        "../../experiment plan/V4/README.md 第3节“受限大图解锁”]`",
        "",
        "候选缓存命中表示同图同次搜索中重复请求已测候选的次数，"
        "由门控probe_cached标记与解锁前瞻复用轨迹重建。实际编码次数和耗时来自原生执行记录，"
        "最终payload复用记录为selected_payload_reused。逐图CSV包含candidate_cache_hits及两类来源计数。"
        "`[verified: interpretation.json cache_reuse_basis；per-image-results.csv；"
        "v4_policy.py query；finalize_unity_v4_report.py candidate_cache_reuse]`",
    ]
    lines += [
        "",
        "## 门槛附近的预测误差",
        "",
        "下表按实测质量距对应门槛不超过1 dB或1度筛选，计数单位为候选记录。"
        "偏差采用预测值减实测值，误判合格与误判失败按每图实际质量分支判定。"
        "`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.*.within_1]`",
        "",
        "| 指标 | 记录数 | 单位 | 平均预测偏差 | RMSE | 误判合格 | 误判失败 |",
        "|---|---|---|---|---|---|---|",
    ]
    for metric, values in analysis["near_threshold_prediction_diagnostics"].items():
        lines.append(
            f"| {metric} | {values['count']} | {values['unit']} | "
            f"{values['prediction_minus_actual_mean']:+.4f} | {values['rmse']:.4f} | "
            f"{values['false_pass']} | {values['false_fail']}。"
            "`[verified: diagnostic-analysis.json "
            f"threshold_prediction_diagnostics.{metric}.within_1]` |"
        )
    lines += [
        "",
        "开发集196张完整配置不匹配图的原候选均位于预测起点之前，其中193张原候选严格合格。"
        "误判方向与偏差统计见[预测残差诊断](diagnostic-analysis.md)。"
        "`[verified: diagnostic-analysis.json v3_config_mismatch_context]`",
        "",
        "## 起点校准的结论",
        "",
        "下表为冻结预测与已存20候选质量的离线重放。起点按块匹配、完整配置匹配、较少查询数预筛，"
        "门控优先筛选严格回退0张，再比较严格通过率、exhaustive查询和总查询数。"
        "正式九组对照采用选中的一个起点配置和一个门控余量。"
        "`[verified: offline.json start_scan、gate_scan、selected_start、selected_gate_margin_db；"
        "../../experiment plan/V4/README.md 第3节]`",
        "",
        "| 起点方式 | PSNR补偿dB | MS-SSIM补偿dB | 块匹配 | 完整配置匹配 | 严格回退 | 查询数 |",
        "|---|---|---|---|---|---|---|",
    ]
    start_labels = {
        "original": "原起点",
        "back_one": "前移1候选",
        "back_two": "前移2候选",
        "same_block_fastest": "同块fastest",
        "margin": "质量预测补偿",
    }
    for index, row in enumerate(analysis["offline_start_scan"]):
        options, metrics = row["options"], row["metrics"]
        lines.append(
            f"| {start_labels[options['start_mode']]} | {options['psnr_margin_db']:g} | "
            f"{options['ms_ssim_margin_db']:g} | {metrics['accuracy']:.1%} | "
            f"{metrics['full_choice_accuracy']:.1%} | {metrics['strict_regressions_vs_v3']} | "
            f"{metrics['queries']}。`[verified: offline.json start_scan[{index}]]` |"
        )
    alternative = analysis["highest_block_match_zero_regression_offline_start"]
    lines += [
        "",
        f"零严格回退的离线起点中，最高块匹配为{alternative['metrics']['accuracy']:.1%}，"
        f"对应PSNR补偿{alternative['options']['psnr_margin_db']:g} dB、"
        f"MS-SSIM补偿{alternative['options']['ms_ssim_margin_db']:g} dB。"
        "本轮真实矩阵采用按既定匹配率预筛选出的配置，其他起点的实际速度及逐模式质量留待验证。"
        "`[verified: interpretation.json highest_block_match_zero_regression_offline_start；"
        "offline.json selected_start]`",
        "",
    ]
    calibrated = controls["calibrated_start"]["primary_metrics"]
    recovered = controls["calibrated_start"]["configuration_recovered_vs_v3"]
    lost = controls["calibrated_start"]["configuration_matches_lost_vs_v3"]
    lines += [
        f"起点预筛选中PSNR与MS-SSIM各加1 dB的预测补偿。真实主口径下，完整配置匹配从"
        f"{reference['full_choice_accuracy']:.1%}提高到{calibrated['full_choice_accuracy']:.1%}，"
        f"编码从{reference['mean_encoding_count']:.3f}增加到{calibrated['mean_encoding_count']:.3f}次／图，"
        f"相对V3严格质量回退{calibrated['strict_regressions_vs_v3']}张。"
        "`[verified: offline.json selected_start；summary.json controls.calibrated_start.metrics]`",
        "",
        "预测补偿用于重新选择起点，真实编码后的质量判定沿用每图原始门槛。"
        "`[verified: ../../experiment plan/V4/README.md 第3节“搜索起点校准”；"
        "calibration-native-regression.json measurements.*.choice.effective_psnr_threshold]`",
        "",
        f"逐图配对找回原先未匹配的完整配置{recovered}张，同时丢失原先匹配的{lost}张，"
        f"净增加{recovered - lost}张。"
        "`[verified: interpretation.json controls.calibrated_start "
        "configuration_recovered_vs_v3、configuration_matches_lost_vs_v3]`",
        "",
        f"校准后整集payload变化"
        f"{calibrated['payload_bytes'] - reference['payload_bytes']:+,}字节，"
        f"比例{calibrated['payload_bytes'] / reference['payload_bytes'] - 1:+.2%}，"
        f"文件逐图平均耗时为"
        f"{controls['calibrated_start']['timing']['files_single']['median_mean_ms']:.2f} ms。"
        "`[verified: interpretation.json controls.calibrated_start、controls.v3_baseline]`",
        "",
        "已归档的开发图94展示了锁块状态变化。前移后12×12 thorough的PSNR达标，"
        "搜索锁定12×12并返回放宽结果，MS-SSIM为18.65 dB。"
        "V3从12×12 exhaustive起搜，该候选PSNR未达标，"
        "后续10×10 exhaustive达到21.37 dB。"
        "`[verified: calibration-native-regression.json measurements]`",
        "",
        "该图原Unity标签为12×12 thorough放宽输出，校准后恢复了原标签配置，"
        "同时失去了V3在该图上的严格质量改善。"
        "`[verified: calibration-native-regression.json original_unity_selection、measurements]`",
        "",
        "因此，起点校准需要同时核查锁块行为和严格回退，配置匹配率提高本身不足以进入零回退推荐。"
        "`[opinion]`",
        "",
        "## 删除前瞻与门控的结论",
        "",
        "| 门控余量dB | 离线严格通过 | 离线严格回退 | exhaustive查询 | 总查询 |",
        "|---|---|---|---|---|",
    ]
    for index, row in enumerate(analysis["offline_gate_scan"]):
        metrics = row["metrics"]
        lines.append(
            f"| {row['options']['gate_margin_db']:g} | "
            f"{metrics['actual_strict_quality_pass_rate']:.1%} | "
            f"{metrics['strict_regressions_vs_v3']} | {metrics['exhaustive_queries']} | "
            f"{metrics['queries']}。`[verified: offline.json gate_scan[{index}]]` |"
        )
    lines.append("")
    removal = controls["remove_lookahead"]
    before = baseline["timing"]["files_single"]["median_mean_ms"]
    after = removal["timing"]["files_single"]["median_mean_ms"]
    gate_time = controls["exhaustive_gate"]["timing"]["files_single"]["median_mean_ms"]
    calibrated_main = controls["calibrated_start_no_lookahead"]
    calibrated_gate = controls["calibrated_gate_no_lookahead"]
    lines += [
        f"删除跨块前瞻后，平均查询从{reference['mean_encoding_count']:.3f}降至"
        f"{removal['primary_metrics']['mean_encoding_count']:.3f}次／图。四种口径、三次重复的12000组逐图配对"
        "保持最终ASTC一致，每轮减少91次末尾跨块查询。"
        "`[verified: lookahead-complete-comparison.json；"
        "summary.json controls.remove_lookahead.metrics]`",
        "",
        f"文件逐图平均时间为{before:.2f}→{after:.2f} ms，变化{after / before - 1:+.2%}。"
        "四种口径的时间表保留实际波动，较少查询与实际加速分别评价。"
        "`[verified: interpretation.json controls.v3_baseline.timing、"
        "controls.remove_lookahead.timing]`",
        "",
        f"独立exhaustive门控的文件逐图平均耗时为{gate_time:.2f} ms，"
        f"相对V3变化{gate_time - before:+.2f} ms／图、{gate_time / before - 1:+.2%}。"
        "其他计时口径的三轮结果见完整时间表。"
        "`[verified: interpretation.json controls.exhaustive_gate.timing、"
        "controls.v3_baseline.timing]`",
        "",
        "在已校准并删除前瞻的组合中，门控前后平均编码次数为"
        f"{calibrated_main['primary_metrics']['mean_encoding_count']:.3f}→"
        f"{calibrated_gate['primary_metrics']['mean_encoding_count']:.3f}，"
        "exhaustive查询总数为"
        f"{calibrated_main['primary_metrics']['exhaustive_queries']}→"
        f"{calibrated_gate['primary_metrics']['exhaustive_queries']}。"
        "文件逐图平均时间为"
        f"{calibrated_main['timing']['files_single']['median_mean_ms']:.2f}→"
        f"{calibrated_gate['timing']['files_single']['median_mean_ms']:.2f} ms。"
        "`[verified: interpretation.json controls.calibrated_start_no_lookahead、"
        "controls.calibrated_gate_no_lookahead]`",
        "",
        "| 门控方案 | 跳过exhaustive数 | 跳过严格合格候选数 | "
        "PSNR差均值／最小值dB | MS-SSIM差均值／最小值dB |",
        "|---|---|---|---|---|",
    ]
    for name in ["exhaustive_gate", "calibrated_gate_no_lookahead", "combined"]:
        gate = controls[name]["skipped_exhaustive"]
        psnr = gate["final_minus_exhaustive_psnr_db"]
        ssim = gate["final_minus_exhaustive_ms_ssim_db"]
        psnr_text = f"{psnr['mean']:+.3f}／{psnr['minimum']:+.3f}" if psnr["count"] else "无样本"
        ssim_text = f"{ssim['mean']:+.3f}／{ssim['minimum']:+.3f}" if ssim["count"] else "无样本"
        lines.append(
            f"| {LABELS[name]} | {gate['images']} | {gate['skipped_strict_pass_candidates']} | "
            f"{psnr_text} | {ssim_text}。"
            f"`[verified: interpretation.json controls.{name}.skipped_exhaustive]` |"
        )
    lines += [
        "",
        "表中差值为最终输出减去被跳过exhaustive的实测质量，负值表示该指标下降。"
        "严格回退另按同模式、同轮V3最终输出配对统计。"
        "`[verified: v4_report.py gate_changes；interpretation.json controls]`",
        "",
    ]
    for name in ["exhaustive_gate", "calibrated_gate_no_lookahead", "combined"]:
        gate = controls[name]["skipped_exhaustive"]
        psnr = gate["final_minus_v3_psnr_db"]
        ssim = gate["final_minus_v3_ms_ssim_db"]
        if psnr["count"]:
            lines += [
                f"{LABELS[name]}的跳过样本相对实际V3最终输出，PSNR平均差"
                f"{psnr['mean']:+.3f} dB、最小差{psnr['minimum']:+.3f} dB，"
                f"MS-SSIM平均差{ssim['mean']:+.3f} dB、最小差{ssim['minimum']:+.3f} dB。"
                f"`[verified: interpretation.json controls.{name}.skipped_exhaustive]`",
                "",
            ]
    lines += [
        "## 50%体积预算内的质量补救",
        "",
    ]
    unlock = controls["bounded_unlock"]["primary_metrics"]
    lines += [
        "开发集125张V3严格未通过图中，同块严格合格候选为0张，其他候选存在合格结果的为91张。"
        "其中52张位于50%payload预算内，39张的全部合格候选超出预算，34张在20候选内均无严格合格结果。"
        "`[verified: diagnostic-analysis.json failed_reachability；offline.json reachability]`",
        "",
        f"单独解锁实际新增严格合格{unlock['new_strict_pass_vs_v3']}张，严格通过率达到"
        f"{unlock['actual_strict_quality_pass_rate']:.1%}，总payload变化"
        f"{unlock['payload_bytes'] / reference['payload_bytes'] - 1:+.2%}。"
        "逐图预算核验覆盖实际替换事件。"
        "`[verified: summary.json controls.bounded_unlock.metrics；complete-artifact-audit.json]`",
        "",
        f"单独解锁的额外payload为"
        f"{unlock['payload_bytes'] - reference['payload_bytes']:+,}字节，"
        f"文件逐图平均耗时为"
        f"{controls['bounded_unlock']['timing']['files_single']['median_mean_ms']:.2f} ms，"
        f"平均编码{unlock['mean_encoding_count']:.3f}次／图。"
        "`[verified: interpretation.json controls.bounded_unlock、controls.v3_baseline]`",
        "",
        "| 解锁方案 | 解锁事件 | 6×6终点 | 预算阻止 | 预算允许 | 成功替换 | 允许但失败 |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in ["bounded_unlock", "calibrated_unlock_no_lookahead", "combined"]:
        outcomes = controls[name]["unlock_outcomes"]
        lines.append(
            f"| {LABELS[name]} | {outcomes['events']} | {outcomes['terminal_6x6']} | "
            f"{outcomes['budget_blocked']} | {outcomes['budget_permitted']} | "
            f"{outcomes['replaced']} | {outcomes['allowed_but_unsuccessful']}。"
            f"`[verified: interpretation.json controls.{name}.unlock_outcomes]` |"
        )
    lines += [
        "",
        "预算允许的下一块仍可能无法满足严格质量，失败时保留解锁前输出，追加查询进入实际耗时。"
        "6×6终点以空的下一块及候选payload记录。"
        "`[verified: interpretation.json controls.*.unlock_events；"
        "complete-artifact-audit.json counts]`",
        "",
        "## 两类推荐怎么选",
        "",
    ]
    for kind, heading in [("compatibility", "原规则兼容"), ("quality", "质量提升")]:
        name = summary["recommendations"][kind]
        control = controls[name]
        m = control["primary_metrics"]
        timing = control["timing"]["files_single"]
        lines += [
            f"**{heading}推荐为{LABELS[name]}**。块大小匹配{m['accuracy']:.2%}，完整配置匹配"
            f"{m['full_choice_accuracy']:.2%}，严格通过{m['actual_strict_quality_pass_rate']:.2%}，"
            f"相对同模式V3的最大严格回退数{m['max_strict_regressions_vs_v3_across_cells']}，"
            f"相对原Unity标签严格回退{m['quality_regression_images']}张，"
            f"文件逐图平均{timing['median_mean_ms']:.2f} ms。"
            f"`[verified: summary.json recommendations.{kind}；"
            f"interpretation.json controls.{name}]`",
            "",
            f"配置为`{json.dumps(control['options'], ensure_ascii=False)}`。"
            f"`[verified: summary.json controls.{name}.options]`",
            "",
        ]
    lines += [
        "原规则兼容按块匹配、完整配置匹配、真实时间、payload排序，质量提升按严格通过率、真实时间、"
        "payload排序。两类推荐均应用全部计时单元严格回退为0的筛选。"
        "`[verified: v4_report.py compatible、eligible_quality、recommendations]`",
        "",
        "质量提升方案主动允许更小块，原标签匹配率与严格质量通过率分别反映配置一致性和质量达标。"
        "`[opinion]`",
        "",
    ]
    selected_quality = controls[summary["recommendations"]["quality"]]["primary_metrics"]
    if selected_quality["new_strict_pass_vs_v3"] == 0:
        lines += [
            "本轮开发集未获得质量提升，质量类别交付当前最佳对照。"
            "`[verified: summary.json recommendations.quality；"
            "interpretation.json controls.*.primary_metrics.new_strict_pass_vs_v3]`",
            "",
        ]
    lines += [
        "## 一次完整处理耗时怎么读",
        "",
        "| 方案 | 文件批量摊销ms／图 | 文件逐图平均ms | 文件逐图中位数ms | "
        "文件逐图P95 ms | 像素就绪批量ms／图 | 像素就绪逐图平均ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, control in controls.items():
        timing = control["timing"]
        single = timing["files_single"]
        lines.append(
            f"| {LABELS[name]} | {timing['files_batch']['median_mean_ms']:.2f} | "
            f"{single['median_mean_ms']:.2f} | {single['median_latency_ms_median3']:.2f} | "
            f"{single['p95_latency_ms_median3']:.2f} | "
            f"{timing['pixels_ready_batch']['median_mean_ms']:.2f} | "
            f"{timing['pixels_ready_single']['median_mean_ms']:.2f}。"
            f"`[verified: interpretation.json controls.{name}.timing]` |"
        )
    lines += [
        "",
        "每列先分别计算各轮统计，再取三轮中位数。批量数据报告整集摊销，逐图分位数来自实际单图调用。"
        "`[verified: finalize_unity_v4_report.py timing_summary]`",
        "",
        "文件输入耗时包含PNG／属性准备、patch与模型推理、起点与搜索决策、每次ASTC编码、解码和质量门控，"
        "终点为最终内存mip0 ASTC。模型与DLL加载、输出审计及写盘另列，"
        "Unity导入与完整mip链处于本轮计时范围之外。"
        f"`[verified: benchmark1000-{attempt}/result.json "
        "measurements.timings.measurements.scope_details；"
        "interpretation.json separate_costs]`",
        "",
        "分段时间保存在interpretation.json的component_ms_per_image_median3。各分段分别取三轮中位数，"
        "相加可能与端到端三轮中位数存在差异。"
        "`[verified: finalize_unity_v4_report.py timing_summary]`",
        "",
        "| 推荐方案 | 输入准备 | 编码参考像素准备 | 推理 | 决策与记账 | 编码 | 解码 | 质量检查 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    selected_names = list(dict.fromkeys(["v3_baseline", *summary["recommendations"].values()]))
    phase_keys = [
        "input_preparation",
        "reference_load_metadata_and_flip",
        "inference_wall",
        "policy_and_bookkeeping",
        "native_encode",
        "native_decode",
        "native_quality",
    ]
    for name in selected_names:
        phases = controls[name]["timing"]["files_single"]["component_ms_per_image_median3"]
        values = " | ".join(f"{phases[key]:.2f}" for key in phase_keys)
        lines.append(
            f"| {LABELS[name]} | {values}。"
            f"`[verified: interpretation.json controls.{name}.timing.files_single]` |"
        )
    costs = analysis["separate_costs"]
    lines += [
        "",
        "分段表单位为ms／图，采用文件逐图口径。"
        f"本轮模型加载{costs['model_loading_seconds']:.3f}秒，"
        f"DLL加载{costs['binary_loading_seconds']:.3f}秒，"
        f"整个108单元基准流程耗时{costs['entire_benchmark_wall_seconds']:.2f}秒。"
        "逐单元输出审计成本见interpretation.json的output_audit_seconds。"
        "`[verified: interpretation.json separate_costs、controls.*.timing.*.repetitions]`",
        "",
        "本轮采用固定对照顺序，在当前桌面负载下测量，阶段资源采样见resource-observations.jsonl。"
        "时间结论以记录的三轮范围共同解释。"
        f"`[verified: benchmark1000-{attempt}/result.json measurements；"
        "resource-observations.jsonl]`",
        "",
        "## 类型与大图分组",
        "",
        "各方案的颜色、Linear、法线、Alpha、尺寸、Quality、编码次数及分支指标保存在summary.json的groups。"
        "2048、4096与1780×1000独立列出覆盖情况，0样本组使用missing_in_validation标记。"
        "`[verified: summary.json controls.*.groups]`",
        "",
        "| 方案 | 分组 | 图片数 | 严格通过 | 平均编码次数 | 平均ms | 中位ms | P95 ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    group_labels = {
        "srgb_small": "sRGB小图",
        "srgb_large": "sRGB大图",
        "linear": "Linear",
        "normal": "法线",
        "alpha_True": "需要Alpha",
        "alpha_False": "无需Alpha",
        "max_side_exact_2048": "最大边2048",
        "max_side_exact_4096": "最大边4096",
        "resolution_1780x1000": "1780×1000",
    }
    for name in selected_names:
        for key, label in group_labels.items():
            group = summary["controls"][name]["groups"].get(key)
            if not group or "metrics" not in group:
                lines.append(
                    f"| {LABELS[name]} | {label} | 0 | — | — | — | — | —。"
                    f"`[verified: summary.json controls.{name}.groups]` |"
                )
                continue
            metrics = group["metrics"]
            lines.append(
                f"| {LABELS[name]} | {label} | {metrics['images']} | "
                f"{metrics['actual_strict_quality_pass_rate']:.2%} | "
                f"{metrics['mean_encoding_count']:.3f} | {group['mean_ms']:.2f} | "
                f"{group['median_ms']:.2f} | {group['p95_ms']:.2f}。"
                f"`[verified: summary.json controls.{name}.groups.{key}]` |"
            )
    lines += [
        "",
        "分组时间先对每张图的三次文件逐图耗时取中位数，再在组内计算统计量。"
        "类型、Alpha与尺寸组存在交叉，逐组图片数用于说明覆盖范围。"
        "`[verified: v4_report.py latencies、group_indices、groups]`",
        "",
        "sRGB大图组按原规则的面积分支统计，2048与4096尺寸组按最大边统计，"
        "1780×1000组按精确分辨率统计。"
        "`[verified: v4_report.py kind、side、group_indices]`",
        "",
        "## 推荐方案的混淆矩阵与召回率",
        "",
        "矩阵行对应原Unity标签的块大小，列对应当前系统选择。召回率为该行对角线数除以该行总数。"
        "`[verified: v4_report.py confusion、per_class_recall]`",
        "",
    ]
    for name in selected_names:
        metrics = controls[name]["primary_metrics"]
        classes = metrics["classes"]
        lines += [
            f"### {LABELS[name]}",
            "",
            "| 原标签 | 选6×6 | 选8×8 | 选10×10 | 选12×12 | 召回率 |",
            "|---|---|---|---|---|---|",
        ]
        for block, counts in zip(classes, metrics["confusion"], strict=True):
            recall = metrics["per_class_recall"][str(block)]
            recall_text = "无样本" if recall is None else f"{recall:.2%}"
            values = " | ".join(str(value) for value in counts)
            lines.append(
                f"| {block}×{block} | {values} | {recall_text}。"
                f"`[verified: summary.json controls.{name}.metrics.confusion、per_class_recall]` |"
            )
        lines.append("")
    lines += [
        "## 失败记录与证据边界",
        "",
        "早期v2尝试在开发图901的逐图审计中失败。旧审计要求逐图新预测与冻结批量预测走相同轨迹，"
        "该图PSNR预测在30 dB门槛附近出现30.0008与29.9913 dB的模式差异。"
        "审计已改为用每轮实际预测重放当轮轨迹，冻结档案差异单列。v2失败源码、回执及三轮已完成数据保留，"
        "正式结论采用完整v3尝试。"
        "`[verified: runtime-mismatch901-diagnosis.json；"
        "runtime-mismatch901-recovery-check.json；implementation-notes.md]`",
        "",
        "32图闭环已覆盖图901及四种输入模式，正式测量使用同scope、mode和repeat的实际V3结果配对。"
        "`[verified: smoke32-v3-artifact-audit.json；"
        "complete-artifact-audit.json replay_prediction_source]`",
        "",
        "首轮一次性预算检查在开发图226的6×6终点遇到空值并触发TypeError。"
        "该图真实编码按协议保留6×6 exhaustive，检查程序加入终点分支后通过。"
        "独立验收入口同时核查预算禁止、解锁失败保留与完整ASTC容器字节数。"
        "`[verified: unlock-first-native-budget-audit.json checker_recovery、rows；"
        "script/verify_unity_v4.py unlock_event、native_payload_sizes_checked]`",
        "",
        "开发集上的参数选择与效果统计共享1000张图，独立泛化效果留待新资产确认。"
        "`[verified: offline.json selection_split；summary.json independent_confirmation]`",
        "",
        "## 后续训练与专项采集建议",
        "",
        "后续专项采集宜覆盖法线、Linear以及2048、4096、1780×1000尺寸，"
        "按本轮分组表的实际覆盖安排优先级。新资产同步保留Unity导入属性与原始搜索标签。"
        "`[opinion]`",
        "",
        "后续训练对照宜分别检查门槛附近的误判合格与误判失败样本，"
        "结合锁块轨迹确定采样或损失调整，再用冻结权重的完整系统对照验证。"
        "`[opinion]`",
        "",
        "## 产物与复现",
        "",
        "[逐图CSV](per-image-results.csv)、[原始汇总](summary.json)、[解读数据](interpretation.json)、"
        "[独立产物核验](complete-artifact-audit.json)、[原规则兼容确认协议](confirmation-protocol-compatibility.json)与"
        "[质量提升确认协议](confirmation-protocol-quality.json)绑定本轮结果。"
        "`[verified: verification.json；interpretation.json source_bindings]`",
        "",
        "新确认协议已绑定模型、候选、参数、执行源码、DLL与计时口径。新资产名单、原生采集、像素隔离和"
        "首次forward前冻结由cohort_requirements列明，执行授权状态保持待后续安排。"
        "`[verified: confirmation-protocol-compatibility.json；"
        "confirmation-protocol-quality.json]`",
        "",
        "在项目根目录核验和重建解读报告。`[opinion]`",
        "",
        "```powershell",
        f"uv run --no-sync python -u script/verify_unity_v4.py --attempt {attempt}",
        f"uv run --no-sync python script/finalize_unity_v4_report.py --attempt {attempt}",
        "```",
        "",
        "重新执行实验采用新的attempt身份，完整入口为"
        "`script/execute_unity_v4.py --attempt <新身份>`，"
        "离线扫描按当前已绑定开发数据重建，历史结果保留。"
        "`[verified: script/execute_unity_v4.py main；v4_benchmark.py run]`",
        "",
    ]
    (public / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="v3")
    args = parser.parse_args()
    result = finalize(Path(__file__).resolve().parents[1], args.attempt)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
