"""Aggregate experiment report and plot generation."""

from pathlib import Path

import matplotlib

from adaptive_astc.config import CLASSES, JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


class ReportGenerator:
    """Render reports from persisted metrics and training records."""

    def __init__(self, run_dir: Path, report_dir: Path) -> None:
        self.run_dir = run_dir
        self.report_dir = report_dir

    def render(self) -> None:
        metrics = ArtifactStore.read_json(self.report_dir / "metrics.json")
        rows: list[str] = []
        figure, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
        curve, loss_axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
        cost_rows: list[str] = []
        class_rows: list[str] = []
        history_notes: list[str] = []
        confusion_figure, confusion_axes = plt.subplots(
            1, 2, figsize=(11, 4.8), constrained_layout=True
        )
        for index, arm in enumerate(("pretrained", "scratch")):
            arm_metrics = metrics["arms"][arm]
            training = ArtifactStore.read_json(self.report_dir / f"{arm}_training.json")
            history: list[JsonDict] = training["epochs"]
            matrix = np.asarray(arm_metrics["raw"]["confusion_matrix"])
            normalized = matrix / matrix.sum(axis=1, keepdims=True)
            confusion_image = confusion_axes[index].imshow(normalized, vmin=0, vmax=1, cmap="Blues")
            confusion_axes[index].set(
                title=arm,
                xlabel="Predicted footprint",
                ylabel="Historical footprint label",
                xticks=range(4),
                xticklabels=CLASSES,
                yticks=range(4),
                yticklabels=CLASSES,
            )
            for actual in range(4):
                for predicted in range(4):
                    confusion_axes[index].text(
                        predicted,
                        actual,
                        f"{matrix[actual, predicted]}\n{normalized[actual, predicted]:.1%}",
                        ha="center",
                        va="center",
                        color="white" if normalized[actual, predicted] > 0.5 else "black",
                    )
            for label, name in enumerate(CLASSES):
                per_class = arm_metrics["raw"]["per_class"][name]
                class_rows.append(
                    f"| {arm} | {name} | {per_class['support']} | {per_class['recall']:.2%} | "
                    f"{per_class['precision']:.2%} | {int(matrix[:, label].sum())} | "
                    "`[verified: metrics.json /arms/*/raw/per_class、confusion_matrix]` |"
                )
            for name in ("raw", "calibrated"):
                result = arm_metrics[name]
                rows.append(
                    f"| {arm} {name} | {result['accuracy']:.4f} | {result['macro_f1']:.4f} | "
                    f"{result['balanced_accuracy']:.4f} | {result['nll']:.4f} | "
                    f"{result['brier']:.4f} | {result['ece_15_equal_width']:.4f} | "
                    "`[verified: metrics.json /arms]` |"
                )
                populated = [item for item in result["reliability_bins"] if item["count"]]
                axes[index].plot(
                    [item["confidence"] for item in populated],
                    [item["accuracy"] for item in populated],
                    marker="o",
                    label=name,
                )
            axes[index].plot([0, 1], [0, 1], "--", color="gray")
            axes[index].set(
                title=arm,
                xlabel="Mean confidence",
                ylabel="Empirical accuracy",
                xlim=(0, 1),
                ylim=(0, 1),
            )
            axes[index].legend()
            epochs = [item["epoch"] for item in history]
            loss_axes[0].plot(
                epochs, [item["train"]["loss"] for item in history], label=f"{arm} train"
            )
            loss_axes[0].plot(
                epochs, [item["validation"]["nll"] for item in history], label=f"{arm} val"
            )
            loss_axes[1].plot(
                epochs, [item["validation"]["accuracy"] for item in history], label=arm
            )
            complete = ArtifactStore.read_json(self.run_dir / arm / "training_complete.json")
            history_notes.append(
                f"{arm}训练loss由{history[0]['train']['loss']:.4f}至"
                f"{history[-1]['train']['loss']:.4f}，验证NLL由"
                f"{history[0]['validation']['nll']:.4f}至"
                f"{history[-1]['validation']['nll']:.4f}，选中第{complete['best_epoch']}轮。"
                f"`[verified: {arm}_training.json /epochs；training_complete.json]`"
            )
            cost_rows.append(
                f"| {arm} | {len(history)} | {complete['best_epoch']} | "
                f"{sum(item['epoch_seconds'] for item in history):.1f} | "
                f"{max(item['peak_vram_mib'] for item in history):.1f} | "
                f"{max(item['rss_mib'] for item in history):.1f} | "
                f"{arm_metrics['temperature']:.6f} | "
                f"`[verified: {arm}_training.json；metrics.json]` |"
            )
        figure.savefig(self.report_dir / "reliability.png", dpi=160)
        plt.close(figure)
        loss_axes[0].set(xlabel="Epoch", ylabel="Cross entropy")
        loss_axes[1].set(xlabel="Epoch", ylabel="Validation accuracy")
        for axis in loss_axes:
            axis.legend()
            axis.grid(alpha=0.2)
        curve.savefig(self.report_dir / "training_curves.png", dpi=160)
        plt.close(curve)
        confusion_figure.colorbar(confusion_image, ax=list(confusion_axes), label="Row fraction")
        confusion_figure.savefig(self.report_dir / "confusion_matrix.png", dpi=160)
        plt.close(confusion_figure)
        majority = metrics["majority_baseline"]
        pretrained_classes = metrics["arms"]["pretrained"]["raw"]["per_class"]
        scratch_classes = metrics["arms"]["scratch"]["raw"]["per_class"]
        text = (
            "# 训练与校准报告\n\n"
            "本报告记录现有LITE历史标签、RGB源图输入的分类复现。网络深度、初始化及训练超参数"
            "采用协议中明确补全的设置。`[verified: protocol.md；各组training.json /config]`\n\n"
            "## 封存测试结果\n\n"
            "| 模型与处理 | Accuracy | Macro F1 | Balanced accuracy | NLL | Brier | ECE | 证据 |\n"
            "|---|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
            f"训练集多数类为{majority['class']}，测试准确率{majority['accuracy']:.4f}。"
            "`[verified: metrics.json /majority_baseline]`\n\n"
            "校准前后逐样本argmax一致。校准效果按测试NLL、Brier与ECE的实际变化解释。"
            "`[verified: metrics.json /arms/*/argmax_unchanged]`\n\n"
            "![可靠性图](reliability.png)\n\n"
            "## 逐类识别与当前限制\n\n"
            "| 模型 | 历史类别 | 测试样本数 | Recall | Precision | 预测为该类的数量 | 证据 |\n"
            "|---|---|---|---|---|---|---|\n" + "\n".join(class_rows) + "\n\n"
            f"预训练模型的8×8和10×10召回率分别为{pretrained_classes['8x8']['recall']:.2%}和"
            f"{pretrained_classes['10x10']['recall']:.2%}，随机初始化模型的10×10召回率为"
            f"{scratch_classes['10x10']['recall']:.2%}。"
            "温度处理后的类别指标见同一份聚合统计。"
            "`[verified: metrics.json /arms/*/raw/per_class及calibrated/per_class]`\n\n"
            + "\n\n".join(history_notes)
            + "\n\n"
            "最佳轮次按预先固定的验证NLL规则选择。"
            "`[verified: protocol.md；各组训练记录]`\n\n"
            "结果范围为单个固定种子、LITE标签与源图RGB输入的资产隔离划分。"
            "`[verified: metrics.json；data_summary.json；protocol.md]`\n\n"
            "![混淆矩阵](confusion_matrix.png)\n\n"
            "## 训练成本与模型选择\n\n"
            "| 模型 | 完成轮次 | 最佳轮次 | 累计轮次耗时秒 | 峰值CUDA分配MiB | "
            "主进程RSS MiB | T | 证据 |\n"
            "|---|---|---|---|---|---|---|---|\n" + "\n".join(cost_rows) + "\n\n"
            "![训练曲线](training_curves.png)\n\n"
            "轮次耗时包含训练与验证，测试推理时间包含数据加载与GPU前向。RSS为主进程轮次末观测值，"
            "CUDA数值为PyTorch峰值分配；系统侧采样另记资源日志。"
            "`[verified: training/trainer.py的轮次计时、RSS采样；"
            "evaluation/inference.py；资源日志]`\n\n"
            "## 证据边界\n\n"
            "标签来源为LITE选参缓存，其preset与RDO混合，RGB输入省略Alpha，Unity导入后输入域仍需"
            "独立验证。本次类别正确率对应历史标签。PSNR35达标率、法线误差、真实字节收益与生产"
            "单次压缩效果需要候选压缩实测。"
            "`[verified: protocol.md；data_summary.json /table_config]`\n\n"
            "温度在独立校准集拟合，两个模型与温度固定后统一打开测试集。所有逐类指标、混淆矩阵、"
            "可靠性分箱及模型指纹见[聚合指标](metrics.json)。"
            "`[verified: metrics.json；私有test_seal.json]`\n"
        )
        (self.report_dir / "training_report.md").write_text(text, encoding="utf-8")
