"""Build independent-test figures and interpretation from the sealed V3 outputs."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.axes import Axes
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal

PUBLIC = Path(__file__).resolve().parent
ROOT = PUBLIC.parents[1]
FIGURES = PUBLIC / "figures"
COLORS = ("#9cb4c4", "#008b7b")


def read(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def trace_signatures(path: Path) -> list[JsonDict]:
    trace = json.loads(gzip.decompress(path.read_bytes()))
    assert len(trace["choices"]) == len(trace["astc_sha256"]) == 2000
    signatures = []
    for index, (choice, astc_sha) in enumerate(
        zip(trace["choices"], trace["astc_sha256"], strict=True)
    ):
        assert choice["source_index"] == index
        assert len(choice["queries"]) == choice["candidates_measured"]
        assert [query["selected_index"] for query in choice["queries"]] == choice[
            "measured_indices"
        ]
        selected_query = next(
            query
            for query in choice["queries"]
            if query["selected_index"] == choice["selected_index"]
        )
        assert selected_query["container_sha256"] == astc_sha
        assert selected_query["metrics"] == choice["selected_metrics"]
        assert choice["selected_encoded_result_reused"]
        signatures.append(
            {
                "source_index": index,
                "starting_decision": choice["starting_decision"],
                "selected_index": choice["selected_index"],
                "selection_reason": choice["selection_reason"],
                "strict_quality_met": choice["strict_quality_met"],
                "measured_indices": choice["measured_indices"],
                "quality_checked_indices": choice["quality_checked_indices"],
                "prediction_context": choice["prediction_context"],
                "gate_context": choice["gate_context"],
                "queries": [
                    {
                        key: query[key]
                        for key in [
                            "selected_index",
                            "block",
                            "preset",
                            "metrics",
                            "strict_quality_met",
                            "container_sha256",
                            "decoded_native_rgba_sha256",
                        ]
                    }
                    for query in choice["queries"]
                ],
                "astc_sha256": astc_sha,
            }
        )
    return signatures


def style(axis: Axes, ylabel: str) -> None:
    axis.set_ylabel(ylabel)
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#b0bec8")
    axis.grid(axis="y", color="#dfe6eb", linewidth=0.7)
    axis.set_axisbelow(True)


def percentage_bars(
    axis: Axes, labels: list[str], validation: list[float], test: list[float]
) -> None:
    positions = np.arange(len(labels))
    for offset, values, color, name in [
        (-0.18, validation, COLORS[0], "开发验证1000图"),
        (0.18, test, COLORS[1], "独立确认2000图"),
    ]:
        bars = axis.bar(positions + offset, np.asarray(values) * 100, 0.34, color=color, label=name)
        axis.bar_label(bars, labels=[f"{value:.2%}" for value in values], padding=4, fontsize=11)
    axis.set_xticks(positions, labels)
    axis.set_ylim(0, 110)
    style(axis, "比例（%）")


def overview(result: JsonDict, validation: JsonDict) -> Path:
    metrics = result["summary"]
    figure, axes = plt.subplots(2, 2, figsize=(12, 8.3))
    figure.suptitle(
        "V3 独立确认结果 · confirmation2000",
        x=0.07,
        ha="left",
        y=0.98,
        fontsize=20,
        fontweight="bold",
    )
    figure.text(
        0.07,
        0.92,
        "冻结Unity输入、ResNet-34权重与20候选续搜规则 · 对照原Unity标签",
        fontsize=11,
        color="#526573",
    )
    axis = axes[0, 0]
    percentage_bars(
        axis,
        ["纯模型预测起点", "实际续搜系统"],
        [validation["pure_start_block_accuracy"], validation["accuracy"]],
        [metrics["pure_start_block_accuracy"], metrics["footprint_accuracy"]],
    )
    axis.set_title("块大小匹配率", loc="left", fontsize=13, fontweight="bold", pad=12)
    axis = axes[0, 1]
    percentage_bars(
        axis,
        ["Blocksize + Quality匹配", "严格质量通过"],
        [validation["full_choice_accuracy"], validation["actual_strict_quality_pass_rate"]],
        [metrics["full_choice_accuracy"], metrics["strict_quality_pass_rate"]],
    )
    axis.set_title("完整配置与实际质量", loc="left", fontsize=13, fontweight="bold", pad=12)
    axis = axes[1, 0]
    matrix = np.asarray(metrics["confusion"])
    axis.imshow(matrix, cmap="Blues", interpolation="nearest")
    axis.set_xticks(range(4), metrics["classes"])
    axis.set_yticks(range(4), metrics["classes"])
    axis.set_xlabel("系统最终Blocksize")
    axis.set_ylabel("原Unity标签Blocksize")
    axis.set_title("独立确认混淆矩阵 · 图片数", loc="left", fontsize=12, pad=12)
    for row in range(4):
        for column in range(4):
            axis.text(
                column,
                row,
                str(matrix[row, column]),
                ha="center",
                va="center",
                color="white" if matrix[row, column] > matrix.max() * 0.55 else "#18394a",
                fontsize=12,
            )
    axis = axes[1, 1]
    names = metrics["classes"]
    recalls = [metrics["per_class"][name]["recall"] for name in names]
    bars = axis.bar(
        names,
        [100 * value if value is not None else 0 for value in recalls],
        color=COLORS[1],
        width=0.58,
    )
    axis.bar_label(
        bars,
        labels=[
            f"{value:.2%}\nn={metrics['per_class'][name]['support']}"
            if value is not None
            else "n=0"
            for name, value in zip(names, recalls, strict=True)
        ],
        padding=5,
        fontsize=10,
    )
    axis.set_ylim(0, 120)
    axis.set_title("各原标签类别的召回率", loc="left", fontsize=12, pad=12)
    style(axis, "召回率（%）")
    figure.subplots_adjust(
        left=0.075, right=0.975, top=0.855, bottom=0.15, hspace=0.47, wspace=0.25
    )
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="center",
        bbox_to_anchor=(0.52, 0.502),
        ncol=2,
        frameon=False,
        fontsize=12,
    )
    figure.text(
        0.07,
        0.052,
        "系统块大小验收线为90%。"
        f"相对原标签严格质量回退 {metrics['quality_regression_images']} 张。",
        fontsize=10,
        color="#526573",
    )
    figure.text(
        0.07,
        0.022,
        "[verified: result.json summary及主评分rows.json · validation来源为V3开发汇总]",
        fontsize=8,
        color="#6d7f8b",
    )
    path = FIGURES / "test-results.png"
    figure.savefig(path, dpi=200, facecolor="white")
    plt.close(figure)
    return path


def timing_figure(result: JsonDict, rows: list[JsonDict]) -> Path:
    count = result["images"]
    figure, axes = plt.subplots(2, 2, figsize=(12, 8.3))
    figure.suptitle(
        "V3 独立确认真实耗时", x=0.07, ha="left", y=0.98, fontsize=20, fontweight="bold"
    )
    figure.text(
        0.07,
        0.92,
        "各计时口径分别实测3次 · 模型与DLL就绪后开始 · 最终内存mip0 ASTC",
        fontsize=11,
        color="#526573",
    )
    axis = axes[0, 0]
    keys = ["files_batch", "pixels_ready_batch", "files_single", "pixels_ready_single"]
    labels = ["文件\n批量摊销", "像素就绪\n批量摊销", "文件\n逐图均值", "像素就绪\n逐图均值"]
    values = [1000 * result["results"][key]["median_end_to_end_seconds"] / count for key in keys]
    bars = axis.bar(labels, values, color=["#008b7b", "#61aaa0", "#3c78b5", "#90b4d4"], width=0.62)
    axis.bar_label(bars, fmt="%.2f", padding=4, fontsize=10)
    axis.set_ylim(0, max(values) * 1.2)
    axis.set_title("每图处理成本 · 三轮整集耗时中位数摊销", loc="left", fontsize=11, pad=12)
    style(axis, "ms／图")
    axis = axes[0, 1]
    single = [
        record
        for record in result["measurements"]
        if (record["scope"], record["mode"]) == ("files", "single")
    ]
    positions = np.arange(3)
    for offset, label, statistic, color in [
        (-0.24, "均值", "mean", "#008b7b"),
        (0, "中位数", "median", "#3c78b5"),
        (0.24, "P95", "p95", "#d47a35"),
    ]:
        values = []
        for record in single:
            latency = np.asarray(record["timings"]["single_image_latencies_seconds"]) * 1000
            values.append(
                float(
                    np.mean(latency)
                    if statistic == "mean"
                    else np.median(latency)
                    if statistic == "median"
                    else np.percentile(latency, 95)
                )
            )
        bars = axis.bar(positions + offset, values, 0.23, color=color, label=label)
        axis.bar_label(bars, fmt="%.0f", padding=3, fontsize=8)
    axis.set_xticks(positions, ["正式重复1", "正式重复2", "正式重复3"])
    axis.set_title("文件输入逐图延迟分布", loc="left", fontsize=12, pad=12)
    style(axis, "ms／图")
    axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=3,
        frameon=False,
        fontsize=10,
    )
    axis.margins(y=0.2)
    axis = axes[1, 0]
    calls = np.asarray([row["candidates_measured"] for row in rows])
    bins = np.arange(0.5, int(calls.max()) + 1.5)
    axis.hist(calls, bins=bins, color=COLORS[1], rwidth=0.8)
    axis.set_xticks(sorted(set(calls.tolist())))
    axis.set_xlabel("每张图片实际编码次数")
    axis.set_title(f"主评分编码次数 · 均值{calls.mean():.4f}次", loc="left", fontsize=12, pad=12)
    style(axis, "图片数")
    axis = axes[1, 1]
    batch = [
        record
        for record in result["measurements"]
        if (record["scope"], record["mode"]) == ("files", "batch")
    ]
    median_seconds = result["results"]["files_batch"]["median_end_to_end_seconds"]
    selected = min(
        batch, key=lambda row: abs(row["timings"]["end_to_end_seconds"] - median_seconds)
    )
    components = [
        ("input_preparation_seconds", "模型输入准备"),
        ("inference_wall_seconds", "推理、传输与聚合"),
        ("reference_load_metadata_and_flip_seconds", "实际编码输入准备"),
        ("policy_and_bookkeeping_seconds", "规则与流程管理"),
        ("native_encode_seconds", "ASTC编码"),
        ("native_decode_seconds", "ASTC解码"),
        ("native_quality_seconds", "质量计算"),
    ]
    values = [selected["timings"][key] * 1000 / count for key, _ in components]
    positions = np.arange(len(components))
    bars = axis.barh(positions, values, color="#3c78b5", height=0.65)
    axis.set_yticks(positions, [name for _, name in components], fontsize=9)
    axis.invert_yaxis()
    axis.bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
    axis.set_xlim(0, max(values) * 1.24)
    axis.set_xlabel("ms／图")
    axis.set_title("文件批量中位数对应重复的分段摊销", loc="left", fontsize=11, pad=12)
    axis.spines[["top", "right"]].set_visible(False)
    figure.subplots_adjust(left=0.075, right=0.975, top=0.855, bottom=0.16, hspace=0.5, wspace=0.36)
    figure.text(
        0.07,
        0.052,
        "编码时间累计所有续搜试压。Unity导入、模型/DLL加载、最终质量审计和写盘另列。",
        fontsize=10,
        color="#526573",
    )
    figure.text(
        0.07,
        0.022,
        "[verified: result.json measurements.timings及files-batch-outputs/rows.json]",
        fontsize=8,
        color="#6d7f8b",
    )
    path = FIGURES / "test-timing.png"
    figure.savefig(path, dpi=200, facecolor="white")
    plt.close(figure)
    return path


def main() -> None:
    result_path = PUBLIC / "result.json"
    result = read(result_path)
    if result["status"] != "passed" or result["images"] != 2000 or not result["test_opened"]:
        raise ValueError("The complete sealed independent evaluation must pass before reporting")
    expected = {
        (scope, mode, repeat)
        for scope in ["files", "pixels_ready"]
        for mode in ["batch", "single"]
        for repeat in range(3)
    }
    assert {
        (row["scope"], row["mode"], row["repeat"]) for row in result["measurements"]
    } == expected
    assert len(result["measurements"]) == 12
    assert result["model_parameters_and_buffers_unchanged"]
    seal_path = Path(result["seal_path"])
    seal_record = read(seal_path)
    seal = UnityEvaluationSeal(seal_path.parent.parent, seal_record["identity"])
    seal.record = seal_record
    seal.verify()
    assert seal.fingerprint == result["seal_fingerprint"]
    runtime = seal_record["identity"]["runtime"]
    libraries = {
        Path(path).name: {"path": path, "sha256": sha}
        for path, sha in seal_record["identity"]["files_sha256"].items()
        if Path(path).name.lower() in {"astcenc-avx2-shared.dll", "unity_astc_quality.dll"}
    }
    assert set(libraries) == {"astcenc-avx2-shared.dll", "unity_astc_quality.dll"}
    attempts = [read(path) for path in (seal_path.parent / "attempts").glob("*.json")]
    assert len(attempts) == 1
    assert attempts[0]["status"] == "passed" and attempts[0]["test_opened"]
    assert attempts[0]["seal_fingerprint"] == seal.fingerprint
    manifests = {
        row["outputs_manifest"]["path"]: row["outputs_manifest"]["sha256"]
        for row in result["measurements"]
    }
    checked = 0
    for path, digest in manifests.items():
        assert A_SHA(Path(path)) == digest
        manifest = read(Path(path))
        assert manifest["images"] == 2000
        for filename, expected_sha in manifest["files_sha256"].items():
            assert A_SHA(Path(filename)) == expected_sha, filename
            checked += 1
    baseline_trace = trace_signatures(Path(result["measurements"][0]["trace"]))
    for record in result["measurements"]:
        assert A_SHA(Path(record["trace"])) == record["trace_sha256"]
        assert trace_signatures(Path(record["trace"])) == baseline_trace
        assert (
            A_SHA(Path(record["predictions_archive"]["path"]))
            == record["predictions_archive"]["sha256"]
        )
        if record["mode"] == "single":
            latency = np.asarray(record["timings"]["single_image_latencies_seconds"])
            assert latency.shape == (2000,) and np.isfinite(latency).all()
            assert (latency > 0).all()
    primary = next(
        row
        for row in result["measurements"]
        if (row["scope"], row["mode"], row["repeat"]) == ("files", "batch", 0)
    )
    rows_path = Path(primary["outputs_manifest"]["path"]).with_name("rows.json")
    rows = read(rows_path)["rows"]
    assert len(rows) == 2000
    assert len({row["path"].casefold() for row in rows}) == 2000
    for manifest_path in manifests:
        other_rows = read(Path(manifest_path).with_name("rows.json"))["rows"]
        assert [row["path"] for row in other_rows] == [row["path"] for row in rows]
        assert [row["original_selection"] for row in other_rows] == [
            row["original_selection"] for row in rows
        ]
    for record in result["measurements"]:
        assert record["summary"] == primary["summary"]
    assert (
        sum(row["footprint_match"] for row in rows) / 2000
        == result["summary"]["footprint_accuracy"]
    )
    assert (
        sum(row["strict_quality_met"] for row in rows) / 2000
        == result["summary"]["strict_quality_pass_rate"]
    )
    assert (
        sum(row["full_choice_match"] for row in rows) / 2000
        == result["summary"]["full_choice_accuracy"]
    )
    assert (
        sum(row["quality_regression"] for row in rows)
        == result["summary"]["quality_regression_images"]
    )
    assert sum(row["payload_bytes"] for row in rows) == result["summary"]["payload_bytes"]
    validation_path = ROOT / "experiment report/unity-v3-20261113/summary.json"
    development = read(validation_path)
    validation = dict(development["recommendation"]["metrics"])
    pure_validation = next(
        case
        for case in development["controls"]
        if case["name"] == "pure-unity-full20"
        and case["checkpoint_sha256"] == result["checkpoint_sha256"]
    )
    validation["pure_start_block_accuracy"] = pure_validation["metrics"]["accuracy"]
    hardware = read(PUBLIC / "hardware.json")
    gpu_name, gpu_memory, gpu_driver = hardware["gpu"].split(", ")
    assert result["checkpoint_sha256"] == development["recommendation"]["checkpoint_sha256"]
    font_manager.fontManager.addfont("C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update(
        {"font.family": "Microsoft YaHei", "font.size": 12, "axes.unicode_minus": False}
    )
    FIGURES.mkdir(exist_ok=True)
    images = [overview(result, validation), timing_figure(result, rows)]
    metrics = result["summary"]
    total_pixels = sum(row["width"] * row["height"] for row in rows)
    development_audit_path = ROOT / "experiment report/unity-v3-20261113/source-input-audit.json"
    development_audit = read(development_audit_path)
    development_manifest_path = Path(development_audit["manifest"])
    assert A_SHA(development_manifest_path) == development_audit["manifest_sha256"]
    validation_rows = read(development_manifest_path)["splits"]["validation"]
    assert development_audit["status"] == "passed" and len(validation_rows) == 1000
    validation_pixels = sum(row["target_width"] * row["target_height"] for row in validation_rows)
    mean_pixel_ratio = (total_pixels / 2000) / (validation_pixels / 1000)
    matching = sum(row["footprint_match"] for row in rows)
    strict_count = sum(row["strict_quality_met"] for row in rows)
    transitions = Counter(
        (
            row["starting_decision"]["block_size"] == row["original_selection"]["block_size"],
            row["footprint_match"],
        )
        for row in rows
    )
    assert (transitions[(True, True)] + transitions[(True, False)]) / 2000 == metrics[
        "pure_start_block_accuracy"
    ]
    paired_start_to_final = {
        "kept_correct": transitions[(True, True)],
        "corrected": transitions[(False, True)],
        "new_errors": transitions[(True, False)],
        "still_wrong": transitions[(False, False)],
    }
    original_strict = sum(
        row["original_selection"]["selection_reason"] in {"first_valid", "size_first_strict"}
        for row in rows
    )
    remaining = Counter(
        row["original_selection"]["selection_reason"]
        for row in rows
        if not row["strict_quality_met"]
    )
    verdict = "达到" if result["accuracy90_met"] else "低于"
    timing_rows = []
    for key, name in [
        ("files_batch", "文件输入／批量摊销"),
        ("pixels_ready_batch", "像素就绪／批量摊销"),
        ("files_single", "文件输入／逐图均值"),
        ("pixels_ready_single", "像素就绪／逐图均值"),
    ]:
        value = result["results"][key]["median_end_to_end_seconds"] * 1000 / 2000
        timing_rows.append(
            f"| {name} | {value:.2f} ms／图。`[verified: result.json results.{key}]` |"
        )
    single_records = [
        row for row in result["measurements"] if (row["scope"], row["mode"]) == ("files", "single")
    ]
    single_means = [
        float(np.mean(row["timings"]["single_image_latencies_seconds"]) * 1000)
        for row in single_records
    ]
    single_medians = [
        float(np.median(row["timings"]["single_image_latencies_seconds"]) * 1000)
        for row in single_records
    ]
    single_p95 = [
        float(np.percentile(row["timings"]["single_image_latencies_seconds"], 95) * 1000)
        for row in single_records
    ]
    markdown = [
        "# V3独立确认测试报告",
        "",
        "## 实验结论",
        "",
        "冻结的Unity参考图输入、ResNet-34、20候选预测起点续搜系统，"
        "在2000张独立确认图上块大小匹配率为 "
        f"**{metrics['footprint_accuracy']:.2%}**，{verdict}90%的系统验收目标。"
        "执行状态、封存复核和输出审计均通过。"
        "`[verified: result.json status、accuracy90_met、summary；共享seal对应attempt]`",
        "",
        f"纯模型预测起点的块大小匹配率为{metrics['pure_start_block_accuracy']:.2%}，"
        f"实际续搜系统为{metrics['footprint_accuracy']:.2%}。"
        f"开发验证1000图对应值为{validation['pure_start_block_accuracy']:.1%}"
        f"和{validation['accuracy']:.1%}。"
        "`[verified: result.json summary；V3开发summary.json recommendation及controls]`",
        "",
        "## 测试对象与协议",
        "",
        "测试使用开发阶段选定的同一权重、Unity参考像素、原始20候选标签及原生质量规则，"
        "采用共享cohort封存。各计时单元8图预热一次、正式重复三次，"
        "覆盖files／pixels_ready及batch／single四种组合。"
        "`[verified: execution-config-v2.json；execution-seal.json；result.json measurements]`",
        "",
        f"测试CPU为{hardware['cpu']}，{hardware['logical_processors']}个逻辑处理器，"
        f"内存{hardware['ram_bytes'] / 1024**3:.2f} GiB。"
        f"GPU为{gpu_name}，显存{gpu_memory}，驱动{gpu_driver}。"
        "`[verified: hardware.json cpu、logical_processors、ram_bytes、gpu]`",
        "",
        f"封存运行信息为PyTorch {runtime['torch']}、NumPy {runtime['numpy']}、"
        f"device={runtime['device']}、threads={runtime['threads']}。"
        "`[verified: 共享seal identity.runtime]`",
        "",
        f"确认集含2000张图，总像素数{total_pixels:,}，"
        f"RGBA原始字节总量为{total_pixels * 4:,}。"
        "输出范围为LDR、RGBA8、mip0，RDO关闭，法线用途由导入配置提供。"
        "`[verified: prepared-inputs.json rows；UnityCaptureInputAdapter；冻结V3协议]`",
        "",
        "## 主要结果",
        "",
        "| 指标 | 独立确认结果 |",
        "|---|---|",
        f"| 系统块大小匹配 | {matching}／2000，{metrics['footprint_accuracy']:.2%}。"
        "`[verified: result.json summary.footprint_accuracy]` |",
        f"| Blocksize＋Quality匹配 | {metrics['full_choice_accuracy']:.2%}。"
        "`[verified: result.json summary.full_choice_accuracy]` |",
        f"| 严格质量通过 | {strict_count}／2000，{metrics['strict_quality_pass_rate']:.2%}。"
        "`[verified: result.json summary.strict_quality_pass_rate]` |",
        f"| 相对原标签严格质量回退 | {metrics['quality_regression_images']}张。"
        f"原标签严格合格{original_strict}张。"
        "`[verified: result.json summary.quality_regression_images；"
        "主评分rows.json original_selection]` |",
        f"| 平均实际编码次数 | {metrics['candidates_measured']['mean']:.4f}次／图，"
        f"P95为{metrics['candidates_measured']['p95']:g}次，"
        f"最大{metrics['candidates_measured']['max']}次。"
        "`[verified: result.json summary.candidates_measured]` |",
        f"| mip0 payload | {metrics['payload_bytes']:,}字节，"
        f"为固定8×8几何payload的{metrics['payload_ratio_to_fixed8']:.2%}。"
        "`[verified: result.json summary.payload_bytes、payload_ratio_to_fixed8]` |",
        f"| 相对原标签payload | {metrics['payload_ratio_to_original']:.2%}。"
        "`[verified: result.json summary.payload_ratio_to_original]` |",
        "",
        "## 真实耗时",
        "",
        "| 计时口径 | 三轮整集耗时中位数摊销 |",
        "|---|---|",
        *timing_rows,
        "",
        "文件输入逐图模式的三轮均值为"
        f"{'、'.join(f'{value:.2f}' for value in single_means)} ms，"
        f"中位数为{'、'.join(f'{value:.2f}' for value in single_medians)} ms，"
        f"P95为{'、'.join(f'{value:.2f}' for value in single_p95)} ms。"
        "`[verified: result.json measurements中files／single的single_image_latencies_seconds]`",
        "",
        "主计时从所需模型及DLL就绪开始，覆盖必要文件或已就绪像素到最终内存ASTC，"
        "包含预测、选参、实际编码以及续搜中的解码和质量门控。"
        "Unity导入、模型／DLL加载、最终输出审计与写盘另列。"
        "`[verified: result.json measurements.timings.scope；V3DeploymentTrial.run]`",
        "",
        "文件输入批量模式对整集预测，像素就绪批量模式按8图分组后聚合。"
        "两个口径的时间差同时包含输入边界与分组粒度的影响。"
        "`[verified: v3_confirmation.py L233–274；opinion: 时间差解释]`",
        "",
        "## 结论解读",
        "",
        "块大小匹配率衡量最终参数与原Unity标签的一致性，完整配置匹配还要求Quality相同，"
        "严格质量通过率衡量最终解码像素是否满足原生门槛。"
        "放宽和最高PSNR回退均保留原始分支身份。"
        "`[verified: 主评分rows.json；UnityV3Policy.search、strict_quality]`",
        "",
        f"逐张配对后，续搜保留{paired_start_to_final['kept_correct']}张正确起点，"
        f"纠正{paired_start_to_final['corrected']}张起点错误，"
        f"新增{paired_start_to_final['new_errors']}张错误，"
        f"仍有{paired_start_to_final['still_wrong']}张块大小未匹配。"
        "`[verified: 主评分rows.json starting_decision、original_selection、footprint_match]`",
        "",
        f"原标签严格合格{original_strict}张，系统严格合格{strict_count}张，"
        f"相对原标签严格质量回退{metrics['quality_regression_images']}张。"
        f"当前严格未通过{2000 - strict_count}张，按原标签分支分组，"
        f"其中放宽分支{remaining['size_first_relaxed']}张，"
        f"最高PSNR回退{remaining['highest_psnr_fallback']}张。"
        "`[verified: 主评分rows.json strict_quality_met、original_selection.selection_reason]`",
        "",
        f"{2000 - matching}张块大小未匹配图中，"
        f"系统使用更小块{metrics['smaller_block_images']}张，"
        f"更大块{metrics['larger_block_images']}张。"
        f"相对原标签payload变化为{metrics['payload_ratio_to_original'] - 1:+.4%}。"
        "`[verified: result.json summary.smaller_block_images、larger_block_images、"
        "payload_ratio_to_original]`",
        "",
        f"原标签12×12占{metrics['per_class']['12x12']['support']}／2000张，"
        f"四类平均召回率为{metrics['balanced_accuracy']:.2%}。"
        f"法线仅{metrics['groups']['normal']['images']}张，"
        f"Linear仅{metrics['groups']['linear']['images']}张。"
        "`[verified: result.json summary.per_class、balanced_accuracy、groups]`",
        "",
        "各用途的泛化判断应结合当前样本量，法线和Linear的覆盖仍有限。`[opinion]`",
        "",
        "本轮确认结果用于评价已冻结系统。确认集尺寸分布及实际编码次数共同影响每图耗时，读图准备、模型预测和所有试压编码成本应结合计时分段阅读。`[opinion]`",
        "",
        f"开发验证1000图共{validation_pixels:,}像素，"
        f"平均{validation_pixels / 1000 / 1e6:.3f}百万像素／图。"
        f"独立确认2000图平均{total_pixels / 2000 / 1e6:.3f}百万像素／图，"
        f"为开发验证平均像素数的{mean_pixel_ratio:.2f}倍。"
        "`[verified: V3 source-manifest.json splits.validation target_width、target_height；"
        "主评分rows.json width、height]`",
        "",
        "本次输出质量审计复算最终选中ASTC，查询轨迹保留运行时实际测得的候选质量。"
        "20候选整体质量RMSE需完整候选监督，本报告按当前实际测量范围解释误差。"
        "`[verified: result.json outputs_manifest及trace；opinion: 误差解释范围]`",
        "",
        "## 结果图",
        "",
        f"![独立确认结果](<{images[0].as_posix()}>)",
        "",
        f"![独立确认耗时](<{images[1].as_posix()}>)",
        "",
        "## 证据与核验",
        "",
        "12个正式计时单元、每单元2000图覆盖与有序原标签复核通过。"
        f"重新核验{checked}份选中输出、行记录及预测文件，"
        "并核验12份查询轨迹和12份重复预测档案。"
        "模型参数与buffer保持验收前状态。"
        "`[verified: result.json；report-verification.json；outputs.json清单逐项SHA核对]`",
        "",
        "执行证据保存在同目录execution-config-v2.json、authorization.json、preparation.json、"
        "smoke-verification.json、execution-seal.json和result.json。"
        "原始ASTC、PNG、NPZ与查询轨迹位置由result.json各outputs_manifest、trace"
        "和predictions_archive定位。`[verified: 对应文件与result.json measurements]`",
        "",
        *[
            f"- `{name}`的SHA-256为`{value['sha256']}`。"
            "`[verified: 共享seal identity.files_sha256]` "
            f"[库文件](<{Path(value['path']).as_posix()}>)"
            for name, value in libraries.items()
        ],
        "",
        "pixels_ready阶段按8图分组运行，progress.json中的completed_images为当前组内进度。"
        "完整2000图覆盖由聚合后的全局source_index、查询轨迹及输出清单核验。"
        "`[verified: v3_confirmation.py L237–274；report-verification.json]`",
        "",
    ]
    (PUBLIC / "README.md").write_text("\n".join(markdown), encoding="utf-8")
    with (PUBLIC / "test-image-metrics.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = [
            "path",
            "width",
            "height",
            "normal",
            "srgb",
            "block_size",
            "preset",
            "footprint_match",
            "full_choice_match",
            "strict_quality_met",
            "quality_regression",
            "candidates_measured",
            "payload_bytes",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in rows)
    verification = {
        "status": "passed",
        "source_result_sha256": A_SHA(result_path),
        "validation_summary_sha256": A_SHA(validation_path),
        "hardware_sha256": A_SHA(PUBLIC / "hardware.json"),
        "development_input_audit_sha256": A_SHA(development_audit_path),
        "development_source_manifest_sha256": A_SHA(development_manifest_path),
        "dataset_size": {
            "validation_images": 1000,
            "validation_pixels": validation_pixels,
            "confirmation_images": 2000,
            "confirmation_pixels": total_pixels,
            "mean_pixel_ratio": mean_pixel_ratio,
        },
        "images": 2000,
        "unique_assets": 2000,
        "timing_cells": 12,
        "saved_files_verified": checked,
        "traces_verified": 12,
        "prediction_archives_verified": 12,
        "per_image_trace_consistency_checks": 24000,
        "repeated_trace_identity_verified": True,
        "shared_seal_verified": True,
        "formal_attempts": len(attempts),
        "seal_fingerprint": seal.fingerprint,
        "sealed_runtime": runtime,
        "native_libraries": libraries,
        "quality_outcomes": {
            "original_strict_pass_images": original_strict,
            "system_strict_pass_images": strict_count,
            "strict_failures_by_original_reason": dict(remaining),
        },
        "paired_start_to_final": paired_start_to_final,
        "visual_review": "pending",
        "document_sha256": A_SHA(PUBLIC / "README.md"),
        "figures": [],
    }
    for path in images:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            size = list(image.size)
        verification["figures"].append({"path": str(path), "sha256": A_SHA(path), "pixels": size})
    (PUBLIC / "report-verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "images": 2000,
                "accuracy": metrics["footprint_accuracy"],
                "accuracy90_met": result["accuracy90_met"],
                "report": str(PUBLIC / "README.md"),
                "figures": [str(path) for path in images],
            },
            ensure_ascii=True,
            indent=2,
        )
    )


def A_SHA(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
