---
title: "Thread-Efficient Decoding for Neural Texture Compression"
method_name: ThreadEfficientNTC
aliases: [ThreadEfficientNTC]
authors: [Janarbek Matai, Sho Ikeda, Lukasz Lipski, Takahiro Harada]
year: 2026
venue: arXiv preprint
arxiv: 2608.27888v1
doi: null
tags: [paper-note, texture-compression, gpu-decoding]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§2–5、Table 2、Table 5–6"
pdf_file: papers/ThreadEfficientNTC.pdf
---

# ThreadEfficientNTC

## 来源与阅读范围

简读arXiv v1原文HTML的方法、质量结果、微基准和讨论，版本日期2026-08-28。本记录按预印本归档。`[verified: arXiv 2608.27888v1题头、§2–5]` [原文HTML](https://arxiv.org/html/2608.27888v1) · 本机归档`papers/ThreadEfficientNTC.pdf`

## 核心方法

论文研究同一GPU wave访问多个神经纹理解码网络引起的执行分歧。每张纹理保留独立编码表示，同一组纹理共享MLP解码器。先提取CLIP特征并k-means分组，训练时逐步冻结解码器，让独立编码表示继续适应各纹理。共享程度用于平衡重建质量与网络切换成本。`[verified: arXiv 2608.27888v1 §2–3、Algorithm 1–2]` [原文](https://arxiv.org/html/2608.27888v1)

## 实验与证据

586张Polyhaven纹理的平均PSNR，独立解码基线为34.07 dB，聚类共享为33.18 dB，全部共享单解码器为32.61 dB。RX 9070 XT上的HLSL微基准以5或10个解码器均匀分布于wave，Table 6在1.6 GHz、1024²输出时，共享解码耗时207 μs，非共享WMMA为1950 μs。这是特定解码微基准。`[verified: arXiv 2608.27888v1 §4.1、Table 2、§4.4、Table 5–6]` [原文](https://arxiv.org/html/2608.27888v1)

## 局限与AdaptiveASTC关联

作者把聚类数量敏感性及低层纹理特征分组列为后续工作。`[verified: arXiv 2608.27888v1 §5]` 对AdaptiveASTC，该工作主要解释神经运行时的部署代价，不能据此推算ASTC块大小预测或编码加速。共享解码的质量损失也提醒评价压缩效率时同时报告重建质量与GPU耗时，微基准倍数不宜直接写成完整游戏帧率收益。`[opinion]`
