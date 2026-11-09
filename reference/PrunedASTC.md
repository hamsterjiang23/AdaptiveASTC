---
title: "Pruned Lightweight Encoders for Computer Vision"
method_name: PrunedASTC
aliases: [PrunedASTC]
authors: [Jakub Žádník, Markku Mäkitalo, Pekka Jääskeläinen]
year: 2022
venue: IEEE MMSP
arxiv: "2211.13137"
doi: 10.1109/MMSP55362.2022.9949477
tags: [paper-note, texture-compression, astc, computer-vision]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "arXiv v1原文简读，§III–VI、Tables I–III"
pdf_file: papers/PrunedASTC.pdf
---

# PrunedASTC

## 来源与阅读范围

阅读arXiv v1的摘要、简化编码器、实验设置、分类／分割结果和讨论。作者机构库下载返回403，改由arXiv取得有效PDF。`[verified: 本地PDF p.1、§III–VI；本次curl机构库403与arXiv下载输出]` 本机归档`papers/PrunedASTC.pdf`、[预印本](https://arxiv.org/abs/2211.13137)

## 核心方法

将ASTC配置空间剪到单一内部配置，采用5-bit端点、2-bit权重、8×5权重网格，支持8×8与12×12输入块。端点通过包围盒内缩选取，像素投影得到理想权重，再下采样及量化；ARM NEON加速主要循环。随后用压缩并解压的数据重新训练下游视觉网络，补偿编码伪影导致的任务性能损失。`[verified: 原文§III-A、§IV-A、§IV-B]`

## 实验与证据

ImageNet上的ShuffleNet V2在12×12 ASTC输入下，重训练前Top-1下降15.1–16.8个百分点，重训练后下降4.9–5.0个百分点。Cityscapes语义分割中，12×12重训练后的mIoU损失仍为4.0–4.4个百分点。Samsung S10单A76核上，2048×1024图像12×12编码5.8 ms，对比libjpeg-turbo编码13.3 ms。`[verified: 原文Table I、Table II、Table III及§V-B]`

## 局限与AdaptiveASTC关联

作者研究低延迟机器视觉，明确其用途不包含人类视觉验收。重训练恢复任务准确率与人眼不可分辨是不同的评价目标。`[verified: 原文§II-C“without the human in the loop”、§V-A]`

本项目可借鉴压缩域数据适配与固定格式下削减编码搜索的思路。它没有给出整图块大小分类校准方案，对本项目更直接的启发是显式记录训练输入域，并分别验证压缩质量与任务指标。`[opinion]`
