"""Build the V3 development and independent-confirmation interpretation."""

from __future__ import annotations

import hashlib
import json
import sys
from importlib import import_module
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import PageBreak, SimpleDocTemplate

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "experiment report/unity-v3-confirmation-20261116"
sys.path.insert(0, str(TEST))
Interpretation = import_module("build_test_pdf").Interpretation


def footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont("CJK", 7.5)
    canvas.drawString(44, 28, "V3 / 开发实验与方案选择 / 2026-11-17")
    canvas.drawRightString(A4[0] - 44, 28, f"开发概览 {document.page} / 2")
    canvas.restoreState()


def main() -> None:
    report = Interpretation()
    development = json.loads(
        (ROOT / "experiment report/unity-v3-20261113/summary.json").read_text(encoding="utf-8")
    )
    selected = development["recommendation"]
    d = selected["metrics"]
    t = report.result["summary"]
    report.title("V3 ASTC 自动选参实验报告")
    report.story.append(
        report.p(
            "本实验研究原图输入、exhaustive候选裁剪与真实耗时。"
            "最终选定Unity参考图、ResNet-34候选质量预测、20候选起点续搜。"
            f"2000张独立确认图系统块大小匹配率{t['footprint_accuracy']:.2%}，达到90%目标。",
            "V3 summary.json recommendation；确认result.json summary、accuracy90_met",
        )
    )
    report.table(
        ["指标", "开发验证1000张", "独立确认2000张"],
        [
            [
                "系统块大小匹配",
                f"{d['accuracy']:.2%}",
                f"{t['footprint_accuracy']:.2%} [verified: 两阶段summary accuracy]",
            ],
            [
                "完整配置匹配",
                f"{d['full_choice_accuracy']:.2%}",
                f"{t['full_choice_accuracy']:.2%} [verified: summary full_choice_accuracy]",
            ],
            [
                "严格质量通过",
                f"{d['actual_strict_quality_pass_rate']:.2%}",
                f"{t['strict_quality_pass_rate']:.2%} [verified: summary strict quality]",
            ],
            [
                "相对原标签质量回退",
                str(d["quality_regression_images"]),
                f"{t['quality_regression_images']}张 [verified: summary quality_regression_images]",
            ],
            [
                "平均实际编码次数",
                f"{d['mean_encoding_count']:.4f}",
                f"{t['candidates_measured']['mean']:.4f} [verified: summary encoding count]",
            ],
            [
                "文件批量摊销ms／图",
                f"{selected['median_file_batch_seconds']:.2f}",
                f"{report.result['results']['files_batch']['median_end_to_end_seconds'] / 2:.2f} "
                "[verified: results files_batch]",
            ],
        ],
        [145, 125, 237],
    )
    report.story.append(
        report.p(
            "训练10000张，开发验证1000张用于选模及路线比较。"
            "2000张独立确认按冻结的单一系统评价，使用原20候选Unity标签评分，训练更新0次。",
            "V3训练配置；确认authorization.json、result.json training_updates",
        )
    )
    report.story.append(
        report.p(
            "开发阶段逐项比较了冻结模型换输入、Unity／原图配对训练、20／16候选，"
            "并实测原规则搜索、固定8×8、预测一次编码与预测起点续搜。"
            "按块大小准确率优先选择方案。",
            "V3 summary.json controls、systems、recommendation；V3计划第2节",
        )
    )
    report.story.append(
        report.p(
            "当前选定系统完成一次图片处理时，包含模型推理、真实ASTC编码／解码及质量门控。"
            "开发图平均0.239百万像素，确认图平均1.011百万像素，约4.23倍。"
            "后附四页给出独立测试的详细结果、混淆矩阵和计时分段。",
            "确认report-verification.json dataset_size；result.json scope_details；独立测试PDF",
        )
    )
    report.story.append(PageBreak())
    report.title("输入、训练、规则与方案取舍")
    report.story.append(
        report.p(
            "Unity参考RGBA图片记录在语料reference字段。工程侧C#插桩在ASTC编码回调"
            "记录srcdata哈希，读取PNG后对齐行序，验证像素与回调输入一致。"
            "训练将图片切为240×240 patch，结合有效区域mask形成5通道卷积输入，"
            "并提供8项图片属性。监督为20候选的实测通道误差与整图质量。",
            "metadata.py L57-62；unity_capture_input.py L89-101；unity_patch_dataset.py；"
            "unity_quality.py L75、L107-114",
        )
    )
    report.story.append(
        report.p(
            "两条配对路线分别使用Unity参考图和尺寸对齐原图。每条先全模型训练30轮，"
            "再冻结骨干训练整图头30轮，每批16图、每图4次patch采样。",
            "V3计划第3节；train-unity及train-source_aligned的配置与训练报告",
        )
    )
    report.story.append(
        report.p(
            "模型预测20候选质量，规则从预测值选起点，再用真实压缩质量向后续搜。"
            "sRGB颜色图要求PSNR与MS-SSIM，Linear非法线图按PSNR，法线图按角度误差。"
            "sRGB非法线图面积达到512²时，首个PSNR达标候选锁块，同块继续找完整质量达标项，"
            "必要时返回该块最后一个PSNR合格候选。",
            "v3_policy.py select、search、_strict；确认policy_tables",
        )
    )
    comparisons = [
        case
        for case in development["systems"]
        if case["checkpoint_sha256"]
        in {
            selected["checkpoint_sha256"],
            "85f414f92934acaedaa542405573d2b5b32525122278f21fe203dc96ae9731d8",
        }
    ]
    report.table(
        ["开发验证路线", "系统匹配率", "批量ms／图"],
        [
            [
                f"{'Unity参考图' if c['input_mode'] == 'unity' else '尺寸对齐原图'} / "
                f"{'20候选' if c['candidate_set'] == 'full20' else '16候选'}",
                f"{c['metrics']['accuracy']:.2%}",
                f"{c['median_file_batch_seconds']:.2f} [verified: V3 summary.json systems]",
            ]
            for c in comparisons
        ],
        [220, 90, 197],
    )
    report.story.append(
        report.p(
            "删除exhaustive后，Unity系统开发验证准确率86.7%，出现14张相对严格质量回退。"
            "尺寸对齐原图重训练系统达到92.1%，平均编码1.838次／图。"
            "原图用于模型起点预测，最终编码和质量门控使用Unity参考像素。",
            "V3 summary.json systems；v3_deployment.py run",
        )
    )
    report.story.append(
        report.p(
            "范围为LDR、Tex2D、RGBA8、mip0、RDO关闭。法线身份由导入配置提供，"
            "独立确认仅13张法线与16张Linear，专项覆盖需结合样本量解读。",
            "V3计划第1节；确认result.json summary.groups；opinion: 泛化解释",
            small=True,
        )
    )
    work = ROOT / "tmp/pdfs/v3-combined"
    work.mkdir(parents=True, exist_ok=True)
    front = work / "development-overview.pdf"
    doc = SimpleDocTemplate(
        str(front), pagesize=A4, leftMargin=44, rightMargin=44, topMargin=42, bottomMargin=58
    )
    doc.build(report.story, onFirstPage=footer, onLaterPages=footer)
    assert len(PdfReader(front).pages) == 2
    source = Path(report.checks.get("pdf", ROOT / "output/pdf/V3-ASTC-独立测试解读报告.pdf"))
    pdf_check = json.loads((TEST / "pdf-verification.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == pdf_check["sha256"]
    output = ROOT / "output/pdf/V3-ASTC-实验报告-综合版.pdf"
    writer = PdfWriter()
    writer.append(front)
    writer.append(source)
    writer.add_metadata({"/Title": "V3 ASTC实验报告 综合版", "/Author": "ASTC Compression"})
    writer.write(output)
    reader = PdfReader(output)
    assert len(reader.pages) == 6
    assert all(
        reader.pages[i + 2].extract_text() == PdfReader(source).pages[i].extract_text()
        for i in range(4)
    )
    print(
        json.dumps(
            {
                "pdf": str(output),
                "pages": 6,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
