---
title: "SegTC: Fast Texture Compression using Image Segmentation"
method_name: SegTC
aliases: [SegTC]
authors: [Pavel Krajcevski, Dinesh Manocha]
year: 2014
venue: High Performance Graphics
arxiv: null
tags: [paper-note, texture-compression, bptc, segmentation]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "原文选读，Abstract、§3、§4、§5，PDF共7页"
pdf_file: papers/SegTC.pdf
---

# SegTC

## 来源与阅读范围

阅读作者公开的HPG 2014论文摘要、分区匹配方法、实验口径及局限。实验使用BPTC格式。`[verified: 原文Abstract、§3–5]` 本机归档`papers/SegTC.pdf`、[作者PDF](https://gamma-web.iacs.umd.edu/FasTC/extra/SegTC.pdf)

## 核心方法

先对整张图做超像素分割，用分割边界确定每个压缩块的理想分区，再通过Hamming距离与VP-tree寻找最近的预定义P-shape。其想法是在全图预处理中提取结构，减少逐块分区搜索。`[verified: 原文§1末段、§3、§3.3.2]`

## 实验与证据

作者在单核、无专用向量指令的BPTC编码比较中报告最高约6倍加速，并用PSNR及转灰度后的SSIM比较质量。Figure 1的256×256示例，SegTC为143 ms，FasTC为567 ms，穷举为64 s。`[verified: 原文Abstract、Figure 1、§4]`

## 局限与AdaptiveASTC关联

论文明确指出Alpha纹理、超像素大小参数敏感性及单子集编码竞争带来的限制。作者提出法线可按重建方向相似性分割，属于未来研究设想。`[verified: 原文§5“Future Work”“Limitations”]`

本项目可以参考全图结构辅助块编码决策的思想，尤其是不同贴图用途需要不同误差。该文没有验证ASTC整图footprint预测，也没有验证概率校准，其BPTC速度结果需要保留原格式与历史基线。`[opinion]`
