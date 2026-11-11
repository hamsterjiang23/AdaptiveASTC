# AdaptiveASTC

根据最终压缩质量，为每张贴图选择合适的ASTC块大小，在项目质量要求下减少纹理体积，并研究通过机器学习实现预测选参后单次压缩的生产流程。相关资料从网易雷火GDC 2023演讲及其公开字幕、视频画面开始整理。`[verified: 用户需求说明（2026-11-09）“主要目的就是通过最终压缩质量选择合适的压缩参数”“一张图压缩一次”；本文“从这里阅读”]`

## 项目需求与优化目标

### 当前生产基线与优化空间

项目目前统一使用ASTC 8×8。用户观察到，部分图片使用6×6或8×8时，压缩结果的差异人眼难以分辨，其中一些图片可能进一步采用10×10或12×12，仍保持与现有方案相当的视觉效果。另一些图片则可能需要6×6，以满足更高的质量要求。`[verified: 用户需求说明（2026-11-09）“目前项目全都是统一使用8*8”“10*10或者12*12”“有的图片可能需要用6*6”]`

研究目标为逐图选择参数，以最终压缩质量是否达标决定可用候选，并在质量可接受的候选中选择体积更小的结果。候选示例为6×6、8×8、10×10和12×12，具体集合在实验协议中确定。`[verified: 用户需求说明（2026-11-09）“通过最终压缩质量选择合适的压缩参数”“6*6 8*8 10*10等一系列压缩参数”；opinion: 按质量约束选择较小体积的目标整理]`

### 按贴图类型定义质量标准

| 贴图类型 | 当前质量判据与待明确内容 |
|---|---|
| 普通图片／颜色贴图 | 项目当前采用PSNR 35 dB作为压缩前后人眼难以分辨的经验判据。阈值的严格比较方式、计算颜色空间和参与通道在实验协议中明确。`[verified: 用户需求说明（2026-11-09）“目前的恒定标准是：PSNR为35”；opinion: 指标计算口径待明确]` |
| 法线贴图 | 需要符合其用途的独立质量指标与固定阈值，具体标准待定义。`[verified: 用户需求说明（2026-11-09）“针对法线贴图，MSAK贴图之类，需要其他的恒定标准”]` |
| MSAK等贴图 | 需要独立质量标准，通道含义、参与评价的通道和阈值按项目实际使用方式明确。`[verified: 用户需求说明（2026-11-09）“MSAK贴图之类，需要其他的恒定标准”；opinion: 评价口径待明确]` |

PSNR 35 dB在此记录为项目当前采用的经验判据，其与实际视觉接受程度的对应关系属于后续验证内容。各类贴图的质量标准共同约束标签生成、模型评价与最终结果验收。`[verified: 用户需求说明（2026-11-09）“认为压缩前后人眼分辨不出来”；opinion: 研究验证与验收口径]`

### 从多次试压缩到预测后单次压缩

既有方案逐张尝试6×6、8×8、10×10等多种参数，比较压缩结果后选择合适的参数。用户反馈，这种流程需要重复压缩，处理较慢，维护也较麻烦。`[verified: 用户需求说明（2026-11-09）“需要压缩多次，而且维护起来也麻烦”]`

希望实现的流程为“贴图及必要的导入信息 → 机器学习预测合适的块大小 → 按预测参数执行一次最终ASTC压缩”。单次压缩为生产流程目标，预测效果与满足质量约束的最优候选之间的差距需要通过实验衡量。`[verified: 用户需求说明（2026-11-09）“想用机器学习的方式做到一张图压缩一次，得到最优结果”；opinion: 输入接口与最优候选的评价方式]`

单次压缩目标暂按日常生产选参阶段理解。离线训练数据和标签的构建方法待确定，分别记录其多候选测量成本与生产阶段的预测、压缩成本。质量未达标样本及其处理方式单列统计。`[opinion: 对单次压缩目标的阶段划分与实验记录要求]`

### Unity导入结果与训练数据准备

用户指出，很多图片的训练需要使用Unity导入后的结果，而原图与Unity实际导入后的图存在差异。获取导入后的训练数据、建立源图与导入结果的对应关系，是当前认为较麻烦的工程问题。`[verified: 用户需求说明（2026-11-09）“很多图片需要unity导入后的结果做训练”“原题和unity导入后的图是不太一样的”]`

数据方案需要明确模型读取哪个阶段的纹理、质量测量使用哪个阶段的参考图，以及如何复现对应的Unity导入配置。采集输入、导入结果、候选压缩结果与质量标签时保留可追溯对应关系，并分别统计Unity数据获取和训练数据构建耗时。具体导入差异及其影响通过项目资产样本核实。`[opinion: 由Unity导入差异引出的数据接口与验证要求]`

现有参数快照与图片位置已完成[实际数据调查](notes/实际数据位置与训练可用性调查.md)。附件183,051条记录在`F:\MLBB_Test\haijiangli1_HAMSTERMLBB`中匹配177,184张图片及对应meta，64张分层样本MD4一致。附件采用LITE基础PSNR 30配置，主包代码常量为35；本项目的研究质量目标与历史策略标签需分别记录。`[verified: notes/实际数据调查统计.json的baseline、path_coverage/image_project、md4_sample；报告“LITE与主包质量配置”]` `[opinion]`

源码侧的参考图、标签、候选报告与缓存位置集中标注于[Unity训练数据导出与源码导航](#unity训练数据导出与源码导航)，包含缓存命中、磁盘调试、提前停止与回退条件。`[verified: 本文对应小节]`

### 研究顺序与分类校准

执行顺序更新为Unity搜索耗时baseline、Nah 2023作者代码、Nah 2022论文重实现、TexNN论文重实现、GDC压缩闭环复现，再研究新模型与校准。复现入口与实际状态见[reproductions](reproductions/README.md)。Unity主基线采用LITE配置且关闭RDO，文献原始配置与项目适配配置分别记录。`[verified: 用户2026-11-10确认的实施计划]`

优先研究原始块大小分类模型上的calibration，先评估分类方案能达到的质量与体积权衡。分类校准方案经实验仍达不到项目目标时，再研究多候选质量预测及其calibration。当前确定的是研究顺序，方法效果待实验验证。`[verified: 用户研究决策（2026-11-09）“在最原本的分类上进行calibration”“先研究这个，如果不行，在研究预测质量的calibration”]`

- **分类基线**。保留以ResNet等网络输出块大小类别的方案，并保存完整logits／类别概率，作为后处理输入。训练标签按候选压缩质量和项目质量标准生成。`[opinion: 分类优先路线的实验设计]`
- **概率校准**。先以temperature scaling作为后处理基线，在独立校准集上拟合温度，检查置信度与标签正确率的一致性。该方法对所有logits使用同一个正温度缩放，类别排序与argmax预测保持一致。`[verified: Guo等，On Calibration of Modern Neural Networks，§4.2，公式9及其后说明；opinion: 本项目方法选择]` [论文](https://proceedings.mlr.press/v70/guo17a.html)、[方法原文第6页](https://proceedings.mlr.press/v70/guo17a/guo17a.pdf#page=6)
- **选参决策校准**。研究如何利用校准后的概率、置信度阈值或类别相关代价，确定最终块大小。保持生产阶段选定参数后只执行一次最终编码，决策规则及其保守程度通过离线数据确定。`[opinion: 决策层校准方案]`
- **评价对象**。分别记录“预测是否命中最优块大小标签”和“最终压缩质量是否达标”。例如选择了质量达标但体积较大的候选，应计入体积损失。离线数据保留各候选的实测质量、达标状态与字节数，用于评价决策结果。`[opinion: 标签与质量可行性的评价定义]`
- **校准与生产指标**。概率层记录NLL、Brier score、ECE和可靠性图，生产层记录质量违规率、相对固定8×8的字节变化、相对穷举可行最优结果的差距，以及推理与最终编码耗时。temperature scaling后继续argmax选参时，最终候选和相应质量结果与原分类基线一致，需单独检验使用校准输出的决策规则。`[verified: Guo等§4.2的argmax性质；opinion: 评价指标及其对本流程的含义]` [方法原文第6页](https://proceedings.mlr.press/v70/guo17a/guo17a.pdf#page=6)
- **实验划分与切换条件**。按资产或项目划分训练、模型验证、校准和最终测试数据，近重复资产归入同一划分。可接受的质量违规上限、最低体积收益与处理成本预算，在小样本实验前明确。以独立测试中的质量／体积权衡判断分类校准路线是否满足目标，再决定是否启用质量回归校准备选。`[opinion: 验证协议与备选路线启用条件]`

## 当前状态

| 项目 | 状态与证据 |
|---|---|
| Unity 搜索基线 | 10,000 张已完成，包含 32 张技术失败补测，状态为 passed_with_retries。搜索合计 4,060.47 秒，选参及编码合计 4,163.31 秒，详见[基线报告](<experiment report/unity-search-baseline-lite-rdo-off/README.md>)。源图哈希与实际搜索选择通过核验，metadata 恢复无冲突。`[verified: 基线报告 summary.json phases.full]` |
| Nah 2023 作者代码 | 固定版本的 64 张项目源图适配完成压缩、解码与全图质量复查。40 dB 下 RGBA 达标 46/64，RGB 达标 26/64，搜索及最终编码 73.248 秒。[实测报告](<experiment report/nah2023_adaptive_astcenc/source-rgb64-target40/README.md>)保留随机抽样实现与同方法固定 8×8 对照。`[verified: 对应 summary.json quality_audit/search_and_final_encode_seconds]` |
| Nah 2022 论文重实现 | astcenc 3.3 的 64 张项目源图适配完成压缩、解码。采用 Game 目标 37.3873 dB，RGBA 达标 64/64，RGB 达标 62/64，搜索及最终编码 546.329 秒。[实测报告](<experiment report/nah2022_psnr_search/source-rgb64-game/README.md>)记录初始 6×6 的补全来源及测量范围。`[verified: 对应 receipt.json/summary.json]` |
| TexNN 与新 GDC 复现 | TexNN 主文及 13 页 Appendix 已归档，六个网络尺寸已实现并通过前向检查。历史编码器的 4×4、6×6、8×8 标签导出已通过原生 ASTC、像素及字节一致性核验，见[探针报告](<experiment report/texnn/reference-probe-20261111/README.md>)。数据集、训练与预测配置回填继续执行，新 GDC 压缩闭环随后开展。`[verified: reproductions/texnn/source.json；探针报告；用户确认的实施顺序]` |
| 资料归档 | 视频、中英文网站字幕、19张每分钟截图、10张关键页补充截图已保存。`[verified: materials/gdc2023-astc-parameter-selection/；verification.json]` |
| 全文整理 | 中英文字幕各328条，校订稿按40段覆盖全部条目，逐条原文另存对照稿。音轨独立ASR转写状态为未运行。`[verified: source/material-metadata.json；transcripts/完整字幕对照.md]` |
| 方法核实 | 正文展示有标签数据集、块大小分类和ResNet。官网简介另提到强化学习，具体对应关系待作者材料确认。`[verified: 视频10:00、11:28、12:28；官方简介Overview]` |
| 实验复现 | 已完成14,000张LITE源图划分、两组ResNet18各30轮及独立温度校准。测试准确率为67.50%／62.35%，中间块大小类别召回较低。[比例复核](<experiment report/gdc-lite-rgb-resnet18-seed20261109/数据集划分比例复核.md>)发现测试集中Mask单组占46.05%，详见[实验报告](<experiment report/gdc-lite-rgb-resnet18-seed20261109/training_report.md>)。质量与字节收益需候选压缩实测。`[verified: 实验metrics.json、data_summary.json、split_proportion_audit.json；opinion: 生产质量评价范围]` |
| Git | 已初始化，分支为`main`，远端为`hamsterjiang23/AdaptiveASTC`，MP4视频通过Git LFS管理。`[verified: git init、git branch --show-current、git remote add origin输出；.gitattributes中的*.mp4规则]` |

## Unity训练数据导出与源码导航

当前引擎具备“压缩前参考图采集、候选试压缩与质量测量、参数选择、最终参数写表和调试产物导出”的采集基础。训练样本可按“参考图＋blockSize标签＋编码及导入协议”组织，批量采集、稳定配对和训练集封装按待实施工作记录。`[verified: ASTCCompressor.cpp L1982–2021、L2958–3422、L3435–3539]` `[opinion]`

### 压缩参数与图像术语

本节统一解释blockSize、preset、LDR、HDR、sRGB和Linear，并补充理解现有代码所需的texel、bpp、payload、法线用途及质量指标。压缩参数、亮度范围、颜色编码和贴图用途分别记录。`[verified: 用户本次术语入文档要求；ASTCCompressor.cpp L547–577、L3466–3475]` `[opinion]`

#### blockSize、texel、bpp与payload

blockSize为一个ASTC块覆盖的像素宽高，也称block footprint。texel表示纹理中的一个像素。ASTC每块固定输出128 bit，即16字节，块覆盖的像素数决定平均每像素位数bpp。`[verified: Arm《ASTC Format Overview》“Block compression”L190–197]` [Arm格式说明](https://github.com/ARM-software/astc-encoder/blob/main/Docs/FormatOverview.md#block-compression)

- 4×4覆盖16个texel，每块16字节，平均8 bpp。`[verified: Arm《ASTC Format Overview》L197；128/(4*4)=8]`
- 8×8覆盖64个texel，每块16字节，平均2 bpp。`[verified: Arm《ASTC Format Overview》L197；128/(8*8)=2]`
- 12×12覆盖144个texel，每块16字节，平均约0.89 bpp。`[verified: Arm《ASTC Format Overview》L197；128/(12*12)≈0.89]`

固定图像尺寸时，较大的块让更多像素共享同一份存储，通常减少payload并增加细节表达的约束。payload在本项目指原始ASTC块数据，按`ceil(width/bx)*ceil(height/by)*16`计算；完整mip链、容器与包压缩后的大小另行计量。`[verified: ASTCCompressor.cpp L3067–3072、L3163–3164；ImageOperations.cpp L2975–2985]` `[opinion]`

#### preset与编码速度

preset是编码器的搜索投入／质量预设。此前交流中的“present速度”统一写为“preset编码档位”或“编码速度”。本项目候选依次使用`fastest → fast → medium → thorough → exhaustive`，候选qualityValue为0～4，底层编码值对应0、10、60、98、100。`[verified: ASTCCompressor.cpp L547–552、L620–625、L3075–3086；用户术语提问]`

从fastest到exhaustive通常投入更多编码时间以寻找更好的编码，额外时间带来的质量改善逐渐减小。这里的速度描述导入／制作阶段的编码过程。`[verified: Arm astc-encoder README “Experimenting”L285–287]` [Arm编码预设说明](https://github.com/ARM-software/astc-encoder#experimenting)

例如，同图、同尺寸、同8×8块大小下，fastest和thorough使用相同的ASTC payload容量，编码内容、耗时和质量可能不同。blockSize控制每像素的存储预算，preset控制寻找编码结果的计算投入。`[verified: ASTCCompressor.cpp L3067–3108]` `[opinion]`

#### LDR与数值归一化

LDR是Low Dynamic Range，低动态范围。常见8位颜色图的单通道整数值为0～255，归一化后为0～1。归一化表示把整数除以255，例如128/255≈0.502；该数值对应怎样的线性光强还取决于颜色编码。`[verified: Unity 2019.4《High dynamic range》“How HDR works”L161–164；Unity《Color space》L177–182；128/255算式]` [Unity亮度范围说明](https://docs.unity3d.com/2019.4/Documentation/Manual/HDR.html)、[Unity颜色编码说明](https://docs.unity3d.com/2019.4/Documentation/Manual/LinearLighting.html)

普通PNG／JPEG是Arm编码器列出的LDR输入示例，实际资产的编码解释还需结合导入设置与贴图用途。`[verified: Arm astc-encoder README “Encoder feature support”L180；ASTCCompressor.cpp L3466–3475]` `[opinion]` [Arm输入格式说明](https://github.com/ARM-software/astc-encoder#encoder-feature-support)

#### HDR与亮度范围

HDR是High Dynamic Range，高动态范围。在游戏的线性光照表示中，可以保留超过1的亮度值，通常用浮点形式承载更大的范围。假设普通表面为0.3、较亮表面为1、强光为10，可以继续保留这些光强差异，供曝光、泛光和色调映射使用。`[verified: Unity 2019.4《High dynamic range》L159–180；平台纹理格式手册“Terminology”L180]` `[opinion]` [Unity HDR说明](https://docs.unity3d.com/2019.4/Documentation/Manual/HDR.html)

Arm编码器列出的HDR输入示例包括EXR和HDR。亮度范围、数值精度与实际纹理存储格式在实验协议中分别记录。`[verified: Arm astc-encoder README L180–194]` `[opinion]` [Arm格式支持](https://github.com/ARM-software/astc-encoder#encoder-feature-support)

#### sRGB与颜色编码

sRGB是一套常用颜色空间标准。在这段代码的讨论中，主要关注其颜色编码值与线性光强之间的非线性映射。这种映射使有限的存储精度更适合视觉需求；线性渲染时，sRGB纹理采样值会转换成线性值参与计算。`[verified: Unity 2019.4《Color space》“Linear and gamma color space”L170–182；《Gamma Textures with linear rendering》L180]` [Unity颜色空间说明](https://docs.unity3d.com/2019.4/Documentation/Manual/LinearLighting.html)、[Unity采样转换说明](https://docs.unity3d.com/2019.4/Documentation/Manual/LinearRendering-GammaTextures.html)

本项目useSRGB读取的是当前纹理reportTex的stored color space。判断图像编码与质量分支时，保留纹理导入配置及运行时读到的属性。`[verified: ASTCCompressor.cpp L3466–3475、L3206–3225]` `[opinion]`

#### Linear与数据贴图

对颜色／光照而言，Linear表示按线性光强解释数值，供光照叠加和混合计算。对遮罩、查找表等数据纹理而言，线性采样保留其存储值的数学含义，例如遮罩0.5可表示一半权重。Unity文档要求这些数据纹理绕过sRGB采样转换。`[verified: Unity 2019.4《Color space》L177–182；《Working with linear Textures》“Linear authored Textures”L174–183]` `[opinion: 遮罩含义用例]` [Unity线性计算说明](https://docs.unity3d.com/2019.4/Documentation/Manual/LinearLighting.html)、[Unity数据纹理说明](https://docs.unity3d.com/2019.4/Documentation/Manual/LinearRendering-LinearTextures.html)

Normal Map表示法线用途，通道值用于还原方向，Unity将法线纹理按线性数据处理。本地实现通过normal usage设置isNormalMap，并采用法线角度评价分支。`[verified: Unity《Working with linear Textures》L174–177；ASTCCompressor.cpp L2552–2559、L3474–3475、L3198–3204]` [Unity法线采样说明](https://docs.unity3d.com/2019.4/Documentation/Manual/LinearRendering-LinearTextures.html)

#### 属性组合与本地代码对应

LDR／HDR描述亮度范围，sRGB／Linear描述编码及数值解释，这两个维度可以组合。Arm编码器分别提供Linear LDR、sRGB LDR、HDR RGB／RGBA模式。Unity使用Linear渲染流程时，也可以采样采用sRGB编码的颜色纹理并执行转换。`[verified: Arm astc-encoder README “Compressing an image”L259–264；Unity《Gamma Textures with linear rendering》L160–180]` [Arm编码模式](https://github.com/ARM-software/astc-encoder#compressing-an-image)、[Unity线性流程与sRGB纹理](https://docs.unity3d.com/2019.4/Documentation/Manual/LinearRendering-GammaTextures.html)

以下组合用于帮助对应概念，具体资产以导入配置及实际像素为准。`[opinion]`

```text
用途             普通颜色贴图
亮度范围         LDR
颜色编码         sRGB
ASTC块大小       8×8
编码preset       medium
```

本地isHDR由输入纹理格式判断，useSRGB由纹理stored color space判断，isNormalMap由usage判断。blockSize与preset在候选表中搜索。这些属性共同决定编码profile与质量评价分支。`[verified: ASTCCompressor.cpp L3746–3747、L3466–3475、L620–625、L3090–3108、L3198–3225]`

#### PSNR、SSIM、MS-SSIM与RDO

PSNR是Peak Signal-to-Noise Ratio，峰值信噪比，通过均方像素误差计算dB值，相同测量口径下越高表示误差越小。本地通道参与规则、全无损返回值等见[导出字段口径](#导出产物与字段口径)。`[verified: ASTCCompressor.cpp L2181–2296]`

SSIM是Structural Similarity，结构相似性，比较局部亮度、对比度和结构。MS-SSIM是多尺度版本，在不同分辨率组合结构相似性。本地保存亮度MS-SSIM的dB转换值msSsimDb。`[verified: Wang等《Multi-scale structural similarity for image quality assessment》§2–3；ASTCCompressor.cpp L2299–2304、L2456–2541]` [作者论文](https://www.cns.nyu.edu/pub/eero/wang03b.pdf)

RDO是Rate-Distortion Optimization，率失真优化，权衡编码失真与码率代价。Arm的ASTC设计讨论将提高应用包中纹理的后续可压缩性列为目标。本地当前核实的是搜索后重编码、质量复测与采用条件，内部代价模型按外部DLL待核实。`[verified: Arm ASTC RDO讨论“Approaches”L136–141；ASTCCompressor.cpp L2754–2956]` `[opinion]` [Arm RDO讨论](https://github.com/ARM-software/astc-encoder/issues/361)

### 源码范围与调用链

本节于2026-11-10按本机源码静态阅读定位。下表链接指向本机文件，行号与下列SHA-256对应，源文件更新后需按符号重新定位。`[verified: 本次Get-FileHash输出及源码读取]` `[opinion]`

| 文件 | 职责与SHA-256 |
|---|---|
| [ImageOperations.cpp](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ImageOperations.cpp:2945) | 组织纹理压缩，从Texture2D取得输入，调用ASTC选参，再遍历image／mip编码。SHA-256为`442fc8fbbb57f78077ee3bd7f79e0ba6357cd8ce7733a53fb78206ba0eaeb9aa`。`[verified: ImageOperations.cpp L2945–2985；本次Get-FileHash输出]` |
| [ASTCCompressor.cpp](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3435) | ASTC后端、自动选参、指标、缓存和调试导出。SHA-256为`ccc8eea44b6bff44b8976389d7ecce96e9ce7f6831f149578f91fc54fb2dd209`。`[verified: ASTCCompressor.cpp L3435–3539、L3925–3967；本次Get-FileHash输出]` |

调用关系按实际代码整理如下。调试图片与报告在磁盘调试开启且进入搜索路径时生成，参数JSONL写出由选参结果及资产路径条件控制。`[verified: ImageOperations.cpp L2958–2968；ASTCCompressor.cpp L2963–2970、L3383–3385、L3506–3523]`

```text
CompressTextureWithMultipleImages                 ImageOperations.cpp L2945
  → FindOptimalASTCFormat                         ASTCCompressor.cpp L3738
    → FindOptimalParameters                       L3435
      → GetCachedParameters                       L1901，命中时L3461返回
      → PrepareOriginalImageData                  L2676，RGBA32参考像素
      → TestAllParameterCombinations              L2958
        → SetupTestEnvironment                    L1999，调试导出original.png
        → 编码／解码                              L3088／L3131
        → PSNR／MS-SSIM／法线角度                 L3160–3226
        → allResults与参数选择                    L3228–3359
        → TryAstcRdoRefinementAfterSearch          L2755，调用点L3361
      → SelectBestParameter                       L3364
        → GenerateParameterTestReport             L2023，调试报告
      → SaveBestParametersToCache                 L1935，调用点L3522
        → SaveCacheEntryToFile                    L1836，追加JSONL
          → CompactCacheLogToSnapshot             L1730，按阈值合并JSON
      → 返回选中payload                           L3526
    → 保存选中payload供后续压缩复用               L3787
```

本地早期基础提交`789b144a7`的`ISPCTexCompASTC`与当前命名空间内容相同，后续`d0d3980d7`新增`ASTCParameterOptimizer`、选参与写表功能。这里将ISPC归为基础引擎后端，将自动选参和采集逻辑归为项目扩展。官方原版逐行来源仍需对应Unity源码基线。`[verified: 本次Git历史、namespace比较输出；d0d3980d7差异]` `[opinion]`

### 入口、开关与输入属性位置

| 源码位置 | 行范围 | 与采集的关系 |
|---|---|---|
| [CompressTextureWithMultipleImages](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ImageOperations.cpp:2945) | 2945–2985 | 从Texture2D取第一个image的mip0，ASTC目标格式进入选参，随后遍历image／mip执行压缩。 `[verified: ImageOperations.cpp L2945–2985]` |
| [FindOptimalASTCFormat](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3738) | 3738–3784 | 检查自动选参开关，调用FindOptimalParameters，输出格式与preset。 `[verified: ASTCCompressor.cpp L3738–3784]` |
| [第三方编码／解码接口注册](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:428) | 428–478 | SetAstc3rdCompressFuncPtrEx、SetAstc3rdDecompressFuncPtr和SetAstc3rdOptionOnce提供搜索所需后端。 `[verified: ASTCCompressor.cpp L428–478]` |
| [选参、RDO和磁盘调试开关](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:453) | 453–472 | SetASTCOptimizationEnabled控制搜索，SetAstc3rdRdoSettings控制RDO，SetAstcDebugEnabled控制图片／报告落盘。 `[verified: ASTCCompressor.cpp L453–472]` |
| [FindOptimalParameters](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3435) | 3435–3539 | 总调度，依次处理缓存、纹理属性、参考像素、搜索、选择、写表和压缩数据返回。 `[verified: ASTCCompressor.cpp L3435–3539]` |
| [GetCachedParameters与提前返回](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1901) | 1901–1932、3437–3462 | 按资产路径索引并检查源文件MD4，命中后在参考图准备和调试导出之前返回。 `[verified: ASTCCompressor.cpp L1901–1932、3437–3462]` |
| [纹理类型与颜色空间](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3466) | 3466–3482 | 从reportTex读取stored color space和normal usage，缺失reportTex时默认sRGB颜色图。 `[verified: ASTCCompressor.cpp L3466–3482]` |
| [缓存目录设置](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3573) | 3573–3588 | ResetParameterDiskCacheStateForEditorTableDirectory／SetAstcParameterCacheTableDirectory切换目录并重置参数内存缓存。 `[verified: ASTCCompressor.cpp L3573–3588]` |
| [运行时质量设置](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3590) | 3590–3665 | SetAstcQualityThresholds校验输入后设置PSNR、MS-SSIM和法线角度阈值。 `[verified: ASTCCompressor.cpp L3590–3665]` |
| [附加策略设置](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3694) | 3694–3735 | 设置RDO余量、纯黑像素PSNR策略和大图面积门槛。 `[verified: ASTCCompressor.cpp L3694–3735]` |

### 参考像素、候选搜索与质量测量位置

| 源码位置 | 行范围 | 与采集的关系 |
|---|---|---|
| [ASTCParamCandidate与候选表](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:547) | 547–553、618–625 | 定义块大小与preset，20组候选按12×12、10×10、8×8、6×6及由快到慢preset排序。 `[verified: ASTCCompressor.cpp L547–553、618–625]` |
| [默认质量与搜索策略](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:627) | 627–643 | 默认PSNR 35、MS-SSIM 24、法线阈值、黑色像素分级、大图门槛和RDO余量。 `[verified: ASTCCompressor.cpp L627–643]` |
| [TestResult与SharedResult](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:568) | 568–577、645–684 | 保存候选指标、valid、allResults、选中数据、earlyExit和RDO尝试／采用状态。 `[verified: ASTCCompressor.cpp L568–577、645–684]` |
| [PrepareOriginalImageData](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2676) | 2675–2694 | 按输入颜色空间转换／绑定RGBA32，保留当前输入尺寸，是参考图采集位置。 `[verified: ASTCCompressor.cpp L2675–2694]` |
| [PrepareTextureName](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2697) | 2697–2719 | 生成纹理名称并替换文件名非法字符，供调试目录命名。 `[verified: ASTCCompressor.cpp L2697–2719]` |
| [TestAllParameterCombinations](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2958) | 2958–3031 | 建立可选调试环境，确定size-first模式，顺序遍历候选。 `[verified: ASTCCompressor.cpp L2958–3031]` |
| [候选文件名、块数据大小与preset映射](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3041) | 3041–3086 | 确定候选输出名和TextureFormat，按ceil(width/bx)×ceil(height/by)×16分配payload，映射编码质量。 `[verified: ASTCCompressor.cpp L3041–3086]` |
| [候选编码与解码](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3088) | 3088–3158 | 扫描阶段关闭RDO，编码至内存，调试时写ASTC／解压PNG，失败候选跳过后续测量。 `[verified: ASTCCompressor.cpp L3088–3158]` |
| [CalculatePSNR](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2181) | 2180–2296 | 逐通道MSE、纯黑比例、Alpha参与规则、误差非零通道平均及无损返回100。 `[verified: ASTCCompressor.cpp L2180–2296]` |
| [MS-SSIM基础运算](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2309) | 2309–2454 | BuildGaussianKernel11、GaussianBlurSeparable11、Downsample2x2、ComputeSSIMComponents计算局部统计。 `[verified: ASTCCompressor.cpp L2309–2454]` |
| [CalculateMSSSIMDb_Luma与SafeMsSsimToDb](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2456) | 2456–2541、2299–2304 | RGB转亮度、多尺度组合并转换为dB，保留本地实现的颜色空间与截断规则。 `[verified: ASTCCompressor.cpp L2456–2541、2299–2304]` |
| [法线角度基础运算](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2552) | 2552–2620 | DecodeNormalRGB_U8、NormalizeSafe、Dot、DownsampleNormal2x2、ComputeAngleStats完成法线解码和角度统计。 `[verified: ASTCCompressor.cpp L2552–2620]` |
| [CalculateNormalAngularErrorMip0To3](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2622) | 2622–2673 | 从参考／解压mip0构造最多四级法线降采样图，按像素数加权mean和各级p95。 `[verified: ASTCCompressor.cpp L2622–2673]` |
| [候选测量与有效阈值](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3160) | 3160–3226 | 计算PSNR和payload字节数，纯黑比例提高PSNR阈值，按normal／sRGB／其他路径判断合格。 `[verified: ASTCCompressor.cpp L3160–3226]` |
| [候选记录追加](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3228) | 3228–3239 | 构造TestResult并加入allResults，供候选报告或后续结构化采集使用。 `[verified: ASTCCompressor.cpp L3228–3239]` |
| [大图size-first选择](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3241) | 3241–3290、3348–3359 | 先按PSNR锁块，在该块内提升preset，保留PSNR通过候选作为MS-SSIM失败时的回退。 `[verified: ASTCCompressor.cpp L3241–3290、3348–3359]` |
| [常规选择与提前停止](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3293) | 3293–3338 | 首个有效结果保存payload并break，候选数组实际覆盖范围由搜索路径决定。 `[verified: ASTCCompressor.cpp L3293–3338]` |
| [TryAstcRdoRefinementAfterSearch](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2755) | 2754–2956、3361 | 满足开关与PSNR余量条件后对同一块大小／preset额外编码，复测后决定是否采用RDO数据。 `[verified: ASTCCompressor.cpp L2754–2956、3361]` |
| [SelectBestParameter](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3364) | 3364–3422 | 返回选中结果，全部不合格时在已测结果中选PSNR最高者，调试开启时生成报告。 `[verified: ASTCCompressor.cpp L3364–3422]` |

### 图片、标签、报告与缓存写出位置

| 源码位置 | 行范围 | 与采集的关系 |
|---|---|---|
| [ExportImageToPNG](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1982) | 1982–1997 | 将当前ImageReference写出PNG。 `[verified: ASTCCompressor.cpp L1982–1997]` |
| [SetupTestEnvironment](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1999) | 1999–2021 | 创建ASTC_Cache/<纹理名>_<计数>/，将参考像素写成original.png。 `[verified: ASTCCompressor.cpp L1999–2021]` |
| [GenerateParameterTestReport](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2023) | 2023–2178 | 写parameter_test_report.txt，包含阈值、已测候选、角度、选择与RDO精炼状态。 `[verified: ASTCCompressor.cpp L2023–2178]` |
| [CachedParameter](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:555) | 555–566 | 定义最终记录的资产路径、MD4、块大小、preset、质量、字节数、时间戳与RDO采用标志。 `[verified: ASTCCompressor.cpp L555–566]` |
| [GetFileVerificationHash与GetCurrentTimestamp](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:700) | 699–705、522–537 | MD4针对资产源文件，时间戳取系统时刻，Windows实现使用FILETIME/10000。 `[verified: ASTCCompressor.cpp L699–705、522–537]` |
| [SaveBestParametersToCache](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1935) | 1935–1975 | 组装最终记录并调用写表函数，截图字段在1964–1973行赋值。 `[verified: ASTCCompressor.cpp L1935–1975]` |
| [写表调用条件](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3506) | 3506–3523 | 要求选参成功、资产路径有效、候选存在且源文件存在，随后写入最终记录。 `[verified: ASTCCompressor.cpp L3506–3523]` |
| [缓存文件名和路径](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:607) | 607–615、1158–1175 | 默认ASTC_Cache/tables/default，文件为parameter_cache_detail.json与同名.jsonl。 `[verified: ASTCCompressor.cpp L607–615、1158–1175]` |
| [BuildAstcTableConfigFingerprintObjectJson](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1179) | 1178–1205 | 保存表级质量、黑像素、大图、RDO和优化开关配置，JSONL首行写配置头。 `[verified: ASTCCompressor.cpp L1178–1205]` |
| [缓存配置匹配与加载](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1372) | 1372–1467 | 配置不匹配时选择_cfg_后缀目录，旧版缺少tableConfig时保留兼容读取。 `[verified: ASTCCompressor.cpp L1372–1467]` |
| [SaveCacheEntryToFile与AppendStringToFile](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1836) | 1836–1899、1683–1713 | 加锁后追加JSONL，写入失败输出日志，日志达到2MiB阈值时触发快照合并。 `[verified: ASTCCompressor.cpp L1836–1899、1683–1713]` |
| [CompactCacheLogToSnapshot](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1730) | 1730–1834 | 合并快照和JSONL并输出entries，1809–1817行写截图形式的最终字段。 `[verified: ASTCCompressor.cpp L1730–1834]` |
| [返回并缓存选中payload](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3526) | 3526–3535、3787–3824 | 将搜索所得压缩数据交给外层内存缓存，供正式纹理压缩复用。 `[verified: ASTCCompressor.cpp L3526–3535、3787–3824]` |
| [HandleASTCTextureCompression复用入口](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3925) | 3925–3967 | 校验尺寸、格式与字节数后复制选中payload，使用后清除该内存条目。 `[verified: ASTCCompressor.cpp L3925–3967]` |

### 导出产物与字段口径

| 产物／字段 | 含义与对应位置 |
|---|---|
| `original.png` | [SetupTestEnvironment](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1999)导出当前ASTC入口的RGBA32参考图，输入来自Unity当前纹理的第一个image／mip0。`[verified: ASTCCompressor.cpp L1999–2010、L2675–2694；ImageOperations.cpp L2947–2964]` |
| 候选`.astc`／`*_decompressed.png` | [候选编码与解码落盘](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3041)记录实际尝试的组合，磁盘调试开关控制写出。`[verified: ASTCCompressor.cpp L3041–3046、L3091–3099、L3137–3145]` |
| `parameter_test_report.txt` | [GenerateParameterTestReport](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2023)记录已测候选及选择过程，包含精炼前后指标和RDO状态。`[verified: ASTCCompressor.cpp L2023–2178]` |
| 资产路径／`fileHash` | [最终记录组装](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1964)按资产路径配对，MD4标识源文件内容。采集清单还需保存导入设置和参考像素身份。`[verified: ASTCCompressor.cpp L699–705、L1964–1966]` `[opinion]` |
| `blockSize`／`qualityLevel` | [参数字段赋值](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1967)保存策略选中的块大小和编码preset，分类输入／标签协议需同时保留preset。`[verified: ASTCCompressor.cpp L1967–1968、L3075–3086]` `[opinion]` |
| `psnr` | [CalculatePSNR](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2181)计算像素误差对应的dB值，参与通道中只平均误差非零通道，恒定Alpha排除，全无损返回100。`[verified: ASTCCompressor.cpp L2238–2296]` |
| `msSsimDb` | [MS-SSIM亮度计算](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2456)比较多尺度亮度结构，[SafeMsSsimToDb](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:2299)使用`-10*log10(max(1-msSsim,1e-6))`转换。未计算分支可保留0。截图21.42 dB按公式对应约0.99279。`[verified: ASTCCompressor.cpp L2299–2304、L2456–2541、L3191–3225；本次公式换算输出]` |
| `fileSize` | [payload大小计算](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:3067)为本次参考尺寸的ASTC块payload字节数，公式为`ceil(width/bx)*ceil(height/by)*16`。完整mip链、容器、打包后字节数分开计量。`[verified: ASTCCompressor.cpp L3067–3072、L3163–3164；ImageOperations.cpp L2975–2985]` `[opinion]` |
| `timestamp` | [GetCurrentTimestamp](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:522)在写缓存时取得系统时刻，Windows路径为`FILETIME/10000`，压缩耗时需要另行采样。`[verified: ASTCCompressor.cpp L522–537、L1972]` `[opinion]` |
| `rdo` | [RDO采用标志](E:/hamster_unity/unity20190433/Editor/Src/AssetPipeline/TextureImporting/ASTCCompressor.cpp:1973)表示最终采用RDO精炼payload，attempted／status及精炼前后指标在SharedResult与调试报告中另存。`[verified: ASTCCompressor.cpp L657–666、L2115–2158、L2941–2953、L1973]` |

PSNR与MS-SSIM在这里用于质量测量，RDO在搜索后尝试一次同块大小／preset的重编码。固定尺寸和块大小下，两次编码的ASTC payload容量按同一公式确定。RDO内部失真与码率代价的具体实现位于外部编码DLL，当前核实范围覆盖Unity侧调用及质量验收。`[verified: ASTCCompressor.cpp L2754–2807、L2828–2833、L2863–2953]` `[opinion]`

### 自动选参的偏好与判定规则

这些规则共同定义“当前策略选中配置”，也是现有分类标签的生成口径。它们包含候选顺序、贴图类型质量门槛、纯黑像素分级、常规提前停止、大图块大小锁定、无合格结果回退和搜索后RDO精炼。以下按当前源码执行顺序记录，验证深度为静态代码分析。`[verified: ASTCCompressor.cpp L618–643、L2983–2990、L3160–3422、L2754–2956]`

以下C++摘录来自本节记录的同一份源码，仅省略纯注释、空行和公共左缩进。各片段按所标行范围独立展示。`[verified: 本次源码提取规则及ASTCCompressor.cpp对应行]`

#### 候选集合与尝试顺序

搜索表包含20组，块大小依次为`12×12 → 10×10 → 8×8 → 6×6`，每组preset依次为`fastest → fast → medium → thorough → exhaustive`。候选循环顺序执行，较大块和较快preset在前。候选数与排列顺序属于协议的一部分。`[verified: ASTCCompressor.cpp L618–625、L2979–2981、L3026–3028]` `[opinion]`

每次候选的payload大小为`ceil(width/bx)*ceil(height/by)*16`。preset档位`qualityValue=0..4`对应底层编码值`0、10、60、98、100`。顺序搜索阶段RDO关闭，编码或解码检查失败时跳过当前候选，成功测量后才追加allResults。`[verified: ASTCCompressor.cpp L550–552、L3067–3108、L3121–3125、L3157–3158、L3228–3239]`


候选数组及排列顺序对应源码L618–625。`[verified: ASTCCompressor.cpp L618–625]`

```cpp
static const int kParamCandidateCount = 20;  // 4 block sizes * 5 quality levels
static const ASTCParamCandidate kParamCandidates[] = {
    {"12x12", "fastest", 12, 0}, {"12x12", "fast", 12, 1}, {"12x12", "medium", 12, 2}, {"12x12", "thorough", 12, 3}, {"12x12", "exhaustive", 12, 4},
    {"10x10", "fastest", 10, 0}, {"10x10", "fast", 10, 1}, {"10x10", "medium", 10, 2}, {"10x10", "thorough", 10, 3}, {"10x10", "exhaustive", 10, 4},
    {"8x8", "fastest", 8, 0}, {"8x8", "fast", 8, 1}, {"8x8", "medium", 8, 2}, {"8x8", "thorough", 8, 3}, {"8x8", "exhaustive", 8, 4},
    {"6x6", "fastest", 6, 0}, {"6x6", "fast", 6, 1}, {"6x6", "medium", 6, 2}, {"6x6", "thorough", 6, 3}, {"6x6", "exhaustive", 6, 4},
};
```

#### 质量门槛与纯黑像素策略

下表列C++默认值。运行时可通过SetAstcQualityThresholds等接口覆盖，实际标签协议读取有效配置与tableConfig。LITE与主包阈值差异沿用[配置调查](notes/实际数据位置与训练可用性调查.md#lite与主包质量配置)中的记录。`[verified: ASTCCompressor.cpp L627–643、L1178–1205、L3590–3665、L3694–3735；配置调查“LITE与主包质量配置”]` `[opinion]`

| 贴图／策略条件 | 当前代码的判定方式与默认值 |
|---|---|
| 法线图 | `meanWavg ≤ 2.5° AND p95Wavg ≤ 7°`，PSNR留作参考。角度从参考／解压mip0及其最多四级法线降采样图计算，按像素数加权各级均值和各级p95。`[verified: ASTCCompressor.cpp L630–631、L2622–2673、L3198–3204]` |
| LDR、sRGB颜色图 | `PSNR ≥ effectivePSNRThreshold AND msSsimDb ≥ 24`。PSNR通过后才计算MS-SSIM，PSNR失败时msSsimDb保留0。`[verified: ASTCCompressor.cpp L629、L3206–3219]` |
| 其他分支，包括Linear或HDR | `PSNR ≥ effectivePSNRThreshold`。`[verified: ASTCCompressor.cpp L3222–3225]` |
| 纯黑RGB像素比例≤40% | 有效PSNR门槛采用基础值，默认35 dB。`[verified: ASTCCompressor.cpp L628、L2206–2208、L3167–3175]` |
| 纯黑RGB像素比例>40%且≤80% | 有效PSNR门槛默认40 dB。`[verified: ASTCCompressor.cpp L634–637、L3168–3174]` |
| 纯黑RGB像素比例>80% | 有效PSNR门槛默认42 dB，先判断这一档。`[verified: ASTCCompressor.cpp L636–637、L3168–3170]` |

PSNR、MS-SSIM和法线角度的数值方向及通道口径按[导出字段说明](#导出产物与字段口径)和对应实现读取。法线合格分支直接使用角度条件，纯黑比例设置的PSNR门槛还会参与RDO尝试余量判断。`[verified: ASTCCompressor.cpp L3198–3204、L2754–2787]`


默认质量、黑像素及精炼配置对应源码L627–643。`[verified: ASTCCompressor.cpp L627–643]`

```cpp
static float kTargetPSNR = 35.0f;
static float kTargetMSSSIMDb = 24.0f;
static float kTargetNormalAngleMeanWavgDeg = 2.5f;
static float kTargetNormalAngleP95WavgDeg = 7.0f;
static float kBlackPixelRatioForElevatedPsnrMild = 0.40f;
static float kBlackPixelElevatedPsnrMildDb = 40.0f;
static float kBlackPixelRatioForElevatedPsnrStrong = 0.80f;
static float kBlackPixelElevatedPsnrStrongDb = 42.0f;
static int kSizeFirstMinSideForLargeTexture = 512;
static float kAstcRdoRefineMinPsnrMarginDb = 1.0f;
```

有效PSNR门槛的分级计算对应源码L3167–3175。`[verified: ASTCCompressor.cpp L3167–3175]`

```cpp
float effectivePSNRThreshold = kTargetPSNR;
if (blackPixelRatio > kBlackPixelRatioForElevatedPsnrStrong)
{
    effectivePSNRThreshold = kBlackPixelElevatedPsnrStrongDb;
}
else if (blackPixelRatio > kBlackPixelRatioForElevatedPsnrMild)
{
    effectivePSNRThreshold = kBlackPixelElevatedPsnrMildDb;
}
```

按纹理类型设置isValid对应源码L3195–3226。`[verified: ASTCCompressor.cpp L3195–3226]`

```cpp
bool isValid = false;
float distance = psnr - effectivePSNRThreshold;
if (isNormalMap)
{
    NormalAngularResult ang = CalculateNormalAngularErrorMip0To3(originalDataPtr, decompressedRGBA32.data(), origWidth, origHeight, mipCount);
    angleMeanWavg = ang.meanWavgDeg;
    angleP95Wavg = ang.p95WavgDeg;
    isValid = (angleMeanWavg <= kTargetNormalAngleMeanWavgDeg) && (angleP95Wavg <= kTargetNormalAngleP95WavgDeg);
}
else if (!isHDR && useSRGB)
{
    if (psnr >= effectivePSNRThreshold)
    {
        msSsimDb = CalculateMSSSIMDb_Luma(originalDataPtr, decompressedRGBA32.data(), origWidth, origHeight);
        isValid = (msSsimDb >= kTargetMSSSIMDb);
    }
    else
    {
        msSsimDb = 0.0f;
        isValid = false;
    }
}
else
{
    isValid = (psnr >= effectivePSNRThreshold);
}
```

#### 常规搜索的接受与停止

常规路径在isValid为true后，将候选保存为bestResult，保存对应payload、格式与尺寸，并立即break。SharedResult初始bestResult.valid为false，因此实际流程是“按既定顺序接受首个合格候选”。`[verified: ASTCCompressor.cpp L673–683、L3293–3337]`

代码还列出了已存在有效bestResult时的比较次序，依次为payload字节更少、相同字节下PSNR更低、字节与PSNR都相同时qualityValue更低。当前常规路径首个有效候选即退出，解读行为时同时保留这个break，跨候选全量比较的评价需要额外候选测量。`[verified: ASTCCompressor.cpp L3293–3337]` `[opinion]`


常规候选比较、保存及break对应源码L3295–3339。`[verified: ASTCCompressor.cpp L3295–3339]`

```cpp
if (isValid)
{
    bool isBetter = false;
    if (sharedResult.bestResult.valid)
    {
        if (fileSize < sharedResult.bestResult.fileSize)
        {
            isBetter = true;
        }
        else if (fileSize == sharedResult.bestResult.fileSize)
        {
            if (psnr < sharedResult.bestResult.psnr)
            {
                isBetter = true;
            }
            else if (psnr == sharedResult.bestResult.psnr && param->qualityValue < sharedResult.bestResult.param->qualityValue)
            {
                isBetter = true;
            }
        }
    }
    else
    {
        isBetter = true;
    }
    if (isBetter)
    {
        sharedResult.bestDistanceToTarget = distance;
        sharedResult.bestResult = result;
        sharedResult.bestCompressedData = std::move(compressedData);
        sharedResult.bestTextureFormat = textureFormat;
        sharedResult.bestWidth = width;
        sharedResult.bestHeight = height;
        sharedResult.hasCompressedData = true;
        sharedResult.earlyExit = true;
        break;  // Exit the for loop immediately: we can stop testing other parameters since they will have larger file sizes or same size with higher quality
    }
}
```

#### 大图size-first的块大小锁定与回退

触发条件是`!isNormalMap AND !isHDR AND useSRGB AND width*height ≥ sizeFirstMinSideLarge²`，默认面积门槛为512²像素，1024×256也满足这一面积条件。`[verified: ASTCCompressor.cpp L640、L2988–2990；1024×256=512²]`

1. 从较大块开始搜索，首个PSNR达标候选锁定其blockSizeValue。`[verified: ASTCCompressor.cpp L620–625、L3241–3247]`
2. 锁定后，选择范围限定在同一块大小内，依preset顺序继续尝试，每个PSNR达标候选更新回退记录。`[verified: ASTCCompressor.cpp L3250–3269]`
3. 同组中某个PSNR达标候选同时满足MS-SSIM门槛时，立即接受并结束搜索。`[verified: ASTCCompressor.cpp L3260–3284]`
4. 同组始终未满足MS-SSIM时，采用该组最后一个PSNR达标候选。代码将该回退记录valid置为true，再保存为bestResult。`[verified: ASTCCompressor.cpp L3262–3264、L3348–3359]`

该分支允许以MS-SSIM门槛的放宽保留锁定块大小，因此策略接受状态与逐项质量阈值通过状态分别存储。锁组后的切组判断位于候选测量及allResults追加之后，报告可能含一条下一块大小的已测候选，该条在切组位置结束循环。`[verified: ASTCCompressor.cpp L3238–3256、L3262–3264、L3348–3359]` `[opinion]`


大图策略触发条件对应源码L2988–2990。`[verified: ASTCCompressor.cpp L2988–2990]`

```cpp
const long long pixelCountLL = (long long)origWidth * (long long)origHeight;
const long long sizeFirstPixelMin = (long long)kSizeFirstMinSideForLargeTexture * (long long)kSizeFirstMinSideForLargeTexture;
const bool useSizeFirstOnLargeTexture = (!isNormalMap && !isHDR && useSRGB && pixelCountLL >= sizeFirstPixelMin);
```

锁定块大小、保存组内回退及接受候选对应源码L3241–3291。`[verified: ASTCCompressor.cpp L3241–3291]`

```cpp
if (useSizeFirstOnLargeTexture)
{
    if (lockedBlockSizeValue < 0)
    {
        if (psnr >= effectivePSNRThreshold)
            lockedBlockSizeValue = param->blockSizeValue;
    }
    if (lockedBlockSizeValue >= 0)
    {
        if (param->blockSizeValue != lockedBlockSizeValue)
        {
            break;
        }
        if (psnr >= effectivePSNRThreshold)
        {
            sizeFirstFallbackResult = result;
            sizeFirstFallbackResult.valid = true; // acceptable for selection under size-first mode
            sizeFirstFallbackCompressedData = compressedData; // keep a copy for later selection
            sizeFirstFallbackTextureFormat = textureFormat;
            sizeFirstFallbackWidth = width;
            sizeFirstFallbackHeight = height;
            hasSizeFirstFallback = true;
            if (msSsimDb >= kTargetMSSSIMDb)
            {
                sharedResult.bestDistanceToTarget = distance;
                sharedResult.bestResult = result;
                sharedResult.bestResult.valid = true;
                sharedResult.bestCompressedData = std::move(compressedData);
                sharedResult.bestTextureFormat = textureFormat;
                sharedResult.bestWidth = width;
                sharedResult.bestHeight = height;
                sharedResult.hasCompressedData = true;
                sharedResult.earlyExit = true;
                selectedBySizeFirst = true;
                break;
            }
        }
    }
    continue;
}
```

锁定块的MS-SSIM回退落地对应源码L3349–3359。`[verified: ASTCCompressor.cpp L3349–3359]`

```cpp
if (useSizeFirstOnLargeTexture && !selectedBySizeFirst && lockedBlockSizeValue >= 0 && hasSizeFirstFallback)
{
    sharedResult.bestResult = sizeFirstFallbackResult;
    sharedResult.bestDistanceToTarget = sizeFirstFallbackResult.psnr - sizeFirstEffectivePSNRThreshold;
    sharedResult.bestCompressedData = std::move(sizeFirstFallbackCompressedData);
    sharedResult.bestTextureFormat = sizeFirstFallbackTextureFormat;
    sharedResult.bestWidth = sizeFirstFallbackWidth;
    sharedResult.bestHeight = sizeFirstFallbackHeight;
    sharedResult.hasCompressedData = true;
    sharedResult.earlyExit = false;
}
```

#### 全部未取得有效结果时的通用回退

SelectBestParameter在bestResult无效且allResults非空时，按严格大于比较选取PSNR最高的已测候选，PSNR并列时保留先出现的候选。该回退统一按PSNR执行，覆盖法线分支；随后仍返回true。allResults为空且bestResult无效时返回false。`[verified: ASTCCompressor.cpp L3371–3380、L3390–3422]`

因此success、策略接受、逐项质量通过、fallback原因和是否存在payload分别记录。最终JSON保存回退参数及质量数值，完整候选与valid／fallback信息需要采集清单或报告支持。`[verified: ASTCCompressor.cpp L3406–3419、L3506–3535、L1964–1975]` `[opinion]`


遍历已测候选选最高PSNR对应源码L3370–3381。`[verified: ASTCCompressor.cpp L3370–3381]`

```cpp
TestResult finalSelectedResult = bestResult;
if (!bestResult.valid && !sharedResult.allResults.empty())
{
    finalSelectedResult = sharedResult.allResults[0];
    for (const auto& result : sharedResult.allResults)
    {
        if (result.psnr > finalSelectedResult.psnr)
        {
            finalSelectedResult = result;
        }
    }
}
```

写出回退结果与无结果时返回失败对应源码L3407–3422。`[verified: ASTCCompressor.cpp L3407–3422]`

```cpp
if (!sharedResult.allResults.empty())
{
    *outBestParam = finalSelectedResult.param;
    *outBestPSNR = finalSelectedResult.psnr;
    if (outTempDir != NULL)
    {
        *outTempDir = tempDir;
    }
    if (outBestResultDetails != NULL)
    {
        *outBestResultDetails = finalSelectedResult;
    }
    return true;
}
return false;
```

#### 搜索后RDO精炼的尝试与接受

尝试RDO要求全局开启、余量参数>0、编码／解码接口可用、已有有效选中参数及payload，并且`winnerPSNR ≥ sharedResult.effectivePSNRThreshold + rdoRefineMarginDb`，默认余量为1 dB。精炼沿用选中的块大小与preset，额外执行一次编码与质量复测。`[verified: ASTCCompressor.cpp L643、L2754–2833、L2863–2900]`

精炼结果按纹理类型重新检查角度或PSNR／MS-SSIM门槛，并要求payload字节数≤原结果。通过后替换payload和最终指标，标记最终rdo为true。接受条件允许PSNR在通过门槛的前提下低于精炼前结果，精炼前后指标、attempted及status在调试结果中保留。`[verified: ASTCCompressor.cpp L2878–2953、L657–666、L1973、L2115–2158]`


RDO尝试前的开关、接口、有效结果及余量检查对应源码L2761–2788。`[verified: ASTCCompressor.cpp L2761–2788]`

```cpp
if (!Astc3rd_RdoEnabled)
{
    sharedResult.rdoRefineStatusLine = "skipped: global RDO (Astc3rd) off";
    return;
}
if (kAstcRdoRefineMinPsnrMarginDb <= 0.0f)
{
    sharedResult.rdoRefineStatusLine = Format("skipped: RDO refine PSNR headroom margin <= 0 (%.2f dB)", kAstcRdoRefineMinPsnrMarginDb);
    return;
}
if (Astc3rd_Enable != 1 || astc3rd_funcptr_optimize == NULL || astc3rd_decompress_funcptr == NULL)
{
    sharedResult.rdoRefineStatusLine = "skipped: Astc3rd encoder/decompressor not available";
    return;
}
if (!sharedResult.hasCompressedData || !sharedResult.bestResult.valid || sharedResult.bestResult.param == NULL)
{
    sharedResult.rdoRefineStatusLine = "skipped: no valid search winner or no compressed data";
    return;
}
const float eff = sharedResult.effectivePSNRThreshold;
if (sharedResult.bestResult.psnr < eff + kAstcRdoRefineMinPsnrMarginDb)
{
    sharedResult.rdoRefineStatusLine = Format("skipped: insufficient PSNR headroom for refine (winner %.2f dB < effective %.2f + margin %.2f)",
        sharedResult.bestResult.psnr, eff, kAstcRdoRefineMinPsnrMarginDb);
    return;
}
```

RDO结果的质量拒绝、大小检查及最终采用对应源码L2902–2953。`[verified: ASTCCompressor.cpp L2902–2953]`

```cpp
const long fileSize = compressedSize;
if (!isValid)
{
    if (isNormalMap)
    {
        sharedResult.rdoRefineStatusLine = Format(
            "skipped: RDO refine failed normal angular gates (mean=%.2f deg p95=%.2f deg; require mean<=%.2f p95<=%.2f)",
            angleMeanWavg, angleP95Wavg, kTargetNormalAngleMeanWavgDeg, kTargetNormalAngleP95WavgDeg);
    }
    else if (!isHDR && useSRGB)
    {
        if (psnr < effectivePSNRThreshold)
        {
            sharedResult.rdoRefineStatusLine = Format(
                "skipped: RDO refine failed PSNR gate (PSNR=%.2f dB < effective target %.2f dB)",
                psnr, effectivePSNRThreshold);
        }
        else
        {
            sharedResult.rdoRefineStatusLine = Format(
                "skipped: RDO refine failed MS-SSIM gate (MS-SSIM=%.2f dB < target %.2f dB; PSNR=%.2f dB passes)",
                msSsimDb, kTargetMSSSIMDb, psnr);
        }
    }
    else
    {
        sharedResult.rdoRefineStatusLine = Format(
            "skipped: RDO refine failed PSNR gate (PSNR=%.2f dB < effective target %.2f dB)",
            psnr, effectivePSNRThreshold);
    }
    return;
}
if (fileSize > sharedResult.bestResult.fileSize)
{
    sharedResult.rdoRefineStatusLine = "skipped: RDO refine larger than winner (unexpected for ASTC fixed block rate)";
    return;
}
sharedResult.bestResult.psnr = psnr;
sharedResult.bestResult.msSsimDb = msSsimDb;
sharedResult.bestResult.normalAngleMeanWavgDeg = angleMeanWavg;
sharedResult.bestResult.normalAngleP95WavgDeg = angleP95Wavg;
sharedResult.bestResult.fileSize = fileSize;
sharedResult.bestResult.valid = true;
sharedResult.bestDistanceToTarget = psnr - effectivePSNRThreshold;
sharedResult.bestCompressedData = std::move(compressedData);
sharedResult.bestTextureFormat = textureFormat;
sharedResult.bestWidth = width;
sharedResult.bestHeight = height;
sharedResult.hasCompressedData = true;
sharedResult.bestCompressedDataFromRdoRefine = true;
```

#### 标签协议与规则变更

离线数据按“参考像素及导入属性 → 当前规则选中的blockSize／preset／RDO状态”建立对应。更新候选顺序、质量阈值、黑像素策略、大图策略或回退条件时，记录源码／DLL版本和协议变化，重新评价已有标签有效性。表级配置变化、缓存复用与逐图重新测量的影响分开记录。`[verified: ASTCCompressor.cpp L1178–1205、L1372–1446、L3437–3462、L1964–1975]` `[opinion]`

### 批量采集时的执行约束

- **确定采集范围与后端**。目标格式为ASTC才进入该选参入口，自动选参开关及第三方编码／解码接口决定搜索是否执行。固定块大小与preset的直接编码和离线试参分别记录。`[verified: ImageOperations.cpp L2958–2968；ASTCCompressor.cpp L3738–3741、L3030–3031、L3131–3158]` `[opinion]`
- **处理缓存命中与调试开关**。参数缓存命中会在导出前返回。采集方案应显式选择缓存复用／重新测量方式，保存cache-hit与导出成功状态，图片导出需开启磁盘调试。`[verified: ASTCCompressor.cpp L3437–3462、L2963–2970]` `[opinion]`
- **建立稳定配对**。当前调试目录使用纹理名和进程内计数，参数表使用资产路径。建议采集清单保存资产路径、源文件MD4、参考图路径与哈希、导入设置、尺寸、颜色空间、用途、Alpha、mip、Editor／DLL版本及tableConfig。`[verified: ASTCCompressor.cpp L2001–2009、L1964–1973、L3466–3499]` `[opinion]`
- **记录候选覆盖和回退状态**。搜索按顺序执行并提前停止，allResults仅保存成功编码／解码后加入的候选。大图可能接受MS-SSIM未通过的PSNR候选，全部不合格时按最高PSNR回退。标签记录为“当前策略选中配置”，另存质量合格状态、回退原因、失败候选与未测候选。`[verified: ASTCCompressor.cpp L2979–2981、L3121–3125、L3157–3158、L3238–3239、L3262–3269、L3337、L3348–3419]` `[opinion]`
- **冻结质量协议**。按本次运行读取tableConfig与有效阈值，保留黑色像素和大图策略。已有LITE快照与主包阈值差异见[配置调查](notes/实际数据位置与训练可用性调查.md#lite与主包质量配置)，新标签按确认的项目标准生成。`[verified: ASTCCompressor.cpp L1178–1205、L3166–3175；配置调查“LITE与主包质量配置”]` `[opinion]`
- **分开保存候选表与最终表**。最终JSON／JSONL保存选中配置，候选指标位于allResults和调试报告。需要评价其他配置或oracle差距时，采集协议明确所需候选覆盖；法线角度指标、valid、earlyExit、回退与RDO尝试状态需追加到样本／候选清单。`[verified: ASTCCompressor.cpp L555–577、L645–671、L1873–1885、L2023–2178、L3238–3239]` `[opinion]`
- **检查实际落盘**。参数记录可能因源文件缺失、哈希失败、锁获取失败或追加写失败而跳过，采集完成后核对输入清单、参考图、候选报告、JSONL和快照的一致性。快照与尚未合并的日志共同读取，并核实实际缓存目录。`[verified: ASTCCompressor.cpp L1937–1939、L3506–3523、L1854–1897、L1372–1397]` `[opinion]`
- **先做小样本验收**。验证Unity导入阶段、参考像素一致性、候选测量复现、标签对应与真实字节数后再批量采集。本节验证深度为源码静态分析和文档检查，Unity实际导入／导出与编码实测按待运行记录。`[verified: 本次执行范围；用户“Smoke test first”要求]` `[opinion]`

## 代码组织与Class规范

核心实现按职责分包，并使用独立class组织模型、数据、训练、校准、评估与报告。后续新增功能沿用这一约定，具体执行要求同时写入[AGENTS.md](AGENTS.md#代码组织与class规范)。`[verified: 用户要求“MODEL，DATA，TRAIN这些按照规范需要全部分开”“全部以class的形式分开”及本次规范入文档要求]`

### 目录职责

下列路径均相对于`src/adaptive_astc/`，新增实现优先归入已有职责目录。`[opinion]`

| 目录或文件 | 主要class | 维护职责 |
|---|---|---|
| `models/` | `ASTCClassifier` | 网络结构、分类头与前向计算。`[opinion]` |
| `data/` | `TextureCatalog`、`ImagePreprocessor`、`DatasetSplitter`、`NearDuplicateIndex`、`DataPreparer`、`TextureDataset`、`TextureDataModule` | 目录筛选、预处理、划分、去重、清单、Dataset和DataLoader。`[opinion]` |
| `training/` | `Trainer` | 优化器、调度器、AMP、训练循环、验证选模和resume。`[opinion]` |
| `calibration/` | `TemperatureCalibrator` | 独立校准集上的拟合与校准产物。`[opinion]` |
| `evaluation/` | `Predictor`、`ClassificationMetrics`、`Evaluator` | 推理、指标计算、测试封存与预测导出。`[opinion]` |
| `reporting/` | `ReportGenerator` | 聚合结果的图表和Markdown报告。`[opinion]` |
| `tracking/` | `SwanLabTracker`、`MetricsUploader` | SwanLab运行生命周期、指标／图表上传和带来源指纹的历史结果导入。`[opinion]` |
| `utils/`、`config.py` | `ArtifactStore`、`CheckpointStore`、`RunEnvironment`、`ExperimentRuntime`、`TrainConfig`、`SwanLabConfig` | 通用持久化、检查点、运行环境及类型化配置，配置定义集中在`config.py`。`[opinion]` |
| `cli.py` | `ExperimentCLI` | 参数解析、组件构造、流程调度与运行回执。`[opinion]` |
| 仓库根目录`script/` | 公开启动脚本 | 读取共享配置并调用class入口，启动脚本集中放在此目录。`[verified: 用户要求“用脚本启动的脚本全部放到script里面”]` |

### 新增与修改代码

- **按职责定义class**。有状态组件通过实例持有配置、依赖和运行状态，纯计算方法可使用`staticmethod`。文件围绕一种主要职责组织，紧密相关的类可放在同一文件。`[opinion]`
- **沿用命名与接口**。类名使用`PascalCase`，模块和方法使用`snake_case`。复用已有class及其接口，并为所有Python函数参数与返回值提供类型注解，无返回值显式写`-> None`。`[opinion]` `[verified: 用户提供的Python Preferences]`
- **保持分层组合**。配置和工具支撑数据、模型、推理及指标，Trainer、校准器与评估器组合这些能力，CLI负责调用。数据准备与CLI帮助路径保持CPU依赖，Torch Dataset从`data.dataset`按需导入。`[opinion]`
- **通过class API扩展**。新业务逻辑放入对应class，旧函数入口通过薄适配委托给class，包入口负责导出与兼容。`[opinion]`
- **验证兼容性**。结构调整时核对CLI、检查点参数名与加载、初始化随机数顺序、resume状态、清单指纹及测试封存。先做小样本回归，再扩大运行范围，检查记录保存到`experiment report/`。`[opinion]`
- **使用统一工具链**。依赖通过`uv`管理，检查使用`uv run --frozen pytest -q`、`uv run --frozen ruff check src script tests`和`uv run --frozen basedpyright`，代码格式检查使用`uv run --frozen ruff format --check src script tests`。`[opinion]`

当前class与文件映射、调用流程和兼容性验证见[架构重构报告](<experiment report/class-refactor-20261110/README.md>)。`[verified: 对应报告“源码结构”“Class API”“验证范围”]`

## 脚本启动与SwanLab

启动脚本集中在[script/](script/)，五个入口共享[train_config.toml](script/train_config.toml)。先编辑`[training]`和`[swanlab]`，再从仓库根目录运行下面的命令。配置文件内的相对路径以该TOML所在目录为基准，显式命令行参数覆盖文件中的对应值。`[verified: script/五个入口的configuration参数；config.py的TrainConfig.load、SwanLabConfig.load]`

```powershell
uv sync --frozen
uv run --frozen python script/prepare.py
uv run --frozen python script/train.py
uv run --frozen python script/train.py --initialization scratch
uv run --frozen python script/calibrate.py --initialization pretrained
uv run --frozen python script/calibrate.py --initialization scratch
uv run --frozen python script/evaluate.py
```

准备数据时可通过`--exclude-manifest`重复传入试跑清单，复核既有GDC数据所用的排除项见[实验入口](<experiment report/README.md#复核本次实验>)。新配置的默认目录为`experiment report/.local/gdc-script-resnet18-seed20261109/`，公开报告目录为同名的`experiment report/`子目录。`[verified: cli.py的prepare参数；script/train_config.toml的run_dir、report_dir]`

```powershell
# 修改轮数和学习率
uv run --frozen python script/train.py --epochs 30 --learning-rate 0.01

# 从last.pt恢复，并复用该训练的SwanLab身份
uv run --frozen python script/train.py --resume

# 先保存离线记录，后续使用SwanLab的sync命令上传
uv run --frozen python script/train.py --swanlab-mode offline

# 上传同一配置目录中已经完成的训练、校准和测试结果
uv run --frozen python script/upload_metrics.py
```

`TrainConfig`集中管理路径、初始化、轮数、micro-batch、有效batch、workers、resume、每轮步数上限、学习率、momentum、weight decay、scheduler周期和seed。核心调用为`TrainConfig.load(...) → Trainer.from_config(...).fit()`。检查点恢复前会核对数据与优化配置，SwanLab身份记录在运行目录的`tracking/`，SDK日志保存在`swanlog/`。`[verified: config.py的TrainConfig；cli.py的ExperimentCLI.train；tracking/swanlab.py的identity_path与log_dir]`

脚本默认按TOML中的online模式上传，登录使用`uv run --frozen swanlab login`。可选择offline或disabled，项目、workspace和实验名可在TOML或命令行配置。逐轮记录train loss／accuracy、验证Accuracy／F1／NLL／Brier／ECE及逐类Precision／Recall／F1，另记录学习率、耗时、VRAM、RSS、校准温度、测试指标和报告图表。完整说明与实际云端记录见[脚本与SwanLab接入报告](<experiment report/script-swanlab-20261110/README.md>)。`[verified: script/train_config.toml；tracking/swanlab.py的log_epoch、log_metrics、log_report；本次SDK检查与验证记录]`

## 从这里阅读

- [Class架构与兼容性检查](<experiment report/class-refactor-20261110/README.md>)记录按职责拆分后的类、调用流程、旧检查点兼容与新旧数值对照。`[verified: src/adaptive_astc/models/resnet.py L10；training/trainer.py L32；对应verification.json]`
- [实验报告与复现入口](<experiment report/README.md>)集中记录数据划分、两组ResNet18、独立温度校准及验证结果，Python环境与命令统一使用uv。`[verified: 用户确认的实验方案；pyproject.toml的project.scripts]`
- [实际数据位置与训练可用性调查](notes/实际数据位置与训练可用性调查.md)及[聚合统计](notes/实际数据调查统计.json)，记录图片主体、快照差异、标签生成机制和训练所需证据。`[verified: 对应报告与统计文件]`
- [文献发展路线与问题演进](#文献发展路线与问题演进)，按已有问题、方法改进和剩余限制串联28篇文献，并说明本项目的位置。`[verified: 本文对应小节]`
- [逐篇文献简读与原文索引](reference/README.md)，按直接ASTC工作、神经纹理压缩与感知质量组织，分别记录阅读范围和原文可得性。`[verified: reference/README.md及逐篇笔记“来源与阅读范围”]`
- [演讲阅读笔记](<notes/GDC2023 ASTC贴图压缩参数选择 阅读笔记.md>)，按问题、标签生成、模型、结果及局限组织，附时间戳与截图。`[verified: 对应笔记内容]`
- [完整中文校订稿](materials/gdc2023-astc-parameter-selection/transcripts/完整中文校订稿.md)，保留开场、转场、结尾和歧义记录。`[verified: 对应全文稿内容]`
- [完整字幕对照](materials/gdc2023-astc-parameter-selection/transcripts/完整字幕对照.md)，逐条查看网站英文原字幕、中文原字幕与时间戳。`[verified: 对应对照稿001–328]`
- [原视频](materials/gdc2023-astc-parameter-selection/source/talk.mp4)、[中文SRT](materials/gdc2023-astc-parameter-selection/source/subtitles.zh.srt)、[英文SRT](materials/gdc2023-astc-parameter-selection/source/subtitles.en.srt)。`[verified: source目录文件]`
- [资料元数据](materials/gdc2023-astc-parameter-selection/source/material-metadata.json)、[检查结果](verification.json)与[整理取舍记录](implementation-notes.md)。`[verified: 对应文件]`
- [学术综述与相关研究](#学术综述与相关研究)，收录ASTC综述、相关论文导读及综述全部37条参考文献。`[verified: 本文“学术综述与相关研究”“综述完整参考文献”]`

演讲来源为 GDC Vault 的 Machine Learning Summit，页面标题为 *Parameter Selection for ASTC Mapping Compression Using Machine Learning*。`[verified: GDC演讲页Session Name、Track / Format、Game Developers Conference 2023]` [官方页面](https://www.gdcvault.com/play/1029226/Machine-Learning-Summit-Parameter-Selection)

## 资料目录

```text
materials/gdc2023-astc-parameter-selection/
├─ source/
│  ├─ talk.mp4
│  ├─ subtitles.zh.srt
│  ├─ subtitles.en.srt
│  └─ material-metadata.json
├─ frames/
│  ├─ frame_00m00s.png … frame_18m00s.png
│  └─ detail_时间戳.png
└─ transcripts/
   ├─ 完整中文校订稿.md
   └─ 完整字幕对照.md
notes/
└─ GDC2023 ASTC贴图压缩参数选择 阅读笔记.md
reference/
├─ README.md
├─ 逐篇英文短名.md
├─ verification.json
└─ papers/  本地PDF原文，Git排除
```

目录按原始资料、截图、文字整理和阅读笔记组织。Obsidian阅读副本位于 `E:\Obsidian_Note\3D_AI`，截图和全文稿在该Vault内有配套副本。`[verified: 交付目录与同步检查；opinion: 组织方式]`

本批论文笔记的Obsidian入口为`3D_AI/神经贴图与材质专题/AdaptiveASTC参考文献/AdaptiveASTC参考文献.md`。可获取的PDF原文分别归档在本仓库`reference/papers/`和Vault的`raw/AdaptiveASTC/`。Git同步阅读笔记、索引、校验记录和官方来源链接，PDF按两个目录的排除规则保存在本机。`[verified: reference/README.md；reference/.gitignore；Obsidian的.gitignore中raw/规则]`

## 视频与处理口径

原视频通过Git LFS管理。克隆仓库前安装Git LFS，克隆后执行以下命令拉取视频原件。`[verified: .gitattributes中的*.mp4规则；GitHub文档“Collaboration with Git Large File Storage”]` [Git LFS协作文档](https://docs.github.com/en/repositories/working-with-files/managing-large-files/collaboration-with-git-large-file-storage)

```powershell
git lfs install --local
git lfs pull
```

| 字段 | 内容 |
|---|---|
| 归档日期 | 2026-11-09。`[verified: 本次归档记录]` |
| 时长 | 1098.030233秒，约18分18秒。`[verified: ffprobe format.duration]` |
| 画面／音频 | 1920×1080，H.264视频，AAC音频。`[verified: ffprobe streams]` |
| 视频文件字节 | 139,878,671 bytes，约133.4 MiB。`[verified: 本地文件长度]` |
| SHA-256 | `10be7c3d136dbe5f2d6028ac0a3369bf139abaabab8994974f6e1b5fd711ed63`，完整值另列于下方。`[verified: 视频原件与副本Get-FileHash输出]` |
| 字幕来源 | 播放器公开的English和Chinese字幕轨，经FFmpeg整理为SRT，切片交界处重复事件由工具消重。`[verified: 网站HLS字幕列表；FFmpeg字幕下载输出]` |
| 固定截图 | 从0秒起，每60秒一张，末张1080秒，共19张，保持1920×1080。`[verified: 提取参数与verification.json]` |

完整SHA-256如下。`[verified: 视频原件与归档副本哈希]`

```text
10be7c3d136dbe5f2d6028ac0a3369bf139abaabab8994974f6e1b5fd711ed63
```

## 已核实的方法与待核实问题

### 正文呈现的方法

1. 对贴图尝试不同ASTC块大小，压缩并解压，计算PSNR。`[verified: 11:28 Calculate Label页]`
2. 根据画质与码率目标生成块大小标签。目标页举例为PSNR > 35.0时尽量增大块大小。`[verified: 11:00 Optimization Target页]`
3. 使用标签训练图像分类模型，由模型为新贴图预测块大小。结构页使用ResNet。`[verified: 10:00 Model Structure页；12:28 Network Structure页]`
4. 与固定6×6、固定12×12及直接使用标签的Best方案比较。`[verified: 15:00、16:00、16:30结果表]`

### 需要保留的证据边界

- 官网Overview包含reinforcement learning措辞，正文已核实到的是监督分类流程。RL相关的状态、动作、奖励及训练更新规则仍待补充材料确认。`[verified: 官方Overview；10:00、11:28、12:28画面；opinion: 机制归类与核实边界]`
- 参数选择粒度为整张贴图，分类输出是ASTC块大小。`[verified: 10:14–10:41字幕；10:00输入贴图到Block-Size图]`
- 标签选择目标、分类网络训练损失及部署时逐图质量验收分别需要记录。演讲画面给出了前者示例，分类损失、无可行标签时的处理和部署质量回退尚待核实。`[verified: 11:00–12:28画面及字幕；opinion: 后续实现需明确的接口]`
- 中英文字幕均有错误。PSNR方向、文件大小和部分口述词句的冲突已在全文稿中逐处记录。`[verified: 完整中文校订稿“校订与待核对记录”]`
- 视频参考页列出ASTC原始论文、ResNet论文与Arm文档；本次尚未确认这项选参方案单独发表的论文或代码。`[verified: 17:57参考页；当前资料范围]`

## 演讲报告值

以下数据从视频表格抄录，原表中的MB及Std (PSNR)标注照录。`[verified: 15:00、16:00、16:30结果表]`

| 方法 | 平均PSNR | 原表Std (PSNR) | Size (MB) |
|---|---|---|---|
| 固定6×6 | 40.38 | 80.73 | 83.25。`[verified: 15:00]` |
| 模型选参 | 36.36 | 47.98 | 47.21。`[verified: 15:00、16:00、16:30]` |
| 固定12×12 | 31.55 | 76.85 | 21.19。`[verified: 16:00]` |
| 标签Best | 36.27 | 43.17 | 43.50。`[verified: 16:30]` |

Std的统计定义、MB计量口径、mip是否计入、逐贴图质量分布及样本列表仍待原始材料核实。`[opinion: 复现实验需要补齐的信息]`

## 后续研究方向

- 优先研究块大小分类模型的概率校准与选参决策校准，按“研究顺序与分类校准”中的独立测试和生产指标评估，质量预测回归及其校准作为后续备选。`[verified: 用户研究决策（2026-11-09）“先研究这个，如果不行，在研究预测质量的calibration”]`
- 以项目当前固定8×8为生产基线，补充固定6×6、固定12×12与按质量目标穷举的标签对照，冻结编码器版本、质量preset、颜色空间、贴图通道、mip和尺寸取整规则。`[verified: 用户需求说明（2026-11-09）“目前项目全都是统一使用8*8”；opinion: 实验对照设计]`
- 小样本检查压缩、解压、质量测量和真实字节统计，再扩大到有标签的分类数据集。报告失败样本和不满足质量目标的比例。`[opinion]`
- 比较模型预测与穷举标签的体积差、质量违规率及处理成本，分别统计数据集生成、训练、推理和最终ASTC编码。`[opinion]`
- 按材质类型和项目划分评估，研究卡通颜色贴图之外的泛化，单列Alpha、法线和mip质量。`[opinion]`
- 优先用小样本核对Unity导入前后差异，明确训练输入、质量参考图与标签的数据对应关系，再确定可维护的数据采集流程。`[opinion]`
- 若后续研究强化学习，单独定义需要序列决策的对象、状态、动作、奖励与预算，并与现有监督分类基线做同口径比较。`[opinion]`

## 参考入口

- ASTC格式原始论文 *Adaptive Scalable Texture Compression*，HPG 2012，DOI `10.2312/EGGH/HPG12/105-114`。`[verified: 视频17:57参考页；论文首页]` [论文PDF](https://www.cs.cmu.edu/afs/cs/academic/class/15869-f11/www/readings/nystad12_astc.pdf)
- ResNet论文 *Deep Residual Learning for Image Recognition*。`[verified: 视频17:57参考页；arXiv 1512.03385标题与作者]` [论文页面](https://arxiv.org/abs/1512.03385)
- Arm ASTC编码器与文档。`[verified: 视频17:57参考页第3项；Arm官方仓库README]` [官方仓库](https://github.com/ARM-software/astc-encoder)

## 学术综述与相关研究

### ASTC综述

In-hyuk Jeong、Jae-Ho Nah，*An Analytical Survey of ASTC Encoding Techniques*，IEEE Computer Graphics and Applications，2026，DOI `10.1109/MCG.2026.3732851`。作者提供的PDF标注为预印本，并列出正式版本DOI。`[verified: 作者主页“Selected Publications”对应条目；综述PDF页脚]` [作者PDF](https://nahjaeho.github.io/papers/CGA26_paper.pdf)、[正式版本](https://doi.org/10.1109/MCG.2026.3732851)、[作者主页](https://nahjaeho.github.io/)

综述讨论ASTC分区、颜色编码、块大小与编码速度／质量权衡，并汇总相关研究。与本仓库直接相关的章节为第8页TexNN介绍、第12页“Block size configuration”，完整参考文献位于第13–14页。`[verified: 综述PDF第1页Abstract、第8页TexNN段落、第12页对应小节、第13–14页REFERENCES]` [综述PDF](https://nahjaeho.github.io/papers/CGA26_paper.pdf)

### 自动块大小选择与学习式编码

- **ASTC Block-Size Determination Method based on PSNR Values**。Jae-Ho Nah，Journal of the Korea Computer Graphics Society，28(2)，21–28，2022，DOI `10.15701/kcgs.2022.28.2.21`。按目标PSNR自动选择纹理块大小。作者后续综述说明，选参阶段使用fastest模式，最终编码使用thorough模式。书目信息由作者主页核实，方法细节依据作者后续综述，原论文全文抓取超时。`[verified: 作者主页“Domestic Papers”对应条目；综述PDF第12页“Block size configuration”]` [论文入口](https://doi.org/10.15701/kcgs.2022.28.2.21)、[作者主页](https://nahjaeho.github.io/)、[综述对应页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=12)
- **Addition of an adaptive block-size determination feature to astcenc, the reference ASTC encoder**。Jae-Ho Nah，Software Impacts，17，100569，2023，DOI `10.1016/j.simpa.2023.100569`。将目标PSNR驱动的块大小搜索集成进修改版astcenc，配套仓库以`-dbtarget 40`演示调用。`[verified: 论文Abstract；配套仓库README“A Note from Jae-Ho Nah”及示例命令]` [论文](https://doi.org/10.1016/j.simpa.2023.100569)、[配套代码](https://github.com/SoftwareImpacts/SIMPAC-2023-337)
- **TexNN: Fast Texture Encoding Using Neural Networks**。Srihari Pratapa、Tom Olson、Alex Chalfin、Dinesh Manocha，Computer Graphics Forum，38(1)，328–339，2019，DOI `10.1111/cgf.13534`，2018年在线发表。将编码搜索转成分类，用网络预测partition、endpoint mode和weight decimation等块内部配置，保留标准ASTC码流。`[verified: 出版页First published、Abstract、How to cite；综述PDF第8页TexNN段落]` [论文](https://doi.org/10.1111/cgf.13534)

这些工作可分别作为质量目标驱动搜索、可调用自动选参实现和学习式编码决策的比较入口。整张贴图的块大小选择与块内部配置预测应分别设计实验。`[opinion]`

### 渲染感知的纹理参数优化

- **Selecting texture resolution using a task-specific visibility metric**。Krzysztof Wolski、Daniele Giunchi、Shinichi Kinuwaki、Piotr Didyk、Karol Myszkowski、Anthony Steed、Rafał K. Mantiuk，Computer Graphics Forum／Pacific Graphics，2019，DOI `10.1111/cgf.13871`。考虑几何、光照、材质贴图相互作用及观察位置，通过感知实验调整可见性指标，在游戏引擎中选择albedo、normal等纹理的分辨率。项目页提供论文、数据集与CNN指标代码。`[verified: 出版页Abstract与发表年份；作者项目页Abstract、Materials]` [论文](https://doi.org/10.1111/cgf.13871)、[项目与代码入口](https://texture-metrics.mpi-inf.mpg.de/)

这项工作的决策参数为纹理分辨率，与ASTC块大小选择相邻，可用于研究渲染条件和感知评价如何进入选参流程。`[opinion]`

### 神经纹理压缩与替代表示

- **Random-Access Neural Compression of Material Textures**。Karthik Vaidyanathan、Marco Salvi、Bartlomiej Wronski、Tomas Akenine-Möller、Pontus Ebelin、Aaron Lefohn，ACM Transactions on Graphics／SIGGRAPH，42(4)，Article 88，2023，DOI `10.1145/3592407`。联合压缩材质的多张纹理及mip链，为每个材质优化小型神经解码器，支持随机访问和实时解压。`[verified: NVIDIA作者页正文、Authors、Publication Date、Published in；综述PDF参考文献36]` [论文](https://doi.org/10.1145/3592407)、[作者页与项目入口](https://research.nvidia.com/publication/2023-08_random-access-neural-compression-material-textures)
- **Neural Texture Block Compression**。Shin Fujieda、Takahiro Harada，Workshop on Joint MAM–MANER Conference，2024，DOI `10.2312/mam.20241178`，arXiv `2407.09543`。学习生成BC格式的块压缩数据，在纹理加载阶段重建块压缩纹理，研究存储体积和加载开销。`[verified: arXiv页面Authors、Journal reference、Related DOI；论文Abstract及第1节]` [论文与全文](https://arxiv.org/abs/2407.09543)、[出版入口](https://doi.org/10.2312/mam.20241178)
- **Hardware Accelerated Neural Block Texture Compression with Cooperative Vectors**。Laurent Belcour、Anis Benyoub，High-Performance Graphics，2025，arXiv `2506.06040`。结合块压缩和PBR多通道神经表示，利用硬件矩阵运算降低运行时成本，讨论纹理过滤支持。`[verified: arXiv页面Abstract、Journal reference；综述PDF参考文献37作者顺序]` [论文与全文](https://arxiv.org/abs/2506.06040)
- **Compact Representation of Mipmapped SVBRDFs via Shared Gaussians**。Fengdi Zhang、Haocheng Ren、Qing Luo、Yaqing Li、Jibing Lou、Hongwei Li，2026年7月30日提交的预印本，arXiv `2607.27943`。提出Gaussian Texture Compression，利用多张材质贴图和不同mip层共享的二维高斯结构，研究随机访问、质量和内存权衡。`[verified: arXiv页面Submitted on、Authors、Abstract]` [预印本与全文](https://arxiv.org/abs/2607.27943)

阅读这些工作时，应分别记录参数选择、编码器加速、存储侧压缩表示、运行时解码表示，以及各自的硬件和过滤要求。对比范围由目标平台与实际资产用途确定。`[opinion]`

### 文献发展路线与问题演进

这批文献可以沿四类问题阅读，分别是编码搜索成本、纹理参数分配、可见质量评价，以及压缩表示与部署成本。下文的路线组织属于跨论文归纳，直接继承关系另按作者表述标明。`[opinion]`

| 研究问题 | 问题如何推进 |
|---|---|
| 编码搜索成本 | 从减少分区／端点搜索，推进到学习配置预测，以及为特定用途裁剪配置空间。`[opinion]` |
| 纹理参数分配 | 从固定footprint和人工设置，推进到目标质量搜索、图内可变分配与学习式整图选参。`[opinion]` |
| 可见质量评价 | 从单张贴图的误差，推进到渲染上下文、主观可见性实验与任务专用指标。`[opinion]` |
| 压缩表示与部署 | 从逐图块压缩，扩展到多通道／多mip联合表示，再处理神经解码、逐材质优化与系统集成成本。`[opinion]` |

#### 编码器加速，从昂贵搜索到近似与学习

这一组工作的共同问题是编码配置的探索成本。各方法分别利用颜色几何、图像分割、启发式或神经预测缩小搜索范围，质量与速度的取舍仍由各自用途和实验协议决定。`[opinion]`

| 工作 | 针对的问题与方法改进 | 剩余限制或取舍 |
|---|---|---|
| FasTC，2013 | 用颜色包围盒估计分区、cluster fit近似端点，再以模拟退火细化，减少昂贵的块配置搜索。`[verified: FasTC原文§3.5–3.7；对应简读“核心方法”]` [简读](reference/FasTC.md) | 主要实验为BPTC，速度结果绑定历史编码器与细化预算。`[verified: 对应简读“实验与证据”“局限与AdaptiveASTC关联”]` |
| SegTC，2014 | 先做整图超像素分割，再将块内分割匹配到预定义分区，借助图像结构减少逐块搜索。`[verified: SegTC原文§3；对应简读“核心方法”]` [简读](reference/SegTC.md) | 实验为BPTC，超像素参数、Alpha和单子集竞争仍带来限制。`[verified: 对应简读“局限与AdaptiveASTC关联”]` |
| Real-Time ASTC for the Web，2016 | 面向浏览器缓冲区实时编码，以启发式替代分支定界搜索，主要实现4×4 ASTC。`[verified: 学位论文Abstract、§4；对应简读“核心方法”]` [简读](reference/RealtimeASTCWeb.md) | 作者承认质量仍低于目标参考编码器，低端设备也可能达不到实时要求。`[verified: 对应简读“实验与证据”]` |
| TexNN，2019 | 用P-NN预测分区，用DEM-NN预测权重缩减与端点模式，以训练数据近似昂贵的ASTC块内部搜索。`[verified: 在线原文§3.2–3.4；对应简读“核心方法”]` [简读](reference/TexNN.md) | 分类对象是块内部配置，不同footprint分别训练。整图footprint选择还需独立定义目标。`[verified: 对应简读“核心方法”]` `[opinion]` |
| Pruned Lightweight Encoders，2022 | 将ASTC配置空间裁剪到单一内部配置，以SIMD加速，再用压缩域数据重训练下游分类／分割网络。`[verified: 原文§III–IV；对应简读“核心方法”]` [简读](reference/PrunedASTC.md) | 目标是机器视觉任务性能，重训练后仍有任务损失，人眼质量需另行评价。`[verified: 对应简读“实验与证据”]` `[opinion]` |

从这些工作抽出的共同思路是，把重复搜索中的规律变成可复用的结构或模型。对本项目，需要进一步明确复用发生在整图footprint决策还是块内部编码阶段。`[opinion]`

#### 自动选参，从统一配置到质量约束与学习式决策

| 工作 | 针对的问题与方法改进 | 剩余限制或取舍 |
|---|---|---|
| PSNR Block-Size Determination，2022 | 人工逐图设置难以扩展，全候选高质量编码成本又高。采用类别级人工预分析、fastest目标PSNR搜索与thorough最终编码。`[verified: 原文Abstract、§3.1–3.2；对应简读“核心方法”]` [简读](reference/PSNRBlockSize.md) | 仍有人工预分析和试探编码，质量目标依赖类别与PSNR。论文计时排除预分析。`[verified: 对应简读“核心方法”“实验与证据”]` |
| Adaptive astcenc，2023 | 将目标PSNR选块集成到修改版astcenc，软件接口以`-dbtarget`指定目标。作者后续综述描述其用部分像素评价以减少选参成本。`[verified: 软件README L1–8；综述p.12；对应简读“核心方法”]` [简读](reference/AdaptiveASTCEncoder.md) | 当前证据覆盖摘要、软件说明与综述，实际达标率和耗时仍待同口径复核。`[verified: 对应简读“来源与阅读范围”]` `[opinion]` |
| VBTC，2016，局部分配分支 | 增加间接寻址，使同一纹理内部采用不同块大小，把更多比特分配给细节区域。`[verified: 官方摘要；对应简读“核心方法”]` [简读](reference/VBTC.md) | 需要额外寻址及硬件解码支持，部署条件与整张纹理选一个footprint有所区别。`[verified: 综述p.13；对应简读“局限与AdaptiveASTC关联”]` |

GDC 2023演讲提供另一条学习式路径，离线尝试多个footprint并按质量／体积目标生成标签，再用ResNet预测整图块大小。这与上述质量搜索工作可以按共同问题对照，演讲与这些论文之间的直接技术承继仍需作者资料支持。`[verified: 演讲10:00、11:00–12:28；演讲阅读笔记“标签生成”“分类网络与训练信息”]` `[opinion]` [演讲笔记](<notes/GDC2023 ASTC贴图压缩参数选择 阅读笔记.md>)

本项目在学习式选参上优先研究分类calibration。需要检验的具体问题是，置信度是否能支持更好的质量／字节决策。统一正温度的temperature scaling保持argmax，继续按argmax选参时，最终候选保持一致。因此概率校准指标与质量违规率、字节损失应分别报告，并单独评价使用校准概率的决策规则。`[verified: 本文“研究顺序与分类校准”；Guo等§4.2]` `[opinion]` [校准方法原文](https://proceedings.mlr.press/v70/guo17a/guo17a.pdf#page=6)

#### 质量评价，从贴图误差到渲染可见性

| 工作 | 针对的问题与方法改进 | 剩余限制或取舍 |
|---|---|---|
| Texture IQA，2014 | 通过多视点原始／压缩纹理渲染对比，把几何映射和diffuse、gloss、bump之间的掩蔽纳入评价。`[verified: 原文§3–5；对应简读“核心方法”]` [简读](reference/TextureIQA.md) | 测量需给定场景与视点，论文数值与项目接受阈值的关系仍需标定。`[opinion]` |
| Texture Masking IQA，2015 | 官方摘要继续研究渲染视点采样、贴图类别敏感性和掩蔽效应，目标是在最终渲染质量约束下减少码率。`[verified: NIST Abstract；对应简读“核心方法”“实验与证据”]` [简读](reference/TextureMaskingIQA.md) | 当前为摘要级阅读，相对2014年方法的具体增量待全文核实。`[verified: 对应简读“来源与阅读范围”]` |
| Psychophysical Masking，2019 | 通过受控2AFC实验研究diffuse与normal相互掩蔽，直接测量ASTC伪影何时可见，检查纹理指标与人类检测的关系。`[verified: 原文§3–4、§6；对应简读“核心方法”“实验与证据”]` [简读](reference/PsychophysicalMasking.md) | 光照、贴图组合和实验刺激影响结论，迁移到完整游戏场景仍需验证。`[verified: 对应简读“局限与AdaptiveASTC关联”]` `[opinion]` |
| Task-specific Visibility，2019 | 针对任务专用主观数据稀缺，先用已有指标产生大批预测，再用少量感知实验修正并训练CNN指标，应用于albedo／normal分辨率选择。`[verified: 作者项目页Abstract；原文§6–8]` [简读](reference/TextureVisibility.md) | 优化变量为分辨率。将其适配到ASTC选块或Unity导入域，需要新的任务数据和评价。`[verified: 对应简读“核心方法”]` `[opinion]` |
| FLIP，2020 | 为交替显示参考图和测试图时的差异设计误差图，结合颜色、边缘、点状特征及观看条件。`[verified: 原文§1–2；对应简读“核心方法”]` [简读](reference/FLIP.md) | 原始版本§2明确其不能检测视觉掩蔽，可能高估被遮蔽差异。指标阈值仍需结合项目条件建立。`[verified: 对应简读“局限与AdaptiveASTC关联”]` `[opinion]` |

这一组工作的启发是，将“质量达标”的定义与实际使用场景联系起来。PSNR 35 dB可以作为本项目的经验基线，法线、MSAK及最终渲染质量的阈值还需要分别建立。任务专用感知指标的适配与分类置信度校准具有不同的评价对象，实验时应分别测量。`[opinion]` [可见性指标项目](https://texture-metrics.mpi-inf.mpg.de/)

#### 神经纹理，从联合表示到硬件、训练与解码效率

这条路线把同一材质的多个通道与mipmap作为联合信号。NTC提出量化特征与逐材质MLP的随机访问表示，后续工作分别改进率失真、压缩感知训练、硬件过滤、编码成本和GPU执行效率。`[verified: NTC Abstract、§4；HyperNTC §2.1]` [NTC原文](https://arxiv.org/html/2305.17105)、[后续工作梳理](https://arxiv.org/html/2606.26913v1)

| 工作 | 针对的问题与方法改进 | 剩余限制或取舍 |
|---|---|---|
| NTC，2023 | 联合压缩多张材质属性贴图及mipmap，以量化特征金字塔和小型MLP支持按坐标、LOD随机解码。`[verified: 原文Abstract、§4；对应简读“核心方法”]` [简读](reference/NTC.md) | 逐材质优化、神经解码及过滤均需计算，论文单列了编码与渲染成本。`[verified: 对应简读“实验与证据”“局限与AdaptiveASTC关联”]` |
| NGTC／CNTC，2024 | 针对神经图像压缩适配随机访问、多mip和多通道的困难，采用不对称编码／解码架构、量化网格和按尺度采样。`[verified: 原文Abstract、§4；对应简读“核心方法”]` [简读](reference/NGTC.md) | 仍逐纹理集合训练，作者讨论mip间插值引起aliasing的限制。`[verified: 对应简读“核心方法”“局限与AdaptiveASTC关联”]` |
| BC Neural Materials，2024 | 将特征直接参数化为BC6块，训练时模拟解码，让特征支持硬件纹理过滤，减轻神经材质的运行时集成负担。`[verified: 原文§1、§4–5；对应简读“核心方法”]` [简读](reference/BCNeuralMaterials.md) | 直接压缩训练后特征会产生伪影，因此需将压缩结构纳入训练，渲染仍执行MLP。`[verified: 原文§4 Figure 3；对应简读“局限与AdaptiveASTC关联”]` |
| NBC，2025 | 将块压缩推广到神经特征域，用多尺度基础／残差特征及分层量化改善低码率表示，默认采用8／4／2／1 bit分配。`[verified: 原文§3.2–3.4；对应简读“核心方法”]` [简读](reference/NBC.md) | 文中的variable bitrates指特征层的量化分配，仍需训练特征和MLP并执行神经解码。`[verified: 对应简读“核心方法”“局限与AdaptiveASTC关联”]` |
| DBC，2025 | 针对块压缩误差与后续模型损失不一致，将编码、解码纳入端到端优化，用可微近似、配置采样和Mixture of Partitions处理离散配置。`[verified: 原文Abstract、§3–4；对应简读“核心方法”]` [简读](reference/DBC.md) | 重点为BC6／BC7。作者说明直接压缩普通albedo时通常不会优于标准编码器，并将ASTC列为未来扩展。`[verified: 对应简读“局限与AdaptiveASTC关联”]` |
| Cooperative Vectors，2025 | 作者明确扩展BC Neural Materials，改用BC1特征与新分辨率布局，通过tile组织和硬件矩阵乘加速MLP，并支持各向异性过滤。`[verified: 原文Abstract、§1、§3–4]` [简读](reference/CooperativeVectorNTC.md) | 混合材质tile仍需分类与重排，原子分配有扩展性成本。`[verified: 原文§6；对应简读“局限与AdaptiveASTC关联”]` |
| HyperNTC，2026 | 针对逐材质梯度优化昂贵，训练共享hypernetwork，一次产生BC1潜在纹理及该材质MLP权重，将逐资产优化成本摊销到共享训练。`[verified: 原文Abstract、§3、§5]` [简读](reference/HyperNTC.md) | 仍需共享训练及运行时解码，原文比较中PSNR与MS-SSIM优势并不一致。`[verified: 对应简读“实验与证据”“局限与AdaptiveASTC关联”]` |
| Thread-Efficient NTC，2026，预印本 | 针对同一GPU wave访问不同材质MLP的执行分歧，将纹理聚类并共享解码器，采用逐步冻结的训练策略。`[verified: 原文Abstract、§2–3]` [简读](reference/ThreadEfficientNTC.md) | 共享程度带来重建质量取舍，聚类参数和GPU微基准的适用范围仍需保留。`[verified: 对应简读“实验与证据”“局限与AdaptiveASTC关联”]` |

其中BC Neural Materials → Cooperative Vectors的扩展关系由后者明确陈述。HyperNTC沿用BCF1表示并解决逐材质优化成本，Thread-Efficient NTC则处理多网络执行分歧。将这些工作串成“先压得下，再降低使用成本”的问题链属于本文归纳。`[verified: Cooperative Vectors §1；HyperNTC §2.1、§3.2；Thread-Efficient NTC §2–3]` `[opinion]` [硬件加速原文](https://arxiv.org/html/2506.06040)、[HyperNTC原文](https://arxiv.org/html/2606.26913v1)、[共享解码原文](https://arxiv.org/html/2608.27888v1)

#### 其他表示与系统分支

| 工作 | 针对的问题与方法改进 | 剩余限制或取舍 |
|---|---|---|
| NTBC，2024，加载阶段重建 | 为减少标准块纹理的存储开销，保存紧凑神经模型，在加载阶段生成BC1／BC4块，渲染继续使用BC纹理采样。`[verified: 原文Abstract、§3.2、§4.4]` [简读](reference/NTBC.md) | 节省对象为存储，重建与上传增加加载成本，显存收益应另测。`[verified: 对应简读“核心方法”“实验与证据”]` `[opinion]` |
| Image-GS，2025 | 用内容自适应二维高斯分配表达能力，以局部高斯查询支持随机访问与预算控制。`[verified: 原文§3；对应简读“核心方法”]` [简读](reference/ImageGS.md) | 需要专用查询实现，表现依赖图像内容与预算，低码率比较的mip降采样协议需保留。`[verified: 对应简读“实验与证据”“局限与AdaptiveASTC关联”]` |
| Shared Gaussian SVBRDF／GTC，2026，预印本 | 在多通道和多mip之间共享二维高斯支撑，并用残差初始化、稀疏正则和剪枝减少冗余，实现非神经随机访问解码。`[verified: 原文§3.2–3.4；对应简读“核心方法”]` [简读](reference/SharedGaussianSVBRDF.md) | 逐资产优化与高频纹理仍有代价，PSNR和FLIP的比较优势存在冲突。`[verified: 对应简读“实验与证据”“局限与AdaptiveASTC关联”]` |
| JPEG Textures，正式版2026 | 针对变码率图像格式的实时随机访问困难，引入索引、按需MCU解码和跨帧块缓存，在渲染系统层面支持JPEG纹理。`[verified: 原文Abstract、§4–5；对应简读“核心方法”]` [简读](reference/JPEGTextures.md) | 索引、缓存与解码带来额外开销，效果依赖缓存命中、质量及mip使用。`[verified: 对应简读“实验与证据”“局限与AdaptiveASTC关联”]` |
| TexF，2026，预印本 | 针对UV映射载荷与空间关系被切分的问题，将纹理属性组织为表面对齐的稀疏三维场，并研究存储码流及GPU驻留神经压缩。`[verified: 原文§I、§III；对应简读“核心方法”]` [简读](reference/TexF.md) | 高效UV资产、近邻表面混合、过滤支持和逐资产优化仍有取舍。`[verified: 对应简读“实验与证据”“局限与AdaptiveASTC关联”]` |

Multi-output ASTC Decoder，2017，研究相邻2×2 texel解码时重复计算的问题，通过共享块配置、端点和权重计算改善性能／面积。它属于解码电路路线，收益依赖请求跨块情况及位置、footprint分布假设。`[verified: 原文§2–3；对应简读“核心方法”“实验与证据”]` [简读](reference/MultiOutputASTC.md)

ASTC Encoding Survey，2026，汇总编码结构、加速、自动选块与相关表示，可作为上述路线的技术地图。其比较设置和对其他论文的转述范围需要分别保留。`[verified: 原文p.8、p.12–14；对应简读“核心方法”“实验与证据”]` [简读](reference/ASTCEncodingSurvey.md)

#### AdaptiveASTC在这些路线中的位置

- 当前研究问题是，在给定质量标准与候选footprint下，以尽量少的生产选参成本获得质量／体积可接受的结果。固定8×8为生产基线，分类校准优先，质量预测校准作为经实验决定的后续备选。`[verified: 用户需求；本文“项目需求与优化目标”“研究顺序与分类校准”]`
- 与搜索式选参比较时，需要同时测量真实总字节、逐图质量违规、按贴图类别结果，以及离线标签构建和生产推理／编码成本。2022年论文总字节下降与逐图等权bpp上升并存，说明两种汇聚口径都值得保留。`[verified: PSNRBlockSize原文Table 2；对应简读“实验与证据”]` `[opinion]`
- 分类校准研究需要连接“概率可信度”和“实际选参结果”。其研究价值由独立资产测试中的质量违规率、字节损失与成本决定，本批文献尚不足以确立该组合的新颖性或效果。`[opinion]`
- 法线／MSAK的任务质量、Unity导入域的数据对应关系，以及跨资产／跨项目泛化，属于本项目需要采集数据并验证的环节。感知与神经纹理文献提供方法线索，采用前需明确各自的表示与部署条件。`[opinion]`

### 文献核实口径

- 上述导读依据已读取的论文摘要、作者项目页与综述对应章节。2022年自动选参论文的原文访问限制已在条目中注明，2026年高斯表示按预印本记录。`[verified: 上述条目的来源与访问说明]`
- 下方完整书目按作者PDF第13–14页REFERENCES转录，保持原编号。每条的核实范围为综述中的书目信息，另有原始来源核实的导读见上文。`[verified: 综述PDF第13–14页REFERENCES 1–37]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)

### 综述完整参考文献

1. Microsoft，*Texture block compression in Direct3D 11*，2020。`[verified: 综述PDF第13页参考文献1]` [文档](https://learn.microsoft.com/en-us/windows/win32/direct3d11/texture-block-compression-in-direct3d-11)
2. Jacob Ström、Tomas Akenine-Möller，*iPACKMAN: high-quality, low-complexity texture compression for mobile phones*，Graphics Hardware，2005，63–70。`[verified: 综述PDF第13页参考文献2]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)
3. Jacob Ström、Martin Pettersson，*ETC 2: texture compression using invalid combinations*，Graphics Hardware，2007，49–54。`[verified: 综述PDF第13页参考文献3]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)
4. Simon Fenney，*Texture compression using low-frequency signal modulation*，Graphics Hardware，2003，84–91。`[verified: 综述PDF第13页参考文献4]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)
5. Jørn Nystad、Anders Lassen、Andy Pomianowski、Sean Ellis、Tom Olson，*Adaptive scalable texture compression*，High-Performance Graphics，2012，105–114。`[verified: 综述PDF第13页参考文献5]` [论文PDF](https://www.cs.cmu.edu/afs/cs/academic/class/15869-f11/www/readings/nystad12_astc.pdf)
6. Arm Limited，*astc-encoder*，综述列录年份2026。`[verified: 综述PDF第13页参考文献6]` [代码](https://github.com/ARM-software/astc-encoder)
7. Jørn Nystad、Anders Lassen、Thomas J. Olson，*Flexible texture compression using bounded integer sequence encoding*，SIGGRAPH Asia 2011 Sketches，2011，Article 32。`[verified: 综述PDF第13页参考文献7]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)
8. Andrew Garrard，*Khronos Data Format Specification v1.4.0*，The Khronos Group，2025。`[verified: 综述PDF第13页参考文献8]` [规范](https://registry.khronos.org/DataFormat/specs/1.4/dataformat.1.4.html)
9. Arm Limited，*Adaptive Scalable Texture Compression User Guide*，Issue 01，2020。`[verified: 综述PDF第13页参考文献9]` [文档PDF](https://developer.arm.com/-/media/ArmDeveloperCommunity/PDF/ASTC_User_Guide_102162_0001_01.pdf)
10. Jon Rrocatis，*ASTC Partitions*，2018。`[verified: 综述PDF第13页参考文献10，姓名按原书目转录]` [原文入口](https://rockets2000.wordpress.com/2018/01/09/astc-partitions)
11. Daniel Oom，*Real-Time Adaptive Scalable Texture Compression for the Web*，硕士论文，Chalmers University of Technology，2016。`[verified: 综述PDF第13页参考文献11]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)
12. Pontus Andersson、Jim Nilsson、Tomas Akenine-Möller、Magnus Oskarsson、Kalle Åström、Mark D. Fairchild，*FLIP: A Difference Evaluator for Alternating Images*，Proceedings of the ACM on Computer Graphics and Interactive Techniques，2020，Article 15。`[verified: 综述PDF第13页参考文献12]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)
13. Matt Pharr、William R. Mark，*ispc: A SPMD compiler for high-performance CPU programming*，Innovative Parallel Computing，2012，1–13。`[verified: 综述PDF第13页参考文献13]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=13)
14. Intel，*Fast ISPC Texture Compressor*，2023。`[verified: 综述PDF第13页参考文献14]` [代码](https://github.com/GameTechDev/ISPCTextureCompressor)
15. Srihari Pratapa、Tom Olson、Alex Chalfin、Dinesh Manocha，*TexNN: Fast Texture Encoding Using Neural Networks*，Computer Graphics Forum，38，2019，328–339。`[verified: 综述PDF第13–14页参考文献15]` [论文](https://doi.org/10.1111/cgf.13534)
16. NVIDIA，*NVIDIA Texture Tools 3*，综述列录年份2026。`[verified: 综述PDF第14页参考文献16]` [工具入口](https://developer.nvidia.com/gpu-accelerated-texture-compression)
17. Jae-Ho Nah，*QuickETC2: How to Finish ETC2 Compression within 1 ms*，ACM SIGGRAPH 2020 Talks，2020，Article 4。`[verified: 综述PDF第14页参考文献17]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=14)
18. Jae-Ho Nah，*QuickETC2: Fast ETC2 Texture Compression using Luma Differences*，ACM Transactions on Graphics，39(6)，2020，Article 270。`[verified: 综述PDF第14页参考文献18]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=14)
19. Jae-Ho Nah，*QuickETC2-HQ: Improved ETC2 encoding techniques for real-time, high-quality texture compression*，Computers & Graphics，116，2023，308–316。`[verified: 综述PDF第14页参考文献19]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=14)
20. Hyeon-ki Lee、Jae-Ho Nah，*H-ETC2: Design of a CPU-GPU Hybrid ETC2 Encoder*，Computer Graphics Forum，42(7)，2023，Article e14969。`[verified: 综述PDF第14页参考文献20]` [论文](https://doi.org/10.1111/cgf.14969)
21. Pavel Krajcevski、Abhinav Golas、Karthik Ramani、Michael C. Shebanow、Dinesh Manocha，*VBTC: GPU-Friendly Variable Block Size Texture Encoding*，Computer Graphics Forum，35(2)，2016，409–418。`[verified: 综述PDF第14页参考文献21]` [论文](https://doi.org/10.1111/cgf.12842)
22. Arm Limited，*Adaptive Scalable Texture Compression Developer Guide*，Version 4.3，2023。`[verified: 综述PDF第14页参考文献22]` [文档入口](https://developer.arm.com/documentation/102162/latest)
23. Jae-Ho Nah，*ASTC Block-Size Determination Method based on PSNR Values*，Journal of the Korea Computer Graphics Society，28(2)，2022，21–28。`[verified: 综述PDF第14页参考文献23]` [论文入口](https://doi.org/10.15701/kcgs.2022.28.2.21)
24. Jae-Ho Nah，*Addition of an adaptive block-size determination feature to astcenc, the reference ASTC encoder*，Software Impacts，17，2023，Article 100569。`[verified: 综述PDF第14页参考文献24]` [论文](https://doi.org/10.1016/j.simpa.2023.100569)、[代码](https://github.com/SoftwareImpacts/SIMPAC-2023-337)
25. Oleksandr Popov，*Automated ASTC compression*，2025。`[verified: 综述PDF第14页参考文献25]` [代码](https://github.com/keaukraine/astc-compression)
26. Jon Sneyers，*SSIMULACRA 2 - Structural SIMilarity Unveiling Local And Compression Related Artifacts*，2023。`[verified: 综述PDF第14页参考文献26]` [代码](https://github.com/cloudinary/ssimulacra2)
27. Wesley Griffin、Marc Olano，*Objective image quality assessment of texture compression*，Symposium on Interactive 3D Graphics and Games，2014，119–126。`[verified: 综述PDF第14页参考文献27]` [论文PDF](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=914900)
28. Guillaume Lavoué、Michael Langer、Adrien Peytavie、Pierre Poulin，*A Psychophysical Evaluation of Texture Compression Masking Effects*，IEEE Transactions on Visualization and Computer Graphics，25(2)，2019，1336–1346。`[verified: 综述PDF第14页参考文献28]` [论文](https://doi.org/10.1109/TVCG.2018.2805355)
29. Peter Harris，*High quality RGBM texture compression with ASTC*，Arm Community，2019。`[verified: 综述PDF第14页参考文献29]` [原文入口](https://developer.arm.com/community/arm-community-blogs/b/mobile-graphics-and-gaming-blog/posts/high-quality-rgbm-texture-compression-with-astc)
30. Kenneth C. Rovers、Sam Elliott，*On Improving the Performance Per Area of ASTC with a Multi-output Decoder*，IEEE Symposium on Computer Arithmetic，2017，58–59。`[verified: 综述PDF第14页参考文献30]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=14)
31. Jakub Žádník、Markku Mäkitalo、Jussi Iho、Pekka Jääskeläinen，*Performance of Texture Compression Algorithms in Low-Latency Computer Vision Tasks*，European Workshop on Visual Information Processing，2021，1–6。`[verified: 综述PDF第14页参考文献31]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=14)
32. Jakub Žádník、Markku Mäkitalo、Pekka Jääskeläinen，*Pruned Lightweight Encoders for Computer Vision*，IEEE Workshop on Multimedia Signal Processing，2022，1–6。`[verified: 综述PDF第14页参考文献32]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=14)
33. Hardik Sharma、Tom Olson、Alex Chalfin，*Using Texture Compression Hardware for Neural Network Inference*，Hot Chips Symposium on High Performance Chips，Posters，2017。`[verified: 综述PDF第14页参考文献33]` [书目原页](https://nahjaeho.github.io/papers/CGA26_paper.pdf#page=14)
34. Ethan Li等，*Apple Intelligence Foundation Language Models: Tech Report 2025*，arXiv `2507.13575`，2025。`[verified: 综述PDF第14页参考文献34]` [预印本](https://arxiv.org/abs/2507.13575)
35. BinomialLLC，*basis_universal v2.5*，综述列录年份2026。`[verified: 综述PDF第14页参考文献35]` [代码](https://github.com/BinomialLLC/basis_universal)
36. Karthik Vaidyanathan、Marco Salvi、Bartlomiej Wronski、Tomas Akenine-Möller、Pontus Ebelin、Aaron Lefohn，*Random-Access Neural Compression of Material Textures*，ACM Transactions on Graphics，42(4)，2023，Article 88。`[verified: 综述PDF第14页参考文献36]` [论文](https://doi.org/10.1145/3592407)、[作者页](https://research.nvidia.com/publication/2023-08_random-access-neural-compression-material-textures)
37. Laurent Belcour、Anis Benyoub，*Hardware accelerated neural block texture compression with cooperative vectors*，High-Performance Graphics，2025。`[verified: 综述PDF第14页参考文献37]` [论文与全文](https://arxiv.org/abs/2506.06040)
