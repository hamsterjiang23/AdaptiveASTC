---
title: "Image-GS: Content-Adaptive Image Representation via 2D Gaussians"
method_name: ImageGS
aliases: [Image-GS]
year: 2025
venue: SIGGRAPH Conference Papers
doi: 10.1145/3721238.3730596
arxiv: "2407.01866v2"
type: literature-note
tags: [paper-note, texture-compression, gaussian-representation]
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§3.1–3.3、§4.4–4.5"
pdf_file: papers/ImageGS.pdf
---

# ImageGS

## 来源与阅读范围

简读SIGGRAPH 2025版本的原文HTML，关注二维高斯表示和纹理比较。`[verified: 原文首页会议信息、摘要、§3、§4.4–4.5]` [原文HTML](https://arxiv.org/html/2407.01866v2) · 本机归档`papers/ImageGS.pdf`

## 核心方法

Image-GS用显式、带颜色的各向异性二维高斯表示图像，按内容初始化并根据误差渐进增加表达能力。像素查询先定位tile，再选择局部top-K高斯并归一化权重，支持随机访问和连续质量控制。`[verified: 原文§3.1–3.3、图1]`

## 实验与证据

纹理实验比较19组纹理集合。由于BC1、BC7及ASTC的最低码率限制，同码率比较会取较低mipmap并双线性放大回2K评估，解读图6必须保留这个协议。原文报告0.059 bppc时平均PSNR为32.20±4.06 dB。`[verified: 原文图6标题、§4.5]`

## 局限与AdaptiveASTC关联

作者指出自然图像上的表现弱于风格化图像，并讨论高斯预算及像素级噪声的影响。`[verified: 原文§4.3末段]` 对项目可借鉴的是内容自适应与预算／失真曲线，采用高斯表示则需要专用查询和渲染实现。对比固定8×8时，应保留一致的参考分辨率并单列降采样的贡献。`[opinion]`
