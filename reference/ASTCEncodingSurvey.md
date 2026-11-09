---
title: "An Analytical Survey of ASTC Encoding Techniques"
method_name: ASTCEncodingSurvey
aliases: [ASTCEncodingSurvey]
authors: [In-hyuk Jeong, Jae-Ho Nah]
year: 2026
venue: IEEE Computer Graphics and Applications
doi: 10.1109/MCG.2026.3732851
arxiv: null
tags: [paper-note, texture-compression, astc, survey]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "作者预印本选读，p.1摘要、p.8实验设置与编码器、p.12块大小、p.13结论、p.13–14书目"
pdf_file: papers/ASTCEncodingSurvey.pdf
---

# ASTCEncodingSurvey

## 来源与阅读范围

阅读作者公开的14页预印本中的摘要、实验设置、其他编码器、块大小选择与结论，并核对37项书目。PDF页脚列出正式版本DOI。`[verified: 本地PDF p.1、8、12–14及页脚]` 本机归档`papers/ASTCEncodingSurvey.pdf`、[作者PDF](https://nahjaeho.github.io/papers/CGA26_paper.pdf)、[正式版本](https://doi.org/10.1109/MCG.2026.3732851)

## 核心方法

综述围绕astcenc解释分区、颜色编码、权重网格及块大小的质量／速度权衡，并分别讨论编码器加速、逐图选块、RGBM、硬件解码和神经网络用途。文中将TexNN的P-NN分区预测与DEM-NN端点／权重模式预测，与目标PSNR驱动的整图块大小搜索分开介绍。`[verified: 原文p.1 Abstract、p.8“Other encoders”、p.12“Block size configuration”]`

## 实验与证据

实验设置采用astcenc v5.7、QuickETC2数据集64张RGB／RGBA图片，比较4×4、6×6、8×8，以PSNR和FLIP v1.6评价质量。平台为Windows 10、Ryzen 5 5600X。综述同时比较历史ISPC Texture Compressor，并明确其他编码器的特性与支持范围。`[verified: 原文p.8“Experimental setup”、Table 6]`

## 局限与AdaptiveASTC关联

这篇文献适合作为技术地图与候选基线入口。其选定图片、三种footprint和平台上的观察，需要在本项目资产、10×10／12×12候选及Unity处理配置中重新验证。综述对其他论文的介绍只能用作二手证据。`[opinion]`

原文p.12说明已有方法迭代寻找目标PSNR，2022方案以fastest试探后thorough最终编码，2023方案在astcenc内部采样部分像素评价块大小。当前分类校准路线可与这些目标质量搜索方法比较选参成本、质量违规和字节变化。`[verified: 原文p.12“Block size configuration”]` `[opinion]`
