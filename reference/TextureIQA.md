---
title: "Objective Image Quality Assessment of Texture Compression"
method_name: TextureIQA
authors: [Wesley N. Griffin, Marc Olano]
year: 2014
venue: I3D
arxiv: null
doi: null
tags: [paper-note, texture-compression, perceptual-quality]
type: literature-note
status: skim
aliases: [TextureIQA]
created: 2026-11-09
read_scope: "原文简读，摘要、§3方法、§4结果、§5结论与Table 2"
pdf_file: papers/TextureIQA.pdf
---

# TextureIQA

## 来源与阅读范围

已获取NIST公开PDF，简读摘要、§3–5和Table 2，页码按论文印刷页119–126定位。`[verified: TextureIQA.pdf p.119、§3–5、Table 2]` 本机归档`papers/TextureIQA.pdf` · [NIST书目](https://www.nist.gov/publications/objective-image-quality-assessment-texture-compression)

## 核心方法

作者将评价对象移到最终渲染图。对场景采样多个视点，分别使用原始纹理和压缩纹理渲染，再计算颜色误差与SSIM，以覆盖几何映射和diffuse、gloss、bump组合造成的掩蔽效应。单模型采用包围球上的Sobol视点采样，单一视角不能覆盖视点间变化。`[verified: TextureIQA.pdf §3、§3.1、§5]` [原文](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=914900)

## 实验与证据

Table 2比较Fire Hydrant、Urban Guy、Japanese Castle，包含NVTT/BC和ASTC 4×4、8×8、12×12，并区分所有纹理同时压缩与仅某类贴图压缩。Urban Guy在所有贴图压缩时的视点平均SSIM从ASTC 8×8的0.9833降为12×12的0.9639。Figure 9展示高频bump对diffuse色带的掩蔽，作者据此主张结合贴图类别和渲染上下文评估压缩。`[verified: TextureIQA.pdf Table 2、Figure 9、§4.3、§5]` [原文](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=914900)

## 局限与AdaptiveASTC关联

这些数值属于论文的模型、采样视点与编码设置，不能直接变成项目的通用合格阈值。`[opinion]` 对AdaptiveASTC，它支持增加最终渲染质量验证，并为法线、颜色及打包材质通道分别设计评价口径。分类校准仍需检验实际质量违规率。Unity导入后数据应作为项目单独记录的测量域，本文没有提供该数据管线。`[opinion]`
