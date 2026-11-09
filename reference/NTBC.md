---
title: "Neural Texture Block Compression"
method_name: NTBC
aliases: [NTBC]
type: literature-note
year: 2024
venue: MAM-MANER
doi: 10.2312/mam.20241178
arxiv: "2407.09543v2"
tags: [paper-note, texture-compression, neural-texture]
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§1、§3.2、§4.1–4.4"
pdf_file: papers/NTBC.pdf
---

# NTBC

## 来源与阅读范围

简读原文2024年10月arXiv v2的摘要、用途、方法和实验。MAM正式四页版摘要写最多约45%存储减少，v2扩展版写约70%，本笔记的实验数字按v2记录。`[verified: arXiv v2摘要、§1、§3.2、§4；MAM正式页Abstract及Pages字段]` [原文HTML](https://arxiv.org/html/2407.09543v2) · [正式版本](https://diglib.eg.org/items/c6e1f8c5-1530-47e5-a2bc-1adc3c57c39b) · 本机归档`papers/NTBC.pdf`

## 核心方法

NTBC逐材质训练端点网络和颜色网络，再根据预测颜色与调色板的距离生成索引，输出BC1／BC4块。其神经模型作为磁盘侧紧凑表示，在加载阶段重建标准BC纹理并复制到VRAM，运行时继续使用现有BC采样。`[verified: 原文§1、§3.2、§4.4 Inference]`

## 实验与证据

实验为10组4096²材质，在RX 7900 XT上比较Compressonator及朴素神经方案。MetalPlates013中六张贴图的块重建耗时，保守方案49.84 ms、激进方案27.31 ms。摘要所述最多约70%的节省针对存储占用。`[verified: 原文摘要、§4.2、§4.4、表1]`

## 局限与AdaptiveASTC关联

保守方案分别建模RGB与单通道纹理，激进方案共用模型以降低存储，但增加联合训练复杂度。`[verified: 原文§4.1]` 项目评价可沿用其存储、加载、VRAM分列的口径。若扩展到ASTC，仍需解决复杂块模式、partition及端点编码的学习问题。`[opinion]`
