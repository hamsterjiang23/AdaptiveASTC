---
title: "Differentiable Block Compression for Neural Texture"
method_name: DBC
aliases: [Differentiable BC]
year: 2025
venue: Eurographics Symposium on Rendering Symposium Track
doi: 10.2312/sr.20251199
arxiv: null
type: literature-note
tags: [paper-note, texture-compression, differentiable-compression]
status: skim
created: 2026-11-09
read_scope: "原文PDF简读，摘要、§3–4、§5.1–5.2、§6.1–6.2"
pdf_file: papers/DBC.pdf
---

# DBC

## 来源与阅读范围

已取得12页原文PDF，简读摘要、框架、可微编码、配置选择、实验及局限。`[verified: 原文pp.3–8、pp.10–11；pdfinfo输出Pages: 12]` [正式页面](https://diglib.eg.org/items/9dfee807-eeec-485a-82a6-f466268d28c2) · 本机归档`papers/DBC.pdf`

## 核心方法

DBC把块编码及解码纳入神经纹理的优化，目标包括后续模型损失。框架使用可微编码、基于压缩误差的随机配置采样，以及Mixture of Partitions降低多partition的计算量。研究重点为BC6和BC7。`[verified: 论文Abstract；原文p.3 §3.1.2]`

可微编码以PCA／SVD拟合块内主方向，对端点和插值系数量化并采用STE传播梯度。BC6实现暂省略端点量化，训练完成后通过NVTT输出压缩格式。`[verified: 原文p.4 §3.2、§4.1]`

## 实验与证据

原文p.8包含MBD系数纹理及RGBM实验。表2的Scene 0在等存储设定下，DBC为23.79 dB、FLIP 0.0297，直接BC为18.11 dB、0.061。该结果对应MBD场景。`[verified: 原文p.8 MBD Experiments、表2]` [原文PDF](https://diglib.eg.org/bitstream/handle/10.2312/sr20251199/sr20251199.pdf)

## 局限与AdaptiveASTC关联

作者明确说明，直接压缩普通albedo时，DBC质量一般不会优于标准块压缩器。ASTC扩展被列为后续工作，涉及更多partition、可变块大小及weight grid等结构。`[verified: 原文§6.1 Compression of General Textures、§6.2 Support for More Texture Block Compression Formats]`

这一框架的价值在于使编码误差服从最终任务损失，项目可据此研究法线／MSAK的用途相关评价。将其配置选择机制用于ASTC，仍需实现对应编码结构并验证质量与开销。`[opinion]` 作者代码包含BC7神经材质运行示例。`[verified: 作者代码README Run示例]` [作者代码](https://github.com/Ubpa/DBC)
