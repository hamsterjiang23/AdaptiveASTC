---
title: "Hardware Accelerated Neural Block Texture Compression with Cooperative Vectors"
method_name: CooperativeVectorNTC
aliases: [BCF1]
year: 2025
venue: High-Performance Graphics
arxiv: "2506.06040"
type: literature-note
tags: [paper-note, texture-compression, neural-material]
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§3.1、§4–7"
pdf_file: papers/CooperativeVectorNTC.pdf
---

# CooperativeVectorNTC

## 来源与阅读范围

简读原文HTML的摘要、BC1表示、运行时架构、性能结果及局限。`[verified: 原文摘要、§3.1、§4–7]` [原文HTML](https://arxiv.org/html/2506.06040) · 本机归档`papers/CooperativeVectorNTC.pdf`

## 核心方法

该工作扩展BC神经特征方案，将BC6特征改为BC1并调整分辨率布局，解码仍使用小MLP。运行时以tile组织像素，配合cooperative vectors调用矩阵乘硬件，处理同一工作组中材质网络不同的问题。`[verified: 原文§1 Our method、§3.1、§4]`

## 实验与证据

作者在Intel B580与RTX 4090、1920×1080输出上比较软件FMA和cooperative vectors。表2的耗时排除了visibility与lighting pass，网络宽度和配置会显著改变加速幅度。摘要的0.55 ms、28 MB对应B580上4K九通道材质及各向异性过滤的设定。`[verified: 原文摘要、§5 Performance、表2]`

## 局限与AdaptiveASTC关联

混合材质tile的全局原子分配还存在扩展性问题，共享MLP被列为后续方向。`[verified: 原文§6]` 本项目可以借此明确测量边界，分开列出模型预测成本与真实运行时成本。采用这类表示还涉及BC1特征、神经解码及矩阵硬件的集成。`[opinion]`
