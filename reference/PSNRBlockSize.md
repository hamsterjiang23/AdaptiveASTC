---
title: "ASTC Block-Size Determination Method based on PSNR Values"
method_name: PSNRBlockSize
aliases: [PSNRBlockSize]
authors: [Jae-Ho Nah]
year: 2022
venue: Journal of the Korea Computer Graphics Society 28(2) 21–28
doi: 10.15701/kcgs.2022.28.2.21
arxiv: null
tags: [paper-note, texture-compression, astc, parameter-selection]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "原文选读，p.21摘要、§3.1–3.2、Tables 2–3、§5局限"
pdf_file: papers/PSNRBlockSize.pdf
---

# PSNRBlockSize

## 来源与阅读范围

取得期刊8页原文，简读摘要、预处理与搜索过程、体积／时间表以及结论。最初HTTPS入口失败，随后HTTP下载完成并经pdfinfo确认有效。`[verified: 本地PDF p.21–28；本次pdfinfo“Pages: 8”]` 本机归档`papers/PSNRBlockSize.pdf`、[论文入口](https://doi.org/10.15701/kcgs.2022.28.2.21)

## 核心方法

三个阶段依次为类别级人工预分析、fastest模式下搜索目标PSNR对应的最大块、thorough模式最终编码。预分析先人工找可接受块大小，再测其fastest PSNR；通常以类别最大PSNR与平均PSNR的均值设目标，也允许类别例外。搜索从类别初值出发，按当前质量决定搜索方向。`[verified: 原文p.23–24 §3.1–3.2、Equation 1、Figure 2]`

## 实验与证据

64张纹理的压缩总大小从固定6×6的216.3 MB降至69.8 MB，主要来自7张高分辨率Captured images由199.3 MB降至49.8 MB；其余四类体积均增加。编码总时间169 s增至220 s，该计时排除预处理。论文还报告逐图等权平均bpp由3.56增至3.85，与总字节下降并存。`[verified: 原文p.26 Table 2、Table 3及§4.3–4.4]`

## 局限与AdaptiveASTC关联

作者指出只使用PSNR的限制，以及实验限于RGB／RGBA的2D LDR纹理。多指标组合与额外计算开销被列为后续问题。`[verified: 原文p.27 §5]`

这篇是项目目标质量搜索基线的重要来源。总体68%节省高度受大尺寸样本影响，因此本项目应同时报告真实总字节、逐图指标和按材质类别结果。类别目标的人工预分析成本也应单列，分类模型的生产单次编码收益需要在相同质量口径下重新比较。`[opinion]`
