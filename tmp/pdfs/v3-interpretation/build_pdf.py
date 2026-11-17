"""Create and validate the requested Chinese V3 interpretation PDF."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

ROOT = Path("E:/ASTC_Compression")
ARCHIVE = ROOT / "experiment report/unity-v3-20261113"
OUTPUT = ROOT / "output/pdf/V3-ASTC-实验解读报告.pdf"
WORK = ROOT / "tmp/pdfs/v3-interpretation"
PAGE_W, PAGE_H = A4
MARGIN = 48.0
WIDTH = PAGE_W - 2 * MARGIN
INK = colors.HexColor("#193748")
TEAL = colors.HexColor("#007F78")
MUTED = colors.HexColor("#556F7E")
PALE = colors.HexColor("#EFF5F6")
LINE = colors.HexColor("#D9E5E8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class Page:
    title: str
    subtitle: str
    items: list[Flowable]


class ProcessDiagram(Flowable):
    def __init__(self, labels: list[str], caption: str) -> None:
        super().__init__()
        self.labels = labels
        self.caption = caption
        self.width = WIDTH
        self.height = 83

    def draw(self) -> None:
        canvas = self.canv
        gap = 16.0
        box_width = (WIDTH - gap * (len(self.labels) - 1)) / len(self.labels)
        for index, label in enumerate(self.labels):
            x = index * (box_width + gap)
            canvas.setFillColor(PALE)
            canvas.setStrokeColor(LINE)
            canvas.roundRect(x, 37, box_width, 35, 4, fill=1, stroke=1)
            canvas.setFillColor(INK)
            canvas.setFont("CJK-Bold", 9)
            canvas.drawCentredString(x + box_width / 2, 50, label)
            if index < len(self.labels) - 1:
                canvas.setStrokeColor(TEAL)
                canvas.line(x + box_width + 3, 54.5, x + box_width + gap - 3, 54.5)
                canvas.line(x + box_width + gap - 6, 57, x + box_width + gap - 3, 54.5)
                canvas.line(x + box_width + gap - 6, 52, x + box_width + gap - 3, 54.5)
        canvas.setFillColor(MUTED)
        canvas.setFont("CJK", 9)
        canvas.drawCentredString(WIDTH / 2, 16, self.caption)


class PDFReport:
    def __init__(self) -> None:
        pdfmetrics.registerFont(TTFont("CJK", "C:/Windows/Fonts/msyh.ttc", subfontIndex=0))
        pdfmetrics.registerFont(TTFont("CJK-Bold", "C:/Windows/Fonts/msyhbd.ttc", subfontIndex=0))
        pdfmetrics.registerFontFamily("CJK", normal="CJK", bold="CJK-Bold")
        self.styles = {
            "body": ParagraphStyle("body", fontName="CJK", fontSize=10.3, leading=16.8,
                                   textColor=INK, spaceAfter=9, wordWrap="CJK"),
            "lead": ParagraphStyle("lead", fontName="CJK", fontSize=11.5, leading=19.2,
                                   textColor=INK, spaceAfter=12, wordWrap="CJK"),
            "heading": ParagraphStyle("heading", fontName="CJK-Bold", fontSize=12.3,
                                      leading=19, textColor=TEAL, spaceBefore=10, spaceAfter=7,
                                      wordWrap="CJK"),
            "small": ParagraphStyle("small", fontName="CJK", fontSize=8.5, leading=13.0,
                                    textColor=MUTED, spaceAfter=7, wordWrap="CJK"),
            "scope": ParagraphStyle("scope", fontName="CJK", fontSize=9.0, leading=14.0,
                                    textColor=MUTED, spaceAfter=7, wordWrap="CJK"),
            "cell": ParagraphStyle("cell", fontName="CJK", fontSize=9.1, leading=14.0,
                                   textColor=INK, alignment=TA_LEFT, wordWrap="CJK"),
            "headcell": ParagraphStyle("headcell", fontName="CJK-Bold", fontSize=9.0,
                                       leading=13.4, textColor=colors.white, wordWrap="CJK"),
        }
        self.summary = read_json(ARCHIVE / "summary.json")
        self.doc_check = read_json(ROOT / "experiment report/V3/verification.json")
        for path, expected in self.doc_check["source_files_sha256"].items():
            if sha256(Path(path)) != expected:
                raise ValueError(f"Report source changed: {path}")
        if sha256(ROOT / "experiment report/V3/README.md") != self.doc_check["document_sha256"]:
            raise ValueError("The approved interpretation text changed")
        self.texts: list[str] = []
        self.pages: list[Page] = []

    def p(self, text: str, source: str = "", *, opinion: bool = False,
          style: str = "body") -> Paragraph:
        self.texts.append(text)
        suffix = f"[verified: {source}]" if source else "[opinion]" if opinion else ""
        self.texts.append(suffix)
        markup = escape(text).replace("\n", "<br/>")
        if suffix:
            markup += ' <font size="7.2" color="#607987">' + escape(suffix) + "</font>"
        return Paragraph(markup, self.styles[style])

    def h(self, text: str) -> Paragraph:
        return self.p(text, style="heading")

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float],
              sources: list[str]) -> Table:
        data = [[Paragraph(escape(text), self.styles["headcell"]) for text in headers]]
        self.texts.extend(headers)
        for row, source in zip(rows, sources, strict=True):
            cells = []
            for index, text in enumerate(row):
                self.texts.append(text)
                markup = escape(text)
                if index == 0:
                    label = f"[verified: {source}]"
                    self.texts.append(label)
                    markup += '<br/><font size="6.9" color="#607987">' + escape(label) + "</font>"
                cells.append(Paragraph(markup, self.styles["cell"]))
            data.append(cells)
        table = Table(data, colWidths=widths, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, INK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.45, LINE),
        ]))
        table.spaceAfter = 11
        return table

    def page(self, title: str, subtitle: str, items: list[Flowable]) -> None:
        self.texts.extend([title, subtitle])
        self.pages.append(Page(title, subtitle, items))

    def content(self) -> None:
        self.page("V3 ASTC 自动选参解读报告", "实验目的、实施方法、最终结论与实际含义", [
            self.p("当前选定方案是Unity参考图输入、ResNet-34候选质量预测、20候选起点续搜。1000张开发验证图的块大小匹配率为93.6%，批量实测195.60 ms／图。", "结果汇总 recommendation", style="lead"),
            self.table(["所选系统指标", "结果", "统计含义"], [
                ["块大小准确率", "93.6%", "936张的Blocksize与原Unity标签一致"],
                ["完整配置匹配", "80.4%", "804张的Blocksize和Quality档位均一致"],
                ["严格质量通过", "87.5%", "875张满足原生严格质量阈值"],
            ], [160, 70, WIDTH - 230], ["结果汇总 accuracy", "结果汇总 full_choice_accuracy", "结果汇总 actual_strict_quality_pass_rate"]),
            self.h("为什么做V3"),
            self.p("V2已有可用的预测起点续搜系统。V3继续验证三件事：处理一张图实际花多久，删除exhaustive的代价是什么，以及模型能否直接读取源图。", "V3计划 第1、2节"),
            self.table(["问题", "本轮结论"], [
                ["真实成本", "原规则同DLL搜索445.02 ms／图，所选系统195.60 ms／图"],
                ["删除exhaustive", "Unity系统105.33 ms／图，块大小准确率86.7%"],
                ["原图输入", "尺寸对齐原图重训练后，续搜92.1%，208.32 ms／图"],
            ], [160, WIDTH - 160], ["冻结实测 original-full20；结果汇总", "实测Unity no_exhaustive16", "实测原图 full20"]),
            self.p("这些数字对应10000张训练图、1000张开发验证图，范围为LDR、Tex2D、RGBA8、mip0、RDO关闭。2000张独立确认图的合同已准备，执行授权为false。", "V3计划 第1节；确认合同 cohort、test_opened", style="small"),
        ])

        self.page("图片经过什么处理", "源图、Unity参考图和ASTC解码图承担不同用途", [
            ProcessDiagram(["源文件及配置", "Unity参考像素", "ASTC编码", "ASTC解码像素"], "质量监督与实际门控比较Unity参考像素和ASTC解码像素"),
            self.p("源图是磁盘资产。Unity参考图是完成导入处理后、进入ASTC编码前的RGBA像素。解码图是ASTC重新解码得到的像素。训练质量目标与实际质量检查均使用Unity参考图和解码图的差异。", "完整报告 输入与质量监督；计时代码 V3NativeQueries.measure"),
            self.h("原图入口怎样使用"),
            self.p("模型接收源文件或RGBA数据，以及源尺寸、目标导入尺寸、srgb、normal、need_alpha、normal_metric_mips。黑像素比例与Alpha恒定性由原图输入计算，法线用途由调用方提供。", "输入代码 SourceTextureSpec、UnityV3InferenceInput"),
            self.p("尺寸对齐原图用Pillow解码为RGBA，并以BICUBIC缩放至Unity目标尺寸。起点预测完成后，真实编码和门控使用Unity参考像素及其实际属性。", "输入代码 pixels；计时代码 run"),
            self.h("实际存在多少输入差异"),
            self.table(["核验项目", "观察结果"], [
                ["开发源文件", "10000张训练图、1000张验证图全部解码，原采集MD4匹配，失败0张"],
                ["尺寸变化", "训练3167张、验证368张的源尺寸与Unity目标尺寸不同"],
                ["对齐后的RGB与Alpha", "验证集653张有RGB差异，60张有Alpha差异，分组可重叠"],
                ["属性与规则阈值", "对齐原图的347张黑像素比例变化，50张的预测分支PSNR阈值变化"],
            ], [163, WIDTH - 163], ["原图核验 counts、failures", "原图核验 counts", "输入诊断 group_indices", "输入诊断 controls[4].input_context_differences"]),
            self.p("原图路线支持已知配置下的起点预测，训练监督和最终质量门控继续采用Unity协议。输入像素差异需要在模型与完整系统中共同评价。", "V3计划 第3节", style="small"),
        ])

        self.page("模型与实验怎么做", "固定数据、训练配方与评价目标，比较输入和候选集合", [
            self.p("使用ImageNet初始化的ResNet-34。图像按240×240切patch，边缘复制填充并携带有效mask，结合8项导入属性预测候选质量。逐patch四通道误差聚合为PSNR，整图头预测MS-SSIM与法线角度等指标，规则层决定Blocksize和Quality。", "模型代码 encode、predict_images；完整报告 模型与配对训练"),
            self.table(["训练约定", "两条输入路线共用"], [
                ["训练输入", "Unity参考图，或BICUBIC尺寸对齐原图"],
                ["两阶段", "全模型30轮，再冻结编码器等部分训练整图头30轮"],
                ["采样与优化", "每批16图，每图4patch，学习率3e-4，weight decay 0.05"],
                ["选模", "seed 20261112，块大小Top-1优先、近阈值PSNR RMSE次之，最佳权重重载核验"],
            ], [125, WIDTH - 125], ["V3计划 第3节", "完整报告 配对训练；训练回执 history", "V3计划 第3节；训练回执 config", "V3计划 第3节；训练回执 checkpoint_audit"]),
            self.table(["输入", "全模型最佳", "整图头最佳", "进程时间"], [
                ["Unity参考图", "86.2%", "86.9%", "2227.99 + 412.73秒"],
                ["尺寸对齐原图", "81.0%", "81.7%", "2767.52 + 617.31秒"],
            ], [150, 80, 80, WIDTH - 310], ["训练回执；结果汇总 training_costs.unity", "训练回执；结果汇总 training_costs.source_aligned"]),
            self.h("20候选怎样裁成16候选"),
            self.p("块大小按12×12、10×10、8×8、6×6排列。每块包含fastest、fast、medium、thorough、exhaustive。16候选屏蔽每块的exhaustive，模型保留20个输出位置，预测、真实查询和回退使用同一有效候选集合。主评分仍对照原20候选Unity标签。", "续搜代码 NativeCandidateSet；V3计划 第2、3节"),
            self.p("整套执行包含24组正式对照、288次正式测量和120轮训练。全量执行前完成32训练图／8验证图的小样本闭环。", "归档复核 formal_cases、formal_measurements、paired_training_epochs；V3计划 第4节", style="small"),
        ])

        self.page("结果与最终选型", "主指标为最终块大小对原20候选Unity标签的匹配率", [
            self.table(["配对训练后的输入与候选", "纯预测", "续搜后", "编码次数", "ms／图"], [
                ["Unity参考图 / 20", "86.9%", "93.6%", "1.627", "195.60"],
                ["Unity参考图 / 16", "84.9%", "86.7%", "1.562", "105.33"],
                ["尺寸对齐原图 / 20", "81.7%", "92.1%", "1.838", "208.32"],
                ["尺寸对齐原图 / 16", "80.9%", "85.3%", "1.693", "121.26"],
            ], [182, 66, 66, 83, WIDTH - 397], ["实测Unity full20", "实测Unity no_exhaustive16", "实测原图 full20", "实测原图 no_exhaustive16"]),
            self.p("按已约定的准确率优先排序，选定Unity参考图、20候选、预测起点续搜。702张图一次编码完成，编码次数P95为5次，最大16次。Unity重训练的完整1000图质量预测存档SHA与V2相同，验证预测得到复现。", "结果汇总 recommendation、unity_input_retraining_reproduction；完整报告 编码次数"),
            self.h("真实成本的四组基线"),
            self.table(["冻结V2的同批对照", "块大小匹配", "严格质量", "次数／图", "ms／图"], [
                ["原规则搜索重放", "100.0%", "87.4%", "7.061", "445.02"],
                ["固定8×8 / medium", "14.3%", "81.1%", "1.000", "23.70"],
                ["纯预测后一次编码", "86.9%", "68.2%", "1.000", "128.38"],
                ["预测起点后续搜", "93.6%", "87.5%", "1.627", "200.84"],
            ], [182, 66, 66, 83, WIDTH - 397], ["冻结实测 original-full20", "冻结实测 fixed8-full20", "冻结实测 pure-unity-full20", "冻结实测 forward-unity-full20"]),
            self.p("本轮原规则重放与所选系统的实测耗时相差56.05%。所选系统耗时约为固定8×8的8.25倍，同时严格质量通过87.5%，payload为固定8×8的53.66%。这些数值共同描述逐图选参的质量、体积与成本取舍。", "报告复核 derived.timing_comparisons；结果汇总 recommendation.metrics"),
            self.p("历史Unity采集的search_ms平均1068.42 ms，中位514.70 ms，P95为4219.77 ms，保留原采集计时范围。上表使用本轮文件到内存ASTC的实际重放口径。", "结果汇总 historical_unity_capture_timings.search_ms", style="small"),
        ])

        self.page("原图结果为什么这样", "续搜效果同时取决于预测准确率与起点错误方向", [
            self.table(["20候选下的输入与模型", "纯预测", "续搜后", "次数／图", "ms／图"], [
                ["原尺寸源图 / 冻结V2", "76.9%", "92.8%", "2.382", "239.33"],
                ["尺寸对齐原图 / 冻结V2", "81.9%", "87.3%", "1.577", "197.14"],
                ["尺寸对齐原图 / 重训练", "81.7%", "92.1%", "1.838", "208.32"],
            ], [182, 66, 66, 83, WIDTH - 397], ["冻结实测 source_native", "冻结实测 source_aligned", "实测原图 full20"]),
            self.p("原尺寸源图方案达到92.8%，同时需要2.382次平均编码。尺寸对齐原图重训练后为92.1%，平均1.838次编码。输入处理和权重不同的两条路线各自体现了准确率与处理成本的取舍。", "结果汇总 controls、systems"),
            self.h("大白话理解单向续搜"),
            self.p("假设原标签为8×8。起点在12×12时，候选后缀还包含10×10和8×8。起点已到6×6时，查询范围只剩6×6的后续档位。更小块通常占用更多payload，偏小的起点会跳过前面的更大块候选。", "续搜代码 GRID、search；模型评分的payload计算"),
            self.table(["尺寸对齐原图", "偏小起点", "偏大起点", "续搜后正确"], [
                ["冻结V2", "125张", "56张", "873张"],
                ["原图重训练", "77张", "106张", "921张"],
            ], [182, 95, 95, WIDTH - 372], ["结果汇总 冻结原图 controls、systems", "结果汇总 重训练原图 controls、systems"]),
            self.p("逐张配对后，续搜纠正65张旧错误、新增17张错误，净增加48张正确。", "报告复核 derived.source_training_paired_transitions.forward"),
            self.p("纯预测纠正63张、增加65张错误，净减少2张正确。", "报告复核 derived.source_training_paired_transitions.pure"),
            self.p("错误方向的分布变化与续搜收益相符。评价原图训练时，起点质量、后续查询次数及最终系统结果需要一起读。", opinion=True),
            self.p("颜色候选近阈值PSNR RMSE从2.0300变为2.4997 dB。当前收益体现在续搜后的标签匹配，纯预测准确率和该误差指标各保留其实际结果。", "输入诊断 controls[2]、controls[4]；实测原图 full20", style="small"),
        ])

        self.page("Quality与质量怎么解读", "标签匹配、严格达标和相对回退各自回答一个问题", [
            self.table(["所选系统的四项结果", "正确含义"], [
                ["93.6% 块大小匹配", "936／1000张的最终Blocksize与原标签一致"],
                ["80.4% 完整配置匹配", "804张的Blocksize与Quality档位均一致"],
                ["87.5% 严格质量通过", "875张的实际压缩结果达到原生严格质量阈值"],
                ["0张 相对质量回退", "原标签已严格合格的874张全部保留，另新增1张合格"],
            ], [210, WIDTH - 210], ["结果汇总 accuracy", "结果汇总 full_choice_accuracy", "结果汇总 actual_strict_quality_pass_rate", "结果汇总 quality_regression_images；原规则基线"]),
            self.p("其余125张严格未通过图中，92张来自大图锁块后的放宽分支，33张来自最高PSNR回退。原标签的126张严格未通过图为93张放宽、33张回退。", "报告复核 derived.strict_quality_outcomes"),
            self.p("1000图的mip0 payload为32,067,120字节，固定8×8／medium为59,761,616字节，比例53.66%。相对原搜索标签的payload比例为101.28%，ASTC容器头另计。", "结果汇总 recommendation.metrics payload_bytes、payload_ratio_to_original"),
            self.h("删除exhaustive节省多少，代价是什么"),
            self.p("Unity输入系统从20候选改为16候选，耗时195.60降至105.33 ms／图，实测相差46.15%。平均编码次数1.627变为1.562，块大小准确率93.6%降至86.7%，相对原标签出现14张严格质量回退。", "实测Unity full20、no_exhaustive16；报告复核 timing_comparisons"),
            self.p("当前开发准入按块大小Top-1达到90%执行，因此本轮选定20候选。16候选规则参照本身与原20候选标签有6.2%的块大小变化，模型评分继续使用原20候选标签。", "V3计划 第2、4节；结果汇总 recommendation；候选重放 no_exhaustive16.oracle"),
            self.h("严格质量遵循什么标准"),
            self.p("颜色图PSNR基础门槛30 dB，纯黑比例大于40%时为35 dB，大于80%时为37 dB。sRGB颜色图还要求原生MS-SSIM的dB表达达到21 dB，Linear非法线按PSNR判断。法线要求平均角度不超过3.2°、p95不超过9°，均按原采集规则的float32精度判定。", "报告复核 derived.policy_values；续搜代码 effective_threshold、_strict"),
        ])

        self.page("时间花在哪里", "批量摊销与单图等待预算使用各自的实际测量", [
            self.p("下表取所选系统第2次files／batch正式重复，1000图总耗时195.5956秒，正好对应三次总耗时中位数。各行是同一次重复的分段摊销，末位差异包含循环及计时开销。", "单次分段 repeat=1.timings"),
            self.table(["处理环节", "ms／图"], [
                ["模型输入准备", "6.28"],
                ["patch读取、推理、传输和聚合", "12.72"],
                ["编码参考像素、属性和行序准备", "6.85"],
                ["策略与簿记", "0.78"],
                ["ASTC编码", "134.99"],
                ["ASTC解码", "12.60"],
                ["原生质量计算", "21.33"],
                ["文件到最终内存ASTC总时间", "195.60"],
            ], [370, WIDTH - 370], ["单次分段 input_preparation_seconds", "单次分段 inference_wall_seconds", "单次分段 reference_load_metadata_and_flip_seconds", "单次分段 policy_and_bookkeeping_seconds", "单次分段 native_encode_seconds", "单次分段 native_decode_seconds", "单次分段 native_quality_seconds", "单次分段 end_to_end_seconds"]),
            self.table(["逐图正式重复", "平均ms", "中位ms", "P95 ms"], [
                ["第1次", "228.48", "91.46", "608.67"],
                ["第2次", "229.12", "93.40", "610.91"],
                ["第3次", "230.49", "95.04", "612.54"],
            ], [210, 90, 90, WIDTH - 390], ["结果汇总 single_image_latency_ms.files[0]", "结果汇总 single_image_latency_ms.files[1]", "结果汇总 single_image_latency_ms.files[2]"]),
            self.p("纯预测一次编码与固定8×8都只进行一次编码，各自耗时包含所选Blocksize和Quality的编码成本。预测输入准备和推理成本直接参考上表的独立字段。", "冻结实测 pure、fixed8；单次分段", style="small"),
        ])

        self.page("适用范围与证据", "开发准入已达到，独立确认按已准备的合同执行", [
            self.p("主计时在所需模型与DLL就绪后开始。搜索和续搜在真实门控完成、最终ASTC确定并保留时结束。纯预测和固定8×8在内存ASTC生成时结束，其质量由输出审计评价。Unity导入与标签准备复用归档，加载、训练、最终审计及写盘另有记录，轨迹哈希与进度写盘成本单列。", "计时代码 run；完整报告 计时与评价口径", style="scope"),
            self.p("各路线预热8图一次、正式重复三次，并做GPU同步。files批量覆盖1000图，pixels_ready按8图分组。原图pixels_ready接收解码后的源尺寸RGBA，尺寸对齐仍计时。并发Blender CPU活动已记录，200.84与195.60 ms／图两批时间的模型归因存在不确定性。", "计时代码 measure、run；资源记录；完整报告 实际时间花在哪里", style="scope"),
            self.p("法线用途由调用方normal属性给定。45张法线图中，所选系统40张块大小匹配、42张严格角度合格。mask／MSAK专项通道语义按本轮约定暂缓。2000张确认图合同状态为prepared_for_execution_review，授权和test_opened均为false，正式确认需单独授权。", "结果汇总 groups.normal；V3计划；确认合同", style="scope"),
            self.p("压缩和解压调用astcenc-avx2-shared.dll，PSNR、MS-SSIM与法线角度计算调用unity_astc_quality.dll。库路径及SHA绑定位于experiment plan/V3/evidence.json。", "完整报告 实施与证据入口", style="scope"),
            self.h("配套证据定位"),
            self.p("以下路径均以E:/ASTC_Compression为仓库根。页内verified标记使用下列内容名称及对应字段。", "完整报告 实施与证据入口", style="small"),
            self.p("完整报告　experiment report/V3/README.md\n报告复核　experiment report/V3/verification.json\nV3计划　experiment plan/V3/README.md", style="small"),
            self.p("其余数据位于experiment report/unity-v3-20261113/。", "完整报告 实施与证据入口", style="small"),
            self.p("结果汇总　summary.json\n输入诊断　input-diagnostics.json\n原图核验　source-input-audit.json\n冻结实测　benchmark-v2-full1000-v1.json\n实测Unity　benchmark-trained-unity-full1000-v1.json\n实测原图　benchmark-trained-source_aligned-full1000-v1.json\n候选重放　candidate-ablation.json\n确认合同　confirmation-contract.json\n归档复核　final-integrity-verification.json\n资源记录　resource-observations.jsonl", style="small"),
            self.p("结果汇总的主指标位于recommendation.metrics，组合对照位于systems和controls。", "结果汇总", style="small"),
            self.p("单次分段对应实测Unity中forward-unity-full20、files、batch、repeat=1的timings。训练回执为train-unity-full-full-v1.json、train-unity-head-full-v1.json及两个train-source_aligned-*报告。", style="small"),
            self.p("模型代码　src/adaptive_astc/models/unity_quality.py\n输入代码　src/adaptive_astc/data/unity_v3_input.py\n续搜代码　reproductions/unity_search_baseline/v3_policy.py\n模型评分　src/adaptive_astc/training/unity_v3_trainer.py\n计时代码　reproductions/unity_search_baseline/v3_deployment.py及v3_benchmark.py", style="small"),
        ])

    def build(self) -> dict:
        self.content()
        if len(self.pages) != 8:
            raise ValueError("Require the planned eight-page interpretation")
        regular = pdfmetrics.getFont("CJK").face.charWidths
        bold = pdfmetrics.getFont("CJK-Bold").face.charWidths
        missing = sorted({char for text in self.texts for char in text
                          if not char.isspace() and (ord(char) not in regular or ord(char) not in bold)})
        if missing:
            raise ValueError(f"Missing embedded-font glyphs: {missing}")
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        canvas = Canvas(str(OUTPUT), pagesize=A4, pageCompression=1)
        canvas.setTitle("V3 ASTC 自动选参实验解读报告")
        canvas.setAuthor("ASTC Compression Experiment")
        canvas.setCreator("Codex with ReportLab")
        canvas.setSubject("原图输入、候选裁剪、真实耗时及结论解读")
        layouts = []
        for number, page in enumerate(self.pages, 1):
            canvas.setFillColor(TEAL)
            canvas.setFont("CJK-Bold", 8.4)
            canvas.drawString(MARGIN, PAGE_H - 35, "ASTC COMPRESSION")
            canvas.setFillColor(MUTED)
            canvas.setFont("CJK", 8.4)
            canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 35, "V3 实验解读")
            canvas.setStrokeColor(LINE)
            canvas.line(MARGIN, PAGE_H - 45, PAGE_W - MARGIN, PAGE_H - 45)
            canvas.setFillColor(INK)
            canvas.setFont("CJK-Bold", 20 if number == 1 else 18)
            canvas.drawString(MARGIN, PAGE_H - 84, page.title)
            canvas.setFillColor(MUTED)
            canvas.setFont("CJK", 9.2)
            canvas.drawString(MARGIN, PAGE_H - 106, page.subtitle)
            y = PAGE_H - 129
            for item in page.items:
                before = item.getSpaceBefore()
                after = item.getSpaceAfter()
                _, height = item.wrapOn(canvas, WIDTH, 10000)
                if y - before - height < 55:
                    raise ValueError(f"Page {number} overflow by {55 - y + before + height:.1f}pt at {item.__class__.__name__}")
                item.drawOn(canvas, MARGIN, y - before - height)
                y -= before + height + after
            canvas.setStrokeColor(LINE)
            canvas.line(MARGIN, 43, PAGE_W - MARGIN, 43)
            canvas.setFillColor(MUTED)
            canvas.setFont("CJK", 7.4)
            canvas.drawString(MARGIN, 27, "1000张开发验证图 / LDR Tex2D / mip0 / RDO关闭 [verified: V3计划范围]")
            canvas.drawRightString(PAGE_W - MARGIN, 27, f"{number:02} / 08")
            layouts.append({"page": number, "title": page.title, "content_bottom_pt": y})
            canvas.showPage()
        canvas.save()
        result = {"pdf": str(OUTPUT), "sha256": sha256(OUTPUT), "pages": len(self.pages),
                  "embedded_fonts": ["Microsoft YaHei", "Microsoft YaHei Bold"],
                  "missing_glyphs": missing, "layout": layouts,
                  "source_markdown_sha256": sha256(ROOT / "experiment report/V3/README.md")}
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / "build-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result


if __name__ == "__main__":
    print(json.dumps(PDFReport().build(), ensure_ascii=True))
