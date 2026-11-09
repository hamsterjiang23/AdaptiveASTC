---
title: "Variable-Rate Texture Compression: Real-Time Rendering with JPEG"
method_name: JPEGTextures
aliases: [JPEG Textures]
year: 2026
venue: Eurographics / Computer Graphics Forum
doi: 10.1111/cgf.70338
arxiv: "2510.08166v2"
type: literature-note
tags: [paper-note, texture-compression, variable-rate]
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§4、§5.3、§6.1–6.2"
pdf_file: papers/JPEGTextures.pdf
---

# JPEGTextures

## 来源与阅读范围

简读arXiv修订版的摘要、渲染流程及评价。正式期刊页记录首次发表为2026年4月25日。`[verified: 原文摘要、§4–6；Wiley正式页First published]` [原文HTML](https://arxiv.org/html/2510.08166v2) · [正式版本](https://onlinelibrary.wiley.com/doi/10.1111/cgf.70338) · 本机归档`papers/JPEGTextures.pdf`

## 核心方法

延迟渲染先记录UV、材质及mip，标记当前帧所需的JPEG MCU，只解码缺失块，并跨帧缓存已解码结果。索引表、并行Huffman解码和block cache共同支持按需访问。`[verified: 原文§4、§5.1–5.2、图4]`

## 实验与证据

论文报告索引和DC重编码的实际额外开销约0.17 bit/pixel，质量评估把这部分计入JPEG，并使用PSNR、FLIP、SSIM和LPIPS。性能测试包括Sponza与Graffiti，在RTX 4090、桌面1080p及VR配置上测量。`[verified: 原文§5.3、§6.1–6.2、表3]`

## 局限与AdaptiveASTC关联

实现当前支持JPEG 4:2:0，性能随质量、缓存命中及mipmap使用变化。`[verified: 原文§6.1、§6.2.1]` 项目可参考其把额外索引、缓存和解码时间纳入完整成本的做法。采用这种表示涉及渲染管线重构，选参校准实验应单独定义部署范围。`[opinion]`
