---
title: "Neural Graphics Texture Compression Supporting Random Access"
method_name: NGTC / CNTC
aliases: [CNTC]
type: literature-note
year: 2024
venue: ECCV
arxiv: "2407.00021v2"
tags: [paper-note, texture-compression, neural-texture]
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§4、§5.1–5.2、§5.4"
pdf_file: papers/NGTC.pdf
---

# NGTC

## 来源与阅读范围

简读原文HTML的摘要、方法、主要实验和局限，文中方法也称CNTC。`[verified: 原文摘要、§4、§5.1–5.2、§5.4]` [原文HTML](https://arxiv.org/html/2407.00021v2) · 本机归档`papers/NGTC.pdf`

## 核心方法

不对称自编码器以卷积编码器生成瓶颈特征，构造一对量化网格。查询时以坐标和mip选择采样步长，将网格特征与位置编码送入带残差连接的全连接解码器，重建多通道texel。每个纹理集合训练专用模型。`[verified: 原文§4.1–4.4、图4]`

## 实验与证据

评估使用7组2048×2048、5–12通道材质，ASTC基线包含12×12、10×10、8×8和6×6。作者报告相对于其复现的NTC，PSNR曲线的BD-rate节省为40.8%。该数值的比较对象与数据集应一并保留。`[verified: 原文§5.1 Datasets、Compared methods、§5.2]`

## 局限与AdaptiveASTC关联

作者指出单分辨率网格在mip之间需要插值，可能产生aliasing，后续拟研究数据驱动插值。`[verified: 原文§5.4]` 该工作对项目的启发主要是检验跨通道、跨mip冗余与最终质量。将其质量增益迁移到现有ASTC分类器，需要另行设计表示或训练目标。`[opinion]`
