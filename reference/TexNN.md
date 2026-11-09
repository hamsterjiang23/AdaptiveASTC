---
title: "TexNN: Fast Texture Encoding Using Neural Networks"
method_name: TexNN
aliases: [TexNN]
authors: [Srihari Pratapa, Tom Olson, Alex Chalfin, Dinesh Manocha]
year: 2019
venue: Computer Graphics Forum 38(1) 328–339
doi: 10.1111/cgf.13534
arxiv: null
tags: [paper-note, texture-compression, astc, neural-network]
type: literature-note
status: skim
created: 2026-11-09
read_scope: "出版社在线摘要及可检索正文§3.2–3.4、§4和Tables 1–3；PDF访问失败"
pdf_file: null
---

# TexNN

## 来源与阅读范围

简读出版社在线原文摘要、方法和实验段落。正式卷期为2019年，在线首发为2018年8月9日。PDF下载返回403，故未保存原文PDF。`[verified: 出版社页面“First published”“How to cite”及§3–4；本次PDF访问输出]` [论文原文入口](https://onlinelibrary.wiley.com/doi/abs/10.1111/cgf.13534)

## 核心方法

用神经网络分类替代昂贵的块内部编码配置搜索。P-NN预测分区，DEM-NN预测权重缩减与端点模式，保留后续参数求解。不同块大小分别训练，以预先压缩数据提供配置标签。`[verified: 在线原文§3.2–3.4；ASTCEncodingSurvey p.8“TexNN”段]` [综述对应页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=8)

## 实验与证据

测试包含89张图，涵盖48张Albedo、21张bump和20张normal。Table 3中exhaustive-top:(1,1)对4×4、6×6、8×8分别报告6.38、6.57、7.66倍平均加速，采用单CPU线程比较。`[verified: 在线原文§4、Table 3]` [出版社原文](https://onlinelibrary.wiley.com/doi/abs/10.1111/cgf.13534)

## 局限与AdaptiveASTC关联

它为学习近似搜索提供直接先例，分类粒度是压缩块内部配置。本项目整图footprint选择应另建标签与决策规则。原文历史加速结果也需要绑定当时的参考编码器与preset。`[opinion]`

可以借鉴保留多个高概率配置的策略，思考置信度怎样影响搜索预算。但当前项目要求选定footprint后执行一次最终编码，需要独立验证校准后决策对质量违规率和字节损失的影响。`[opinion]`
