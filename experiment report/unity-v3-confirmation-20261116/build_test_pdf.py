"""Render the sealed independent-test interpretation with embedded Chinese fonts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import mean, median
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

import numpy as np
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

if TYPE_CHECKING:
    from adaptive_astc.config import JsonDict

PUBLIC = Path(__file__).resolve().parent
ROOT = PUBLIC.parents[1]
OUTPUT = ROOT / "output/pdf/V3-ASTC-独立测试解读报告.pdf"
INK = colors.HexColor("#193748")
TEAL = colors.HexColor("#007F78")
MUTED = colors.HexColor("#556F7E")
PALE = colors.HexColor("#EFF5F6")
WIDTH = A4[0] - 88


def read(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D9E5E8"))
    canvas.line(44, 43, A4[0] - 44, 43)
    canvas.setFont("CJK", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(44, 28, "V3 / 2000张独立确认图 / mip0 / 原Unity标签")
    canvas.drawRightString(A4[0] - 44, 28, f"{document.page} / 4")
    canvas.restoreState()


class Interpretation:
    def __init__(self) -> None:
        self.result = read(PUBLIC / "result.json")
        self.checks = read(PUBLIC / "report-verification.json")
        if self.result["status"] != "passed" or self.checks["status"] != "passed":
            raise ValueError("Complete and verify the formal test before building the PDF")
        if digest(PUBLIC / "result.json") != self.checks["source_result_sha256"]:
            raise ValueError("The report's result binding changed")
        if digest(PUBLIC / "README.md") != self.checks["document_sha256"]:
            raise ValueError("The verified interpretation changed")
        for figure in self.checks["figures"]:
            if digest(Path(figure["path"])) != figure["sha256"]:
                raise ValueError("A verified figure changed")
        pdfmetrics.registerFont(TTFont("CJK", "C:/Windows/Fonts/msyh.ttc", subfontIndex=0))
        pdfmetrics.registerFont(TTFont("CJK-Bold", "C:/Windows/Fonts/msyhbd.ttc", subfontIndex=0))
        pdfmetrics.registerFontFamily("CJK", normal="CJK", bold="CJK-Bold")
        self.body = ParagraphStyle(
            "body",
            fontName="CJK",
            fontSize=9.5,
            leading=15.5,
            textColor=INK,
            spaceAfter=9,
            wordWrap="CJK",
        )
        self.small = ParagraphStyle(
            "small",
            parent=self.body,
            fontSize=8,
            leading=12,
            textColor=MUTED,
        )
        self.heading = ParagraphStyle(
            "heading",
            fontName="CJK-Bold",
            fontSize=18,
            leading=26,
            textColor=INK,
            spaceAfter=14,
            wordWrap="CJK",
        )
        self.cell = ParagraphStyle(
            "cell",
            parent=self.body,
            fontSize=8.2,
            leading=12.4,
            spaceAfter=0,
        )
        self.head_cell = ParagraphStyle(
            "head_cell",
            parent=self.cell,
            fontName="CJK-Bold",
            textColor=colors.white,
        )
        self.story: list[Flowable] = []
        self.texts: list[str] = []

    def p(self, text: str, source: str, *, small: bool = False) -> Paragraph:
        marker = f"[verified: {source}]" if source != "opinion" else "[opinion]"
        self.texts.append(text + marker)
        markup = escape(text)
        markup += f' <font size="7" color="#607987">{escape(marker)}</font>'
        return Paragraph(markup, self.small if small else self.body)

    def title(self, text: str) -> None:
        self.texts.append(text)
        self.story.append(Paragraph(escape(text), self.heading))

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        data = [[Paragraph(escape(text), self.head_cell) for text in headers]]
        self.texts.extend(headers)
        for row in rows:
            self.texts.extend(row)
            data.append([Paragraph(escape(text), self.cell) for text in row])
        table = Table(data, colWidths=widths, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E5E8")),
                ]
            )
        )
        self.story.extend([table, Spacer(1, 10)])

    def image(self, filename: str) -> None:
        self.story.append(Image(str(PUBLIC / "figures" / filename), WIDTH, WIDTH * 8.3 / 12))
        self.story.append(Spacer(1, 10))

    def content(self) -> None:
        r = self.result
        s = r["summary"]
        verdict = "达到" if r["accuracy90_met"] else "低于"
        self.title("V3 ASTC 独立测试解读")
        self.story.append(
            self.p(
                "Unity参考图输入、ResNet-34候选质量预测、20候选起点续搜系统，"
                f"在2000张独立确认图上的块大小匹配率为{s['footprint_accuracy']:.2%}，"
                f"{verdict}90%的系统验收目标。",
                "result.json summary.footprint_accuracy、accuracy90_met",
            )
        )
        values = [
            (
                "纯模型起点块大小匹配",
                f"{s['pure_start_block_accuracy']:.2%}",
                "pure_start_block_accuracy",
            ),
            ("续搜系统块大小匹配", f"{s['footprint_accuracy']:.2%}", "footprint_accuracy"),
            (
                "Blocksize和Quality均匹配",
                f"{s['full_choice_accuracy']:.2%}",
                "full_choice_accuracy",
            ),
            ("严格质量通过", f"{s['strict_quality_pass_rate']:.2%}", "strict_quality_pass_rate"),
            (
                "相对原标签严格质量回退",
                f"{s['quality_regression_images']}张",
                "quality_regression_images",
            ),
            (
                "平均实际编码次数",
                f"{s['candidates_measured']['mean']:.4f}次／图",
                "candidates_measured.mean",
            ),
            (
                "相对原标签payload",
                f"{s['payload_ratio_to_original']:.4%}",
                "payload_ratio_to_original",
            ),
        ]
        self.table(
            ["指标", "独立测试结果"],
            [
                [name, f"{value} [verified: result.json summary.{field}]"]
                for name, value, field in values
            ],
            [205, WIDTH - 205],
        )
        self.story.append(
            self.p(
                "测试目的为评价开发阶段选定系统的独立泛化与真实处理成本。"
                "使用原Unity标签评分，共享封存绑定权重、规则、DLL、输入与执行源码。"
                "一次正式确认包含四种计时口径，每种预热8图一次、完整重复三次。",
                "authorization.json；execution-config-v2.json timing；共享seal及attempt",
            )
        )
        self.story.append(
            self.p(
                "模型训练更新数为0，测试输入为已归档的Unity参考RGBA像素和导入属性。"
                "范围为LDR、RGBA8、mip0，RDO关闭。",
                "result.json training_updates；execution-config-v2.json；prepared-inputs.json",
            )
        )
        self.story.append(PageBreak())
        self.title("准确率、质量与结果解读")
        self.image("test-results.png")
        self.story.append(
            self.p(
                "块大小匹配比较最终Blocksize，完整配置匹配同时比较Quality。"
                "严格质量通过按实际ASTC解码像素与原生质量门槛判定。",
                "主评分rows.json footprint_match、full_choice_match、strict_quality_met",
            )
        )
        self.story.append(
            self.p(
                f"原标签12×12有{s['per_class']['12x12']['support']}张，"
                f"四类平均召回率为{s['balanced_accuracy']:.2%}。"
                f"{s['smaller_block_images']}张使用比原标签更小的块，"
                f"{s['larger_block_images']}张使用更大的块。",
                "result.json summary.per_class、balanced_accuracy、smaller_block_images",
            )
        )
        self.story.append(
            self.p(
                f"法线样本{s['groups']['normal']['images']}张，"
                f"Linear样本{s['groups']['linear']['images']}张。",
                "result.json summary.groups",
            )
        )
        outcomes = self.checks["quality_outcomes"]
        failures = outcomes["strict_failures_by_original_reason"]
        self.story.append(
            self.p(
                f"原标签严格合格{outcomes['original_strict_pass_images']}张，"
                f"系统严格合格{outcomes['system_strict_pass_images']}张。"
                f"严格未通过的图中，原标签为放宽分支的有{failures['size_first_relaxed']}张，"
                f"最高PSNR回退分支的有{failures['highest_psnr_fallback']}张。",
                "report-verification.json quality_outcomes；主评分rows.json",
            )
        )
        self.story.append(
            self.p(
                "开发验证与独立确认的样本组成和尺寸不同，指标需结合各自数据分布解读。"
                "法线和Linear的专项泛化判断仍受当前样本量限制。",
                "opinion",
            )
        )
        dataset = self.checks["dataset_size"]
        self.story.append(
            self.p(
                f"开发验证平均{dataset['validation_pixels'] / 1000 / 1e6:.3f}百万像素／图，"
                f"独立确认平均{dataset['confirmation_pixels'] / 2000 / 1e6:.3f}百万像素／图，"
                f"平均像素数约为{dataset['mean_pixel_ratio']:.2f}倍。",
                "report-verification.json dataset_size；V3源图清单目标尺寸及主评分rows.json",
                small=True,
            )
        )
        self.story.append(PageBreak())
        self.title("训练完成后，一次处理耗时")
        timing = []
        for key, label in [
            ("files_batch", "文件输入／批量摊销"),
            ("pixels_ready_batch", "像素就绪／批量摊销"),
            ("files_single", "文件输入／逐图均值"),
            ("pixels_ready_single", "像素就绪／逐图均值"),
        ]:
            ms = 1000 * r["results"][key]["median_end_to_end_seconds"] / 2000
            timing.append([label, f"{ms:.2f} ms／图 [verified: result.json results.{key}]"])
        self.table(["口径", "三轮整集耗时中位数摊销"], timing, [205, WIDTH - 205])
        single = [x for x in r["measurements"] if (x["scope"], x["mode"]) == ("files", "single")]
        rows = []
        for index, record in enumerate(single, 1):
            latency = np.asarray(record["timings"]["single_image_latencies_seconds"]) * 1000
            rows.append(
                [
                    f"正式重复{index}",
                    f"{mean(latency):.2f}",
                    f"{median(latency):.2f}",
                    f"{np.percentile(latency, 95):.2f} [verified: files/single repeat={index - 1}]",
                ]
            )
        self.table(
            ["文件输入逐图实测", "平均ms", "中位ms", "P95 ms"], rows, [135, 80, 80, WIDTH - 295]
        )
        batch = [x for x in r["measurements"] if (x["scope"], x["mode"]) == ("files", "batch")]
        selected = min(
            batch,
            key=lambda x: abs(
                x["timings"]["end_to_end_seconds"]
                - r["results"]["files_batch"]["median_end_to_end_seconds"]
            ),
        )
        components = [
            ("模型输入准备", "input_preparation_seconds"),
            ("推理、传输与聚合", "inference_wall_seconds"),
            ("实际编码输入准备", "reference_load_metadata_and_flip_seconds"),
            ("规则及流程管理", "policy_and_bookkeeping_seconds"),
            ("全部ASTC试压编码", "native_encode_seconds"),
            ("全部ASTC解码", "native_decode_seconds"),
            ("全部质量门控", "native_quality_seconds"),
        ]
        self.table(
            ["文件批量中位数对应重复的处理环节", "分段ms／图"],
            [
                [
                    name,
                    f"{1000 * selected['timings'][field] / 2000:.2f} "
                    f"[verified: repeat={selected['repeat']} timings.{field}]",
                ]
                for name, field in components
            ],
            [205, WIDTH - 205],
        )
        self.story.append(
            self.p(
                "主计时在模型和DLL就绪后开始，终点为最终内存mip0 ASTC。"
                "包含预测、选参、所有续搜编码、解码和质量门控。"
                "Unity导入、模型／DLL加载、输出审计、写盘及轨迹哈希另列。",
                "result.json measurements.timings.scope_details",
                small=True,
            )
        )
        self.story.append(
            self.p(
                "文件批量对整集预测，像素就绪按8图分组后聚合，"
                "时间差同时包含输入边界与分组粒度的影响。",
                "v3_confirmation.py L233–274；opinion: 时间差解释",
                small=True,
            )
        )
        self.story.append(PageBreak())
        self.title("耗时分布与核验证据")
        self.image("test-timing.png")
        self.story.append(
            self.p(
                "每张图的尺寸、候选起点、Quality及续搜次数共同影响处理时间。"
                "批量摊销和逐图P95分别来自各自运行模式的实测。",
                "opinion",
            )
        )
        hardware = read(PUBLIC / "hardware.json")
        self.story.append(
            self.p(
                f"测试CPU为{hardware['cpu']}，"
                f"{hardware['logical_processors']}个逻辑处理器，"
                f"内存{hardware['ram_bytes'] / 1024**3:.2f} GiB。"
                f"GPU记录为{hardware['gpu']}，依次为名称、显存和驱动版本。",
                "hardware.json cpu、logical_processors、ram_bytes、gpu",
                small=True,
            )
        )
        self.story.append(
            self.p(
                "12个正式测量单元均覆盖完整2000图，预测起点、查询轨迹、最终候选和ASTC"
                "在重复测量中保持一致。最终选中ASTC逐张解码复算质量，模型参数与buffer复核通过。",
                "result.json；report-verification.json；四份outputs.json及12份trace",
                small=True,
            )
        )
        self.story.append(
            self.p(
                "完整Markdown、逐图CSV、结果JSON和图表位于仓库的"
                "experiment report/unity-v3-confirmation-20261116目录。"
                "实际ASTC、PNG、预测NPZ和轨迹由result.json中的路径定位。",
                "result.json outputs_manifest、trace、predictions_archive",
                small=True,
            )
        )

    def build(self) -> JsonDict:
        self.content()
        widths = pdfmetrics.getFont("CJK").face.charWidths
        missing = sorted(
            {
                character
                for text in self.texts
                for character in text
                if not character.isspace() and ord(character) not in widths
            }
        )
        if missing:
            raise ValueError(f"Missing embedded-font glyphs: {missing}")
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(OUTPUT),
            pagesize=A4,
            leftMargin=44,
            rightMargin=44,
            topMargin=42,
            bottomMargin=58,
            title="V3 ASTC 独立测试解读报告",
            author="ASTC Compression Experiment",
        )
        doc.build(self.story, onFirstPage=footer, onLaterPages=footer)
        reader = PdfReader(OUTPUT)
        if len(reader.pages) != 4:
            raise ValueError(f"Expected four pages, got {len(reader.pages)}")
        text = "\n".join(page.extract_text() for page in reader.pages)
        for token in [f"{self.result['summary']['footprint_accuracy']:.2%}", "2000", "P95"]:
            if token not in text:
                raise ValueError(f"Missing report content: {token}")
        verification = {
            "status": "built_pending_visual_review",
            "pdf": str(OUTPUT),
            "sha256": digest(OUTPUT),
            "pages": len(reader.pages),
            "missing_glyphs": missing,
            "source_result_sha256": digest(PUBLIC / "result.json"),
            "source_markdown_sha256": digest(PUBLIC / "README.md"),
            "page_text_lengths": [len(page.extract_text()) for page in reader.pages],
        }
        (PUBLIC / "pdf-verification.json").write_text(
            json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return verification


if __name__ == "__main__":
    print(json.dumps(Interpretation().build(), ensure_ascii=True, indent=2))
