---
title: "Neural Texture Compression using Hypernetworks"
method_name: HyperNTC
aliases: [Hypernetwork NTC]
year: 2026
venue: Eurographics Symposium on Rendering
doi: 10.2312/sr.20261015
arxiv: "2606.26913v1"
type: literature-note
tags: [paper-note, texture-compression, hypernetwork]
status: skim
created: 2026-11-09
read_scope: "原文HTML简读，摘要、§3、§4.1、§5"
pdf_file: papers/HyperNTC.pdf
---

# HyperNTC

## 来源与阅读范围

简读2026年原文HTML的摘要、超网络架构和主要实验，本地保存arXiv版本。正式收录于EGSR 2026 Symposium Track。`[verified: 原文首页、§3–5；Eurographics正式页Collections及BibTeX]` [原文HTML](https://arxiv.org/html/2606.26913v1) · [正式页面](https://diglib7.eg.org/items/0229b276-af2d-4abf-82de-de48c4a5e22b) · 本机归档`papers/HyperNTC.pdf`

## 核心方法

一个共享hypernetwork读取材质集合，同时产生BC1潜在纹理及逐材质MLP的权重、偏置。架构以全局token和cross-attention联系输入与输出，并在训练中通过生成的解码器回传重建误差，将逐材质梯度优化成本摊销到共享网络。`[verified: 原文§3.1–3.4、图2]`

## 实验与证据

作者在同一A6000 Ada上比较BCF1的40K步优化和超网络，报告每组材质分别约14分钟与2.4秒。超网络的平均PSNR较低、MS-SSIM较高，原文将这一现象联系到L1／感知损失与BCF1 L2损失的差异。`[verified: 原文§5 Comparison with BCF1]`

## 局限与AdaptiveASTC关联

超网络生成的是BC1神经特征和MLP，渲染仍需该解码器。`[verified: 原文§3.2]` 它与“一次预测减少逐资产重复优化”的工程动机接近，但项目中的块大小分类和质量约束仍是独立决策问题。实验应把共享训练成本、泛化资产质量和逐资产推理成本分别记录。`[opinion]`
