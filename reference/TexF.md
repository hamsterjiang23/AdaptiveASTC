---
title: "Beyond UV Mapping: Mesh Texture Compression via Surface-Aligned Texture Fields"
method_name: TexF
aliases: [TexF, 3DNTC]
authors: [Jianqiang Wang, Junhui Hou, Siyu Ren, Weiyao Lin, Wenping Wang]
year: 2026
venue: arXiv preprint
arxiv: 2609.23606v2
doi: null
tags: [paper-note, texture-compression, uv-free]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§III-D、§IV-D、§IV-F与Table III"
pdf_file: papers/TexF.pdf
---

# TexF

## 来源与阅读范围

简读arXiv v2原文HTML的摘要、GPU驻留压缩方法、评测与局限，版本日期2026-10-16。本记录按预印本归档。`[verified: arXiv 2609.23606v2题头、§III-D、§IV-D、§IV-F]` [原文HTML](https://arxiv.org/html/2609.23606v2) · 本机归档`papers/TexF.pdf`

## 核心方法

TexF将属性组织在网格表面相交的稀疏体素中，利用局部3D关系。存储码流可复用3D属性编码器。GPU驻留版本3DNTC使用两层INT4哈希特征和FP16 MLP，在表面位置插值特征后解码，并用多视图渲染监督进一步优化。GPU载荷包含量化潜变量表和网络参数。`[verified: arXiv 2609.23606v2 摘要、§III-D]` [原文](https://arxiv.org/html/2609.23606v2)

## 实验与证据

Table III中，3DNTC相对UV-Source/ASTC在MPEG和AOM基准的匹配PSNR平均驻留内存BD-BR分别为−33.2%和−31.0%，该口径计入UV映射载荷。平均帧时分别10.8和23.1 ms，逐资产编码约17和28分钟。ASTC渲染帧时未测，因为使用的RTX A6000不原生支持ASTC。`[verified: arXiv 2609.23606v2 §IV-D、Table III]` [原文](https://arxiv.org/html/2609.23606v2)

## 局限与AdaptiveASTC关联

作者指出部分高效UV资产更有利于UV编码，粗体素可能导致邻近表面属性混合，原生TexF渲染尚缺完整纹理过滤功能。`[verified: arXiv 2609.23606v2 §IV-F]` AdaptiveASTC可参考其完整驻留载荷和渲染质量统计方式。TexF需要改变表示、训练和采样流程，归入跨表示研究更合适，其内存收益不能作为同一Unity导入设置下ASTC选参的收益。`[opinion]`
