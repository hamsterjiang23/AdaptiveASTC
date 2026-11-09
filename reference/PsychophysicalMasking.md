---
title: "A Psychophysical Evaluation of Texture Compression Masking Effects"
method_name: PsychophysicalMasking
aliases: [PsychophysicalMasking]
authors: [Guillaume Lavoué, Michael Langer, Adrien Peytavie, Pierre Poulin]
year: 2019
venue: IEEE Transactions on Visualization and Computer Graphics
doi: 10.1109/TVCG.2018.2805355
arxiv: null
tags: [paper-note, texture-compression, psychophysics]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "作者版PDF简读，摘要、§3–4、§6与Figure 13"
pdf_file: papers/PsychophysicalMasking.pdf
---

# PsychophysicalMasking

## 来源与阅读范围

已获取作者版PDF，简读实验刺激、2AFC协议、掩蔽分析和讨论。作者版标注2018年版权，按2019年TVCG卷期归档。`[verified: PsychophysicalMasking.pdf 首页、§3–4、§6；DOI出版记录卷25期2]` 本机归档`papers/PsychophysicalMasking.pdf` · [DOI](https://doi.org/10.1109/TVCG.2018.2805355)

## 核心方法

研究分别压缩diffuse或normal贴图，再与不同内容的另一类贴图组合，在平面Lambertian表面及不同光向下渲染。使用ASTC多种块大小和128²刺激，两个实验分别评估normal掩蔽diffuse伪影及其反向作用。2AFC任务要求观察者从两个测试图中找出与参考不同的图，采用校准显示器、固定观察距离与暗室条件。`[verified: PsychophysicalMasking.pdf §3.1–3.2]` [原文](https://perso.liris.cnrs.fr/guillaume.lavoue/revue/TVCG2018.pdf)

## 实验与证据

§6指出某些无掩蔽条件下6×6也有可见伪影，另一些条件下12×12伪影完全被掩蔽。Figure 13中直接在贴图上用PSNR预测两组合并数据的伪影可见性，AUC约0.60。将感知指标用于渲染图显著改善预测，说明只看独立贴图会丢失上下文。`[verified: PsychophysicalMasking.pdf §6、Figure 13]` [原文](https://perso.liris.cnrs.fr/guillaume.lavoue/revue/TVCG2018.pdf)

## 局限与AdaptiveASTC关联

原文§6说明其贴图采用传统实时着色工作流，任意3D场景及未知渲染条件下的感知评价仍复杂。`[verified: PsychophysicalMasking.pdf §3.1.1、§6 Limitation段]` 这篇文献与按质量选ASTC块大小直接相关，可用于设计法线与颜色的独立/联合验收。将PSNR 35 dB视为项目工作标准仍可做工程基线，但普遍“人眼不可分辨”的表述需要改成具体测试条件下的结论。分类calibration应以最终质量违规率评价。`[opinion]`
