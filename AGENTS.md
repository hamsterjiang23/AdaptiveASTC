# AGENTS.md

## 适用范围与研究定位

- 本文件适用于 `E:\ASTC_Compression` 全目录，执行任务时同时遵循用户提供的全局规则。`[opinion]`
- 当前研究主题为ASTC纹理压缩块大小自动选择，关注质量、真实字节数与处理成本的权衡。`[verified: README.md“当前状态”“已核实的方法与待核实问题”]`
- 以固定8×8为当前生产基线，研究机器学习预测参数后执行一次最终压缩。PSNR 35 dB按项目经验判据记录，法线与MSAK贴图的标准和Unity导入后训练数据的获取方式按待明确事项处理。`[verified: README.md“项目需求与优化目标”]`
- 当前执行用户确认的V1原分辨率patch误差回归计划，分类对照保留为基线；按固定容量诊断、单项训练改进、必要时扩大网络的顺序推进。分别评价标签正确率、质量指标和完整成本，最终采用Unity导入后参考像素与同次原搜索标签验收。`[verified: experiment plan/V1/README.md“目标与开发数据”“实验步骤”；当前active goal objective]`
- 开始任务先读 [README.md](README.md)，按任务需要读取对应资料和检查记录。研究题目、算法路线与新增实验范围以用户确认的内容为准。`[opinion]`

## 文献发展路线与研究定位

- 完整问题链见[README的发展路线](README.md#文献发展路线与问题演进)，每项工作按“已有问题 → 方法改进 → 剩余限制”阅读和维护。`[verified: README.md“文献发展路线与问题演进”]` `[opinion]`
- **编码加速路线**。昂贵配置搜索 → FasTC／SegTC的结构近似和Web ASTC的启发式 → TexNN的块内部配置预测；Pruned ASTC另以配置裁剪和下游重训练换取低延迟。记录格式、质量损失和任务用途。`[verified: README.md“编码器加速，从昂贵搜索到近似与学习”]` `[opinion]`
- **自动选参路线**。固定参数与人工设置 → 2022年目标PSNR搜索 → 2023年astcenc内部集成。GDC 2023另展示离线试压缩标签与ResNet整图选参；本项目保留分类基线，当前以V1的质量预测和规则决策推进。VBTC作为图内可变分配的系统分支记录。`[verified: README.md“自动选参，从统一配置到质量约束与学习式决策”“研究顺序与分类校准”；experiment plan/V1/README.md]`
- **质量评价路线**。贴图误差 → 多视点渲染比较 → diffuse／normal掩蔽的主观实验、任务专用可见性指标与FLIP误差图。分别记录纹理指标、渲染指标、观看条件和人类接受标准。`[verified: README.md“质量评价，从贴图误差到渲染可见性”]` `[opinion]`
- **表示与部署路线**。NTC联合材质通道与mip，后续分别研究BC特征／NBC的表示、DBC的任务损失、cooperative vectors的硬件加速、hypernetwork的逐材质优化成本及共享解码器的执行分歧。NTBC加载重建、高斯、JPEG和TexF分支分别保留其存储、采样与运行时条件。`[verified: README.md“神经纹理，从联合表示到硬件、训练与解码效率”“其他表示与系统分支”]`
- 直接继承关系以作者明确表述为依据，跨论文的问题链标为综述归纳。Multi-output ASTC归入解码电路，ASTC Encoding Survey作为技术地图；本项目的新颖性与质量／字节收益以进一步文献核实和独立实验评价。`[verified: README.md对应路线及“AdaptiveASTC在这些路线中的位置”]` `[opinion]`

## 目录与资料维护

- `README.md` 汇总项目定位、进展、资料入口、相关研究和综述完整书目。新增研究资料时优先补入已有分类。`[verified: README.md“从这里阅读”“学术综述与相关研究”]` `[opinion]`
- `materials/gdc2023-astc-parameter-selection/source/` 保存视频、原始双语字幕和元数据。按原件维护，校订内容写入 `transcripts/` 并保留字幕条目及时间戳映射。`[verified: README.md“资料目录”]` `[opinion]`
- `materials/gdc2023-astc-parameter-selection/frames/` 保存定时截图和关键页截图。新增截图使用能识别视频时间点的文件名。`[verified: README.md“资料目录”“视频与处理口径”]` `[opinion]`
- `notes/` 保存阅读笔记，`implementation-notes.md` 记录取舍与边界问题，`verification.json` 保存已执行检查的结果。`[verified: README.md“从这里阅读”]`
- Obsidian副本位置由README记录，跨目录同步按用户本次授权范围执行。`[verified: README.md“资料目录”末段]` `[opinion]`

## 文献与证据要求

- 技术结论优先引用论文原文、作者项目页、官方规范与对应代码。引用定位到章节、页码、表格、视频时间戳或代码行。`[opinion]`
- 每项事实、推断和建议使用行内标记。实际读取的证据使用 `[verified: 可定位来源]`，推断、研究设想和建议使用 `[opinion]`。`[verified: 用户提供的全局规则“Output Style — Epistemic Markers”]`
- 分别标明原文结果、综述转述、本地复现结果和研究提议。摘要阅读、全文阅读、书目转录与原文访问失败分别记录核实深度。`[opinion]`
- 综述完整书目保留原编号和书目信息。新增独立论文放入相应导读分类，并附稳定论文链接、DOI或arXiv编号。`[opinion]`
- 演讲正文当前整理为有标签的块大小分类流程。官网简介中的强化学习表述与正文机制的关系，继续按待核实问题记录。`[verified: README.md“需要保留的证据边界”]`
- 分开描述整张纹理的块大小选择、块内部编码配置预测、存储侧压缩和运行时解码，分别说明格式、硬件与过滤要求。`[opinion]`

## 实现与实验

- 同图patch聚合实验的准备见[成组损失报告](<experiment report/unity-accuracy90-20261111/patch-fixed-capacity/bag-loss.md>)。`ImagePatchBatchSampler`每组只抽同图patch、保留有效像素数；`PatchRegressionLoss`先加权MSE再取log，目标只对实际抽样组精确。权重0／1配对隔离loss，另比较成组采样本身；不能把期望权重一致称为每轮图覆盖一致。CPU检查和训练集抽样核验通过，未接入训练器或启动CUDA实验；已有运行的源码及检查点身份保持。`[verified: patch_bags.py；patch_loss.py；bag-sampling-analysis.json；opinion: 对照与运行边界]`

- 当前goal以用户的[V1原分辨率patch误差回归计划](<experiment plan/V1/README.md>)和[evidence.json](<experiment plan/V1/evidence.json>)为准，实际状态见[执行记录](<experiment report/unity-accuracy90-20261111/README.md>)。按patch目标／编码核验、分类对照、scratch／pretrained回归、按错误分布改进的顺序执行，训练使用CUDA。GDC train／validation用于开发，最终在Unity导入后参考像素与同次原始搜索标签的独立测试上验收Top-1≥90%。`[verified: 用户本轮V1与重新创建goal要求；V1“目标与开发数据”“实验步骤”]`
- V1分类五组最高验证Top-1为68.6%；正式随机初始化／预训练patch回归各14轮完成，最佳Top-1为76.0%／88.8%，阈值附近RMSE为1.7681／0.9736dB，两组最佳权重重载通过。各11,178,564参数，继续固定容量诊断；V1开发联合晋级条件及最终Unity90%均未达到。详见[回归状态](<experiment report/unity-accuracy90-20261111/patch-v1/README.md>)。`[verified: classification-controls/comparison.json；patch-v1/summary.json；scratch-result.json；pretrained-result.json；opinion: 后续顺序]`
- Unity回归采集保留原搜索提前停止、标签及baseline计时，另行补测块大小×preset缺失候选并记录解码图及原生质量分支。抽样真实编码先作为独立成本／质量对照，主路径保持预测后一次最终编码。方案差异、未完成配置和实际测量分别写入执行记录。`[verified: V1“待决定事项”；opinion: 本轮执行决定]`
- 实际编码参数采集入口为`script/capture_unity_options.py`，通过临时受保护的managed回调记录Alpha、profile、normal pack及输入RGBA哈希，结束后恢复源码。两图实际参数绑定的40候选补测通过，64图采集另记录558回调，包含63 Default和1 NormalMap，恢复无冲突。NormalMap样本的normal-pack实际为false，用途与pack标志分别记录；真实mip0法线20候选重编码也已通过，HDR／多mip及最终Unity90%均未验收。`[verified: unity-supplement2-actual.json；unity-actual-options64.json；smoke1-receipt.json；metadata.py；unity-normal-replay20.json]`
- 颜色补测已扩展到8图160候选，原52组指标和8个winner复核一致；真实4096² NormalMap的20原候选重新解码和原生角度评价通过，后续另立身份重新编码20组并核对完整ASTC和RGBA字节一致。法线20组均未过角度门槛，保留最高PSNR回退身份。门槛取真实tableConfig并按float32还原，报告状态允许Valid后附BEST标记；HDR／多mip及全量采集未验收。成本和读写依赖见[实验成本表](references/task-costs.md)。`[verified: unity-color8.json；unity-normal20-policy.json；unity-normal-replay20.json；tests/test_unity_normal_audit.py]`
- 开发参考图支持显式`source_split=train/validation`、`capture_paths`和`phase=batch`，每批1至256个唯一路径，路径必须属于冻结划分且不能跨划分重复。输出manifest保留原划分，禁止test／calibration；原搜索baseline仍要求10000张训练图及原smoke门槛。批次各用独立协议锁、缓存和恢复记录。`[verified: benchmark.py prepare/verify_protocol；unity_reference.py collect；tests/test_unity_reference_batches.py]`
- 强制中断后的batch导入设置恢复使用`script/reproduce.py recover --phase batch`，按原run_id／project／editor／manifest绑定冻结协议；managed源码另用`capture_unity_options.py restore --journal`恢复。两者要求工程Editor关闭，保留冲突且不覆盖独立改动。`[verified: script/reproduce.py recover；benchmark.py restore_metadata；metadata.py ManagedCaptureHook.restore；test_unity_reference_batches.py]`
- 冻结末轮权重的BN诊断入口为`script/patch_normalization.py`，只用train抽样patch重估统计量，再评价validation；参数不更新，保留独立权重和成本。两组完成，随机初始化／预训练EMA为76.7%／89.2%，近阈值RMSE1.6467／0.9512dB；这是末轮后处理对照，与训练中最佳raw的76.0%／88.8%分别记录，仍未达V1／Unity验收。`[verified: normalization-scratch.json；normalization-pretrained.json；scratch-result.json；pretrained-result.json；PatchNormalizationAudit.run]`
- 固定容量学习率单项对照已完成：原scratch仅lr1e-3→3e-4，12轮早停，选中epoch7 raw，验证80.7%／近阈值RMSE1.6040dB，最佳权重重载通过。10×10召回下降4.69个百分点需保留；同LR去maxpool对照也已完成15轮，为74.6%／2.5459dB，下降6.1个百分点，保留标准stem作为后续基准。详见[固定容量对照](<experiment report/unity-accuracy90-20261111/patch-fixed-capacity/README.md>)，BN后处理单列，去maxpool重估EMA为78.6%／2.1127dB。下一项固定容量训练只把组抽样改为cap512，沿用标准stem／scratch／lr0.0003，CUDA小样本通过后启动；cap0保留原图等权分布，test不参与选模。`[verified: scratch-lr0003-result.json、scratch-stem2-lr0003-result.json；normalization-scratch-stem2-lr0003.json；PatchSampling.weights；scratch-group512各suite／smoke-summary；opinion: 后续基准]`
- 完整参考采集由`script/collect_unity_references.py validate/collect/assemble`驱动，45个冻结批次覆盖train10000／validation1000，单批不超过256。已完成train320／validation2，66张已有数据的真实合并检查通过，全量队列运行中；状态见[串行采集报告](<experiment report/unity-accuracy90-20261111/unity-reference-series.md>)。使用Unity工程Library下OS文件锁，逐批校验配置／manifest／Editor／DLL身份、恢复记录、参考SHA和原标签；旧失败不得静默覆盖。活动队列期间不得另开同工程Editor或恢复其临时hook。候选补测和训练验收分别记录。`[verified: collection.py UnityReferenceSeries；unity-reference-series-plan.json、unity-reference-series-smoke.json、unity-reference-series.json；opinion: 运行约束]`
- 持续记录该目标的实验进展，统一入口为[执行报告的progress.json](<experiment report/unity-accuracy90-20261111/progress.json>)。保存配置差异与调整原因、逐epoch训练／验证指标、实际更新数、失败重试和耗时。运行中日志与heartbeat保存在.local，阶段结果同步仓库。`[verified: 用户本轮“时刻记录实验进展”；experiment report/unity-accuracy90-20261111/progress.json；ReproductionJob.run与Trainer.fit；opinion: 记录要求]`
- 当前执行顺序为Unity搜索baseline、Nah 2023、Nah 2022、TexNN、GDC，再研究新模型与校准。新增方法代码集中在`reproductions/`，启动入口仍放`script/`。先完成10,000张训练图的真实搜索计时报告，再启动正式文献实验。缺作者代码时允许论文重实现，原文设置、补全假设和实际完成状态分别记录。`[verified: 用户2026-11-10实施请求及复现标准选择]`
- 正式文献实验通过`BaselineGate`检查10,000张覆盖、原生搜索记录、源图哈希核验、退出码与metadata恢复。Unity基线按实际进入ASTC的目标格式测量，临时Android覆盖与恢复、参数缓存隔离和计时区间见[复现入口](reproductions/README.md)。`[verified: reproductions/common/upstream.py BaselineGate；reproductions/unity_search_baseline/benchmark.py]`
- 技术失败补测使用独立空缓存，保留初次失败记录与退出码，合并结果使用`passed_with_retries`并校验来源SHA-256。初次批次、补测批次、逐图计时与整轮墙钟分别记录。`[verified: reproductions/unity_search_baseline/recovery.py；reproductions/common/upstream.py BaselineGate]`
- Nah 项目适配实验使用固定训练子集的源图 RGB8、原始尺寸、Linear LDR、无 mip 和单编码线程。Nah 2022 按完整 RGBA PSNR 搜索，Nah 2023 保留作者的随机块抽样 RGBA 估计。报告分别复查全图 RGB、RGBA 质量，保留原始 receipt，并通过 `report --method ... --run-id ...` 生成结果。`[verified: reproductions/common/nah_experiment.py protocol/_measure；common/reporting.py write；script/reproduce.py main]`
- Nah 2022／2023 已完成各 64 张项目适配闭环，公开报告保留质量达标率和同方法固定 8×8 控制。两者的原文设置、Unity 导入像素及当前源图适配分别记录。Nah 2022 本轮计时期间存在同机检查活动。后续性能结论按明确输入、计时范围和运行背景解释。`[verified: experiment report/nah2022_psnr_search/source-rgb64-game/summary.json；experiment report/nah2023_adaptive_astcenc/source-rgb64-target40/summary.json；reproductions/README.md]`
- 阶段结果形成后提交并推送仓库，原始逐图日志、图片和二进制按 `.local/` 忽略规则保存，公开报告保留来源标识与原始记录 SHA-256。`[verified: 用户要求“记得有进展同步仓库”；reproductions/common/reporting.py quality_audit；.gitignore]`
- TexNN 主文及用户补充的 13 页 Appendix 已归档，六个网络层尺寸取自 Appendix 第1页 Tables 1–2，并保存于 `architectures.json`。历史参考编码器固定到 `ddadf547770ddbe8261cfd854b2a5f21b3a9074c`，该版本选择按论文引用的访问日期补全。数据收集入口为 `collect --method texnn`，核对原生块数据、坐标与源码的 PNG Y 翻转，完整训练及预测配置回填按实际结果验收。`[verified: reproductions/texnn/source.json、architectures.json、data.py；script/reproduce.py TexNN 分支]`
- TexNN 项目适配已完成 64 源图块标签、六网络训练及独立 validation 8 图／48 次编码的闭环，报告保留质量损失和全部阶段耗时。训练 DEM 特征固定 `partition_single_plane_rgb24_v2`，只用像素与分区拟合端点，禁止采用教师尚未预测的双平面／编码模式生成推理特征。早期 v1 探针只作标签配对证据。`[verified: reproductions/texnn/native/labels.cpp texnn_ideal_endpoints；corpus.py rows；实测 validation8-patch128.json]`
- TexNN 的 `dataset`、`train`、`evaluate`、`benchmark`、`report` 入口统一在 `script/reproduce.py`。P-NN 和 DEM-NN 的 top-k 配置进入真实历史编码器，非法组合回退原始搜索并计时；恒色块走原始快速路径。原文百万块数据规模及论文性能复现仍未完成，当前项目适配不能作为等质量生产收益。`[verified: script/reproduce.py TexNN 分支；native/prediction.cpp texnn_process_block；实测报告 limits、groups]`
- TexNN 已扩展到 1,024 张源图，三种 footprint 共 310,355 个非恒色块，六网络训练总计 1,865.59 秒。扩展报告使用与先期相同的 validation 8 图裁剪协议，保留 48 次编码及 96 次重新解码。按实际输入规模和单个项目 validation 子集解释结果。`[verified: experiment report/texnn/source-rgb1024-patch64-v2/data.json、validation8-patch128.json]`
- 新 GDC 路径使用源 RGB8、原始尺寸、Linear LDR、无 mip／RDO、固定 astcenc 3.3 medium，候选为 6／8／10／12 四种方块；完整演讲候选与编码设置未公开，这些是项目重建设置。标签严格 PSNR >35 dB、最小实际 payload，同字节取更大 footprint，无可行候选则保留最高 PSNR 并标记违规。`[verified: reproductions/gdc2023/dataset.py GDCLabelSelection、collect protocol；gdc2023/source.json]`
- GDC 的 `dataset／assemble／train／evaluate／report --method gdc2023` 共用冻结源划分。缓存与组装校验四候选、实际 ASTC 和重建质量，训练核对 RGB224 缓存及标签；评估核对完成状态，在首次 test forward 前通过 `EvaluationSeal` 绑定模型。概率评估保留原 arms／temperature，压缩评估扩展 compression_models。`[verified: gdc2023/dataset.py、training.py、evaluation.py；utils/evaluation_seal.py；evaluation/evaluator.py]`
- 训练记录区分梯度累积后的 step 尝试、实际 optimizer_updates 与 amp_skipped_steps；scheduler 及 best 选择要求本轮实际更新。正式 14k 标签及组装通过，10k 图 30 轮 CUDA 训练已完成，独立test2000最终编码与报告审计通过，RGB>35dB达标1540/2000，违规率23%。GDC 训练计时绑定 checkpoint／完成记录，未记账的恢复前史保留未知。`[verified: training/trainer.py train_epoch/fit；gdc2023/training.py；正式 training_complete.json、wall-clock.json、test2000/pretrained-test.json]`
- 模型训练使用 CUDA，GDC Trainer 与 TexNN 训练入口均检查 CUDA 设备。正式 ResNet18 使用 RTX4070、CUDA12.8 和 FP16 AMP。`[verified: 用户本轮要求“训练优先用CUDA，不要用CPU”；training/trainer.py fit；texnn/training.py train；正式 pretrained/config.json]`
- 分类调优参考[准确率提升调研](<experiment report/classification-accuracy-research-20261111/README.md>)。当前GDC复现CLI未透传learning_rate，effective_batch与micro_batch分别记录。报告中的新loss、骨干和搜索范围为待实验提案，原始冻结结果与新的输入协议分别维护。`[verified: script/reproduce.py GDC train；GDCTraining.train；调研报告及diagnostics.json]`
- 调研按用户补充覆盖影响最终结果的全流程因素，包含导入、Alpha／颜色、mip、编码器／候选、规则、数值精度、随机性、缓存身份、部署计时和渲染评价。当前源码静态快照与历史Editor／DLL实测使用各自版本身份。`[verified: 用户本轮范围补充；准确率提升调研“导入、编码与部署的全流程因素”；diagnostics.json current_engine_source_inspection]`
- 源图64对照和Unity参考像素64对照均已完成，后者核验各方法RGB PNG字节一致，按完整RGB>35dB及真实payload评价。GDC源图训练模型在导入后参考像素上属于输入变化诊断，64图均来自训练划分，独立test2000用于泛化评价。原生目标、Alpha及计时范围分别保留。`[verified: experiment report/reproduction-shared64/comparison.json；reproduction-unity-reference64/comparison.json；GDC正式test2000报告]`
- GDC 报告保留固定 6／8／10／12 的离线候选质量、真实 payload 与原采集计时；部署延迟以单独实测的 fixed8 配对流程为对照。共享 Unity64 属于训练集诊断，冻结 config 经 protocol-lock 与 baseline receipt 双层哈希核验，名称／配置 SHA／路径顺序写入 binding；独立 test2000 用于泛化评价。Nah/GDC 源 RGB 输入逐图核对，Unity 导入像素和 mip 范围分别保留，不据此声称等质量加速。`[verified: common/cohort.py；common/comparison.py；gdc2023/reporting.py；gdc2023/README.md]`
- GDC 的 collection 计时覆盖候选采集，完整数据准备成本另由进程启动／退出时刻覆盖清单验证与缓存组装。`preparation-process.json` 的完整记录经评估 SHA 绑定，报告核对协议、collection 和 manifest。缺失或不完整的可选计时保留未知成本。`[verified: gdc2023/costs.py；evaluation.py；reporting.py；正式运行的 preparation-process.json]`
- 进程与重启恢复保留原始失败日志，RGB224 缓存异常副本先归档，再校验可写临时文件、fsync 并原子替换。长任务由 `script/run_reproduction_job.py` 记录命令、存活心跳和退出码。原始进程的未知部分耗时与已测成功／失败阶段分别记录。`[verified: gdc2023/dataset.py copy_classifier_cache；common/jobs.py；classifier-cache-recovery.json；preparation-process.json]`
- Unity 参考图采集使用 `--capture-references`，预热后开启原生导出，完整成功及 metadata 恢复后通过 `collect` 归档。原生解码 PNG 垂直翻转后与参考图统一方向，缓存复查包含镜像 PNG。已测固定 64 图中 38 图源 RGB 完全相同、26 图不同，全部选参配置与原基线一致。`[verified: common/unity_reference.py；BenchmarkRunner.cs；experiment report/unity-reference64-lite-rdo-off/summary.json]`
- 实验协议、数据、训练、校准、成本及验证报告统一保存在`experiment report/`，逐图清单、缓存、原始日志、预测和检查点保存在该目录的`.local/`并Git忽略。`[verified: 用户确认的GDC复现计划及报告目录要求]`
- Python环境和依赖统一使用uv，提交`pyproject.toml`、`uv.lock`与`.python-version`；安装使用`uv sync --frozen`，实验和检查使用`uv run`。`[verified: 用户要求“仓库里使用uv进行python依赖管理”；pyproject.toml]`
- 实施前检查已有文件、工具和入口，采用完成任务所需的最小修改，保留用户已有工作。Git状态在实际操作前重新查询。`[opinion]`
- 先运行小样本压缩、解压、质量测量和字节统计，再扩大到完整数据集、训练或批处理。`[verified: 用户提供的全局规则“Smoke test first”；README.md“后续研究方向”]`
- 实验协议记录编码器版本、preset、候选块集合、颜色空间、通道用途、Alpha、mip、尺寸取整、容器与硬件。`[opinion]`
- 质量目标、标签生成规则、训练目标和部署质量复检分别定义。记录无可行候选、编码失败、质量违规及回退处理。`[opinion]`
- 对照优先覆盖当前生产使用的固定8×8，补充固定6×6、固定12×12和同质量目标下的搜索选参，学习方法与搜索方法使用一致的编码和测量口径。`[verified: README.md“当前生产基线与优化空间”]` `[opinion]`
- 分别报告数据准备、训练、预测和最终编码耗时，以及体积、质量分布和失败率。跨资产或跨项目划分时检查近重复数据泄漏。`[opinion]`
- 实验状态以本次运行日志和产物为依据。`verification.json` 中的历史资料检查与新增实验验证分别记录。`[opinion]`

## Unity训练数据采集与源码定位

- Unity规则重放入口为`script/replay_unity_policy.py --config ...`，固定完整20候选顺序、float32阈值、黑像素分档、法线／MS-SSIM、大图锁组和回退；保留切组前已测候选的计数。缓存必须来自冻结原采集phase并重做LITE完整来源审计，不能仅信任调用者提供的SHA。260张开发图的块大小、preset、原因和尝试次数全部一致；PSNR-only诊断仅207张块大小一致，不作为模型准确率或上限。后续质量预测必须按完整规则单独验收，详见[规则重放报告](<experiment report/unity-accuracy90-20261111/unity-policy-replay.md>)。`[verified: policy.py select；policy_audit.py verify_policy_origin、run；unity-policy260-bound-v2.json；opinion: 模型验收要求]`

- 原搜索提前停止的颜色／mip0法线候选可用`script/complete_unity_candidates.py --config ...`补齐，256图5120候选及原winner审计已通过。全量跟随入口为`script/complete_unity_candidate_series.py --config ... --follow`，仅消费已发布的参考批次；归档复核后复用已完成结果，部分失败使用新retry身份并保留原始成本，最终按原划分生成完整清单。258图实跑检查通过。法线限定Linear RGBA8、Profile1、normal-pack=false和Tex2D；角度评价层数按已归档mipmaps与尺寸推导并clamp1–4，每个原候选须复现原指标。两张mipmaps=true法线40候选实测通过；这仍是mip0编码，不是完整mip压缩链。HDR单独验证。详见[补测进展](<experiment report/unity-accuracy90-20261111/unity-supplement.md#连续补测队列与训练清单>)。`[verified: candidate_completion.py verify_actual_options、verify_normal_imports；candidate_queue.py run、prepare_attempt；candidate_archive.py verify；unity-candidates-train256-audit.json；unity-candidate-queue-smoke.json]`

- Unity监督提取入口为`script/unity_patch_targets.py --config ...`，RGBA各通道SSE按240patch保存，整图聚合后排除零误差通道及不参与的Alpha；MS-SSIM和法线角度保留整图指标。258图5160候选重建检查通过，另两张四级法线评价数据通过；原标签不变，未开始Unity正式训练。数据身份及恢复要求见[原生监督报告](<experiment report/unity-accuracy90-20261111/unity-patch-targets.md>)。`[verified: patch_targets.py UnityChannelErrors、UnityPatchCorpus；unity-patches-train256.json；unity-patches-multimip2.json]`

- 离线候选补测入口为`script/unity_supplement.py`，其质量函数从本机引擎原样提取到.local并编译，编码DLL沿原采集协议锁与identity核验。当前两张LDR Default开发图的40候选与原16项质量重放通过；needAlpha等仍是重放核验的推定设置，正式采集要记录实际回调参数。参见[补测报告](<experiment report/unity-accuracy90-20261111/unity-supplement.md>)。`[verified: unity-supplement2-bound.json capture_binding、rows、config.items；quality.py]`

- 面向 Unity 生产选参的训练与评估使用导入处理完成后、进入 ASTC 搜索前的第一个 image／mip0 参考图。RGB224限定为历史分类输入，当前V1开发回归使用原分辨率240patch；Unity迁移保留RGBA、用途及原生质量分支，质量测量使用原尺寸导入后参考像素。参考图与同次导入和原始搜索标签配对，缺图时补采或标记缺失；原图用于来源核验、对照及明确标注的历史／文献复现。`[verified: README“Unity导入结果与训练数据准备”；experiment plan/V1/README.md“输入与数据”；LITE训练协议L21；opinion: Unity迁移要求]`
- LITE／RDO 关闭的 64 张实测配对中，19 张尺寸变化（例如 4096×4096 → 128×128、240×390 → 256×512），7 张同尺寸但 RGB 变化，38 张尺寸和 RGB 相同。7 张中有 5 张只在两侧均完全透明的像素改变 RGB，另 2 张是原因待核实的 JPEG。当前模型只读取 RGB，透明区域的差异也会进入模型。按这批样本解释差异，Alpha 等价性和全量比例分别核实。详见[README 实测差异](README.md#导入前后的实测差异)。 `[verified: 64 张配对图尺寸和 RGBA 逐像素复查；LITE 训练协议 L21]`
- 训练数据导出任务先读[README源码导航](README.md#unity训练数据导出与源码导航)，再核对本机引擎文件哈希、函数和行号。README保存完整位置表、调用链、字段与采集条件。`[verified: 用户要求“全部整理到readme和agent里面”；README对应小节]` `[opinion]`
- 输入取自`ImageOperations.cpp`的`CompressTextureWithMultipleImages`取得的第一个image／mip0，经`PrepareOriginalImageData`转换／绑定为RGBA32。参考图采集从`SetupTestEnvironment → ExportImageToPNG`读取，源图与参考像素的等价性按样本实测。`[verified: ImageOperations.cpp L2947–2964；ASTCCompressor.cpp L2675–2694、L1999–2010]` `[opinion]`
- 主链为`FindOptimalASTCFormat → FindOptimalParameters → TestAllParameterCombinations → SelectBestParameter → SaveBestParametersToCache → SaveCacheEntryToFile`，分别定位到`ASTCCompressor.cpp`的L3738、L3435、L2958、L3364、L1935、L1836。`[verified: ASTCCompressor.cpp L3767、L3499–3522、L1975]`
- 采集前核对ASTC目标格式、自动选参开关、第三方编码／解码接口和磁盘调试开关。缓存命中在图片导出前返回，采集方式需显式记录缓存复用、重新测量、cache-hit及导出结果。`[verified: ImageOperations.cpp L2958–2968；ASTCCompressor.cpp L428–478、L2963–2970、L3437–3462]` `[opinion]`
- 维护资产路径、源MD4、参考图及其哈希、导入配置、尺寸、颜色空间、用途、Alpha、mip、Editor／DLL版本与tableConfig的对应关系。调试目录的纹理名和进程内计数用于定位产物，批量数据集通过清单建立稳定样本身份。`[verified: ASTCCompressor.cpp L2001–2009、L1964–1973、L3466–3499]` `[opinion]`
- 记录实际候选覆盖、编码／解码失败、earlyExit、valid与回退原因。常规搜索提前停止，大图允许MS-SSIM失败时采用PSNR通过候选，全部不合格时按最高PSNR回退。标签称为“当前策略选中配置”，最优性与质量达标分别评价。`[verified: ASTCCompressor.cpp L3121–3125、L3157–3158、L3262–3269、L3337、L3348–3419]` `[opinion]`
- 字段采用源码口径，PSNR仅平均误差非零的参与通道且排除恒定Alpha，msSsimDb为亮度MS-SSIM的dB转换，fileSize为本次参考尺寸payload，timestamp为写缓存时刻，rdo为最终采用精炼payload。法线角度、候选表与RDO尝试状态单独保存。`[verified: ASTCCompressor.cpp L2238–2304、L2456–2478、L3067–3072、L1964–1973、L657–666]` `[opinion]`
- 核对实际缓存目录、tableConfig、JSONL新增记录和快照合并，保留历史LITE与主包协议差异。锁或写入失败、源文件缺失及哈希失败需要纳入采集完整性检查。`[verified: ASTCCompressor.cpp L1178–1205、L1372–1397、L1836–1899、L1937–1939、L3506–3523；README对应小节]` `[opinion]`
- 源码静态定位、图片导出实测、候选压缩质量和训练效果分别报告。先验收小样本，再按用户授权范围扩展批量采集。`[verified: 用户“Smoke test first”要求]` `[opinion]`

### 术语口径

- 术语解释沿用[README完整术语表](README.md#压缩参数与图像术语)，分别记录压缩参数、亮度范围、颜色编码及贴图用途。`[verified: 用户要求“这些所有的术语的解释也放到agents和readme里面”；README对应小节]` `[opinion]`
- blockSize／block footprint为每个ASTC块覆盖的texel宽高，texel为纹理像素，块输出固定128 bit／16字节。4×4、8×8、12×12分别为8、2、约0.89 bpp，payload为原始块数据，mip链、容器与打包大小分别计量。`[verified: Arm《ASTC Format Overview》“Block compression”；ASTCCompressor.cpp L3067–3072；ImageOperations.cpp L2975–2985]` `[opinion]`
- preset统一称编码预设／编码档位，原交流“present速度”按preset解释。fastest至exhaustive控制编码搜索投入与时间／质量取舍，同图同尺寸同blockSize的payload容量相同，编码耗时和最终质量分别测量。`[verified: ASTCCompressor.cpp L620–625、L3067–3108；Arm astc-encoder README “Experimenting”]` `[opinion]`
- LDR为Low Dynamic Range，低动态范围，常见8位颜色分量0～255归一化到0～1。整数除以255只描述归一化，光强解释还取决于颜色编码。`[verified: Unity 2019.4《High dynamic range》“How HDR works”；《Color space》“Linear and gamma color space”]`
- HDR为High Dynamic Range，高动态范围，在线性光照表示中可保留超过1的值，常见浮点表示与EXR／HDR输入。亮度范围、数值精度、实际存储格式分别记录。`[verified: Unity 2019.4《High dynamic range》L159–180；Arm astc-encoder README “Encoder feature support”]` `[opinion]`
- sRGB是常用颜色空间标准，本项目重点区分其非线性颜色编码与Linear数值解释。线性渲染流程可使用sRGB颜色纹理，并在采样时转换，项目渲染色彩空间与逐纹理sRGB属性分别核对。`[verified: Unity《Color space》L170–182；《Gamma Textures with linear rendering》L160–180；ASTCCompressor.cpp L3466–3472]` `[opinion]`
- Linear对颜色表示线性光强，对遮罩／查找表等数据图保留存储值的数学含义并绕过sRGB转换。Normal Map是贴图用途，按线性数据采样，通道值用于还原方向，质量按法线角度分支评价。`[verified: Unity《Working with linear Textures》L174–183；ASTCCompressor.cpp L2552–2559、L3198–3204]`
- LDR／HDR与sRGB／Linear按两个维度记录，可组合为Linear LDR、sRGB LDR和HDR模式。isHDR来自输入格式，useSRGB来自stored color space，isNormalMap来自usage；blockSize和preset来自候选配置。`[verified: Arm astc-encoder README “Compressing an image”L259–264；ASTCCompressor.cpp L3746–3747、L3466–3475、L620–625]`
- PSNR衡量像素误差，SSIM比较局部亮度／对比度／结构，MS-SSIM跨尺度组合，本地msSsimDb为亮度MS-SSIM的dB值。RDO为率失真优化，质量测量、编码优化及打包后收益分别描述，保留本地通道、单位、分支与DLL核实深度。`[verified: ASTCCompressor.cpp L2181–2304、L2456–2541、L2754–2956；Wang等MS-SSIM论文§2–3；Arm ASTC RDO讨论“Approaches”]` `[opinion]`

### 自动选参偏好与标签判定规则

- 修改选参、采集、分类标签或质量评价前，读取[README完整判定规则](README.md#自动选参的偏好与判定规则)，按当前源码复核，区分C++默认值、运行时有效配置和历史快照协议。`[verified: 用户要求“偏好规则…全部写入到readme和agent里面”；ASTCCompressor.cpp L627–643、L1178–1205、L3590–3665]` `[opinion]`
- 候选顺序固定为12×12、10×10、8×8、6×6，每组依次fastest、fast、medium、thorough、exhaustive，共20组。顺序是标签协议的一部分，当前循环顺序执行，扫描阶段RDO关闭。`[verified: ASTCCompressor.cpp L618–625、L2979–2981、L3026–3028、L3088–3108]`
- 按贴图类型判断质量，法线默认meanWavg≤2.5°且p95Wavg≤7°，LDR sRGB默认PSNR≥有效门槛且msSsimDb≥24，其他分支按PSNR门槛。法线角度为从mip0构造的最多四级法线图中各级统计量的像素数加权。`[verified: ASTCCompressor.cpp L627–631、L2622–2673、L3198–3225]`
- 纯黑RGB像素比例≤40%时采用基础PSNR默认35，>40%且≤80%时默认40，>80%时默认42 dB，强档优先。数值随运行配置核对，LITE与主包协议分别保留。`[verified: ASTCCompressor.cpp L628、L634–637、L3166–3175、L3704–3709；README配置调查入口]` `[opinion]`
- 常规分支接受顺序中的首个合格候选后break。源码中的比较次序为payload更少、同字节下PSNR更低、字节与PSNR相同时qualityValue更低，解读时保留首个有效结果立即退出的控制流。`[verified: ASTCCompressor.cpp L3293–3337]`
- 大图size-first触发条件为LDR sRGB颜色图且width×height≥默认512²。首个PSNR通过候选锁定块大小，同块依preset继续尝试，PSNR与MS-SSIM都通过时立即接受。该组始终MS-SSIM失败时，采用最后一个PSNR通过候选并将valid置true。`[verified: ASTCCompressor.cpp L2988–2990、L3241–3284、L3348–3359]`
- size-first锁组后的切组判断发生在候选测量及allResults追加之后，报告中的下一块候选按实际执行记录解释。保留候选覆盖、失败跳过与提前停止状态。`[verified: ASTCCompressor.cpp L3121–3125、L3157–3158、L3238–3256]` `[opinion]`
- 无有效bestResult但有已测结果时，统一按最高PSNR回退，包括法线分支，PSNR并列保留先出现者并返回成功。已测结果为空且bestResult无效时返回失败，success、valid、逐项阈值通过和fallback原因分别记录。`[verified: ASTCCompressor.cpp L3371–3380、L3390–3422]` `[opinion]`
- RDO精炼要求全局开启、正余量、接口可用、有效选中参数和payload，且winnerPSNR≥保存的有效PSNR门槛+默认1 dB余量。沿用块大小与preset重编码，复测质量且payload≤原结果才采用，保留精炼前后指标、attempted、status和最终rdo。`[verified: ASTCCompressor.cpp L643、L2754–2833、L2878–2953、L657–666]` `[opinion]`
- 规则变化同步README与本节，记录候选、阈值、黑像素、大图、回退和RDO协议及源码／DLL版本，复核旧标签与缓存。已有标签称为当前策略选中配置，候选最优性、严格质量通过和实际训练效果分别评价。`[verified: ASTCCompressor.cpp L1178–1205、L1372–1446、L3437–3462；用户本次文档要求]` `[opinion]`

#### 关键判定源码摘录

以下保留质量判断、常规接受和大图回退的实际语句，完整候选表、黑像素分级、锁组、通用回退与RDO代码见[README完整源码片段](README.md#自动选参的偏好与判定规则)。片段只省略纯注释、空行和公共左缩进。`[verified: ASTCCompressor.cpp下列行范围；README对应小节]`


质量判定分支对应源码L3195–3226。`[verified: ASTCCompressor.cpp L3195–3226]`

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

常规保存候选并提前停止对应源码L3324–3338。`[verified: ASTCCompressor.cpp L3324–3338]`

```cpp
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
```

size-first回退采用对应源码L3349–3359。`[verified: ASTCCompressor.cpp L3349–3359]`

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

## 代码组织与Class规范

- 核心实现使用独立class，按[README的目录职责](README.md#目录职责)分包。`models/`维护模型，`data/`维护数据准备、Dataset和DataModule，`training/`维护Trainer，`calibration/`、`evaluation/`、`reporting/`分别维护校准、推理评估和报告。`[verified: 用户要求“MODEL，DATA，TRAIN这些按照规范需要全部分开”“全部以class的形式分开”及本次规范入文档要求]`
- 新功能优先归入已有目录和class，文件围绕一种主要职责组织，紧密相关的类可同文件维护。有状态组件通过实例持有配置、依赖及运行状态，纯计算方法可使用`staticmethod`。`[opinion]`
- 类名使用`PascalCase`，模块和方法使用`snake_case`，新增接口复用现有表示和调用方式，所有Python函数遵循下节的类型注解要求。`[opinion]`
- 依赖按配置与工具 → 数据／模型／推理与指标 → 训练／校准／评估 → CLI组织。数据准备和CLI帮助路径保持CPU依赖，Torch Dataset与DataModule从`data.dataset`按需导入。`[opinion]`
- 新业务逻辑放入对应class，CLI构造组件并调用公开方法。包入口负责导出和薄兼容，既有函数入口委托给class实现。`[opinion]`
- 结构调整时核对CLI、检查点键与严格加载、初始化随机数顺序、resume状态、数据清单指纹及测试封存。先运行小样本回归，再扩大运行范围，报告写入`experiment report/`。`[opinion]`
- 修改架构时同步[README规范](README.md#代码组织与class规范)和本节，具体实现与兼容性记录见[重构报告](<experiment report/class-refactor-20261110/README.md>)。`[opinion]`
- 可维护的启动脚本统一放在根目录`script/`，调用src中的class，阶段之间共享同一TOML的实验目录。历史运行脚本与原始日志按实验工件归档在`experiment report/.local/`。`[verified: 用户要求“用脚本启动的脚本全部放到script里面”；opinion: 入口与历史工件的维护边界]`
- 训练配置使用`TrainConfig`，SwanLab设置使用`SwanLabConfig`，命令行显式值覆盖TOML。添加配置项时同步参数校验、有效配置快照和resume兼容性检查。`[opinion]`
- 实验跟踪逻辑放入`tracking/`的class，上传已有可计算指标与聚合图表。创建跟踪run前检查训练目录与resume条件，保存run ID，失败时正确结束跟踪；历史导入保留来源指纹与historical_import标记。接入和验证记录见[脚本与SwanLab报告](<experiment report/script-swanlab-20261110/README.md>)。`[opinion]`

## 工具与代码风格

- 文本检索优先 `rg`，Python依赖与执行优先 `uv`、`uv run`，采用用户全局规则中的工具偏好。`[verified: 用户提供的全局规则“Available CLI Tools”]`
- 所有Python函数参数和返回值都写类型注解，无返回值显式使用 `-> None`，优先现代类型语法。`[verified: 用户提供的全局规则“Python Preferences”]`
- Python格式与静态检查优先 `ruff`、`basedpyright`，长任务使用无缓冲输出。依赖、检查命令和运行入口以实际代码为准。`[verified: 用户提供的全局规则“Python Preferences”]` `[opinion]`
- 遇到连续3–5次无收敛的排查，汇总已观察的输出与剩余未知项，再调整方法。`[verified: 用户提供的全局规则“Bound investigation”]`

## 修改后验证与交付

- GDC压缩评估使用`--resume`核验同一binding和逐图原始产物后续跑。已有progress中的receipt SHA必须匹配，缺失进度文件时单独核验源图、候选payload、解码图、质量与计时。技术失败及未知历史耗时保留在报告中。JSON写入采用唯一临时文件、fsync和Windows替换重试。`[verified: reproductions/gdc2023/recovery.py、evaluation.py、costs.py；src/adaptive_astc/utils/artifacts.py]`

- Markdown修改后检查本地链接、内部锚点、书目编号及新增内容的来源定位。外部URL格式检查与网络可访问性检查分别报告。`[opinion]`
- 修改原始资料或处理流程时，按影响范围复查哈希、字幕覆盖、截图时间点和元数据一致性。修改代码时先运行对应的小规模入口与相关检查。`[opinion]`
- 检查结果中记录实际命令、输入范围和结果，沿用已有验证记录时注明历史来源。`[opinion]`
- 最终回复列出交付文件、需要用户核对的选择与限制，并以 `Verification:` 汇报实际执行的检查和结果。`[verified: 用户提供的全局规则“Verification after changes”]`
