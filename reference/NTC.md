---
title: "Random-Access Neural Compression of Material Textures"
method_name: NTC
aliases: [NTC]
type: literature-note
year: 2023
venue: SIGGRAPH / ACM TOG
doi: 10.1145/3592407
arxiv: "2305.17105"
tags: [paper-note, texture-compression, neural-texture]
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§4、§6.4–6.5"
pdf_file: papers/NTC.pdf
---

# NTC

## 来源与阅读范围

简读arXiv原文HTML的摘要、表示方法、质量和性能实验。`[verified: 原文摘要、§4、§6.4–6.5]` [原文HTML](https://arxiv.org/html/2305.17105) · 本机归档`papers/NTC.pdf`

## 核心方法

NTC联合压缩同一材质的多张属性贴图及mipmap链，用量化特征金字塔和逐材质优化的小型MLP表示。查询纹理坐标和LOD时，从两种分辨率网格采样特征，拼接位置编码，再解码各通道。训练直接优化特征及解码器。`[verified: 原文§4、图4]`

## 实验与证据

论文同时进行近似同存储、同质量比较与最终渲染比较。表4在RTX 4090上报告4K材质、3840×2160输出时，NTC各配置的材质渲染耗时1.15–1.92 ms，传统BC方案0.49 ms，过滤方式分别涉及随机过滤与三线性过滤。`[verified: 原文§6.4、§6.5.2、表4]`

压缩耗时也需计入成本。作者报告自定义CUDA训练比其PyTorch实现约快一个数量级，并讨论压缩器质量preset会改变传统BC编码成本。`[verified: 原文§6.5.1、图11]`

## 局限与AdaptiveASTC关联

部署需要神经解码及相应过滤实现，跨材质通道的联合表示是收益来源之一。`[verified: 原文§4、§5.3]` 项目可借鉴“纹理误差＋最终渲染误差＋编码／解码成本”的评价设计。若研究仍采用逐图标准ASTC选参，应将这类运行时表示的实验成本单独列出。`[opinion]`
