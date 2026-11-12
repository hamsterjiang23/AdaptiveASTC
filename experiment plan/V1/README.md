# 实验计划 V1：原分辨率 patch 误差回归

当前数据采集交接中的确认集已按用户批准的V2范围生成[新版名单与采集链](<../../experiment report/unity-accuracy90-20261111/unity-confirmation-v2-revision.md>)，替换47张范围外图，旧名单和失败保留；不恢复V1正式训练。`[verified: unity-confirmation2000-v2.json；unity-data-handoff.md；用户本次替换选择]`

V1 记录于 2026-11-11。用户于 2026-11-12 将本 goal 收尾范围改为数据采集与完整性验收，具体见[数据交接](<../../experiment report/unity-accuracy90-20261111/unity-data-handoff.md>)；模型训练和独立 90% 验收由后续 V2 承接，以下 V1 方案与结果保留为历史记录。`[verified: 用户2026-11-12最新范围调整]` 原始验收口径见 [Unity90%执行记录](<../../experiment report/unity-accuracy90-20261111/README.md>)。诊断数值保存在 [evidence.json](evidence.json)，由归档脚本 `experiment report/.local/unity-accuracy90-20261111/plan_v1_analysis.py` 生成，脚本 SHA-256 记录在同一文件。`[verified: 用户本轮重新创建goal要求；create_goal返回active；evidence.json script]`

核心判断是把块大小选择改写为逐块大小的 PSNR 预测。四分类标签由四个候选 PSNR 按阈值唯一确定，PSNR 预测误差约 0.75 dB 时推出的标签准确率约 90%，整图缩放到 224×224 的输入难以提供这种精度。`[verified: evidence.json label_structure、precision_requirement] [opinion: 方案判断]`

[开发集原始采集](<../../experiment report/unity-accuracy90-20261111/unity-development-capture11000-v1.json>)与[全部20候选](<../../experiment report/unity-accuracy90-20261111/unity-development-candidates11000-v1.json>)已完成train10000／validation1000，共220000候选。完整数据流水线的patch整理、合并、Dataset全读和原规则重放均通过：训练67105个patch、验证7082个patch；11000张的块大小、preset、选择原因、候选测量次数（candidates_measured）全部一致，见[开发语料验收](<../../experiment report/unity-accuracy90-20261111/unity-development-data11000-verification.json>)。确认集2000张采集和完整像素审计仍待完成，因此V2的E0与本goal尚未完成；重放一致不代表模型准确率。`[verified: unity-development-data11000-verification.json counts、patch_counts、exact_policy_replay、e0_complete；opinion: 验收边界]`

## 目标与开发数据

- 最终验收不变：Unity 导入后参考像素与同次搜索标签，独立测试 Top-1≥90%，同时报告质量达标率、payload 与端到端成本。`[verified: unity-accuracy90 README“已确定的验收口径”]`
- Unity 生产数据尚未采集完成。V1 的方法筛选先使用已冻结的 GDC 源图 RGB 数据，即 10,000 训练图和 1,000 验证图，astcenc 3.3 medium，6／8／10／12 四候选，标签规则为 RGB PSNR>35 dB 的最小 payload。选模只看验证集，选出的方法再迁移到 Unity 数据复核。test2000 已有观察结果，只作历史对照。`[verified: data-readiness.json；manifest protocol] [opinion: 开发集安排]`

## 当前基线

- 配置为 ImageNet 预训练 ResNet-18，整图双线性缩放到 224×224，不保留长宽比；SGD lr 0.01、momentum 0.9、weight decay 1e-4，余弦 30 轮，有效 batch 64，未加权交叉熵，FP16 AMP；训练与评估代码中未检索到数据增强。`[verified: evidence.json current_cnn；reproductions/gdc2023/evaluation.py L237–238；src/adaptive_astc/training/trainer.py L131]`
- 验证 Top-1 在第 2 轮达到最高 66.3%，验证 NLL 同时最低（0.828）；第 30 轮训练准确率 99.96%，验证准确率 64.0%，验证 NLL 1.872。`[verified: evidence.json current_cnn]`
- test2000 Top-1 73.55%，balanced accuracy 56.38%。逐类召回为 6×6 88.7%、8×8 25.9%、10×10 20.2%、12×12 90.8%。`[verified: evidence.json current_cnn.test2000]`

## 诊断依据

以下统计均来自训练划分 10,000 张图的 receipt，元数据查表另用验证划分评估。`[verified: evidence.json]`

- **标签等价于阈值规则。** “PSNR>35 dB 的最大块大小，无可行候选时取最高 PSNR”复现全部训练标签，98.62% 的图 PSNR 随块大小单调下降。`[verified: label_structure.rule_reproduces_labels、monotonic_psnr_share]`
- **中间档窗口窄。** 相邻块大小的 PSNR 中位数降幅为 6→8 3.94 dB、8→10 2.83 dB、10→12 1.98 dB。8×8 标签有 61.1%、10×10 标签有 84.9% 的图距最近的阈值边界不足 1 dB。`[verified: label_structure.median_psnr_drop_db、middle_class_margins]`
- **精度要求。** 在四个实测 PSNR 上加高斯误差后重新套用规则，准确率如下表，共享偏移与逐候选独立误差的结果基本相同。`[verified: precision_requirement]`

| PSNR 误差 σ | 0.25 dB | 0.5 dB | 0.75 dB | 1.0 dB | 1.5 dB | 2.0 dB |
|---|---|---|---|---|---|---|
| 推出标签准确率 | 96.6% | 93.4% | 90.3% | 87.2% | 82.0% | 77.2% |

- **元数据单独不足。** 按长边量级、非不透明 Alpha、非方形查表，验证准确率 49.3%，全部预测多数类 12×12 为 46.2%。`[verified: metadata_lookup]`
- **缩放损失细节。** 训练图长边中位数 256，22.2% 的长边≥1024，5.1%≥2048，55.9%≤256。整图统一缩放到 224×224 后，大图细节被压缩，长宽比和绝对尺度也一并丢失。`[verified: label_structure.long_side] [opinion: 信息损失判断]`
- **6×6 类混合两种情况。** 2,593 个 6×6 标签中有 1,167 个是四候选均不达标时的最高 PSNR 回退。`[verified: label_structure.infeasible_fallbacks]`
- **资产组不均衡。** 训练集有 1,305 个资产组，最大组 `Assets/Art/Effects/Texture/Common/Special` 含 2,077 张。`[verified: label_structure.asset_groups]`
- **误差可由已存解码图精确分解。** 300 张训练图的 1,200 个候选，从源图与存档解码 PNG 重算的整图 PSNR 与 receipt 全部一致（容差 0.001 dB，无需翻转）。任意 patch 在整图编码下的误差因此可以直接计算。`[verified: sampled_block_estimator.full_psnr_reconstruction] [opinion: 推论]`

## V1 方案

### 优化目标

- 主输出为四个块大小的误差。patch 级目标为 `10·log10(MSE+ε)`，ε 处理纯色 patch 的零误差；loss 用 Huber，δ 取 1 dB。`[opinion]`
- 用结构保证单调：输出 6×6 的误差，以及三个经 softplus 的非负增量，依次得到 8×8、10×10、12×12。`[opinion]`
- 整图 PSNR 由预测的 patch MSE 按像素数加权平均后再换算，平均在 MSE 域进行。整图 MSE 常由少数高误差 patch 主导，图级 PSNR loss 作为对照项，检验其对阈值附近精度的作用。`[opinion]`
- 决策规则为“预测 PSNR > 35 dB + δ 的最大块大小，无候选达标时取预测 PSNR 最高者”。δ 在验证集上选择，同时报告 δ 对 Top-1、质量违规率与 payload 的影响曲线。`[opinion]`
- 派生标签上的交叉熵作为辅助 loss，权重 0.1–0.3。阈值留在模型之外，Unity 规则中按黑像素比例分档的 35／40／42 dB 可直接套用，不需要重训。`[verified: AGENTS.md 黑像素分档] [opinion: 设计]`

### 输入与数据

- patch 原点对齐到 120 像素，即 6、8、10、12 的最小公倍数，四种块大小的块网格都与整图一致。patch 边长 240，尺寸小于 240 的图整图输入，并用掩码只统计有效像素。`[opinion]`
- 精确目标取自 `labels/NNNNN/{6x6,8x8,10x10,12x12}.png` 与源图 RGB 的逐 patch 平方误差和及像素数。训练和验证共 11,000 张图，按已测速度外推提取约需 20–30 分钟。`[verified: 存档解码图路径与重算一致性] [opinion: 耗时外推]`
- 训练时每图每轮随机取若干 patch，按资产组限制采样权重，避免最大组主导。推理时按网格覆盖整图，再按上面的规则聚合。`[opinion]`
- 增强只考虑 patch 内的翻转和 90° 旋转。ASTC 分区表不严格对称，先经 E1 重新编码核验误差不变性再启用。颜色抖动、缩放与 mixup 会改变真实误差，不使用。`[opinion]`
- 尺寸、长宽比、透明像素比例作为附加输入在 E4 检验。Unity 迁移时，sRGB、法线用途、黑像素比例和大图 size-first 分支直接决定判定规则，需要作为输入或分支条件。`[verified: AGENTS.md 自动选参判定规则] [opinion: 输入设计]`
- 跨划分重复的 37 张纯色图在报告中单独列出。`[verified: diagnostics.json rgb224_cache_collisions]`

### 模型

- 首轮保持 ResNet-18 容量，输入 240 原分辨率 patch，全局池化后输出上述 4 个量。`[opinion]`
- 标准 stem 一开始就下采样 4 倍，ASTC 误差取决于像素级细节。对照组保留步长 2 的卷积并去掉 maxpool。`[opinion]`
- 初始化以随机初始化为主线，ImageNet 预训练作为同结构对照，两组使用相同 seed 规则。patch 级目标使训练样本量大幅增加，降低随机初始化的过拟合风险。`[verified: 用户随机初始化偏好] [opinion: 风险判断]`
- 推理计算量随图像面积增长。以 ResNet-18 每个 240 patch 约 2 GFLOPs 粗估，2048² 图约 73 个 patch、约 150 GFLOPs，需要实测；必要时对大图抽样 patch，并单独评价抽样带来的误差。`[opinion: 估算]`

### 超参数起点

- patch 回归：AdamW，随机初始化 lr 1e-3，预训练 3e-4，weight decay 0.05，1 轮 warmup 后余弦，batch 128 个 patch，FP16 AMP，权重 EMA 0.999，最多 30 轮。`[opinion]`
- 分类对照：label smoothing 0.1，weight decay 5e-4，lr 0.003 与 0.01 两档，15 轮。历史训练第 2 轮已到验证峰值，按历史 689.86 秒／30 轮折算每组约 6 分钟。`[verified: current_cnn.best_validation；unity-accuracy90 README 历史轮时] [opinion: 配置]`
- 早停与选模：回归组按验证集阈值 ±3 dB 内的图级 PSNR RMSE，分类组按验证 NLL，同时保存验证 Top-1 最优权重。`[opinion]`

### 评估与选模

- 验证集报告 Top-1、balanced accuracy、逐类 precision／recall、混淆矩阵、图级 PSNR RMSE（全体与阈值 ±3 dB 内，目标≤0.75 dB）、质量违规率和相对标签的 payload，并按资产组和尺寸分层。`[opinion]`
- calibration 划分保留给后续概率校准，test2000 不参与选模。`[verified: unity-accuracy90 README] [opinion]`

## 实验步骤

[原生训练图采集与标签分布](<../../experiment report/unity-accuracy90-20261111/unity-native-label-distribution.md>)已覆盖全部10000训练图，旧9792条记录未变；12×12占54.34%，其余三类各13.66%–17.10%，用途、尺寸、preset和回退分支另列。原采集已转入验证图，20候选补测和完整CUDA训练仍待完成。保持首轮配置，等验证错误分布再安排采样／loss对照；训练类别比例不单独作为错误归因，验证／确认标签未参与本次分析。`[verified: unity-native-labels10000-v1.json summary、validation_labels_analyzed、confirmation_labels_analyzed；unity-native-labels10000-verification.json；opinion: 后续实验判据]`

[独立确认集评价入口](<../../experiment report/unity-accuracy90-20261111/unity-confirmation-evaluation.md>)完成75项CPU检查和实际66图报告接口核验。新增开发集准入条件：完整原生训练选出的同一权重在1000张验证图上Top-1≥90%，且原始2000确认图与完整像素审计通过后才推理；目的在于保留确认集独立性，不把验证达标视为最终达标。同协议技术失败可用新输出重试，最终报告绑定完整分批产物；当前正式训练／确认测试仍未完成。`[verified: unity-confirmation-evaluation-readiness.json；confirmation_evidence.py validate_training；opinion: 准入设计与完成边界]`

[原生采集到最终压缩闭环](<../../experiment report/unity-accuracy90-20261111/unity-capture-deployment.md>)完成旧smoke8权重的验证2图CUDA预测、每图一次编码与质量复算，16份ASTC／PNG及指标和原记录一致，57项CPU检查通过。两图预测／固定8×8质量达标1/2、2/2，中位83.09／66.12毫秒；本轮没有新训练、confirmation测试或模型增益，完整独立验收继续推进。`[verified: unity-capture-deployment-verification.json；opinion: 验收范围]`

[原生模型封存与推理](<../../experiment report/unity-accuracy90-20261111/unity-sealed-inference.md>)完成两张已观察验证图／13patch的CUDA接口检查，预测数组和选参与原smoke权重结果一致，进程9.93秒；73项CPU检查通过。首次配置tuple／list差异在forward前失败，修复后新身份复跑；原始证据和活动任务源码保持。正式确认集评价、完整压缩对照与90%验收仍未完成。`[verified: unity-sealed-inference-verification.json；opinion: 验收范围]`

[完整像素审计队列](<../../experiment report/unity-accuracy90-20261111/unity-pixel-pipeline.md>)已完成真实66图归档与两种像素检查，完整进程12.71秒，74项CPU检查通过；10000训练／1000验证／2000确认图任务已启动等待上游采集，25份文件冻结。当前没有确认集模型结果，检查本身不修改划分，也不证明裁剪／缩放或历史语料的像素隔离；V1原始证据保持。`[verified: unity-pixel-pipeline-verification.json smoke、full_queue、v1_evidence_sha256；opinion: 完成边界]`

[原生RGBA近重复筛查](<../../experiment report/unity-accuracy90-20261111/unity-near-duplicates.md>)完成7744训练／2验证图的同尺寸、同坐标检查，找到6对低RMSE候选、共12张训练图；47项CPU检查和6对独立重算通过。此次不修改开发划分或标签、不运行模型，完整验证／确认范围及缩放、裁剪等相似性仍未证明隔离，V1原始证据保持。`[verified: unity-near-duplicates-verification.json results.completed7746、v1_evidence_sha256、splits_modified；pytest 47 passed；opinion: 覆盖限制]`

[原始采集规则绑定](<../../experiment report/unity-accuracy90-20261111/unity-capture-policy.md>)已在train64／validation2的真实记录上通过，直接绑定原生LITE规则与选参来源，独立于候选补测文件。44项CPU检查通过，首次历史train缺split失败及旧源码保留；未进行模型forward、确认集评价或新增编码，原V1证据保持不变。`[verified: unity-capture-policy-verification.json counts、prior_failure、model_forward_calls、v1_evidence_sha256；pytest 44 passed]`

[原生采集输入对齐](<../../experiment report/unity-accuracy90-20261111/unity-capture-inputs.md>)完成按资产路径去重的68张开发图／812patch核验：直接由参考图、实际回调和导入属性构造输入，张量与决策元数据均与训练端一致。49项CPU检查通过，未进行模型forward或确认集评价；后续独立推理可复用该接口，仍需来源／像素隔离与模型封存。`[verified: unity-capture-input-verification.json；pytest 49 passed；opinion: 后续接入]`

[独立确认集2000张串行采集](<../../experiment report/unity-accuracy90-20261111/unity-confirmation-series.md>)已完成入口、50项CPU检查和真实配置只读核验。两图原生预检通过后复用其产物，其余1998张按冻结顺序分8批采集；采集与模型独立测试分开，全量原生数据和90%验收仍待完成，V1原始evidence.json保持不变。`[verified: unity-confirmation-series-readiness.json plan、v1_evidence_sha256；pytest 50 passed；opinion: 验收边界]`

[Sprite补测恢复](<../../experiment report/unity-accuracy90-20261111/unity-sprite-recovery.md>)完成真实20候选检查，原16项指标和选中输出一致。补测及三个下游等待任务已换新身份恢复，旧7744／2图产物复核复用；训练配方、开发划分、确认名单和原搜索策略保持。此次是数据管线修复，未提供新模型准确率，完整Unity验收继续等待。`[verified: unity-sprite-recovery-readiness.json；unity-sprite-recovery-verification.json；opinion: 实验范围]`

[原生像素重复审计](<../../experiment report/unity-accuracy90-20261111/unity-pixel-identity.md>)完成7744训练／2验证图检查，5组精确RGBA重复全部位于训练集内；仅RGB分组会合并13组Alpha不同的图片，因此保留RGBA及尺寸身份。21项CPU测试和最终66图检查通过，当前不修改冻结划分；完整validation／confirmation及近重复隔离仍待后续验收，V1原始证据文件保持。`[verified: unity-pixel-identity-completed-v1.json；unity-pixel-identity-verification.json；opinion: 解释与后续范围]`

[尺寸元数据对照](<../../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/metadata.md>)完成27轮CUDA训练，选中epoch27 raw，验证Top-1为84.2%、同一权重近阈值RMSE1.5334dB；比原cap512低0.3个百分点，8×8／10×10召回分别下降2.60／7.81个百分点。新增16参数，总11,178,580，完整进程6244.32秒；本次保留原84.5%模型作为scratch对照。这是GDC开发集单次对照，完整Unity独立测试尚未完成。`[verified: scratch-group512-metadata-result.json metrics、recall_change_pp、process_seconds；opinion: 选模与解释范围]`

组均衡cap512的[末轮BN诊断](<../../experiment report/unity-accuracy90-20261111/normalization.md>)也已完成，重估EMA为84.4%／近阈值RMSE1.4284dB，未超过原最佳84.5%／1.3869dB，后续继续采用原权重作为对照。重估使用16384训练patch、0次优化器更新，独立计入429.16秒进程成本；当前仍未满足V1联合晋级或Unity最终验收。`[verified: normalization-group512.json；对应job receipt；scratch-group512-result.json；opinion: 选模与验收边界]`

| 编号 | 内容 | 完成或晋级判据 |
|---|---|---|
| E1 | 提取 train＋validation 的 120 对齐 patch 误差目标；抽取约 20 张不同尺寸的图，将对齐 patch 单独编码并与整图编码的对应区域比较；同批 patch 测翻转和旋转后的误差变化 | 11,000×4 个整图 PSNR 由 patch 重建与 receipt 差≤0.001 dB；单独编码与整图编码解码像素一致；增强按误差变化分布决定是否启用 |
| E2 | 分类对照：同一 ResNet-18 与 RGB224，加 label smoothing、weight decay 5e-4、早停，E1 通过后加增强；另测有序 loss（CORAL） | 报告验证 Top-1、逐类召回和 NLL，作为“只改参数与 loss”的参照 |
| E3 | patch 回归 ResNet-18，随机初始化与预训练各一组，在验证集上选 δ | 验证 Top-1≥90% 且阈值附近 PSNR RMSE≤0.75 dB 时进入 Unity 复核，否则进入 E4 |
| E4 | 按 E3 的错误分布逐项加入元数据输入、资产组限权、stem 调整、图级 loss，仍不足再升 ResNet-34／50 | 每次只改一项，相对 E3 最优配置报告验证增益与推理成本 |

`[opinion]`

## 待决定事项

1. **抽样探针路线。** 对每个块大小只真实编码随机抽样的块，用抽样误差估计 PSNR，与 Nah 2023 的随机块抽样估计思路一致。300 张训练图上抽 1%–10% 的块（每块大小至少 64 块），推出的标签准确率为 87.0%–91.0%，标准误约 1.7–1.9 个百分点。按 CLI 编码计时折算，额外编码相当于最终编码的 0.22–0.55 倍（总耗时口径）或 0.35–0.56 倍（单图中位数）。它可作为模型的附加特征，但流程会从“模型预测后只编码一次”变为“模型加少量探测编码”，成本口径需要用户确认。`[verified: evidence.json sampled_block_estimator；AGENTS.md Nah 项目适配条目] [opinion: 结合方式]`
2. **Unity 训练集采集方式。** Unity 搜索在首个合格候选处提前停止，比标签更小的块大小不会被测量，回归目标因此不完整。若 V1 路线迁移到 Unity，需要在 10k 采集前决定是否导出每个候选的解码图，或在训练子集上关闭提前停止。各块大小取哪个 preset 的质量，以及 MS-SSIM 与法线角度如何进入目标，在迁移前单独确定。`[verified: AGENTS.md 摘录 ASTCCompressor.cpp L3324–3338] [opinion: 采集建议]`

## 限制与待核实

- σ 模拟假设误差服从与图像无关的高斯分布，真实模型误差存在异方差和相关性，结果只作精度量级参考。`[opinion]`
- 抽样估计只覆盖 300 张长边≤2048 的训练图。成本按 CLI 编码计时（含进程开销）折算，库接口内的实际成本需要另测。`[verified: sampled_block_estimator] [opinion]`
- 整图 PSNR 重算一致只说明解码图方向与指标复现无误。patch 单独编码与整图编码结果一致这一前提在 E1 核验，它影响抽样探针路线以及 patch 模型的输入充分性。`[verified: sampled_block_estimator.assumption_not_verified_here] [opinion]`
- GDC 开发数据与 Unity 规则不同：Unity 使用 20 组块大小／preset 候选、sRGB 的 MS-SSIM 门槛、法线角度、黑像素分档阈值与大图 size-first 分支。在 GDC 上选出的方法需要在 Unity 数据上重新验证。`[verified: AGENTS.md 自动选参偏好与标签判定规则]`

## 版本记录

- V1（2026-11-11）：初版，依据冻结 GDC 训练结果与本次诊断分析。`[verified: evidence.json]`

## 本轮执行补充

- 历史首次启动记录（该队列后因上游Sprite失败结束）：[独立确认集采集入口](<../../experiment report/unity-accuracy90-20261111/unity-confirmation-capture.md>)完成30项CPU检查和两张真实源资产的只读核验；以独立confirmation划分复用原搜索、参考导出和恢复逻辑。两图任务已等待开发采集／补测／完整数据及首轮原生训练成功退出，当前没有新的确认集标签或模型测试；大于两图的扩展需追溯真实smoke原生证据。`[verified: unity-confirmation-capture-readiness.json；unity-confirmation-capture-smoke2-v1.json status、dependencies、native_labels_collected；opinion: 完成边界]`

- [独立确认集预留](<../../experiment report/unity-accuracy90-20261111/unity-confirmation-cohort.md>)已预留2000张主名单、500张备用，主名单覆盖1227个未出现于9份历史清单的资产组；2500份实际源文件及meta身份复核通过。仅完成源资产隔离，后续仍需Unity参考像素、同次原搜索标签、像素重复审计，以及模型和决策冻结后的独立测试；当前未打开模型测试。`[verified: unity-confirmation2000-v1.json primary_images、primary_groups、reserve_images、native_pixels_audited、native_labels_collected、model_sealed；unity-confirmation-reservation-verification.json；opinion: 后续验收]`

- [冻结预测残差诊断](<../../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/README.md#固定预测的残差与阈值诊断>)完成：cap512验证1000上的全局余量101点扫描最高仍为84.5%；逐候选减去近阈值平均残差仅将RMSE从1.3869降至1.3372dB，准确率为83.9%。这类简单修正不加入部署，尺寸元数据终态见上方，继续完成Unity原生训练。偏移与余量在同一验证集拟合／计分，不能当独立泛化收益或模型上限；没有新增训练或test访问。`[verified: scratch-group512-residuals.json；opinion: 后续选择与解释边界]`

- 历史首次启动记录（该队列后因上游Sprite失败结束）：[完整Unity训练衔接](<../../experiment report/unity-accuracy90-20261111/unity-native-training-queue.md>)已完成32训练图／2验证图的CUDA预检：两轮4次实际更新、0次AMP跳步、最佳权重重载通过，完整进程83.45秒。当时等待完整10000／1000数据四阶段核验，正式训练尚未启动；后续GPU任务继续纳入串行调度，独立测试90%仍待验收。`[verified: native-training-full-v1/smoke.json training_updates、checkpoint_audit；unity-native-training-full-v1.json status、stages；opinion: 验收与调度边界]`

- [同次预测与最终编码](<../../experiment report/unity-accuracy90-20261111/unity-deployment.md>)已完成两图、一次预热及三次配对重复，共16次真实编码。两图合计参考PNG到内存mip0 ASTC的中位数为预测路径48.81ms、fixed8路径38.34ms；质量通过率分别1／2与2／2，payload分别59168与81920字节。使用原生smoke8权重，此小样本没有速度或等质量收益结论，也不代表完整Unity验收。`[verified: unity-deployment-smoke2-v1.json summary、measurements；opinion: 解释边界]`

- [原生独立输入与推理计时](<../../experiment report/unity-accuracy90-20261111/unity-inference.md>)已完成两张验证图／13patch的CUDA计时，一次预热、三次正式测量，新预测与原生smoke8权重的已保存预测完全一致。两图合计预处理＋推理＋决策中位数27.50ms；等待3932.86秒与活动2.39秒分开记录。只验证小样本推理，完整Unity模型效果及最终编码另行评价。`[verified: unity-inference-smoke2-v1.json measurements、median_preprocess_inference_decision_seconds、active_seconds；v1-completed-runtime-verification.json stages；opinion: 解释范围]`

- [原生保存预测到最终编码](<../../experiment report/unity-accuracy90-20261111/unity-final-encoding.md>)已通过两图真实检查：预测路径与固定8×8／medium各两次编码，ASTC／解码／原生质量复核一致，进程4.05秒。40项CPU检查及两项原生指标补跑通过；实际DLL闭环另行通过。本次不运行模型forward，只补齐mip0编码阶段，完整Unity训练与独立测试及端到端计时仍待完成。`[verified: unity-final-encoding-smoke2-v2.json；对应job receipt；本轮pytest；opinion: 完成边界]`

- 历史full-v2记录（后因上游失败结束）：[全量原生数据衔接](<../../experiment report/unity-accuracy90-20261111/unity-native-pipeline.md>)已通过25项状态／边界检查及三次66图四阶段闭环，最终复跑22.70秒。完整任务已启动等待原采集、候选补测和4674图准备成功结束，之后自动准备10000／1000完整语料并执行原规则重放。smoke、等待、数据完成和最终模型90%验收分别记录。`[verified: unity-native-pipeline-smoke66-v3.json；unity-native-pipeline-full-v2.json；opinion: 验收边界]`

- [原生决策接口](<../../experiment report/unity-accuracy90-20261111/unity-native-model.md>)完成3906图复核，精确目标全部重建原块大小／preset，不能算模型准确率。3904训练图含262法线及319大图放宽样本，且候选PSNR存在非单调；原生20候选质量输出继续独立。新增[4674图冻结目标准备](<../../experiment report/unity-accuracy90-20261111/unity-patch-batches.md>)已完成，实际4672／2图、23255patch，复用3906图并补充768图；完整开发覆盖仍未完成。`[verified: unity-prediction-interface3906.json；unity-native3906-target-diagnostics.json；unity-patch-batches4674.json counts、patch_counts、coverage；opinion: 原生约束与完成边界]`

- 有效区域末端特征加权汇总已完成正式10轮CUDA对照，保留RGB输入与11,178,564参数；只改变池化，最佳验证78.0%／同权重近阈值RMSE1.7141dB，比原cap512低6.5个百分点，质量达标率77.4%。保留负结果，后续沿用原池化；原卷积仍读取边缘填充，结论限定于该项对照。配置、预测和重载证据见[有效区域对照](<../../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/pixel-sampling.md>)。`[verified: scratch-group512-validpool-result.json changed_configuration、metrics、parameters；opinion: 后续选择与验收边界]`

- Unity原生patch完成[3906图扩展](<../../experiment report/unity-accuracy90-20261111/unity-patch-batches.md>)：17批3904训练图／2验证图、20832patch已完成提取、合并和完整读取，复用2370图目标；完整开发语料和Unity训练仍未完成。同时核对GDC源RGB cap512模型的155个验证错误，其中83个距最近35dB候选阈值≤0.5dB；单patch图近阈值RMSE仍为2.1655dB。后续继续检查有效区域信息，几何分层的相关性不作为根因结论。`[verified: unity-patch-batches3906-config.json；group512-geometry-diagnosis.json paired_group_cap_change、models.scratch_group512.strata；opinion: 后续判断]`

- 固定容量[按有效像素抽样](<../../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/pixel-sampling.md>)：相对84.5%的cap512方案，只改变图内patch概率。训练清单中小于四分之一面积的期望抽样占比从38.82%降至20.67%，每图／组总权重不变；正式10轮完成，最佳82.0%／同权重近阈值RMSE1.4580dB，比原cap512低2.5个百分点，保留负结果。另核对单调目标投影后10000张训练图标签全不变，作为排查证据，不是模型准确率上限。`[verified: patch-pixel-sampling-analysis.json；patch-monotonicity.json；scratch-group512-pixels-result.json；opinion: 对照范围]`

- 原生模型的[CUDA训练链路](<../../experiment report/unity-accuracy90-20261111/unity-native-training.md>)检查通过：随机初始化、8训练图／2验证图、两轮4次实际更新、0次AMP跳步，权重重载一致，完整进程23.81秒。35项CPU检查通过；正式训练要求完整train10000／validation1000，本次不作为生产准确率。`[verified: unity-native-smoke8-v1-result.json；unity-native-training-verification.json；opinion: 验收边界]`

- GDC成组损失的正式配对实验已全部完成：权重0／1为71.2%／71.7%，对应同权重近阈值RMSE3.5647／2.0188dB，低于历史独立采样80.7%。新增loss提高0.5个百分点，但没有挽回当前成组采样配方的退步；按负结果保留，不扩大参数量来掩盖该对照。`[verified: scratch-bag4-comparison.json；opinion: 实验判断]`

### 前期执行记录

以下保留各阶段当时的状态；后续完成结果见上方执行补充及对应实验报告，实时队列见[progress.json](<../../experiment report/unity-accuracy90-20261111/progress.json>)。`[opinion: 历史记录口径]`

- Unity迁移新增[原生模型接口](<../../experiment report/unity-accuracy90-20261111/unity-native-model.md>)：RGBA＋mask＋导入属性，20候选通道误差、整图零通道和非PSNR质量头，18项CPU检查通过。2370图精确目标全部重建原块大小／preset，尚无模型准确率；原型11,377,660参数，与GDC四输出模型的容量差异明确单列，后续CUDA训练和独立测试验收仍待完成。`[verified: unity-native-model-contract.json；unity-prediction-interface2370.json；opinion: 迁移范围]`

- 固定容量资产组限权对照完成26轮，最佳84.5%／同权重近阈值RMSE1.3869dB，10×10召回71.09%；相对标准采样提高3.8个百分点但仍未过联合门槛。后续[成组损失对照](<../../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/bag-loss.md>)已完成两组CUDA检查并启动正式串行训练。`[verified: scratch-group512-result.json；scratch-bag4-smoke-summary.json；scratch-bag4-summary.json；opinion: 验收边界]`

- [Unity原生patch统一语料](<../../experiment report/unity-accuracy90-20261111/unity-patch-assembly.md>)完成2370图部分覆盖的提取及合并，2368／2图、15619patch、47400候选，原生PSNR重建最大差3.772e-6dB。完整11000图准备、Unity模型和独立测试90%仍待完成，evidence.json保持原SHA。`[verified: unity-patch-batches2370.json；unity-patch-assembly2370.json；evidence.json SHA核对；opinion: 后续范围]`

- Unity原生数据开始[按已完成批次准备patch目标](<../../experiment report/unity-accuracy90-20261111/unity-patch-batches.md>)：64训练图／2验证图检查通过，2370图冻结子集已启动。修复真实Unity日志大小写路径差异，以及小型selected计划被误标完整覆盖的问题；42项检查通过。所有原始数据与失败记录保留，完整训练语料和生产验收尚未完成。`[verified: unity-patch-batches-smoke-v2.json；unity-patch-batches2370-config.json；pytest 42 passed；opinion: 后续范围]`

- Unity迁移的[原生RGBA Dataset](<../../experiment report/unity-accuracy90-20261111/unity-dataset.md>)已通过258训练图／2验证图检查，保留20×4通道误差、零误差目标、有效像素mask和输入属性。跨语料重复判定补强为精确patch目标一致；19项测试及真实260图复核通过。此次尚未训练Unity模型，图级非PSNR质量分支与最终90%验收继续保留。`[verified: unity-dataset260-v2.json；test_unity_patch_dataset.py；opinion: 后续范围]`

- 固定容量阶段准备[同图patch聚合损失对照](<../../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/bag-loss.md>)：成组采样和损失组件CPU检查通过，10000训练图上核对40000次patch抽样及MSE聚合；权重0／1使用相同采样作成对控制。该准备阶段未接入训练器；后续接入和CUDA执行结果见本节顶部。冻结验证预测的分组诊断显示单patch图仍有较大误差，因此聚合只作为一项假设，输入／元数据等后续改动依实际结果安排。`[verified: bag-sampling-analysis.json；patch-coverage-diagnosis.json；test_patch_bags.py；scratch-bag4-smoke-summary.json；opinion: 归因与后续范围]`

- Unity迁移的原规则重放通过260张开发图，四项比较（块大小、preset、选择原因、候选次数）全部一致；去掉非PSNR质量分支时，块大小仅207／260一致。该诊断要求Unity路径继续保留MS-SSIM、法线角度、黑像素和大图分支，四个medium候选的GDC PSNR回归维持原开发协议。质量分支预测／聚合与最终Unity90%验收尚待完成，详见[规则重放报告](<../../experiment report/unity-accuracy90-20261111/unity-policy-replay.md>)。`[verified: unity-policy260-bound-v2.json matching_fields、mismatches、psnr_only_footprint_matches；opinion: 迁移要求与待办]`

- 原搜索提前停止的mip0法线已接入统一离线候选补齐。256图5120候选全部完成，新增覆盖3688组，原指标与winner一致；进程609.70秒，补测与原参考采集／策略标签保持独立。连续补测队列258图检查通过；全量参考队列已核验train1088／validation2，继续按冻结划分推进。多mip／HDR及完整生产验收尚未完成。`[verified: unity-candidates-train256-audit.json；对应job receipt；unity-candidate-queue-smoke.json；unity-reference-series.json；opinion: 验收范围]`

- 后续固定容量学习率对照完成12轮，选中epoch7 raw，验证80.7%／近阈值RMSE1.6040dB，比原scratch提高4.7个百分点，10×10召回下降4.69个百分点。末轮EMA经train-only BN重估达到80.9%／1.3716dB，单独记录419.26秒进程成本。随后只改变remove_maxpool的CUDA对照已完成15轮，最佳74.6%／同权重RMSE2.5459dB，比标准stem低6.1个百分点，参数量不变。详见[固定容量对照](<../../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/README.md>)和[BN记录](<../../experiment report/unity-accuracy90-20261111/normalization.md>)。`[verified: scratch-lr0003-result.json；normalization-scratch-lr0003.json；scratch-stem2-lr0003-result.json；opinion: 单项对照范围]`
- [Unity串行全量采集](<../../experiment report/unity-accuracy90-20261111/unity-reference-series.md>)已启动，45批覆盖train10000／validation1000。先前320张train及2张validation已完成，66张真实归档合并检查通过；逐批核验原生参考像素、同次原标签和恢复记录。全量补测、生产训练及独立测试90%尚未完成。`[verified: unity-reference-series-plan.json；unity-reference-series-smoke.json；unity-reference-series.json counts/current_batch；opinion: 完成边界]`

- 全量目标提取通过：train10000／validation1000生成120,276／12,864个非重叠240patch，44,000个整图候选PSNR重建最大差异1.42e-14 dB，耗时614.55秒。[提取记录](<../../experiment report/unity-accuracy90-20261111/patch-data-full.json>)保留身份与完整归档入口。`[verified: patch-data-full.json counts、patch_counts、wall_seconds]`
- 独立编码检查通过：20张训练图、80个四候选patch，单独编码解码像素均与整图对应区域一致。这是固定astcenc3.3 medium的抽样核验。[检查记录](<../../experiment report/unity-accuracy90-20261111/patch-equivalence20.json>)同时记录320次含变换编码。`[verified: patch-equivalence20.json independent_patch_matches、independent_patch_comparisons、scope]`
- 变换的最大绝对PSNR变化为水平翻转0.84 dB、垂直翻转1.02 dB、90°旋转6.60 dB。首批实验关闭这些增强，后续如启用则重新编码生成对应监督。`[verified: patch-equivalence20.json rows；opinion: 增强决定]`
- 抽样真实编码先保留为独立成本／质量对照，主路径保持预测后一次最终编码。Unity采用原搜索与补测分离的采集方式，保留原策略标签和计时，另补块大小×preset的缺失候选、解码图及各原生质量分支。`[opinion: 本轮执行决定]`
- 先期6次CUDA更新仅为执行探针。独立输出／单调结构、标准stem／去maxpool、EMA及组采样均按配置和对照记录，当时正式分类对照、回归训练与Unity验收均未完成；后续结果分项记录。`[verified: patch-training-smoke.json；执行记录“实施差异与对照”]`
- 后续分类五组已完成，验证Top-1从原配置66.3%提高至最高68.6%，中间类别与质量指标仍不足；详见[分类报告](<../../experiment report/unity-accuracy90-20261111/classification-controls/README.md>)。`[verified: classification-controls/comparison.json；opinion: 指标判断]`
- 单调输出、标准stem、EMA0.999与batch128的新增CUDA探针完成6次更新，权重重载与保存预测核验通过；正式随机初始化／预训练回归队列已启动，见[回归报告](<../../experiment report/unity-accuracy90-20261111/patch-v1/README.md>)。增强继续关闭，组权重及图级loss留待错误分析后逐项比较。`[verified: patch-v1-smoke.json、patch-v1-smoke-audit.json、patch-v1/summary.json；opinion: 后续对照]`
- Unity原搜索与补测分离的两图核验通过：40候选、24新增覆盖，原选中payload／解码一致，原16项质量按两位小数精度吻合。采用原样提取的引擎PSNR／MS-SSIM函数，原DLL通过采集协议锁绑定；真实法线／HDR、直接回调参数与全量数据仍未验收，见[补测报告](<../../experiment report/unity-accuracy90-20261111/unity-supplement.md>)。`[verified: unity-supplement2-bound.json；unity-quality-probe.json]`
- 后续随机初始化正式回归完成14轮，最佳验证Top-1为76.0%、阈值附近RMSE为1.7681dB；同一权重余量0.5dB时为76.2%／质量达标84.4%。最佳权重重载通过，预训练对照继续。EMA最高仅48.3%，后续需要按实际错误选择单项对照。`[verified: patch-v1/scratch-result.json；opinion: 后续实验安排]`
- 直接回调参数两图采集已通过，16次回调的RGBA哈希与归档图一致，原源码字节恢复；基于实际Alpha／profile绑定的40候选补测通过。64图覆盖检查另记录558回调，覆盖63 Default与1 NormalMap，源码及导入设置恢复通过；真实法线／HDR完整补测与全量数据仍未验收。`[verified: unity-actual-options2-revalidated.json；unity-supplement2-actual.json；unity-actual-options64.json；smoke1-receipt.json]`
- 实际参数绑定的颜色补测扩展到8图160候选，原52组指标和winner一致；另复用4096²法线样本20原候选，重新解码及原生角度评价通过，0次新编码。该法线的全部候选均未过角度门槛，原标签保留最高PSNR回退。多mip法线、HDR和完整生产数据尚未验证。`[verified: unity-color8.json；unity-normal20-policy.json]`
- 首批回归两组均已完成14轮并通过最佳权重重载。随机初始化为76.0%／1.7681dB，预训练为88.8%／0.9736dB；参数量都为11,178,564，尚未达到E3联合判据，进入固定容量的误差诊断。预训练组8×8／10×10召回为81.77%／75.78%。先对冻结末轮raw／EMA权重用train-only输入重估BN统计，单独记录结果，之后再决定训练参数与结构对照。`[verified: patch-v1/scratch-result.json、pretrained-result.json；opinion: 诊断顺序]`
- 两组BN诊断完成：固定epoch14 EMA权重、训练输入重估统计量，随机初始化为76.7%／1.6467dB，预训练为89.2%／0.9512dB，比原训练最佳raw分别高0.7／0.4个百分点。学习参数未变、优化器更新0次，按独立后处理实验记录；近阈值误差和最终Unity验收仍待改进。`[verified: normalization-scratch.json；normalization-pretrained.json；patch-v1/scratch-result.json、pretrained-result.json；opinion: 记录范围]`
- 固定容量阶段新增scratch学习率单项对照：1e-3→3e-4，其余正式设置与原V1相同。小语料两轮／4次CUDA更新与最佳权重重载通过，正式train10000／validation1000训练启动。该对照先检查训练配方，再按结果决定元数据、采样、stem或图级loss；扩容仍排在固定容量改进之后。`[verified: patch-fixed-capacity各suite和smoke-summary.json；opinion: 执行次序补充]`
- 真实4096²法线后续重编码全部20候选，完整ASTC与RGBA解码均与同次原搜索一致。该结果只覆盖mip0、normal-pack=false，原候选全不达标的回退身份保持。开发采集新增显式train／validation分批路径，保留划分并拒绝test／calibration；两张真实validation图的导出／恢复通过，7次回调吻合，再补齐40候选，新增33组，原winner一致。`[verified: unity-normal-replay20.json；test_unity_reference_batches.py；unity-validation2.json；unity-validation2-supplement.json]`

- 去maxpool末轮EMA的train-only BN重估完成，为78.6%／2.1127dB，仍低于标准stem。下一项固定容量对照只改变资产组抽样cap512，保留标准stem／scratch／lr0.0003，CUDA小样本与权重重载通过后正式启动；当前没有完整效果结论。`[verified: normalization-scratch-stem2-lr0003.json；scratch-group512-suite.json、scratch-group512-smoke-summary.json；opinion: 单项假设与结果范围]`

- Unity迁移新增RGBA逐通道监督提取：258图、5160候选，PSNR重建最大差3.74e-6dB，数据准备进程57.00秒。两张多级评价法线40候选重放通过，全量补测以新身份继续并保留首轮失败与已完成工作；MS-SSIM／角度仍是整图监督，相关模型目标待完成。详见[原生监督与恢复报告](<../../experiment report/unity-accuracy90-20261111/unity-patch-targets.md>)。`[verified: unity-patches-train256.json；unity-normal-multimip2.json；unity-candidate-queue-multimip-v2-config.json prior_queue；opinion: 迁移待办]`
