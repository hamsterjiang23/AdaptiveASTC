# 实验计划 V1：原分辨率 patch 误差回归

V1 记录于 2026-11-11，当前执行中。本计划是重新创建的goal的执行依据，最终验收口径见 [Unity90%执行记录](<../../experiment report/unity-accuracy90-20261111/README.md>)。诊断数值保存在 [evidence.json](evidence.json)，由归档脚本 `experiment report/.local/unity-accuracy90-20261111/plan_v1_analysis.py` 生成，脚本 SHA-256 记录在同一文件。`[verified: 用户本轮重新创建goal要求；create_goal返回active；evidence.json script]`

核心判断是把块大小选择改写为逐块大小的 PSNR 预测。四分类标签由四个候选 PSNR 按阈值唯一确定，PSNR 预测误差约 0.75 dB 时推出的标签准确率约 90%，整图缩放到 224×224 的输入难以提供这种精度。`[verified: evidence.json label_structure、precision_requirement] [opinion: 方案判断]`

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

- 全量目标提取通过：train10000／validation1000生成120,276／12,864个非重叠240patch，44,000个整图候选PSNR重建最大差异1.42e-14 dB，耗时614.55秒。[提取记录](<../../experiment report/unity-accuracy90-20261111/patch-data-full.json>)保留身份与完整归档入口。`[verified: patch-data-full.json counts、patch_counts、wall_seconds]`
- 独立编码检查通过：20张训练图、80个四候选patch，单独编码解码像素均与整图对应区域一致。这是固定astcenc3.3 medium的抽样核验。[检查记录](<../../experiment report/unity-accuracy90-20261111/patch-equivalence20.json>)同时记录320次含变换编码。`[verified: patch-equivalence20.json independent_patch_matches、independent_patch_comparisons、scope]`
- 变换的最大绝对PSNR变化为水平翻转0.84 dB、垂直翻转1.02 dB、90°旋转6.60 dB。首批实验关闭这些增强，后续如启用则重新编码生成对应监督。`[verified: patch-equivalence20.json rows；opinion: 增强决定]`
- 抽样真实编码先保留为独立成本／质量对照，主路径保持预测后一次最终编码。Unity采用原搜索与补测分离的采集方式，保留原策略标签和计时，另补块大小×preset的缺失候选、解码图及各原生质量分支。`[opinion: 本轮执行决定]`
- 当前6次CUDA更新仅为执行探针。独立输出／单调结构、标准stem／去maxpool、EMA及组采样均按配置和对照记录，正式分类对照、回归训练与Unity验收尚未完成。`[verified: patch-training-smoke.json；执行记录“实施差异与对照”]`
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
