---
title: "Addition of an adaptive block-size determination feature to astcenc, the reference ASTC encoder"
method_name: AdaptiveASTCEncoder
aliases: [AdaptiveASTCEncoder]
authors: [Jae-Ho Nah]
year: 2023
venue: Software Impacts 17 100569
doi: 10.1016/j.simpa.2023.100569
arxiv: null
tags: [paper-note, texture-compression, astc, parameter-selection]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "出版社摘要与Highlights、配套仓库README L1–8、作者2026综述p.12；论文PDF未取得"
pdf_file: null
---

# AdaptiveASTCEncoder

## 来源与阅读范围

本次读到出版社摘要／Highlights和配套代码README开头，另读作者后续综述p.12的介绍。出版社正文与PDF接口返回403，作者主页提供的链接未取得原始论文PDF，因此按摘要及软件说明简读记录。`[verified: 出版社Abstract与Highlights；配套README L1–8；本次curl pdfft输出403]` [论文入口](https://doi.org/10.1016/j.simpa.2023.100569)、[配套仓库](https://github.com/SoftwareImpacts/SIMPAC-2023-337)

## 核心方法

在修改版astcenc中加入按目标PSNR选择块大小的功能。调用时给出的块大小是搜索初值，`-dbtarget`决定目标，例如`astcenc -cl example.png example.astc 6x6 -medium -dbtarget 40`。软件说明称输出PSNR接近或高于目标。`[verified: 配套README L1–8；论文Abstract]` [README原文](https://raw.githubusercontent.com/SoftwareImpacts/SIMPAC-2023-337/master/README.md)

作者2026综述介绍，该版本在选块评价中仅使用部分像素，从而减少代价，并解除早期方法对编码模式的限制。这是综述转述。`[verified: ASTCEncodingSurvey原文p.12“Block size configuration”]` [综述PDF](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=12)

## 实验与证据

摘要说明其目标是减轻逐贴图手动平衡画质与体积的负担。已读材料没有足够的实验表与逐图结果，故此笔记没有摘录压缩时间、达标率或体积改善数值。`[verified: 论文Abstract；本次阅读范围记录]`

## 局限与AdaptiveASTC关联

这是项目可采用的目标质量搜索基线候选，实施前需要固定分支／版本并检查真实质量与耗时。其“接近目标”的描述也需要转换为本项目明确的达标比较规则。预测后单次最终编码的收益，可相对于该搜索流程衡量。`[opinion]`
