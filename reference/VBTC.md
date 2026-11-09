---
title: "VBTC: GPU-Friendly Variable Block Size Texture Encoding"
method_name: VBTC
aliases: [VBTC]
authors: [Pavel Krajcevski, Abhinav Golas, Karthik Ramani, Michael C. Shebanow, Dinesh Manocha]
year: 2016
venue: Computer Graphics Forum 35(2) 409–418
doi: 10.1111/cgf.12842
arxiv: null
tags: [paper-note, texture-compression, variable-rate, hardware]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "Eurographics官方摘要、作者书目与2026综述结论；原文PDF未取得"
pdf_file: null
---

# VBTC

## 来源与阅读范围

阅读Eurographics数字图书馆对应条目的摘要，并核对作者书目。作者旧PDF地址404，Wiley PDF返回403，图书馆旧bitstream接口返回HTML，尚未取得有效论文PDF。`[verified: 官方集合页面VBTC条目Abstract；作者papers页面VBTC条目；本次下载与pdftotext输出]` [官方条目](https://diglib.eg.org/handle/10.1111/cgf12842)、[作者书目](https://www.krajcevski.com/papers.html)

## 核心方法

增加一级间接寻址，允许同一纹理内部采用不同块大小，把更多比特分配给细节区域，并复用冗余纹理信息。块大小与压缩方法从已有固定码率格式中组合，目标是减少纹理硬件的改动。`[verified: Eurographics官方VBTC Abstract]` [官方摘要所在集合](https://diglib.eg.org/collections/5ce3a81a-4c17-4274-b370-0ca455d95d5b)

## 实验与证据

摘要报告最高50%的能耗节省及画质改善。本次未读到实验正文，因此设备、能耗模型、基线与对应压缩率均未核实，该数字只按摘要声明保留。`[verified: 官方VBTC Abstract末句；本次阅读范围]`

## 局限与AdaptiveASTC关联

作者2026综述将其列为需要硬件解码器支持的图内可变块大小方向。`[verified: ASTCEncodingSurvey p.13 Conclusions，VBTC段]` [综述对应页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)

本项目可用它理解选择粒度从整图扩展到局部时的系统代价。现阶段整图选参优先，需要分别记录其与格式兼容性、额外间接寻址和运行时支持的关系。该论文摘要没有提供分类校准或Unity导入数据方案的证据。`[opinion]`
