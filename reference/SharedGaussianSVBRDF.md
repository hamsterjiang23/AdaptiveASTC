---
title: "Compact Representation of Mipmapped SVBRDFs via Shared Gaussians"
method_name: SharedGaussianSVBRDF
aliases: [GTC, SharedGaussianSVBRDF]
authors: [Fengdi Zhang, Haocheng Ren, Qing Luo, Yaqing Li, Jibing Lou, Hongwei Li]
year: 2026
venue: arXiv preprint
arxiv: 2607.27943v1
doi: null
tags: [paper-note, texture-compression, gaussian-representation]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§3–5、Table 1–2"
pdf_file: papers/SharedGaussianSVBRDF.pdf
---

# SharedGaussianSVBRDF

## 来源与阅读范围

简读arXiv v1原文HTML的摘要、方法、结果与局限，版本日期2026-07-30。本记录按预印本归档。`[verified: arXiv 2607.27943v1题头、§3–5]` [原文HTML](https://arxiv.org/html/2607.27943v1) · 本机归档`papers/SharedGaussianSVBRDF.pdf`

## 核心方法

Gaussian Texture Compression以共享2D高斯表示SVBRDF的多通道、多mip贴图。每个高斯分离空间支撑与材质通道特征，粗mip高斯复用于更细层级，从残差初始化新增高斯，结合分组稀疏正则及剪枝减少冗余。运行时先建立tile关联高斯列表，再按查询位置累加局部高斯，实现非神经随机访问解码。`[verified: arXiv 2607.27943v1 §3.2–3.4]` [原文](https://arxiv.org/html/2607.27943v1)

## 实验与证据

评测包含20组SVBRDF，最高层为2048²，分别按texel加权和各mip等权汇聚质量。Table 1中GTC在0.299 bppc达到43.11 dB，ASTC在0.407 bppc达到41.10 dB，但该点ASTC的FLIP为0.0214，优于GTC的0.0247。指标优势因此并不一致。`[verified: arXiv 2607.27943v1 §4.1、Table 1]` [原文](https://arxiv.org/html/2607.27943v1)

## 局限与AdaptiveASTC关联

论文承认高频随机纹理、重复结构和逐资产优化成本的限制。`[verified: arXiv 2607.27943v1 §5]` 对AdaptiveASTC，可借鉴多mip评价、材质通道联合分析和不同指标冲突的呈现方式。采用高斯表示需要自己的访问和解码流程，项目若维持标准ASTC输出，应将它作为不同部署条件下的相关路线。本文没有验证项目分类校准或Unity导入管线。`[opinion]`
