---
title: "Evaluating Texture Compression Masking Effects Using Objective Image Quality Assessment Metrics"
method_name: TextureMaskingIQA
aliases: [TextureMaskingIQA]
authors: [Wesley N. Griffin, Marc Olano]
year: 2015
venue: IEEE Transactions on Visualization and Computer Graphics
doi: 10.1109/TVCG.2015.2429576
arxiv: null
tags: [paper-note, texture-compression, perceptual-quality]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "仅NIST官方摘要与书目信息，全文PDF未获取"
pdf_file: null
---

# TextureMaskingIQA

## 来源与阅读范围

本次读取NIST官方出版页的摘要和书目信息。该页Download Paper指向DOI，IEEE入口访问失败，未获取全文PDF，未核对全文方法细节或表格。论文刊于TVCG 21(8)，2015年8月。`[verified: NIST出版页Abstract、Citation、Volume、Issue、Published与Download Paper段；本次IEEE访问输出]` [官方摘要](https://www.nist.gov/publications/evaluating-texture-compression-masking-effects-using-objective-image-quality-assessment) · [DOI](https://doi.org/10.1109/TVCG.2015.2429576)

## 核心方法

摘要提出对最终渲染图评价纹理压缩。采样场景视点，分别渲染压缩纹理版本与同视点未压缩参考，使用感知误差指标比较，考虑几何映射以及diffuse、gloss、bump之间的掩蔽。`[verified: NIST出版页Abstract第2–3段]` [官方摘要](https://www.nist.gov/publications/evaluating-texture-compression-masking-effects-using-objective-image-quality-assessment)

## 实验与证据

摘要报告掩蔽影响渲染质量，且感知敏感度随贴图类型变化，可以在维持最终渲染质量时降低码率。摘要没有给出实验规模、具体数值及统计协议，本笔记只记录这些定性结论。`[verified: NIST出版页Abstract末段]` [官方摘要](https://www.nist.gov/publications/evaluating-texture-compression-masking-effects-using-objective-image-quality-assessment)

## 局限与AdaptiveASTC关联

适合作为法线与打包材质通道需结合渲染上下文评价的相关文献。项目的PSNR 35 dB经验线、MSAK各通道阈值、Unity导入后的测量域及分类校准效果，均需要自己的数据验证。由于目前仅摘要级阅读，不宜从此条目推断具体算法配置、相对2014年版本的增量或复用论文中的数值标准。`[opinion]`
