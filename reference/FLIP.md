---
title: "FLIP: A Difference Evaluator for Alternating Images"
method_name: FLIP
authors: [Pontus Andersson, Jim Nilsson, Tomas Akenine-Möller, Magnus Oskarsson, Kalle Åström, Mark D. Fairchild]
year: 2020
venue: HPG / PACMCGIT
doi: 10.1145/3406183
arxiv: null
tags: [paper-note, texture-compression, perceptual-quality]
type: literature-note
status: skim
aliases: [FLIP]
created: 2026-11-09
read_scope: "原文简读，摘要、§1–2、§6.2、§7及作者页勘误"
pdf_file: papers/FLIP.pdf
---

# FLIP

## 来源与阅读范围

已获取作者版PDF，简读摘要、目标与局限、用户研究和结论，另核对作者页的勘误与汇聚建议。PDF首页注明个人使用和禁止再分发，本地文件用于阅读归档。`[verified: FLIP.pdf p.15:1版权段、§1–2、§6.2、§7；作者页Hindsight与Errata段]` 本机归档`papers/FLIP.pdf` · [作者页](https://research.nvidia.com/publication/flip)

## 核心方法

FLIP针对参考图与测试图在同一位置交替显示时的可见差异，输出逐像素误差图。模型结合颜色、边缘和点状特征，考虑观察距离及显示器像素大小对应的视角分辨率。它是有参考图的质量评价器。`[verified: FLIP.pdf §1–2]` [原文](https://research.nvidia.com/sites/default/files/node/3260/FLIP_Paper.pdf)

## 实验与证据

§6.2让42名参与者评价21对图像上十种指标的误差图，其中11对为渲染图、10对为自然图。图像每0.5秒交替，参与者按误差图与主观差异的位置及幅度一致性评分。研究经网络进行，未统一显示器校准与精确照明条件。作者报告FLIP在该协议下平均评分最高。`[verified: FLIP.pdf §6.2、Figure 12–13、§7]` 作者后来建议用平均FLIP值汇总，替代原论文提倡的加权中位数。`[verified: 作者页Hindsight段]` [原文](https://research.nvidia.com/sites/default/files/node/3260/FLIP_Paper.pdf) · [作者更新](https://research.nvidia.com/publication/flip)

## 局限与AdaptiveASTC关联

原始2020版本处理LDR输入，§2明确指出不能检测视觉掩蔽，可能高估被其他内容遮蔽的差异。`[verified: FLIP.pdf §2、Figure 11；作者页HDR说明段]` AdaptiveASTC可将FLIP作为渲染图辅助指标，并保留局部误差热图与观察条件。它不能独自给出法线/MSAK通道的统一阈值或证明PSNR 35 dB必然不可分辨，阈值仍需项目样本和主观验收建立。`[opinion]`
