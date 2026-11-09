---
title: "FasTC: Accelerated Fixed-Rate Texture Encoding"
method_name: FasTC
aliases: [FasTC]
authors: [Pavel Krajcevski, Adam Lake, Dinesh Manocha]
year: 2013
venue: ACM I3D
arxiv: null
tags: [paper-note, texture-compression, bptc, encoder]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "作者公开原文选读，Abstract、§3.5–3.7、§4、Figure 1"
pdf_file: null
---

# FasTC

## 来源与阅读范围

阅读作者公开的I3D 2013论文摘要、端点估计／细化、并行实现和实验设置。论文以BPTC进行实验。本地下载因连接中断未完成，有效原文通过作者在线PDF读取。`[verified: 原文p.137 Abstract、p.141 §3.5–4]` [作者PDF](https://gamma-web.iacs.umd.edu/FasTC/extra/paper.pdf)

## 核心方法

以颜色轴对齐包围盒估计块分区，用广义cluster fit近似端点，再通过模拟退火细化量化端点。FasTC-k的k控制退火步骤，通过工作队列实现多核负载分配。`[verified: 原文Abstract、§3.5、§3.6、§3.7]`

## 实验与证据

实验使用游戏纹理及Kodak图像，对照NVIDIA Texture Tools中的BC7压缩器和DirectX SDK实现。Figure 1中Unity Bootcamp的156张纹理，FasTC-64合计8.75分钟，历史NVIDIA BC7编码器为13.27小时。`[verified: 原文Figure 1、§4]`

## 局限与AdaptiveASTC关联

这里的速度比较绑定2013年BPTC编码器；其一般方法对其他端点格式的适用性，需要新的实现与测量。端点离散搜索中的初始近似质量及退火预算，也会改变最终质量／速度权衡。`[opinion]`

本项目可以参考“结构近似缩小搜索，再投入有限细化预算”的编码器设计思路。它没有建立整图footprint分类标签或置信度校准，不能直接支撑项目单次编码预测的质量保证。`[opinion]`
