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

### 研究顺序与分类校准

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
| 资料归档 | 视频、中英文网站字幕、19张每分钟截图、10张关键页补充截图已保存。`[verified: materials/gdc2023-astc-parameter-selection/；verification.json]` |
| 全文整理 | 中英文字幕各328条，校订稿按40段覆盖全部条目，逐条原文另存对照稿。音轨独立ASR转写状态为未运行。`[verified: source/material-metadata.json；transcripts/完整字幕对照.md]` |
| 方法核实 | 正文展示有标签数据集、块大小分类和ResNet。官网简介另提到强化学习，具体对应关系待作者材料确认。`[verified: 视频10:00、11:28、12:28；官方简介Overview]` |
| 实验复现 | 已完成14,000张LITE源图划分、两组ResNet18各30轮及独立温度校准。测试准确率为67.50%／62.35%，中间块大小类别召回较低。[比例复核](<experiment report/gdc-lite-rgb-resnet18-seed20261109/数据集划分比例复核.md>)发现测试集中Mask单组占46.05%，详见[实验报告](<experiment report/gdc-lite-rgb-resnet18-seed20261109/training_report.md>)。质量与字节收益需候选压缩实测。`[verified: 实验metrics.json、data_summary.json、split_proportion_audit.json；opinion: 生产质量评价范围]` |
| Git | 已初始化，分支为`main`，远端为`hamsterjiang23/AdaptiveASTC`，MP4视频通过Git LFS管理。`[verified: git init、git branch --show-current、git remote add origin输出；.gitattributes中的*.mp4规则]` |

## 从这里阅读

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
