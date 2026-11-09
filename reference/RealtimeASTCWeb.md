---
title: "Real-Time Adaptive Scalable Texture Compression for the Web"
method_name: RealtimeASTCWeb
aliases: [RealtimeASTCWeb, astcrt]
authors: [Daniel Oom]
year: 2016
venue: Chalmers University of Technology master's thesis
arxiv: null
tags: [paper-note, texture-compression, astc, realtime]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "学位论文原文选读，Abstract、§4实现、§5.3性能、§7结论"
pdf_file: papers/RealtimeASTCWeb.pdf
---

# RealtimeASTCWeb

## 来源与阅读范围

阅读Chalmers硕士论文公开PDF中的摘要、编码器实现、性能测量和结论。该项是2016年学位论文。`[verified: 本地PDF封面、Abstract、§4、§5.3、§7]` 本机归档`papers/RealtimeASTCWeb.pdf`、[学校原件](https://odr.chalmers.se/server/api/core/bitstreams/2d6c0f22-1afb-41b4-913c-9ed1f092c8b7/content)

## 核心方法

astcrt针对浏览器渲染缓冲区的内存需求，以启发式替代分支定界搜索。论文实现聚焦4×4 ASTC，并分别处理颜色端点、权重、灰度／纯色和可选分区，降低编码开销。`[verified: 原文Abstract、§1.2、§4开头及子节]`

## 实验与证据

笔记本单线程Kodak测试中，astcrt报告24.2 M pixels/s，带分区版本17.7 M pixels/s，历史astcenc veryfast为0.369 M pixels/s。计时排除读写和初始化，通常预热后采50次，极慢编码器仅取一次。作者结论承认质量仍低于目标参考编码器，低端设备也可能达不到实时要求。`[verified: 原文§5.3、Table 5.3、§7]`

## 局限与AdaptiveASTC关联

这些数据来自2016年的编码器、编译器与设备，不能推算当前astcenc的速度差。其优化对象是给定footprint下的编码过程，本项目可把它作为减少内部搜索的历史路线，整图参数预测与概率校准还需要独立设计和评价。`[opinion]`

论文对计时边界的显式处理值得保留。未来比较单次最终压缩时，可以分别记录输入处理、预测、编码和输出耗时，以便判断节省发生在哪个环节。`[opinion]`
