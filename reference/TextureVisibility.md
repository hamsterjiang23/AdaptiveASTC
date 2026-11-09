---
title: "Selecting texture resolution using a task-specific visibility metric"
method_name: TextureVisibility
aliases: [TextureVisibility]
authors: [Krzysztof Wolski, Daniele Giunchi, Shinichi Kinuwaki, Piotr Didyk, Karol Myszkowski, Anthony Steed, Rafał K. Mantiuk]
year: 2019
venue: Pacific Graphics / Computer Graphics Forum
doi: 10.1111/cgf.13871
arxiv: null
tags: [paper-note, texture-compression, quality-calibration]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "原文PDF简读，摘要、§6–8、§10–11与Table 1–2"
pdf_file: papers/TextureVisibility.pdf
---

# TextureVisibility

## 来源与阅读范围

已获取项目站公开PDF，简读任务专用可见性指标的构建、汇聚和评测。PDF首页标Pacific Graphics 2019、CGF卷38期7，页面另保留submitted字样。`[verified: TextureVisibility.pdf 首页及页脚、§6–8、§10–11]` 本机归档`papers/TextureVisibility.pdf` · [项目页](https://texture-metrics.mpi-inf.mpg.de/)

## 核心方法

目标是自动选择albedo和normal贴图分辨率。先由已有可见性指标生成密集预测，再借助少量任务专用感知实验调整为伪标签数据，重新训练CNN指标。§6研究从逐像素图汇聚到整图可见性，§7.1调整感知对比度到检测概率的映射，§7.3采用五折验证，同一3D对象/纹理只出现在一个fold。`[verified: TextureVisibility.pdf 摘要、§6、§7.1、§7.3]` [原文](https://texture-metrics.mpi-inf.mpg.de/files/wolski2019vis_tex_resolution.pdf)

## 实验与证据

Table 1中CNN-GP原始可见性图的Pearson相关系数为0.706，经任务调整的CNN-T-CNN-GP-P93为0.792。Table 2展示资产差异，TreasureBox两类贴图从1024降至512，论文内存统计从8 MB到2 MB，而King保持1024、8 MB。论文优化变量为分辨率。`[verified: TextureVisibility.pdf Table 1–2]` [原文](https://texture-metrics.mpi-inf.mpg.de/files/wolski2019vis_tex_resolution.pdf)

## 局限与AdaptiveASTC关联

可借鉴其用少量主观数据调整既有指标、对象隔离划分及检测概率汇聚的流程，针对Unity导入后的数据域建立小规模校准集。`[opinion]` 这里的任务专用可见性训练与块大小分类的概率calibration具有不同目标，不能直接据此宣称temperature scaling改善压缩合格率。若复用思路，仍需分别验证概率可信度、决策规则、真实编码质量与字节节省。`[opinion]`
