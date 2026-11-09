---
title: "Real-Time Neural Materials using Block-Compressed Features"
method_name: BCNeuralMaterials
aliases: [BCNeuralMaterials]
type: literature-note
year: 2024
venue: Eurographics / Computer Graphics Forum
arxiv: "2311.16121v2"
tags: [paper-note, texture-compression, neural-material]
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§4、§5.2、§6.1–6.2"
pdf_file: papers/BCNeuralMaterials.pdf
---

# BCNeuralMaterials

## 来源与阅读范围

简读2024年版本的摘要、BC特征设计、运行时实现与重建实验。`[verified: 原文摘要、§4、§5.2、§6.1–6.2]` [原文HTML](https://arxiv.org/html/2311.16121v2) · 本机归档`papers/BCNeuralMaterials.pdf`

## 核心方法

作者将神经特征直接参数化为BC6块的端点、索引和partition，在训练前向过程中模拟BC6解码。学到的特征可导出为常规BC6纹理，用硬件三线性过滤后送入轻量MLP，重建连续位置及尺度的材质参数。`[verified: 原文§4.1–4.3、§5.2]`

## 实验与证据

实验含19种Poly Haven材质。表2报告BCf-1K为1.77 MB、31.83 dB，2048分辨率ASTC 12×12为2.11 MB、30.48 dB。这里比较的是不同表示下的材质集合，PSNR先汇总各mip和材质的MSE再换算。`[verified: 原文§6.1、表2及其标题]`

## 局限与AdaptiveASTC关联

训练需要逐材质优化特征与MLP，渲染时执行解码shader。BC6存储的是神经特征，导出后还需网络恢复原材质通道。`[verified: 原文§5、§6.1 Model configuration]` 对本项目有价值的是将压缩及过滤纳入训练、按mip汇总指标的做法。它也提醒我们分别评价特征误差和最终材质重建误差。`[opinion]`
