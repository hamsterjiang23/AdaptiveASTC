# V2 实验报告

## Unity 协议、质量预测、编码续搜与当前结论

整理日期为 2026-11-13（UTC+8）。本文沿用 V1 报告的阅读顺序，说明数据处理、网络输入、模型结构、损失、选参流程、实验结果及验收状态。统计范围为 Unity 原生 train10000／validation1000，确认集预留 2000 张。文中结果来自已归档实验，本次整理执行来源核验与文档生成。文末提供证据名称、文件链接及字段定位。`[verified: 数据交接 counts；训练对照 results；系统实测 status]`

## 当前结论

**单次预测的最佳原始验证 Top-1 为 86.9%，当前选定的“预测候选起点＋实际编码质量门控＋向后续搜”系统达到 93.6%。** 两者使用同一个 ResNet-34 ImageNet 初始化、整图头再训练后的模型。系统平均每张图编码 1.627 次，702／1000 张一次完成；独立确认集的模型评价处于待执行状态。`[verified: 最佳模型 selected_checkpoint_metrics.accuracy；系统实测 summary.forward.validation_metrics；续搜核验 encoding_count_distribution；确认准备 formal_confirmation_ready]`

| 评价对象 | 当前结果与证据 |
|---|---|
| 单次预测＋原规则决策 | validation1000 Top-1 86.9%，完整配置匹配 58.8%，所选候选严格质量通过 68.2%。`[verified: 最佳模型 selected_checkpoint_metrics]` |
| 同验证集余量拟合 | Top-1 87.1%，拟合及计分均使用同一 validation1000。`[verified: 最佳模型 same_validation_fitted_top1、same_validation_fitted_parameters]` |
| 当前选定的真实续搜系统 | Top-1 93.6%，完整配置匹配 80.4%，严格质量通过 87.5%，相对原标签质量回退 0 张。`[verified: 系统实测 summary.forward.validation_metrics]` |
| 系统编码成本 | 平均 1.627 次，中位数 1 次，P95 为 5 次，最大 16 次。`[verified: 系统实测 summary.forward.validation_metrics.candidates_measured]` |
| 系统输出体积 | mip0 payload 32,067,120 字节，为 fixed8／medium 的 53.66%、原搜索标签的 101.28%。`[verified: 系统实测 summary.forward.validation_metrics.payload_bytes、payload_ratio_to_fixed8、payload_ratio_to_original]` |
| 真实配对计时 | 续搜 195.80 ms／图，fixed8／medium 21.34 ms／图，均为三次整集耗时的中位数除以 1000。`[verified: 系统实测 summary.forward、summary.fixed8]` |
| 独立确认验收 | 目标为 confirmation2000 块大小 Top-1≥90%；当前正式结果待测，范围修订与执行授权待决定。`[verified: V2计划 L17–19；确认准备 pending、formal_confirmation_ready；范围提案“待批准的执行范围”]` |

## 1. 任务与评价口径

### 1.1 要预测什么

输入一张 Unity 已完成导入处理的纹理和实际导入属性，预测 20 个 ASTC 候选的质量，使用该图原采集绑定的 `UnitySearchPolicy` 选出块大小和 preset。原始生产目标为预测选参后执行一次最终编码，当前系统主线进一步使用实际压缩质量决定是否续搜。`[verified: V2计划 L9、L27–35、L74–82；系统执行 L17–19]`

主指标为块大小 Top-1，即最终块大小与同次原搜索标签一致的图片比例。完整配置匹配同时要求块大小和 preset 一致。严格质量通过率按最终候选实际解码后的原生质量计算；质量回退统计“原标签严格合格、当前选择严格不合格”的图片数。`[verified: V2计划 L17–19；系统实测 summary.forward.validation_metrics；质量转换 L203–245]`

### 1.2 当前验收进度

| 项目 | 状态 |
|---|---|
| 开发数据完整性 | 10000／1000 张开发图、220000 个候选、74609 个 patch 完成；原规则四字段重放差异 0。`[verified: 数据交接 counts、development_candidate_count、development_patch_counts、exact_policy_replay]` |
| 单次预测开发 90% | 最佳原始结果 86.9%，开发目标仍有 3.1 个百分点差距。`[verified: 最佳模型 selected_checkpoint_metrics.accuracy、validation90_achieved；opinion: 差值计算]` |
| 系统组合开发 90% | 真实 validation1000 为 93.6%，系统准入材料已准备。`[verified: 确认准备 system_admission.accuracy、status]` |
| 独立确认 90% | 2000 张原采集完成，模型评价待执行。`[verified: 数据交接 counts.confirmation、test_opened；确认准备 formal_confirmation_ready]` |

质量、payload、完整配置匹配和耗时均随主指标报告。当前确认验收为块大小 Top-1≥90%，其余指标按用户确定的报告口径记录。`[verified: V2计划 L17–19]`

## 2. Unity 原生协议

### 2.1 输入、候选和质量阈值

| 项目 | 固定协议 |
|---|---|
| 参考像素 | Unity 导入处理完成后、进入 ASTC 搜索前的第一个 image／mip0，原尺寸 RGBA32。实际编码回调提供导入属性。`[verified: V2计划 L27]` |
| 候选顺序 | 块大小依次 12×12、10×10、8×8、6×6；每块依次 fastest、fast、medium、thorough、exhaustive，共 20 个。`[verified: V2计划 L28；原规则 L68–74]` |
| 颜色 PSNR | 基础阈值 30 dB；纯黑像素比例 >40% 时升至 35 dB，>80% 时升至 37 dB。以 PSNR≥有效阈值判断通过。`[verified: V2计划 L29；原规则 L93–112]` |
| sRGB 颜色图 | 在 PSNR 条件之外，严格质量还要求 MS-SSIM≥21 dB。`[verified: V2计划 L29；原规则 L110–112]` |
| 法线图 | 严格质量由平均角度≤3.2° 且 p95≤9°判断。用途按法线标记识别，本轮实际 normal-pack=false。`[verified: V2计划 L29、L33；原规则 L103–109]` |
| 阈值精度 | 从每批原缓存的 tableConfig 取值，质量数值与阈值按 float32 比较。`[verified: 原规则 L30–55、L75–89；质量转换 L159–176]` |
| PSNR 通道 | 对误差非零的参与通道平均 MSE；Alpha 参与由 need_alpha 和 alpha_constant 决定，零通道另有显式掩码。所有参与通道均无误差时返回 100 dB。`[verified: 质量转换 L88–110]` |
| 数据与编码范围 | Default／Sprite LDR 颜色图、Linear RGBA8／Tex2D 法线，mip0、RDO 关闭。HDR、完整 mip 链和导入全过程的结果待后续覆盖。`[verified: V2计划 L33]` |

### 2.2 原标签如何产生

常规分支按固定候选顺序取第一个严格合格候选。大图分支适用于 sRGB 非法线图且面积≥512²，首个 PSNR 合格候选锁定块大小，同块继续寻找同时满足 MS-SSIM 的候选；该块全部尝试后仍未严格合格时，采用最后一个 PSNR 合格候选，记录为 `size_first_relaxed`。其余失败情况按已测候选最高 PSNR 回退，并保留选择原因。`[verified: 原规则 L98–148；V2计划 L30]`

原生循环在跨入下一块大小时先编码并计数，再检查已锁定块大小，因此候选次数包含该次跨块测量。块大小、preset、原因及次数均属于重放验收字段。`[verified: 原规则 L127–148；数据交接 exact_policy_replay]`

标签含常规合格、大图放宽和最高 PSNR 回退分支。validation1000 原标签严格通过 874 张，放宽 93 张、最高 PSNR 回退 33 张；后两类合计 126 张。`[verified: 规则参照 validation_baselines.original_rule_measured；系统实测 summary.forward.validation_metrics.groups.original_size_first_relaxed、original_highest_psnr_fallback]`

## 3. 数据与训练样本

### 3.1 当前使用的新版数据

| 划分 | 图片数 | patch 数 | 质量监督与用途 |
|---|---:|---:|---|
| train | 10000 | 67436 | 原生参考 RGBA、20 候选质量及解码结果，训练使用。`[verified: 数据交接 counts、development_patch_counts；V2计划 L44]` |
| validation | 1000 | 7173 | 20 候选监督供评价、选模及开发诊断，模型输入来自参考像素和属性。`[verified: 数据交接 counts、development_patch_counts；V2计划 L44、L85–92]` |
| confirmation | 2000 | 待正式模型评价时确定 | 原生参考图及原搜索标签已采集，正式独立评价待执行。`[verified: 数据交接 counts、test_opened；确认准备 pending]` |

新版开发语料 SHA-256 为 `560094e9d87b220b037ed37574e5941f0eff0675ffb43f34737f904e1f895c57`。全部 11000 张开发图的原规则四字段重放通过，训练和验证分别为 0 差异。`[verified: 主模型配置 corpus_sha256；数据交接 exact_policy_replay]`

### 3.2 从整图误差得到 patch 监督

1. 每张开发图保留同次原搜索参考图和标签，并补齐 4 种块大小×5 个 preset 的完整 20 候选解码结果及原生质量。开发集共 220000 个候选。`[verified: V2计划 L39、L44；数据交接 development_candidate_count]`
2. 以左上角为原点，每隔 240 像素切一个非重叠 patch，边缘保留实际有效尺寸。240 为 6、8、10、12 的公倍数，四种 ASTC 块网格在 patch 边界对齐。`[verified: V2计划 L44；V1示例 L106–110]`
3. 对参考图及每个候选解码图逐像素计算 RGBA 各通道 SSE，只累计有效像素。每个 patch 具有 20×4 组通道误差目标。`[verified: V2计划 L44、L75；原生Dataset L164–165]`
4. patch 补齐采用边缘复制，另保留有效 mask，张量值由 RGBA／255 得到。整图 MS-SSIM、平均角度、p95 角度及零误差通道保留整图监督。`[verified: 原生Dataset L179–195；V2计划 L75–76]`

训练目标为 `log10(SSE／(有效像素数×255²)+1e-10)`。推理将 patch 预测恢复到 MSE 域，按有效像素数加权聚合至整图通道 MSE，再结合零通道掩码计算 Unity PSNR。`[verified: 原生Dataset L164–165；质量转换 L58–110]`

这里的参考图为 Unity 导入后、ASTC 编码前的像素归档。补测从该 `original.png` 还原实际回调行序，使用原编码 DLL 生成候选解码图，再与同一参考像素比较。模型训练从 Dataset 读取已经准备好的误差目标。磁盘源图经过 Unity 缩放、颜色及用途处理后才形成这份参考输入，直接使用磁盘源图计算误差时，需要重新核验其与实际输入的像素一致性。`[verified: 输入适配 L87–101；候选编码 L365–423；原生训练 L177–184、L343–344；opinion: 输入一致性要求]`

### 3.3 重复审计与确认集状态

完整 13000 张像素审计已完成。精确 RGBA 重复为 9 组、18 张，跨划分精确重复为 0 组；同尺寸、同坐标 RGBA RMSE≤2／255 的近重复为 25 对，其中跨划分 11 对。审计覆盖范围为原尺寸对齐像素。裁剪、缩放与语义相似性属于待覆盖范围。`[verified: 数据交接 pixel_audit、full_pixel_audit_complete；V2计划 L41]`

确认集身份复核将上述 11 条训练—确认关系定位到 10 张确认图，已形成按冻结备用顺序替换的提案，拟保留 1990 个原位置。方案批准、10 张补入图的原生补采和完整像素复审待完成。当前提案核验记录 `cohort_modified=false`、`test_opened=false`，模型调用为 0。`[verified: 范围提案“身份元数据核验”“逐位置替换方案”“本轮执行记录”]`

身份核验记录还保留了初次结构预览显示首条采集记录既有原生选参字段的情况。范围修订依据为身份与近重复关系。`[verified: 范围提案“本轮执行记录”末段]`

## 4. 当前模型如何计算

### 4.1 输入与骨干

当前选定模型为 `UnityQualityRegressor`，使用 ImageNet 初始化的 ResNet-34、仅均值整图池化和后续 sampled4 整图头再训练，总参数 21,414,140。`[verified: 主模型配置 backbone_name、initialization、image_pooling；最佳模型 parameters、selected_variant]`

| 部件 | 具体做法 |
|---|---|
| 像素输入 | 每个 patch 的 RGBA∈[0,1] 映射到 [−1,1]，再与有效 mask 拼成 5×240×240。`[verified: 原生模型 L92–108；原生Dataset L179–195]` |
| ImageNet 迁移 | 首层 RGB 卷积核复制到前 3 通道，新增 Alpha 与 mask 通道权重初始为 0。`[verified: 原生模型 L63–81]` |
| 骨干 | ResNet-34 使用 [3,4,6,3] BasicBlock 配置，输出通道数 512。`[verified: 原生模型 L30、L54–61]` |
| patch 特征 | 将有效 mask 池化到特征图分辨率，用其加权空间特征，得到 512 维 patch 向量。`[verified: 原生模型 L107–110]` |
| 导入属性 | log2 宽、log2 高、sRGB、法线、需要 Alpha、Alpha 恒定、法线评价 mip 数、纯黑比例，共 8 项。按 [12,12,1,1,1,1,4,1] 缩放。`[verified: V2计划 L44；原生模型 L111–113]` |
| FiLM 条件化 | 8 维属性经线性层生成 gain 与 offset，对 patch 特征执行 `f×(1+gain)+offset`。`[verified: 原生模型 L34–36、L111–114]` |
| patch 质量头 | 512→80 的线性层，重排为 20×4 通道 log-MSE。`[verified: 原生模型 L37、L114]` |
| 整图特征 | 同图 patch 特征按有效像素数加权均值聚合，随后拼接 8 项属性，得到 520 维输入。`[verified: 原生模型 L144–159、L183–187；主模型配置 image_pooling]` |
| 整图质量头 | 520→140，前 80 项为 20×4 零通道 logits，后 60 项经 softplus 得到 20×3 的 MS-SSIM／平均角度／p95。`[verified: 原生模型 L38、L46–52、L183–190]` |

### 4.2 训练过程与模型选择

主模型第一阶段完整训练 30 轮，每批 16 张图，每图每轮有放回抽 4 个 patch，workers=2。AdamW 学习率 3e-4、weight decay 0.05，1 轮 warmup 后余弦退火，FP16 AMP，patience=0、seed=20261112。原生三项附加损失权重各 0.1，零通道判定门槛 0.5。验证使用每图全部 patch。`[verified: 主模型配置 epochs、image_batch_size、patches_per_image、learning_rate、weight_decay、warmup_epochs、patience、seed、zero_weight、ssim_weight、angle_weight；系统执行 L69；V1示例 L157–158]`

第二阶段从已完成的 ResNet-34 ImageNet 训练检查点出发，冻结编码器、FiLM、逐通道误差头和 BN 统计量，缓存原生特征，仅训练整图头。每图仍有放回抽 4 个 patch，按有效像素数聚合，AdamW 恒定学习率 3e-4、weight decay 0.05，运行 30 轮。当前选中的为第二阶段 epoch15，训练参数 72,940，编码器和通道头状态核验保持一致。`[verified: 系统执行 L253–259；头部配置 epochs、patches_per_image、learning_rate；最佳模型 selected_checkpoint_epoch、trainable_parameters、encoder_and_channel_head_unchanged]`

第一阶段训练器耗时 2023.56 秒，第二阶段 357.66 秒，合计 2381.22 秒，约 39.69 分钟。这里记录训练器耗时，部署路径的计时见第 8 节。`[verified: 最佳模型 initial_trainer_wall_seconds、trainer_wall_seconds、total_two_stage_trainer_seconds；opinion: 分钟换算]`

### 4.3 损失函数

完整训练的总损失为 `Lpatch + 0.1×Lzero + 0.1×Lssim + 0.1×Langle`。各项只在适用通道或用途上计算。`[verified: 原生损失 L113–133；主模型配置 zero_weight、ssim_weight、angle_weight]`

| 分量 | 定义 |
|---|---|
| patch 通道误差 | 对适用通道的预测及实测 log-MSE 使用 Huber，delta=0.1。`[verified: 原生损失 L113–114]` |
| 零通道 | 对适用通道使用 binary cross entropy with logits，目标为实际是否零误差。`[verified: 原生损失 L115–117]` |
| MS-SSIM | sRGB 颜色图整图指标使用 Huber，delta=1。`[verified: 原生损失 L118–121；V2计划 L76]` |
| 法线角度 | 法线图平均角度与 p95 指标使用 Huber，delta=1。`[verified: 原生损失 L122–124；V2计划 L76]` |
| 整图头再训练 | 使用冻结特征上的零通道、MS-SSIM 与角度监督，编码器及逐通道误差头的冻结状态经过审计。`[verified: 系统执行 L257–259；最佳模型 encoder_and_channel_head_unchanged]` |

## 5. 从预测到最终 ASTC

### 5.1 单次预测路径

参考 RGBA／属性 → 全部 patch 的神经网络特征提取 → 20 候选通道 MSE 与整图质量预测 → 零通道门槛判定 → 原生 PSNR 还原 → 原规则选参 → 最终候选 ASTC 编码一次。所选候选的真实质量使用归档开发目标评价。该路径的最佳原始 validation1000 Top-1 为 86.9%。`[verified: V2计划 L74–82；原生模型 L193–213；质量转换 L58–157；最佳模型 selected_checkpoint_metrics]`

### 5.2 当前选定的预测起点向后续搜

1. 使用冻结 ResNet-34 原始预测，零通道门槛 0.5，各质量余量为 0，先由原规则选出具体块大小＋preset，对应 canonical20 中的候选索引。`[verified: 开发冻结 identity.decision；系统执行 L41–45]`
2. 从该候选索引开始实际编码、解码并计算原生质量，按候选顺序向后搜索。常规分支首个严格合格即停止；大图分支沿用锁块和放宽逻辑。当前执行使用无固定预算的后缀搜索。`[verified: 系统执行 L17–19、L43；系统策略 L92–118]`
3. 失败回退在本次已经实际测量的候选中选择最高 PSNR；大图锁块时保留该块最后一个 PSNR 合格候选。最终结果复用已生成的 ASTC。`[verified: 系统策略 L92–118；系统执行 L17–19、L488–490]`
4. 每轮使用新的完整 1000 图预测，保存实际查询顺序、ASTC、解码像素与原生质量审计。一次预热及三次正式重复的预测数组逐位一致。`[verified: 系统执行 L19、L35–39；系统实测 measurements、model_parameters_and_buffers_unchanged]`

这条路径通过模型跳过部分候选，再以真实质量门控修正输出。平均 1.627 次、最大 16 次的编码开销属于当前系统方案。`[verified: 系统实测 summary.forward.validation_metrics.candidates_measured；opinion: 机制概括]`

## 6. 单次预测实验结果

### 6.1 完整训练与单项对照

下表统一使用各自选中权重的原始 Top-1、同权重颜色近阈值 RMSE、同验证集余量拟合 Top-1。近阈值 RMSE 统计颜色候选实测 PSNR 距各图有效阈值 ±3 dB 的部分，单位 dB。同集拟合结果保留其开发诊断身份。`[verified: 训练对照 results；质量转换 L236–240；系统执行 L189]`

| 实验 | 原始 Top-1 | 近阈值 RMSE | 同集拟合 Top-1 | 依据 |
|---|---:|---:|---:|---|
| ResNet-18 原生基线，均值＋最大池化 | 73.9% | 2.9747 | 76.0% | `[verified: 训练对照 results.baseline]` |
| MS-SSIM 权重改为 0.03 | 72.7% | 3.6068 | 74.3% | `[verified: 训练对照 results.ssim_weight003]` |
| 仅均值池化，早停 | 75.0% | 3.3833 | 77.4% | `[verified: 训练对照 results.mean_pooling]` |
| ResNet-18 ImageNet，早停 | 81.3% | 3.4176 | 82.5% | `[verified: 训练对照 results.imagenet_mean]` |
| ResNet-18 随机初始化，完整 30 轮 | 81.3% | 2.1585 | 81.5% | `[verified: 训练对照 results.mean_full30]` |
| ResNet-18 ImageNet，完整 30 轮 | 85.7% | 1.9217 | 86.4% | `[verified: 训练对照 results.imagenet_full30]` |
| 随机初始化＋EMA，最终选中 raw | 81.3% | 2.1585 | 81.5% | `[verified: 训练对照 results.mean_ema099]` |
| 随机初始化模型＋整图头 sampled4 | 81.2% | 2.1532 | 81.3% | `[verified: 训练对照 results.mean_head_sampled4]` |
| 随机初始化模型＋整图头全部 patch | 81.1% | 2.1432 | 81.4% | `[verified: 训练对照 results.mean_head_all]` |
| ResNet-18 ImageNet＋整图头 sampled4 | 86.3% | 1.9180 | 86.7% | `[verified: 训练对照 results.imagenet_head_sampled4]` |
| PSNR 两阶段＋整图头 sampled4 | 76.4% | 2.0084 | 77.1% | `[verified: 训练对照 results.psnr_head_sampled4]` |
| 资产族每轮限额 64 张 | 78.0% | 2.8970 | 79.0% | `[verified: 训练对照 results.mean_familycap64]` |
| 法线每图每轮重复 2 次 | 79.2% | 2.2757 | 79.8% | `[verified: 训练对照 results.mean_normalrepeat2]` |
| ResNet-34 随机初始化，完整 30 轮 | 79.2% | 2.7386 | 79.4% | `[verified: 训练对照 results.mean_resnet34_full30]` |
| ResNet-34 ImageNet，完整 30 轮 | 86.2% | 1.6128 | 86.8% | `[verified: 训练对照 results.imagenet_resnet34_full30]` |
| ResNet-34 ImageNet＋整图头 sampled4 | 86.9% | 1.6135 | 87.1% | `[verified: 训练对照 results.imagenet_resnet34_head_sampled4]` |
| ResNet-50 随机初始化，完整 30 轮 | 80.5% | 2.6311 | 81.1% | `[verified: 训练对照 results.mean_resnet50_full30]` |
| ResNet-50 ImageNet V1，完整 30 轮 | 85.6% | 1.6411 | 85.9% | `[verified: 训练对照 results.imagenet_resnet50_full30]` |
| ResNet-50 ImageNet V1＋整图头 | 86.0% | 1.6389 | 86.3% | `[verified: 训练对照 results.imagenet_resnet50_head_sampled4]` |
| ResNet-50 ImageNet V2，完整 30 轮 | 85.4% | 1.9043 | 85.4% | `[verified: 训练对照 results.imagenet1k_v2_resnet50_full30]` |
| ResNet-50 ImageNet V2＋整图头 | 85.3% | 1.8845 | 85.5% | `[verified: 训练对照 results.imagenet1k_v2_resnet50_head_sampled4]` |

### 6.2 最佳单次预测模型的输出

| 指标 | ResNet-34 ImageNet＋整图头再训练 |
|---|---|
| Top-1／balanced accuracy | 86.9%／78.96%。`[verified: 最佳模型 selected_checkpoint_metrics.accuracy、balanced_accuracy]` |
| 完整配置匹配 | 58.8%。`[verified: 最佳模型 selected_checkpoint_metrics.full_choice_accuracy]` |
| 严格质量通过／质量回退 | 68.2%／192 张。`[verified: 最佳模型 selected_checkpoint_metrics.actual_quality_pass_rate、quality_regression_images]` |
| 同权重近阈值 RMSE | 1.6135 dB，共 4687 个颜色候选。`[verified: 最佳模型 selected_checkpoint_metrics.color_near_threshold_rmse_db、color_near_threshold_candidate_count]` |
| 所选 mip0 payload | 31,392,800 字节。`[verified: 最佳模型 selected_checkpoint_metrics.selected_payload_bytes]` |
| 同集余量拟合 | Top-1 87.1%，严格质量 69.5%，回退 180 张。`[verified: 最佳模型 same_validation_fitted_top1、same_validation_fitted_metrics]` |

### 6.3 冻结预测替换诊断

固定最佳模型保存的验证预测，每次只把指定分量替换成该候选的实测值，再重放原规则。该操作用于定位预测分量与决策错误的联系。`[verified: 最佳模型 attribution_accuracy；系统执行 L127–131]`

| 替换内容 | Top-1 |
|---|---|
| 原预测 | 86.9%。`[verified: 最佳模型 attribution_accuracy.frozen_predictions]` |
| 通道 MSE | 93.3%。`[verified: 最佳模型 attribution_accuracy.true_channel_mse]` |
| 零通道掩码 | 87.0%。`[verified: 最佳模型 attribution_accuracy.true_zero_mask]` |
| 通道 MSE＋零通道 | 93.3%。`[verified: 最佳模型 attribution_accuracy.true_channel_mse_and_zero]` |
| MS-SSIM | 92.4%。`[verified: 最佳模型 attribution_accuracy.true_ms_ssim]` |
| 法线角度 | 87.9%。`[verified: 最佳模型 attribution_accuracy.true_angles]` |
| 全部质量 | 100.0%。`[verified: 最佳模型 attribution_accuracy.all_true_metrics]` |

在这些冻结预测上，通道 MSE 与 MS-SSIM 替换都带来明显的规则一致性改善。该结果给出条件替换效应，后续训练收益仍需实际训练结果确定。`[verified: 最佳模型 attribution_accuracy；opinion: 诊断解释]`

## 7. 真实向后续搜的结果

### 7.1 与固定基线、原规则及单次预测对照

| 方法 | 块大小 Top-1 | 完整匹配 | 严格质量 | 质量回退 | mip0 payload／字节 |
|---|---:|---:|---:|---:|---|
| 固定 8×8／medium | 14.3% | 5.8% | 81.1% | 139 张 | 59,761,616。`[verified: 系统实测 summary.fixed8.validation_metrics]` |
| 实测完整质量＋原规则 | 100.0% | 100.0% | 87.4% | 0 张 | 31,661,520。`[verified: 规则参照 validation_baselines.original_rule_measured；系统变体 models.imagenet-resnet34-head-sampled4.raw.original_search]` |
| 最佳模型单次预测 | 86.9% | 58.8% | 68.2% | 192 张 | 31,392,800。`[verified: 最佳模型 selected_checkpoint_metrics、quality_regression_images]` |
| 当前真实向后续搜 | 93.6% | 80.4% | 87.5% | 0 张 | 32,067,120。`[verified: 系统实测 summary.forward.validation_metrics]` |

真实续搜与原标签相比，64 张图选择更小块，选择更大块为 0 张。payload 增加 405,600 字节、约 1.28%；相对固定 8×8／medium 减少约 46.34%。`[verified: 系统实测 summary.forward.validation_metrics.larger_block_images、smaller_block_images、payload_ratio_to_original、payload_ratio_to_fixed8；opinion: 字节与比例计算]`

当前严格合格为 875 张。输出原因分布为 first_valid 643 张、size_first_strict 232 张、大图放宽 92 张、最高 PSNR 回退 33 张，后两类合计 125 张。`[verified: 续搜核验 selection_reason_distribution；系统实测 summary.forward.validation_metrics.actual_quality_pass_rate]`

### 7.2 逐类召回与分组

| 原标签块大小 | 支持张数 | 单次预测召回 | 真实续搜召回 |
|---|---:|---:|---|
| 6×6 | 120 | 78.33% | 100.00%。`[verified: 最佳模型 selected_checkpoint_metrics.per_class.6x6；系统实测 summary.forward.validation_metrics.per_class.6x6]` |
| 8×8 | 143 | 79.02% | 88.11%。`[verified: 最佳模型 selected_checkpoint_metrics.per_class.8x8；系统实测 summary.forward.validation_metrics.per_class.8x8]` |
| 10×10 | 138 | 62.32% | 84.06%。`[verified: 最佳模型 selected_checkpoint_metrics.per_class.10x10；系统实测 summary.forward.validation_metrics.per_class.10x10]` |
| 12×12 | 599 | 96.16% | 95.83%。`[verified: 最佳模型 selected_checkpoint_metrics.per_class.12x12；系统实测 summary.forward.validation_metrics.per_class.12x12]` |

| 分组 | 图数或组数 | 真实续搜 Top-1 |
|---|---:|---|
| sRGB 小图 | 612 张 | 91.34%。`[verified: 系统实测 summary.forward.validation_metrics.groups.srgb_small]` |
| sRGB 大图 | 326 张 | 98.47%。`[verified: 系统实测 summary.forward.validation_metrics.groups.srgb_large]` |
| 法线图 | 45 张 | 88.89%。`[verified: 系统实测 summary.forward.validation_metrics.groups.normal]` |
| Linear 颜色图 | 17 张 | 94.12%。`[verified: 系统实测 summary.forward.validation_metrics.groups.linear]` |
| 直接父目录宏平均 | 487 组 | 95.34%。`[verified: 系统实测 summary.forward.validation_metrics.groups.direct_parent_macro]` |
| 资产族宏平均 | 189 组 | 93.51%。`[verified: 系统实测 summary.forward.validation_metrics.groups.asset_family_macro]` |

### 7.3 实际编码次数

| 编码次数范围 | 张数或统计值 |
|---|---|
| 1 次 | 702 张，占 70.2%。`[verified: 续搜核验 encoding_count_distribution.1；opinion: 占比计算]` |
| ≤2 次 | 873 张，占 87.3%。`[verified: 续搜核验 encoding_count_distribution.1、.2；opinion: 累计计算]` |
| ≤3 次 | 926 张，占 92.6%。`[verified: 续搜核验 encoding_count_distribution.1、.2、.3；opinion: 累计计算]` |
| 全集 | 共 1627 次，平均 1.627、中位 1、P95 为 5、最大 16。`[verified: 系统实测 summary.forward.validation_metrics.candidates_measured]` |
| 原搜索标签记录 | 共 7061 次，平均 7.061、中位 5、P95 为 18。`[verified: 系统变体 models.imagenet-resnet34-head-sampled4.raw.original_search.candidates_measured]` |

平均候选编码次数相对原搜索记录减少约 76.96%。具体成本同时受 preset、图片尺寸及质量评价影响，耗时采用下一节的实际测量。`[verified: 系统实测 summary.forward.validation_metrics.candidates_measured；系统变体 models.imagenet-resnet34-head-sampled4.raw.original_search.candidates_measured；opinion: 比例计算及成本解释]`

## 8. 真实计时与离线系统变体

### 8.1 真实配对计时

真实运行采用一次预热和三次正式整集重复。每次续搜均执行完整 1000 图新推理，计时范围为参考 PNG 到内存 mip0 ASTC，包括实际候选编码、解码及原生质量门控。模型／DLL 加载、来源核验、产物写入、Unity 导入及完整 mip 链各有独立范围。`[verified: 系统执行 L35–39；系统实测 scope、summary]`

| 路径 | 三次整集耗时／秒 | 中位数摊销／图 |
|---|---|---|
| 预测起点向后续搜 | 195.795／194.446／197.245 | 195.80 ms。`[verified: 系统执行 L35；系统实测 summary.forward]` |
| 固定 8×8／medium | 21.306／21.341／21.335 | 21.34 ms。`[verified: 系统执行 L35；系统实测 summary.fixed8]` |

续搜耗时为同次 fixed8／medium 的 9.177 倍，其对应 payload 为 fixed8 的 53.66%，严格质量通过率为 87.5%／81.1%。上述每图毫秒数来自整集批量摊销。单张即时调用延迟待专门测量。`[verified: 续搜核验 forward_seconds_over_fixed8；系统实测 summary.forward、summary.fixed8；opinion: 延迟适用范围]`

历史原搜索记录在该验证集上的均值为 1068.42 ms／图，与本次续搜摊销中位数的数值比为 5.457。该比值涉及历史搜索记录及当前预热运行两种采集条件，生产端到端加速收益待同环境原搜索配对实验确认。`[verified: 系统变体 models.imagenet-resnet34-head-sampled4.raw.original_search.encoding_cost_estimate；续搜核验 historical_original_mean_over_measured_forward；opinion: 可比较范围]`

### 8.2 离线系统变体

已完成 3 个模型×原始／既有校准两种口径×39 个变体，共 234 组 validation1000 离线重放。该次变体评估读取归档候选质量及耗时，记录模型调用 0、训练更新 0、实际编码 0、确认集访问 0。以下统一为 ResNet-34 整图头模型的原始预测。`[verified: 系统执行 L11–15、L13；系统变体核验 runtime_guards；V2计划 L11]`

| 系统方式 | Top-1 | 平均编码次数 | 严格质量 | 质量回退 |
|---|---:|---:|---:|---|
| 单次预测 | 86.9% | 1.000 | 68.2% | 192 张。`[verified: 系统变体 models.imagenet-resnet34-head-sampled4.raw.0_pure_model]` |
| 预测候选起点向后续搜 | 93.6% | 1.627 | 87.5% | 0 张。`[verified: 系统变体 models.imagenet-resnet34-head-sampled4.raw.B1_candidate_idx]` |
| 预测 preset 双向探测，预算 2 次 | 94.0% | 1.547 | 77.3% | 101 张。`[verified: 系统变体 models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K2]` |
| 预测 preset 双向探测，预算 3 次 | 95.3% | 1.712 | 81.9% | 55 张。`[verified: 系统变体 models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K3]` |
| 预测 preset 双向探测，无固定预算 | 99.3% | 1.914 | 87.5% | 0 张。`[verified: 系统变体 models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_unlimited]` |

双向探测在起点实测严格合格时向更粗块尝试，优先测试模型为该块预测的 preset；起点失败时向后续搜。预算计入起点及后续唯一编码，最终输出复用已生成的候选。预算耗尽的分支按已测候选及锁块状态回退。`[verified: 系统策略 L134–177；系统执行 L488–490]`

2 次预算的开发 Top-1 为 94.0%，其 77.3% 严格通过率和 101 张质量回退同时列入结果。当前选定真实主线为向后续搜，已有完整 validation1000 实测及开发冻结；双向变体保留离线重放证据层级。`[verified: 系统变体 models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K2；开发冻结 identity.decision；系统实测 status]`

## 9. 当前能够得出的结论

1. **在当前 Unity validation1000 上，单次预测的最好原始 Top-1 为 86.9%。** ResNet-34 ImageNet 初始化加整图头再训练为已完成对照中的最高原始结果，同集余量拟合达到 87.1%。`[verified: 训练对照 results；最佳模型 selected_checkpoint_metrics、same_validation_fitted_top1]`
2. **当前系统组合在真实开发评估上达到 93.6%。** 实际编码质量门控后，严格质量从单次预测的 68.2% 升至 87.5%，相对原标签质量回退从 192 张降至 0 张，编码次数平均为 1.627。`[verified: 最佳模型 selected_checkpoint_metrics、quality_regression_images；系统实测 summary.forward.validation_metrics]`
3. **开发集的字节与耗时形成可量化权衡。** 续搜相对固定 8×8／medium 的 mip0 payload 减少约 46.34%，同次路径耗时为 9.177 倍。与原标签相比，payload 增加约 1.28%，块大小一致率为 93.6%。`[verified: 系统实测 summary.forward.validation_metrics；续搜核验 forward_seconds_over_fixed8；opinion: 体积比例解释]`
4. **模型容量、训练策略与选参指标需要联合观察。** 当前 ResNet-50、BN 重估、法线重复和资产族限额对照均有归档结果，最佳原始模型仍为 ResNet-34 头部再训练。后续方法取舍可依据完整 Top-1、质量、字节与计时证据。`[verified: 训练对照 results；系统执行 L227–233；opinion: 方法取舍]`
5. **独立确认结论仍待实验。** 当前已取得开发集证据、系统协议准备及 8 图原生闭环，确认集 10 张近重复候选的范围方案、补采／像素复审、完整 cohort 证据绑定与正式执行待完成。`[verified: 确认准备 status、formal_confirmation_ready、pending；范围提案“待批准的执行范围”；协议核验 real_validation_smoke]`

## 10. 确认协议与待完成事项

当前选定系统已以 validation 身份冻结模型、原始零余量、0.5 零通道门槛、逐图原规则、候选索引起点及无固定预算向后续搜。合同绑定 8238 份文件、1000 张有序验证输入及 7173 个 patch，封存指纹为 `218fe31a56c94b32f946121063cf8c82533074d4e53cf2eb25e5d8231e216d27`。`[verified: 开发冻结 bound_files、identity、seal_fingerprint；系统执行 L43]`

独立确认入口 `script/evaluate_unity_forward_confirmation.py` 已完成开发准备与 8 图／70 patch 原生闭环，一次预热加三次重复共执行 136 次编码、4 次新预测。既有核验记录为 CPU 1014 项通过、GPU 2 项独立串行通过。当前正式执行开关为 false，cohort 像素与采集证据待绑定。`[verified: 协议核验 cpu_checks、cuda_checks、real_validation_smoke；系统执行 L49–63]`

| 待完成内容 | 当前材料或依赖 |
|---|---|
| 确认集范围决定 | 已有 10 张逐位置修订提案，拟按冻结备用顺序补入。`[verified: 范围提案“逐位置替换方案”“待批准的执行范围”]` |
| 原生补采与像素复审 | 10 张补入图原生采集及完整 cohort 复审待执行，当前已知近重复问题保留追踪。`[verified: 范围提案“逐位置替换方案”；确认准备 pending]` |
| 正式 cohort 绑定与执行 | 准备完整采集／像素证据并固定模型及协议后执行，正式授权当前待决定。`[verified: 确认准备 formal_confirmation_ready、pending；系统执行 L57–63]` |
| 独立确认报告 | 目标为 2000 张块大小 Top-1≥90%，同时报告完整匹配、实际质量、回退、payload 与成本。`[verified: V2计划 L17–19]` |
| 生产集成与验收 | 完整 mip 链、Unity 导入全过程成本、单张即时延迟和人工视觉接受程度继续按各自实验范围验收。`[verified: V2计划 L33；系统实测 scope；opinion: 后续验收内容]` |

## 11. 数据比较、Quality 档位与接入接口说明

### 11.1 训练数据中重新压缩的含义

当前比较链路为“Unity 导入后的参考 RGBA → 指定 Blocksize／Quality 的 ASTC → 解码 RGBA”，误差计算使用链路两端的对应像素。JSON 保存同次原搜索标签、原生质量、输入身份及后续候选档案的关联信息。补测首先复核参考图身份，再核对原搜索已测候选的指标，原胜出候选还核对 ASTC payload 与解码像素。`[verified: 输入适配 L92–101；候选编码 L365–423]`

可以直接比较已经解码的 RGBA 数组，前提是参考输入、实际尺寸、行序、通道及编码选项对齐。当前 PNG 是参考 RGBA 的归档载体，推理读取为 RGBA8，回调像素核验会翻转上下行后重新计算 SHA-256。直接接收 rawdata 的接入层需要复现这一像素约定。`[verified: 输入适配 L95–101；推理输入 L78–82；opinion: rawdata 接入约定]`

数据准备阶段生成 20 候选质量监督，训练循环读取保存的 patch 误差和整图指标。单次预测部署路径在预测后编码一个候选，当前向后续搜系统在候选质量未满足停止条件时继续编码。三处的 ASTC 调用分别对应监督生成、最终输出和运行时质量门控。`[verified: 候选编码 L388–395；原生训练 L177–184、L343–344；系统策略 L92–118；系统实测 summary.forward.validation_metrics.candidates_measured]`

### 11.2 Blocksize 与 Quality，以及排除 exhaustive 的后续对照

当前输出是 Blocksize 与编码 Quality 两个参数。Quality 在本仓库字段名为 `preset`，对应 fastest=0、fast=10、medium=60、thorough=98、exhaustive=100。严格质量通过率另外由 PSNR、MS-SSIM 或法线角度计算。`[verified: 候选编码 L20–22、L80–95；原规则 L103–112]`

当前已完成结果使用 4 个块大小×5 个 Quality，共 20 候选。新版训练原标签使用 exhaustive 的为 1812／10000 张，验证原标签为 194／1000 张。真实续搜最终输出 exhaustive 为 218／1000 张，其中 93 张严格合格，125 张未严格合格，四轮运行的分布一致。`[verified: 新版分布 splits.train.selected_preset.exhaustive、splits.validation.selected_preset.exhaustive；系统实测 measurements[0..3].arms.forward.audit.rows 的 preset／strict_quality_met 聚合]`

后续可评估保留 fastest／fast／medium／thorough 的 16 候选方案。建议先复用既有 20 候选实测质量和模型预测，筛选这 16 个候选，重新运行选择规则，再比较块大小、完整配置、严格质量、回退、payload 与实际耗时。这一步可先验证候选筛选的收益，模型输出维度是否缩减及是否重训随后依据结果决定。`[opinion]`

16 候选规则需要形成相应的选择参照，同时保留与原 20 候选标签的块大小一致率。原验证标签有 19.4% 为 exhaustive，排除该档后对原标签的完整配置匹配率上限为 80.6%。当前 93.6% 系统结果属于包含 exhaustive 的协议，16 候选结果处于待测状态。`[verified: 新版分布 splits.validation.selected_preset.exhaustive；系统实测 summary.forward.validation_metrics.accuracy；opinion: 完整配置上限推导与新评价约定]`

真实运行报告的编码计时为所有候选调用合计，目前该报告缺少 exhaustive 独占编码耗时的汇总。减少这一档后的速度、质量及块大小变化，需要通过 16 候选重放和真实计时确定。`[verified: 系统实测 measurements[1..3].arms.forward.timings.native_encode_seconds；opinion: 后续测量要求]`

### 11.3 法线与材质 mask 的用途和评价

当前 `normal` 由 Unity 导入类型 `NormalMap` 显式提供。模型据此预测适用的质量指标，系统按相应分支选参。8 项属性中包含 normal，材质 mask 用途标志及通道语义目前尚未建模。网络输入中的有效像素 mask 标记 patch 的真实区域与补齐区域，其用途为特征聚合。`[verified: 输入适配 L57–90；原生Dataset L25–34、L179–195；原生模型 L107–114]`

| 输入用途 | 当前质量规则与覆盖 |
|---|---|
| sRGB 颜色图 | PSNR 达到按黑像素比例调整的 30／35／37 dB，严格质量还要求 MS-SSIM≥21 dB。`[verified: 原规则 L93–112；V2计划 L29]` |
| Linear 非法线图 | 当前进入 PSNR 分支，阈值同样来自绑定的原生规则。`[verified: 原规则 L93–112]` |
| 法线图 | 平均角度≤3.2° 且 p95≤9°，法线评价 mip 范围由实际尺寸和 importer 的 mipmaps 属性确定为 1 至 4 层。当前编码范围为 mip0。`[verified: 输入适配 L87–90；推理输入 L27–36；原规则 L103–109；开发冻结 identity.decision.encoding_scope]` |
| 材质 mask／MSAK | 当前依导入属性进入上述颜色或 Linear 分支，缺少独立 mask 类型、通道用途监督与分组验收。`[verified: 原生Dataset L25–34；原规则 L98–112；原生模型 L183–190]` |

验证集 45 张已知法线图，单次预测的块大小 Top-1 为 77.78%、严格质量通过率 68.89%；真实续搜为 88.89%、严格质量通过率 93.33%。这些指标衡量已提供法线标记后的选参结果。当前类型识别准确率及材质 mask 专项效果处于待建立评价的状态。`[verified: 最佳模型归因 variants.frozen_predictions.groups.normal；系统实测 summary.forward.validation_metrics.groups.normal；opinion: 类型识别与专项验收范围]`

后续接入建议由 importer、材质或资产配置提供 texture_usage 和各通道语义。材质 mask 可进一步声明通道用途、参与通道及阈值，例如遮罩边界偏差、各通道误差、材质渲染差异。新增标准需要与训练监督及原生评价实现一并确认，自动用途识别可另设分类任务评估。`[opinion]`

### 11.4 当前输入字段与 rawdata 接入

现有 Python 推理入口接收参考 PNG 路径以及 `srgb`、`normal`、`need_alpha`、`normal_metric_mips`。它从参考像素取得宽高、Alpha 是否恒定和纯黑像素比例，再构造 8 项网络属性及 RGBA＋有效像素 mask。实际回调准入要求 channel=4、Tex2D、LDR、normal_pack=false。`[verified: 推理输入 L19–36、L42–73；输入适配 L57–90]`

| 信息 | 当前来源与接入处理 |
|---|---|
| rawdata、width、height | 使用 Unity 导入后、进入 ASTC 前的 RGBA8 像素。接入 raw buffer 时显式约定行跨度和上下行方向，再转换到训练端显示方向。`[verified: 输入适配 L95–101；推理输入 L78–82；opinion: 内存接口约定]` |
| 通道数／像素格式 | 当前固定 4 通道 RGBA8。单通道、双通道或 RGB 输入须先按对应导入处理规则转换并核验。`[verified: 输入适配 L71–80；候选编码 L61–65；opinion: 新格式适配要求]` |
| sRGB／Linear | 从 importer 或实际 profile 提供，并核对一致性。`[verified: 输入适配 L64–80]` |
| 是否法线 | 从 `texture_type==NormalMap` 提供。`[verified: 输入适配 L87]` |
| 是否材质 mask、各通道含义 | 当前接口尚无对应字段，属于建议扩展的用途元数据。`[verified: 推理输入 L19–25；原生Dataset L25–34；opinion: 扩展建议]` |
| 是否需要 Alpha | 由实际编码选项 `need_alpha` 提供。`[verified: 输入适配 L66、L90]` |
| Alpha 恒定／纯黑比例 | 从输入像素计算。`[verified: 输入适配 L102–103]` |
| 法线评价 mip 数 | 由法线用途、尺寸与 mipmaps 设置计算，取 1 至 4。`[verified: 输入适配 L87–90；推理输入 L27–36]` |
| 规则与允许候选 | 当前绑定原生阈值及 20 候选顺序，后续 16 候选方案需明确允许的 Quality 集合。`[verified: 原规则 L30–55、L68–74；opinion: 后续接口约定]` |

现有实现可作为 rawdata 接入的预处理与推理参照，直接内存输入适配及引擎部署接口仍需实现和验证。最终给编码器的选择结果为 Blocksize 与 Quality/preset，实际编码同时使用 profile、need_alpha 等输入选项。`[verified: 推理输入 L19–25、L78–82；候选编码 L61–95；opinion: 接入实现范围]`

### 11.5 当前使用的 ASTC 二进制

V2 真实续搜实际绑定的压缩与解压库为 `F:/MLBB_Test/haijiangli1_HAMSTERMLBB/Assets/Editor/Astc/Plugins/astcenc-avx2-shared.dll`，当前文件 814592 字节，SHA-256 为 `e78f35b6fc12654118b97a3edf6e0785dbdf865131abdd730963f6d2e6d32d64`。本次重新计算哈希，与完整验证报告绑定值一致。Python 通过 ctypes 调用其中的 `armastc_encode` 和 `armastc_decompress_from_memory`。`[verified: 系统实测 inputs_sha256；本次二进制核验 binaries；候选编码 L24–59]`

原生质量计算使用 `E:/ASTC_Compression/experiment report/.local/unity-accuracy90-20261111/unity-quality-native-retry1/build/Release/unity_astc_quality.dll`，32256 字节，SHA-256 为 `445e037d1aa598527e38b0fa0ae3418a1926fe47339ddd2888a196960f6e41f3`，本次哈希核对同样通过。该库负责 PSNR、MS-SSIM 和法线角度等质量计算，来源构建步骤从引擎提取原生质量函数。`[verified: 系统实测 inputs_sha256；本次二进制核验 binaries；质量库构建 L21–54]`

## 证据与复查入口

下列名称用于行内引用。JSON 引用定位至所列键路径，源码与 Markdown 使用读取时的行号或章节标题。训练指标统一来自已选择检查点，续搜指标统一来自完整 validation1000 真实运行报告。`[verified: 最佳模型 selected_checkpoint_metrics；系统实测 summary]`

| 引用名称 | 实际文件 |
|---|---|
| 数据交接 | [unity-data-delivery-v3-verification.json](<../../experiment report/unity-accuracy90-20261111/unity-data-delivery-v3-verification.json>)。`[verified: 本次文件存在与SHA核验]` |
| V2计划 | [README.md](<../../experiment plan/V2/README.md>)。`[verified: 本次文件存在与SHA核验]` |
| V1示例 | [README.md](<../../experiment report/V1/README.md>)。`[verified: 本次文件存在与SHA核验]` |
| 训练对照 | [comparison.json](<../../experiment report/unity-v2-20261112/comparison.json>)。`[verified: 本次文件存在与SHA核验]` |
| 最佳模型 | [imagenet-resnet34-head-sampled4-result.json](<../../experiment report/unity-v2-20261112/imagenet-resnet34-head-sampled4-result.json>)。`[verified: 本次文件存在与SHA核验]` |
| 主模型配置 | [imagenet-resnet34-full30-config.json](<../../experiment report/unity-v2-20261112/imagenet-resnet34-full30-config.json>)。`[verified: 本次文件存在与SHA核验]` |
| 头部配置 | [imagenet-resnet34-head-sampled4-config.json](<../../experiment report/unity-v2-20261112/imagenet-resnet34-head-sampled4-config.json>)。`[verified: 本次文件存在与SHA核验]` |
| 系统实测 | [forward-search-full1000-v1.json](<../../experiment report/unity-v2-20261112/forward-search-full1000-v1.json>)。`[verified: 本次文件存在与SHA核验]` |
| 续搜核验 | [forward-search-verification.json](<../../experiment report/unity-v2-20261112/forward-search-verification.json>)。`[verified: 本次文件存在与SHA核验]` |
| 系统执行 | [README.md](<../../experiment report/unity-v2-20261112/README.md>)。`[verified: 本次文件存在与SHA核验]` |
| 规则参照 | [rules.json](<../../experiment report/unity-v2-20261112/rules.json>)。`[verified: 本次文件存在与SHA核验]` |
| 系统变体 | [system-variants-result.json](<../../experiment report/unity-v2-20261112/system-variants-result.json>)。`[verified: 本次文件存在与SHA核验]` |
| 系统变体核验 | [system-variants-verification.json](<../../experiment report/unity-v2-20261112/system-variants-verification.json>)。`[verified: 本次文件存在与SHA核验]` |
| 开发冻结 | [forward-search-validation-freeze.json](<../../experiment report/unity-v2-20261112/forward-search-validation-freeze.json>)。`[verified: 本次文件存在与SHA核验]` |
| 确认准备 | [forward-system-protocol-readiness-v1.json](<../../experiment report/unity-v2-20261112/forward-system-protocol-readiness-v1.json>)。`[verified: 本次文件存在与SHA核验]` |
| 协议核验 | [forward-system-protocol-verification.json](<../../experiment report/unity-v2-20261112/forward-system-protocol-verification.json>)。`[verified: 本次文件存在与SHA核验]` |
| 范围提案 | [confirmation-scope-proposal-v1.md](<../../experiment report/unity-v2-20261112/confirmation-scope-proposal-v1.md>)。`[verified: 本次文件存在与SHA核验]` |
| 原规则 | [policy.py](<../../reproductions/unity_search_baseline/policy.py>)。`[verified: 本次文件存在与SHA核验]` |
| 系统策略 | [system_variant_policy.py](<../../reproductions/unity_search_baseline/system_variant_policy.py>)。`[verified: 本次文件存在与SHA核验]` |
| 原生模型 | [unity_quality.py](<../../src/adaptive_astc/models/unity_quality.py>)。`[verified: 本次文件存在与SHA核验]` |
| 原生损失 | [unity_quality_loss.py](<../../src/adaptive_astc/training/unity_quality_loss.py>)。`[verified: 本次文件存在与SHA核验]` |
| 原生Dataset | [unity_patch_dataset.py](<../../src/adaptive_astc/data/unity_patch_dataset.py>)。`[verified: 本次文件存在与SHA核验]` |
| 质量转换 | [unity_quality.py](<../../src/adaptive_astc/evaluation/unity_quality.py>)。`[verified: 本次文件存在与SHA核验]` |
| 输入适配 | [unity_capture_input.py](<../../src/adaptive_astc/data/unity_capture_input.py>)。`[verified: 本次文件存在与SHA核验]` |
| 推理输入 | [unity_inference.py](<../../src/adaptive_astc/data/unity_inference.py>)。`[verified: 本次文件存在与SHA核验]` |
| 候选编码 | [supplement.py](<../../reproductions/unity_search_baseline/supplement.py>)。`[verified: 本次文件存在与SHA核验]` |
| 原生训练 | [unity_quality_trainer.py](<../../src/adaptive_astc/training/unity_quality_trainer.py>)。`[verified: 本次文件存在与SHA核验]` |
| 质量库构建 | [quality.py](<../../reproductions/unity_search_baseline/quality.py>)。`[verified: 本次文件存在与SHA核验]` |
| 新版分布 | [unity-development-v2-distribution.json](<../../experiment report/unity-accuracy90-20261111/unity-development-v2-distribution.json>)。`[verified: 本次文件存在与SHA核验]` |
| 最佳模型归因 | [imagenet-resnet34-head-sampled4-attribution.json](<../../experiment report/unity-v2-20261112/imagenet-resnet34-head-sampled4-attribution.json>)。`[verified: 本次文件存在与SHA核验]` |
| 本次二进制核验 | [input-contract-evidence.json](<../../experiment report/.local/V2-report-20261113/input-contract-evidence.json>)。`[verified: 本次文件存在与SHA核验]` |

### 关键结果文件身份

以下 SHA-256 在本次生成报告时重算，用于定位本文引用的实际结果版本。`[verified: 本次报告生成脚本 hashlib.sha256 输出及核验回执]`

- 数据交接 SHA-256 为 `7ef87508e87a1454046ca75b79696b2182f3feb7234ac9c5d520d1b1f37ba29d`。`[verified: 本次 SHA-256 重算回执 数据交接]`
- 训练对照 SHA-256 为 `8a6c73e08a30a413e49fbc097176d131cdd9afe09e05143c72cb51db5a54ae8d`。`[verified: 本次 SHA-256 重算回执 训练对照]`
- 最佳模型 SHA-256 为 `a25ea7f038b28efc803266a4624f7a44c46a8114da61fe34b14157794fddd114`。`[verified: 本次 SHA-256 重算回执 最佳模型]`
- 系统实测 SHA-256 为 `354fc89505d6392e61bf0cfc23ddd6c21ef5de5e7fc695b194fdc50acd0a447d`。`[verified: 本次 SHA-256 重算回执 系统实测]`
- 续搜核验 SHA-256 为 `2ddf15bb31aae12ce0ea4132084aa383d197a83e60973ccd38b88ced1be498d4`。`[verified: 本次 SHA-256 重算回执 续搜核验]`
- 开发冻结 SHA-256 为 `6fb3e5cda23ea5b510adf87e2adeaf4fc059fbf9e7553d156fe584ce2cd4d783`。`[verified: 本次 SHA-256 重算回执 开发冻结]`
- 确认准备 SHA-256 为 `8b1da37e38a3e97fb2397d7d48a905605b1254216d472288620a60bc5a48fe14`。`[verified: 本次 SHA-256 重算回执 确认准备]`
