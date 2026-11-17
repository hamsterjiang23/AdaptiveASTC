"""Plot archived V3 Unity-input training and validation records."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.axes import Axes
from PIL import Image

from adaptive_astc.config import JsonDict

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "experiment report/unity-v3-20261113"
REPORT_NAMES = ("train-unity-full-full-v1.json", "train-unity-head-full-v1.json")
STAGE_NAMES = ("全模型训练", "仅整图头训练")
COLORS = {
    "total": "#19394b",
    "patch": "#3c78b5",
    "zero": "#8b62aa",
    "ssim": "#008b7b",
    "angle": "#d47a35",
}


def read_report(path: Path) -> JsonDict:
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["status"] == "completed", path
    assert [row["epoch"] for row in report["history"]] == list(range(1, 31)), path
    assert report["checkpoint_audit"]["status"] == "passed", path
    for row in report["history"]:
        assert row["images_seen"] == 10000
        assert row["validation"]["count"] == 1000
        assert all(math.isfinite(float(value)) for value in row["loss"].values())
        patch_loss = row["loss"].get("patch", 0.0)
        expected = patch_loss + sum(
            report["config"][f"{component}_weight"] * row["loss"][component]
            for component in ("zero", "ssim", "angle")
        )
        assert math.isclose(expected, row["loss"]["total"], abs_tol=1e-6)
    selected = report["checkpoint_audit"]["epoch"]
    assert (
        report["history"][selected - 1]["validation"]["accuracy"]
        == report["checkpoint_audit"]["metrics"]["accuracy"]
    )
    return report


def format_axis(axis: Axes, ylabel: str) -> None:
    axis.set_xlabel("阶段内训练轮次")
    axis.set_ylabel(ylabel)
    axis.set_xlim(1, 30)
    axis.set_xticks([1, 5, 10, 15, 20, 25, 30])
    axis.grid(axis="y", color="#dbe3e8", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#acb9c2")


def plot_training(reports: list[JsonDict]) -> Path:
    figure, axes = plt.subplots(2, 2, figsize=(12, 8.1))
    figure.suptitle(
        "V3 当前模型训练 loss", fontsize=20, fontweight="bold", x=0.07, ha="left", y=0.98
    )
    figure.text(
        0.07,
        0.92,
        "Unity参考图输入 · ResNet-34 · 每阶段30轮 · 每轮10000张训练图",
        fontsize=11,
        color="#526573",
    )
    for column, (report, stage) in enumerate(zip(reports, STAGE_NAMES, strict=True)):
        history = report["history"]
        epochs = [row["epoch"] for row in history]
        axis = axes[0, column]
        axis.plot(
            epochs,
            [row["loss"]["total"] for row in history],
            color=COLORS["total"],
            linewidth=2.2,
            marker="o",
            markersize=2.8,
        )
        axis.set_title(f"{stage} · 总loss", loc="left", fontsize=13, fontweight="bold", pad=13)
        format_axis(axis, "训练总loss")
        first, last = history[0]["loss"]["total"], history[-1]["loss"]["total"]
        axis.text(
            0.98,
            0.96,
            f"第1轮 {first:.4f}\n第30轮 {last:.4f}",
            transform=axis.transAxes,
            ha="right",
            va="top",
            fontsize=10,
        )

        axis = axes[1, column]
        components = (["patch"] if column == 0 else []) + ["zero", "ssim", "angle"]
        labels = {
            "patch": "patch误差",
            "zero": "零误差分类 × 0.1",
            "ssim": "MS-SSIM × 0.1",
            "angle": "法线角度 × 0.1",
        }
        for component in components:
            weight = 1.0 if component == "patch" else report["config"][f"{component}_weight"]
            values = [weight * row["loss"][component] for row in history]
            assert all(value > 0 for value in values)
            axis.plot(
                epochs, values, label=labels[component], color=COLORS[component], linewidth=1.8
            )
        axis.set_yscale("log")
        axis.set_title("各分项对总loss的加权贡献", loc="left", fontsize=12, pad=12)
        format_axis(axis, "加权loss分项 · 对数坐标")
        axis.legend(frameon=False, fontsize=9, ncol=2, loc="best")
    figure.subplots_adjust(
        left=0.075, right=0.975, top=0.855, bottom=0.15, wspace=0.23, hspace=0.49
    )
    figure.text(
        0.07,
        0.08,
        "全模型总loss = patch + 0.1 × (zero + MS-SSIM + angle)    "
        "整图头总loss = 0.1 × (zero + MS-SSIM + angle)",
        fontsize=9,
        color="#526573",
    )
    figure.text(
        0.07,
        0.045,
        "[verified: train-unity-full-full-v1.json / "
        "train-unity-head-full-v1.json · history.loss、config]",
        fontsize=8,
        color="#6d7f8b",
    )
    path = OUTPUT / "training-loss.png"
    figure.savefig(path, dpi=200, facecolor="white")
    plt.close(figure)
    return path


def plot_validation(reports: list[JsonDict]) -> Path:
    figure, axes = plt.subplots(2, 2, figsize=(12, 8.1))
    figure.suptitle(
        "V3 验证曲线 · validation1000", fontsize=20, fontweight="bold", x=0.07, ha="left", y=0.98
    )
    figure.text(
        0.07,
        0.92,
        "每轮纯模型选参结果对照原20候选Unity标签 · 虚线标记各阶段选中checkpoint",
        fontsize=11,
        color="#526573",
    )
    for column, (report, stage) in enumerate(zip(reports, STAGE_NAMES, strict=True)):
        history = report["history"]
        epochs = [row["epoch"] for row in history]
        selected = report["checkpoint_audit"]["epoch"]
        accuracy = [100 * row["validation"]["accuracy"] for row in history]
        rmse = [row["validation"]["color_near_threshold_rmse_db"] for row in history]
        axis = axes[0, column]
        axis.plot(epochs, accuracy, color="#008b7b", linewidth=2.1, marker="o", markersize=3)
        axis.axvline(selected, color="#8b62aa", linewidth=1.2, linestyle="--")
        axis.scatter(
            [selected], [accuracy[selected - 1]], color="#8b62aa", s=48, marker="D", zorder=4
        )
        axis.set_title(
            f"{stage} · 块大小匹配率", loc="left", fontsize=13, fontweight="bold", pad=13
        )
        format_axis(axis, "验证块大小匹配率（%）")
        axis.text(
            0.03,
            0.96,
            f"选中第{selected}轮\n{accuracy[selected - 1]:.1f}%",
            transform=axis.transAxes,
            va="top",
            fontsize=11,
            color="#60437d",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 3},
        )
        axis.margins(y=0.16)

        axis = axes[1, column]
        axis.plot(epochs, rmse, color="#3c78b5", linewidth=2.1, marker="o", markersize=3)
        axis.axvline(selected, color="#8b62aa", linewidth=1.2, linestyle="--")
        axis.scatter([selected], [rmse[selected - 1]], color="#8b62aa", s=48, marker="D", zorder=4)
        axis.set_title("颜色候选近阈值PSNR预测误差", loc="left", fontsize=12, pad=12)
        format_axis(axis, "近阈值PSNR RMSE（dB）")
        axis.margins(y=0.16)
    figure.subplots_adjust(
        left=0.075, right=0.975, top=0.855, bottom=0.15, wspace=0.23, hspace=0.49
    )
    figure.text(
        0.07,
        0.08,
        "本图逐轮记录对应纯模型预测。选中模型纯预测为86.9%，其后续真实压缩续搜系统的最终块大小匹配率为93.6%。",
        fontsize=9,
        color="#526573",
    )
    figure.text(
        0.07,
        0.045,
        "[verified: 两份训练报告 history.validation、checkpoint_audit、"
        "summary.json recommendation.metrics]",
        fontsize=8,
        color="#6d7f8b",
    )
    path = OUTPUT / "validation-curves.png"
    figure.savefig(path, dpi=200, facecolor="white")
    plt.close(figure)
    return path


def main() -> None:
    report_paths = [ARCHIVE / name for name in REPORT_NAMES]
    reports = [read_report(path) for path in report_paths]
    summary_path = ARCHIVE / "summary.json"
    contract_path = ARCHIVE / "confirmation-contract.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for path in report_paths:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == summary["parents_sha256"][str(path)]
    assert (
        summary["recommendation"]["checkpoint_sha256"]
        == reports[1]["checkpoint_audit"]["checkpoint_sha256"]
    )
    assert summary["recommendation"]["metrics"]["accuracy"] == 0.936
    seal_path = Path(contract["confirmation_registry"]["seal_path"])
    assert not contract["test_opened"] and not summary["test_opened"]
    assert not seal_path.exists(), (
        "Shared confirmation seal changed. Recheck current evaluation status."
    )

    font_manager.fontManager.addfont("C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update(
        {
            "font.family": "Microsoft YaHei",
            "font.size": 10,
            "axes.unicode_minus": False,
            "savefig.bbox": "standard",
        }
    )
    outputs = [plot_training(reports), plot_validation(reports)]
    rows: list[JsonDict] = []
    for stage, report in zip(STAGE_NAMES, reports, strict=True):
        for record in report["history"]:
            rows.append(
                {
                    "stage": stage,
                    "epoch": record["epoch"],
                    "selected_checkpoint": record["epoch"] == report["checkpoint_audit"]["epoch"],
                    "train_total_loss": record["loss"]["total"],
                    "train_patch_loss": record["loss"].get("patch"),
                    "train_zero_loss": record["loss"]["zero"],
                    "train_ssim_loss": record["loss"]["ssim"],
                    "train_angle_loss": record["loss"]["angle"],
                    "validation_images": record["validation"]["count"],
                    "validation_block_accuracy": record["validation"]["accuracy"],
                    "validation_color_near_threshold_rmse_db": record["validation"][
                        "color_near_threshold_rmse_db"
                    ],
                }
            )
    csv_path = OUTPUT / "epoch-metrics.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    sources = report_paths + [summary_path, contract_path]
    verification = {
        "status": "passed",
        "source_files_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources
        },
        "training_rows": len(rows),
        "epochs_per_stage": [len(report["history"]) for report in reports],
        "loss_reconstruction": "all60 epoch totals match recorded weighted components within1e-6",
        "selected_epochs": [report["checkpoint_audit"]["epoch"] for report in reports],
        "selected_accuracy": [
            report["checkpoint_audit"]["metrics"]["accuracy"] for report in reports
        ],
        "current_checkpoint_binding": "matched recommendation checkpoint SHA256",
        "training_report_binding": (
            "matched both training hashes in archived summary parents_sha256"
        ),
        "validation_scope": (
            "Per-epoch pure-model selection,1000 images, original20-candidate Unity labels"
        ),
        "confirmation_execution_authorized": contract["confirmation_execution_authorized"],
        "test_opened": contract["test_opened"],
        "confirmation_shared_seal_exists": seal_path.exists(),
        "plot_design": (
            "separate30-epoch stages, raw unsmoothed observations, "
            "weighted component losses, no joined stage loss"
        ),
        "plots": [],
        "csv": str(csv_path),
        "visual_review": "pending",
    }
    for path in outputs:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            dimensions = list(image.size)
        verification["plots"].append(
            {
                "path": str(path),
                "dimensions": dimensions,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (OUTPUT / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(verification, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
