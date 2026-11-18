"""Describe frozen confirmation failures without evaluating or tuning a model."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from reproductions.unity_search_baseline.v3_policy import UnityV3Policy

OUTPUT = Path(__file__).resolve().parent
PUBLIC = OUTPUT.parent
ROOT = PUBLIC.parents[1]


def read(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def size_group(side: int) -> str:
    if side < 512:
        return "最大边<512"
    if side < 1024:
        return "最大边512–1023"
    if side < 2048:
        return "最大边1024–2047"
    if side < 4096:
        return "最大边2048–4095"
    return "最大边≥4096"


def summarize(rows: list[JsonDict]) -> JsonDict:
    latency = [r["single_ms_median3"] for r in rows]
    return {
        "images": len(rows),
        "quality_failures": sum(r["quality_failed"] for r in rows),
        "quality_failure_rate": sum(r["quality_failed"] for r in rows) / len(rows),
        "config_mismatches": sum(r["config_mismatch"] for r in rows),
        "block_mismatches": sum(r["block_mismatch"] for r in rows),
        "mean_ms": float(np.mean(latency)),
        "median_ms": float(np.median(latency)),
        "p95_ms": float(np.percentile(latency, 95)),
    }


def write_csv(name: str, rows: list[JsonDict]) -> None:
    with (OUTPUT / name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    result = read(PUBLIC / "result.json")
    assert result["status"] == "passed" and result["images"] == 2000
    primary = result["measurements"][0]
    directory = Path(primary["outputs_manifest"]["path"]).parent
    native_rows = read(directory / "rows.json")["rows"]
    assert (
        hashlib.sha256(Path(primary["trace"]).read_bytes()).hexdigest() == primary["trace_sha256"]
    )
    trace = json.loads(gzip.decompress(Path(primary["trace"]).read_bytes()))
    prepared = read(
        ROOT / "experiment report/.local/unity-v3-confirmation-20261116/prepared-inputs.json"
    )
    latency = (
        np.median(
            np.asarray(
                [
                    row["timings"]["single_image_latencies_seconds"]
                    for row in result["measurements"]
                    if (row["scope"], row["mode"]) == ("files", "single")
                ]
            ),
            axis=0,
        )
        * 1000
    )
    assert latency.shape == (2000,)
    grid = [
        (f"{b}x{b}", q)
        for b in [12, 10, 8, 6]
        for q in ["fastest", "fast", "medium", "thorough", "exhaustive"]
    ]
    rows = []
    for index, (row, choice, captured) in enumerate(
        zip(native_rows, trace["choices"], prepared["rows"], strict=True)
    ):
        assert row["path"] == captured["path"] and choice["source_index"] == index
        assert row["astc_sha256"] == trace["astc_sha256"][index]
        policy = UnityV3Policy(prepared["policy_tables"][prepared["policy_indices"][index]])
        texture = UnityTextureInput(**choice["gate_context"])
        metrics = choice["selected_metrics"]
        assert policy.strict_quality(metrics, texture) == row["strict_quality_met"]
        failed = []
        if row["normal"]:
            if metrics["normal_mean_deg"] > policy.table["targetNormalMeanDeg"]:
                failed.append("法线平均角度")
            if metrics["normal_p95_deg"] > policy.table["targetNormalP95Deg"]:
                failed.append("法线P95角度")
        else:
            if metrics["psnr"] < row["effective_psnr_threshold"]:
                failed.append("PSNR")
            if row["srgb"] and metrics["ms_ssim_db"] < policy.table["targetMsSsimDb"]:
                failed.append("MS-SSIM")
        assert bool(failed) == (not row["strict_quality_met"])
        original = row["original_selection"]
        original_index = grid.index((original["block_size"], original["preset"]))
        kind = (
            "法线"
            if row["normal"]
            else (
                "sRGB大图"
                if row["srgb"] and row["size_first"]
                else "sRGB小图"
                if row["srgb"]
                else "Linear"
            )
        )
        rows.append(
            {
                "asset": row["path"],
                "width": row["width"],
                "height": row["height"],
                "type": kind,
                "size_group": size_group(max(row["width"], row["height"])),
                "resolution": f"{row['width']}×{row['height']}",
                "quality_failed": not row["strict_quality_met"],
                "failed_metrics": "+".join(failed) or "通过",
                "config_mismatch": not row["full_choice_match"],
                "block_mismatch": not row["footprint_match"],
                "original_block": original["block_size"],
                "original_quality": original["preset"],
                "original_reason": original["selection_reason"],
                "original_strict_pass": original["selection_reason"]
                in {"first_valid", "size_first_strict"},
                "starting_block": choice["starting_decision"]["block_size"],
                "starting_quality": choice["starting_decision"]["preset"],
                "original_before_start": original_index
                < choice["starting_decision"]["selected_index"],
                "final_block": row["block_size"],
                "final_quality": row["preset"],
                "final_reason": choice["selection_reason"],
                "psnr_db": metrics["psnr"],
                "psnr_threshold_db": row["effective_psnr_threshold"],
                "psnr_margin_db": metrics["psnr"] - row["effective_psnr_threshold"],
                "ms_ssim_db": metrics["ms_ssim_db"],
                "ms_ssim_threshold_db": policy.table["targetMsSsimDb"] if row["srgb"] else None,
                "normal_mean_deg": metrics["normal_mean_deg"],
                "normal_p95_deg": metrics["normal_p95_deg"],
                "encoding_calls": row["candidates_measured"],
                "single_ms_median3": float(latency[index]),
                "reference_png": captured["reference_png"],
                "decoded_png": str(directory / f"{index:05d}.png"),
            }
        )
    failures = [r for r in rows if r["quality_failed"]]
    mismatches = [r for r in rows if r["config_mismatch"]]
    assert len(failures) == 228 and len(mismatches) == 267
    assert not any(r["original_strict_pass"] for r in failures)
    types = {
        k: summarize([r for r in rows if r["type"] == k])
        for k in ["sRGB大图", "sRGB小图", "Linear", "法线"]
    }
    sizes = {
        k: summarize([r for r in rows if r["size_group"] == k])
        for k in dict.fromkeys(r["size_group"] for r in rows)
    }
    resolutions = {
        k: summarize([r for r in rows if r["resolution"] == k])
        for k in sorted(set(r["resolution"] for r in rows))
    }
    summary = {
        "images": 2000,
        "strict_quality_failures": 228,
        "config_mismatches": 267,
        "block_mismatches": sum(r["block_mismatch"] for r in rows),
        "quality_pass_among_config_mismatches": sum(not r["quality_failed"] for r in mismatches),
        "quality_failure_metrics": dict(Counter(r["failed_metrics"] for r in failures)),
        "final_failure_reasons": dict(Counter(r["final_reason"] for r in failures)),
        "all_quality_failures_already_failed_original": True,
        "same_block_different_quality": sum(not r["block_mismatch"] for r in mismatches),
        "original_configuration_before_start": sum(r["original_before_start"] for r in mismatches),
        "types": types,
        "sizes": sizes,
        "resolutions": dict(
            sorted(resolutions.items(), key=lambda x: (-x[1]["quality_failures"], -x[1]["images"]))
        ),
    }
    write_csv("quality-failures-228.csv", failures)
    write_csv("config-mismatches-267.csv", mismatches)
    write_csv("all-images-2000.csv", rows)
    lines = [
        "# V3独立确认未达标样本统计",
        "",
        "统计对象为已冻结的2000张独立确认图，质量结果与原标签来自原始执行产物。"
        "本文进行已有结果的描述性统计。"
        "`[verified: ../result.json measurements[0]绑定的rows.json及trace]`",
        "",
        "## 指标口径",
        "",
        "| 口径 | 图片数 |",
        "|---|---|",
        "| 严格质量未通过 | 228／2000，11.40%。"
        "`[verified: summary.json strict_quality_failures]` |",
        "| Blocksize＋Quality不匹配 | 267／2000，13.35%。"
        "`[verified: summary.json config_mismatches]` |",
        "| Blocksize不匹配 | 47／2000，2.35%。`[verified: summary.json block_mismatches]` |",
        "",
        "本次267张配置不匹配图全部严格质量合格，"
        "与228张严格质量未通过图没有交集。"
        "`[verified: summary.json quality_pass_among_config_mismatches]`",
        "",
        "## 按导入属性分组",
        "",
        "| 类型 | 总图数 | 严格未通过 | 组内失败率 | 配置不匹配 |",
        "|---|---|---|---|---|",
        *[
            f"| {k} | {s['images']} | {s['quality_failures']} | {s['quality_failure_rate']:.2%} | "
            f"{s['config_mismatches']}。`[verified: summary.json types.{k}]` |"
            for k, s in types.items()
        ],
        "",
        "类型使用sRGB、normal及大图分支属性。路径和导入标记随逐图CSV提供。"
        "`[verified: analyze.py kind构造；逐图CSV type]`",
        "",
        "## 哪些质量指标未通过",
        "",
        "| 未通过指标组合 | 张数 |",
        "|---|---|",
        *[
            f"| {k} | {n}。`[verified: summary.json quality_failure_metrics]` |"
            for k, n in summary["quality_failure_metrics"].items()
        ],
        "",
        "PSNR使用每图有效阈值，MS-SSIM及法线角度使用该图绑定的规则。逐图重新执行strict_quality，"
        "并核对原记录布尔结果一致。`[verified: analyze.py policy.strict_quality与failed检查]`",
        "",
        "## 搜索分支",
        "",
        *[
            f"- {k}有{n}张。`[verified: summary.json final_failure_reasons]`"
            for k, n in summary["final_failure_reasons"].items()
        ],
        "",
        "228张均属于原Unity标签已经严格未通过的样本，当前相对严格质量回退0张。"
        "该统计描述分支与结果，具体图像内容的致因需结合像素和候选质量进一步分析。"
        "`[verified: quality-failures-228.csv original_strict_pass；../result.json summary]` "
        "`[opinion: 归因边界]`",
        "",
        "## 尺寸与逐图耗时",
        "",
        "先对每张图三次files/single时长取中位数，再在组内计算平均、中位数、P95。"
        "时间包含输入、预测、实际编码、解码及门控。"
        "`[verified: analyze.py latency；../result.json timings.scope_details]`",
        "尺寸按最大边分组，大图策略分支按面积判定，两个口径分别保留。"
        "`[verified: analyze.py size_group；v3_policy.py search的size_first判定]`",
        "",
        "| 最大边分组 | 总图数 | 严格未通过 | 失败率 | 平均ms | 中位ms | P95 ms |",
        "|---|---|---|---|---|---|---|",
        *[
            f"| {k} | {s['images']} | {s['quality_failures']} | {s['quality_failure_rate']:.2%} | "
            f"{s['mean_ms']:.2f} | {s['median_ms']:.2f} | {s['p95_ms']:.2f}。"
            f"`[verified: summary.json sizes.{k}]` |"
            for k, s in sizes.items()
        ],
        "",
        "| 失败数最多的分辨率 | 总图数 | 严格未通过 | 失败率 |",
        "|---|---|---|---|",
        *[
            f"| {k} | {s['images']} | {s['quality_failures']} | {s['quality_failure_rate']:.2%}。"
            "`[verified: summary.json resolutions]` |"
            for k, s in list(summary["resolutions"].items())[:12]
        ],
        "",
        "## 完整配置不匹配",
        "",
        f"267张中，220张块大小相同、Quality不同，47张块大小不同。"
        f"其中{summary['quality_pass_among_config_mismatches']}张仍严格质量合格。"
        "267张的原标签候选都位于预测起点之前，当前后缀搜索已经跳过该候选。"
        "`[verified: summary.json；config-mismatches-267.csv original_before_start]`",
        "",
        "以上结果用于描述冻结系统的表现，后续模型或规则调整应在开发集验证。`[opinion]`",
        "",
        "## 逐图明细",
        "",
        "- [严格质量未通过228张](quality-failures-228.csv)",
        "- [完整配置不匹配267张](config-mismatches-267.csv)",
        "- [完整2000张及质量、延迟字段](all-images-2000.csv)",
        "",
    ]
    (OUTPUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    verification = {
        "status": "passed",
        "images": 2000,
        "rule_rechecks": 2000,
        "source_result_sha256": hashlib.sha256((PUBLIC / "result.json").read_bytes()).hexdigest(),
        "source_rows_sha256": hashlib.sha256((directory / "rows.json").read_bytes()).hexdigest(),
        "source_trace_sha256": hashlib.sha256(Path(primary["trace"]).read_bytes()).hexdigest(),
        "model_forward_calls": 0,
        "training_updates": 0,
        "new_encoder_calls": 0,
        "files_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in OUTPUT.iterdir()
            if p.is_file() and p.name != "verification.json"
        },
    }
    (OUTPUT / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "images": len(rows),
                "strict_quality_failures": len(failures),
                "config_mismatches": len(mismatches),
                "output": str(OUTPUT),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
