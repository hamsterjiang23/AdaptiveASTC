---
title: AdaptiveASTC参考文献
type: moc
status: active
created: 2026-11-09
tags: [texture-compression, literature-map]
---

# AdaptiveASTC参考文献

## 定位与阅读口径

本批整理28篇文献，逐篇记录方法、论文证据、局限和与AdaptiveASTC的关系。23篇保存了可解析的本地PDF，访问受限条目按实际阅读范围单列。`[verified: 下方28条笔记的“来源与阅读范围”；verification.json]`

25篇读取了原文方法或实验章节，3篇限于官方摘要、软件说明与综述补充。各篇状态为`skim`，论文报告值与本项目判断分别标注。`[verified: 各篇frontmatter的read_scope及“来源与阅读范围”]`

PDF在本机归档。Git同步笔记、索引、校验记录与官方原文链接，PDF文件按目录规则排除。异地阅读可从各篇来源链接取得原文。`[verified: reference/.gitignore；Obsidian .gitignore的raw/规则；各篇来源链接]`

## 阅读入口

- 先读PSNRBlockSize、AdaptiveASTCEncoder与ASTCEncodingSurvey，建立质量约束选参的直接工作对照。`[opinion]`
- 接着读TextureIQA、PsychophysicalMasking与TextureVisibility，检查贴图误差和最终可见误差之间的关系。`[opinion]`
- 神经纹理组用于比较表示与运行时成本，逐篇核对输出格式、解码器和训练开销。`[opinion]`

## 直接ASTC工作与固定码率编码

| 文献简读 | 年份与来源 | 实际阅读范围 | 本地原文 |
|---|---|---|---|
| [An Analytical Survey of ASTC Encoding Techniques](ASTCEncodingSurvey.md) | 2026 · IEEE Computer Graphics and Applications | 作者预印本选读，p.1摘要、p.8实验设置与编码器、p.12块大小、p.13结论、p.13–14书目 | `ASTCEncodingSurvey.pdf`。`[verified: ASTCEncodingSurvey笔记“来源与阅读范围”]` |
| [ASTC Block-Size Determination Method based on PSNR Values](PSNRBlockSize.md) | 2022 · Journal of the Korea Computer Graphics Society 28(2) 21–28 | 原文选读，p.21摘要、§3.1–3.2、Tables 2–3、§5局限 | `PSNRBlockSize.pdf`。`[verified: PSNRBlockSize笔记“来源与阅读范围”]` |
| [Addition of an adaptive block-size determination feature to astcenc, the reference ASTC encoder](AdaptiveASTCEncoder.md) | 2023 · Software Impacts 17 100569 | 出版社摘要与Highlights、配套仓库README L1–8、作者2026综述p.12；论文PDF未取得 | 未取得有效PDF。`[verified: AdaptiveASTCEncoder笔记“来源与阅读范围”]` |
| [Pruned Lightweight Encoders for Computer Vision](PrunedASTC.md) | 2022 · IEEE MMSP | arXiv v1原文简读，§III–VI、Tables I–III | `PrunedASTC.pdf`。`[verified: PrunedASTC笔记“来源与阅读范围”]` |
| [TexNN: Fast Texture Encoding Using Neural Networks](TexNN.md) | 2019 · Computer Graphics Forum 38(1) 328–339 | 出版社在线摘要及可检索正文§3.2–3.4、§4和Tables 1–3；PDF访问失败 | 未取得有效PDF。`[verified: TexNN笔记“来源与阅读范围”]` |
| [On Improving the Performance Per Area of ASTC with a Multi-output Decoder](MultiOutputASTC.md) | 2017 · IEEE ARITH | 原文两页简读，§1–4、Table 1、Figure 2 | `MultiOutputASTC.pdf`。`[verified: MultiOutputASTC笔记“来源与阅读范围”]` |
| [Real-Time Adaptive Scalable Texture Compression for the Web](RealtimeASTCWeb.md) | 2016 · Chalmers University of Technology master's thesis | 学位论文原文选读，Abstract、§4实现、§5.3性能、§7结论 | `RealtimeASTCWeb.pdf`。`[verified: RealtimeASTCWeb笔记“来源与阅读范围”]` |
| [VBTC: GPU-Friendly Variable Block Size Texture Encoding](VBTC.md) | 2016 · Computer Graphics Forum 35(2) 409–418 | Eurographics官方摘要、作者书目与2026综述结论；原文PDF未取得 | 未取得有效PDF。`[verified: VBTC笔记“来源与阅读范围”]` |
| [FasTC: Accelerated Fixed-Rate Texture Encoding](FasTC.md) | 2013 · ACM I3D | 作者公开原文选读，Abstract、§3.5–3.7、§4、Figure 1 | 未取得有效PDF。`[verified: FasTC笔记“来源与阅读范围”]` |
| [SegTC: Fast Texture Compression using Image Segmentation](SegTC.md) | 2014 · High Performance Graphics | 原文选读，Abstract、§3、§4、§5，PDF共7页 | `SegTC.pdf`。`[verified: SegTC笔记“来源与阅读范围”]` |

## 神经纹理与替代表示

| 文献简读 | 年份与来源 | 实际阅读范围 | 本地原文 |
|---|---|---|---|
| [Random-Access Neural Compression of Material Textures](NTC.md) | 2023 · SIGGRAPH / ACM TOG | 原文HTML简读，摘要、§4、§6.4–6.5 | `NTC.pdf`。`[verified: NTC笔记“来源与阅读范围”]` |
| [Real-Time Neural Materials using Block-Compressed Features](BCNeuralMaterials.md) | 2024 · Eurographics / Computer Graphics Forum | 原文HTML简读，摘要、§4、§5.2、§6.1–6.2 | `BCNeuralMaterials.pdf`。`[verified: BCNeuralMaterials笔记“来源与阅读范围”]` |
| [Neural Graphics Texture Compression Supporting Random Access](NGTC.md) | 2024 · ECCV | 原文HTML简读，摘要、§4、§5.1–5.2、§5.4 | `NGTC.pdf`。`[verified: NGTC笔记“来源与阅读范围”]` |
| [Neural Texture Block Compression](NTBC.md) | 2024 · MAM-MANER | 原文HTML简读，摘要、§1、§3.2、§4.1–4.4 | `NTBC.pdf`。`[verified: NTBC笔记“来源与阅读范围”]` |
| [Neural Block Compression: Variable Bitrates Feature Blocks for Texture Representation](NBC.md) | 2025 · AAAI | 原文简读，摘要、§3–5、表3–4与结论 | `NBC.pdf`。`[verified: NBC笔记“来源与阅读范围”]` |
| [Differentiable Block Compression for Neural Texture](DBC.md) | 2025 · Eurographics Symposium on Rendering Symposium Track | 原文PDF简读，摘要、§3–4、§5.1–5.2、§6.1–6.2 | `DBC.pdf`。`[verified: DBC笔记“来源与阅读范围”]` |
| [Hardware Accelerated Neural Block Texture Compression with Cooperative Vectors](CooperativeVectorNTC.md) | 2025 · High-Performance Graphics | 原文HTML简读，摘要、§3.1、§4–7 | `CooperativeVectorNTC.pdf`。`[verified: CooperativeVectorNTC笔记“来源与阅读范围”]` |
| [Image-GS: Content-Adaptive Image Representation via 2D Gaussians](ImageGS.md) | 2025 · SIGGRAPH Conference Papers | 原文HTML简读，摘要、§3.1–3.3、§4.4–4.5 | `ImageGS.pdf`。`[verified: ImageGS笔记“来源与阅读范围”]` |
| [Neural Texture Compression using Hypernetworks](HyperNTC.md) | 2026 · Eurographics Symposium on Rendering | 原文HTML简读，摘要、§3、§4.1、§5 | `HyperNTC.pdf`。`[verified: HyperNTC笔记“来源与阅读范围”]` |
| [Variable-Rate Texture Compression: Real-Time Rendering with JPEG](JPEGTextures.md) | 2026 · Eurographics / Computer Graphics Forum | 原文HTML简读，摘要、§4、§5.3、§6.1–6.2 | `JPEGTextures.pdf`。`[verified: JPEGTextures笔记“来源与阅读范围”]` |

## 感知质量与渲染评价

| 文献简读 | 年份与来源 | 实际阅读范围 | 本地原文 |
|---|---|---|---|
| [Objective Image Quality Assessment of Texture Compression](TextureIQA.md) | 2014 · I3D | 原文简读，摘要、§3方法、§4结果、§5结论与Table 2 | `TextureIQA.pdf`。`[verified: TextureIQA笔记“来源与阅读范围”]` |
| [Evaluating Texture Compression Masking Effects Using Objective Image Quality Assessment Metrics](TextureMaskingIQA.md) | 2015 · IEEE Transactions on Visualization and Computer Graphics | 仅NIST官方摘要与书目信息，全文PDF未获取 | 未取得有效PDF。`[verified: TextureMaskingIQA笔记“来源与阅读范围”]` |
| [A Psychophysical Evaluation of Texture Compression Masking Effects](PsychophysicalMasking.md) | 2019 · IEEE Transactions on Visualization and Computer Graphics | 作者版PDF简读，摘要、§3–4、§6与Figure 13 | `PsychophysicalMasking.pdf`。`[verified: PsychophysicalMasking笔记“来源与阅读范围”]` |
| [Selecting texture resolution using a task-specific visibility metric](TextureVisibility.md) | 2019 · Pacific Graphics / Computer Graphics Forum | 原文PDF简读，摘要、§6–8、§10–11与Table 1–2 | `TextureVisibility.pdf`。`[verified: TextureVisibility笔记“来源与阅读范围”]` |
| [FLIP: A Difference Evaluator for Alternating Images](FLIP.md) | 2020 · HPG / PACMCGIT | 原文简读，摘要、§1–2、§6.2、§7及作者页勘误 | `FLIP.pdf`。`[verified: FLIP笔记“来源与阅读范围”]` |

## 近期预印本

| 文献简读 | 年份与来源 | 实际阅读范围 | 本地原文 |
|---|---|---|---|
| [Compact Representation of Mipmapped SVBRDFs via Shared Gaussians](SharedGaussianSVBRDF.md) | 2026 · arXiv preprint | 原文HTML简读，摘要、§3–5、Table 1–2 | `SharedGaussianSVBRDF.pdf`。`[verified: SharedGaussianSVBRDF笔记“来源与阅读范围”]` |
| [Thread-Efficient Decoding for Neural Texture Compression](ThreadEfficientNTC.md) | 2026 · arXiv preprint | 原文HTML简读，摘要、§2–5、Table 2、Table 5–6 | `ThreadEfficientNTC.pdf`。`[verified: ThreadEfficientNTC笔记“来源与阅读范围”]` |
| [Beyond UV Mapping: Mesh Texture Compression via Surface-Aligned Texture Fields](TexF.md) | 2026 · arXiv preprint | 原文HTML简读，摘要、§III-D、§IV-D、§IV-F与Table III | `TexF.pdf`。`[verified: TexF笔记“来源与阅读范围”]` |

## 访问限制

- AdaptiveASTCEncoder读取出版社摘要、Highlights和软件README，VBTC读取官方摘要及综述，TextureMaskingIQA读取NIST官方摘要。三篇均明确记录全文访问限制。`[verified: 对应三篇“来源与阅读范围”]`
- FasTC与TexNN已选读在线原文方法和实验，本地有效PDF仍缺失。其余本地原文状态逐行列在上表。`[verified: FasTC、TexNN笔记的read_scope及pdf_file；verification.json]`

## 工作之间的张力与开放问题

- 搜索式块大小选择与学习式选参需要在同一编码器、质量preset和数据划分下比较。离线生成标签的多次编码成本与生产阶段一次编码的成本应分别报告。`[opinion]`
- 最优类别概率的校准与实际质量达标概率之间存在评价对象差异。分类校准后应继续统计质量违规率、字节损失和失败样本。`[opinion]`
- 渲染掩蔽、法线用途和mipmap会改变可见误差，PSNR 35 dB是否适合每类资产需要本项目验证。Unity导入域与源图域的对应数据仍需采集。`[opinion]`
- 神经表示的存储收益、显存占用和运行时解码成本需按论文协议分别记录，再判断目标硬件上的适用性。`[opinion]`

## 本地归档与校验

本地原文位于`reference/papers/`。文件名、SHA-256、PDF页数与阅读范围见[校验记录](verification.json)。`[verified: verification.json]`

项目来源为AdaptiveASTC仓库的reference目录。`[verified: 本批归档目录与同步记录]` [项目文献目录](https://github.com/hamsterjiang23/AdaptiveASTC/tree/main/reference)
