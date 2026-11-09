---
title: "Neural Block Compression: Variable Bitrates Feature Blocks for Texture Representation"
method_name: NBC
aliases: [NBC]
type: literature-note
arxiv: null
year: 2025
venue: AAAI
doi: 10.1609/aaai.v39i7.32738
tags: [paper-note, texture-compression, neural-texture]
status: skim
created: 2026-11-09
read_scope: "原文简读，摘要、§3–5、表3–4与结论"
pdf_file: papers/NBC.pdf
---

# NBC

## 来源与阅读范围

已简读AAAI正式论文的摘要、方法、实现、实验表格与结论，保留原文PDF。`[verified: 原文pp.6878–6884]` [正式页面](https://ojs.aaai.org/index.php/AAAI/article/view/32738) · 本机归档`papers/NBC.pdf`

## 核心方法

NBC把颜色域的块压缩思想迁移到神经特征域，联合优化多分辨率特征网格和轻量MLP解码器。粗尺度网格保存高比特基础特征，细尺度保存低比特残差，通过插值、相加和特征复用重建纹理及mipmap。`[verified: 原文§3.2–3.4、§4.1，图2]`

默认四层特征采用8、4、2、1 bit量化。这里的variable bitrates指不同特征mip层的量化位数，论文明确区分了这种定义与按输入内容调整码率的方案。`[verified: 原文§2.3、§3.3，表2]`

## 实验与证据

表3在约0.05、0.1、0.2、0.5和1.0 BPPC下比较PSNR、SSIM、LPIPS和FLIP。例如0.101 BPPC时NBC报告33.02 dB，0.099 BPPC的NTC为31.53 dB。BPPC是每像素每通道比特数，比较包含整组纹理及mipmap。`[verified: 原文§5 Metrics、§5.1，表3]`

表4显示改变位数分配会同时影响质量和存储，8-4-2-1配置为0.101 BPPC、33.02 dB，2-2-2-2配置为0.141 BPPC、32.36 dB。两组结果仅代表论文协议。`[verified: 原文§5.3，表4(a)]`

## 局限与AdaptiveASTC关联

论文表示需要训练特征和MLP，并在解码阶段执行神经网络。它为学习表示设计了新的码率分配，项目采用它需要额外的训练及运行时集成。`[verified: 原文§3–4]` AdaptiveASTC可以借鉴其同码率／同质量双向比较，以及跨通道、跨mipmap的统计口径。针对现有ASTC的分类校准效果仍需要独立实验。`[opinion]`
