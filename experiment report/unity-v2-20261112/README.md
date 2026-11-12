# Unity V2 原生实验执行

本轮执行 [V2 计划](<../../experiment plan/V2/README.md>)，使用已交付的新版 train10000／validation1000；独立确认集为2000张。主验收为确认集块大小 Top-1≥90%，质量、完整配置匹配、payload和各阶段耗时一并报告。`[verified: experiment plan/V2/README.md L11–13；launch-binding.json development、confirmation_identity_only]`

## 数据与执行身份

- 开发语料 SHA-256 为 `560094e9d87b220b037ed37574e5941f0eff0675ffb43f34737f904e1f895c57`，包含10000／1000张、67436／7173个patch及220000组候选。启动时已重算开发语料、确认清单及总交接报告哈希。`[verified: launch-binding.json development；本轮 development／confirmation／verification sha256_verified 输出]`
- 原数据交接保留的11对跨划分近重复问题继续列入评价边界，划分保持。`[verified: ../unity-accuracy90-20261111/unity-v2-data-inputs.json pixel_audit.cross_split_near_identity_pairs、scope]`
- 模型使用原生随机初始化配方，每批16图、每图4patch、workers2、lr0.0003、weight decay0.05，30轮上限，1轮warmup，patience5，seed20261112。`[verified: r0-config.json；launch-binding.json recipe]`
- 检查点及任务日志位于本机 `experiment report/.local/unity-v2-20261112/`，运行使用独立身份。公开配置、结果和来源哈希保存在本目录。`[verified: r0-config.json output、report；launch-binding.json]`

## 启动核验

按输入属性分层选取32张训练图、16张验证图，共230／128个patch，覆盖颜色、Alpha及法线分支。选择索引保存于启动绑定。两轮CUDA预检完成4次实际更新，AMP跳步0，最佳权重重载、保存预测及原规则决策复核通过，峰值分配显存1,219,232,256字节，训练器全程11.37秒。小样本结果用于执行核验。`[verified: launch-binding.json smoke_source_indices、smoke_counts、smoke_patch_counts；r0-smoke-retry.json history、peak_vram_bytes、wall_seconds、checkpoint_audit]`

首次预检因沙箱拒绝DataLoader子进程命名管道而结束，实际更新0；失败记录保留于`r0-smoke.json`。随后使用新身份和所需执行权限运行原workers2配方，通过预检。pytest同样在受限临时目录遇到权限错误，使用独立临时目录和所需执行权限后50项检查通过。`[verified: r0-smoke.json error、training_updates；r0-smoke-retry.json status；对应jobs/r0-smoke/stderr.log；pytest输出“50 passed in 3.68s”]`

## 验证集规则参照

下表基于全部1000张验证图的实测候选，质量通过率按所选候选的真实质量和原门槛计算。payload为mip0字节。`[verified: rules.json validation_baselines]`

| 选择方式 | 块大小Top-1 | 完整配置匹配 | 严格质量通过 | payload字节 |
|---|---|---|---|---|
| 固定6×6／medium | 12.0% | 1.8% | 95.9% | 107217056。`[verified: rules.json validation_baselines.fixed6_medium]` |
| 固定8×8／medium | 14.3% | 5.8% | 81.1% | 59761616。`[verified: rules.json validation_baselines.fixed8_medium]` |
| 固定10×10／medium | 13.8% | 3.8% | 55.9% | 38897824。`[verified: rules.json validation_baselines.fixed10_medium]` |
| 固定12×12／medium | 59.9% | 10.7% | 31.9% | 27027200。`[verified: rules.json validation_baselines.fixed12_medium]` |
| 始终12×12／fastest | 59.9% | 20.7% | 20.7% | 27027200。`[verified: rules.json validation_baselines.always12_fastest]` |
| 仅PSNR规则 | 81.2% | 42.4% | 39.4% | 29538592。`[verified: rules.json validation_baselines.psnr_only]` |
| 实测完整质量与原规则 | 100.0% | 100.0% | 87.4% | 31661520。`[verified: rules.json validation_baselines.original_rule_measured]` |

## 执行选择

- 计划中的“始终12×12”参照补充指定fastest preset，另保留固定12×12／medium参照。`[opinion]`
- 高斯误差仅施加于训练集实测质量，独立扰动各候选，三个种子，PSNR和MS-SSIM采用dB、角度采用度；联合扰动使用相同数值的标准差，保留负值与原始结果。误差曲线仅作为此噪声模型下的精度量级参照。`[verified: rules-config.json sigmas、seeds；script/diagnose_unity_rules.py UnityRuleDiagnostics.perturb、run noise_scope；opinion: 解释范围]`
- 诊断复用`UnitySearchPolicy`和`UnityQualityPrediction.strict_quality`，全部开发图重新核对块大小、preset、原因及测量次数。零扰动必须完全复现原选择。`[verified: script/diagnose_unity_rules.py UnityRuleDiagnostics.prepare、perturb]`

## 训练集质量误差参照

完整规则诊断耗时65.64秒，覆盖10000张训练图及1000张验证图，四字段重放差异0。以下数值为三个种子平均Top-1达到90%的最大已测标准差，下一列给出更高已测标准差的结果。完整曲线及适用分组保存在[精度参照](rule-precision-reference.json)。`[verified: rules.json status、counts、wall_seconds、exact_four_field_replay_mismatches；rule-precision-reference.json references]`

| 扰动 | 比较范围 | 最大已测通过点 | 下一个已测点 |
|---|---|---|---|
| PSNR | 全训练集10000图 | 1.6dB，92.07% | 3.2dB，86.85%。`[verified: rule-precision-reference.json references.psnr.all_images]` |
| MS-SSIM | 全训练集10000图 | 1.6dB，91.03% | 3.2dB，87.37%。`[verified: rule-precision-reference.json references.ms_ssim.all_images]` |
| 平均及p95角度 | 299张法线图 | 各0.4°，93.31% | 各0.8°，85.40%。`[verified: rule-precision-reference.json references.angles.applicable_images]` |
| 联合扰动 | 全训练集10000图 | 数值标准差0.8，90.72% | 数值标准差1.6，82.45%。`[verified: rule-precision-reference.json references.all.all_images]` |

角度误差单独增大至6.4°时，全训练集Top-1仍为98.21%，同期299张法线图为40.02%；报告保留分组准确率以反映适用范围。高斯试验的误差独立性、同分布及单位设定均为实验假设，训练模型按实际残差和验证结果评价。`[verified: rules.json curves.angles 最后一项trials；opinion: 解释范围]`

## 进度

规则诊断、完整原生基线、初始化与固定容量对照、冻结预测归因及同验证集余量拟合已完成。当前随机初始化参照Top-1为81.3%，最佳独立ImageNet对照为86.3%，PSNR两阶段为76.4%。后续状态与结果写入[本轮进度](progress.json)。`[verified: rules.json status；comparison.json；progress.json]`

全量训练的首轮启动快照为验证Top-1 63.0%、近阈值RMSE 3.4667dB，实际624次更新、1次AMP跳步；训练47.43秒、验证11.67秒，首次数据准备170.30秒。这是训练过程记录，后续最佳权重仍按完整验证和重载审计确定。`[verified: r0.json history中epoch1、preparation_seconds；opinion: 过程与最终选模范围]`

## 完整基线数值重放修复

首次R0完成10轮、6247次实际更新，最佳验证Top-1为74.9%、同权重近阈值RMSE为2.5773dB。训练器全程720.81秒，停止原因是近阈值RMSE patience；随后保存预测的严格重放审计失败。原报告、检查点、历史和11份执行源码均保留。`[verified: r0.json history、training_updates、best_validation_accuracy、stop_reason、wall_seconds、error；.local/unity-v2-20261112/r0-source-archive/manifest.json]`

原始实现的四次完整验证对照均复现1000张保存决策，适用的质量数值逐位相同；其余整图头数值及少量零通道概率存在重复漂移。开启确定性算法的两次重复中，全部预测数组逐位一致。PyTorch 2.8 文档将CUDA `index_add`列入确定性选项覆盖的算子。`[verified: r0-replay-diagnosis.json observations；PyTorch2.8 torch.use_deterministic_algorithms 文档 L78–111]` [PyTorch 2.8文档](https://docs.pytorch.org/docs/2.8/generated/torch.use_deterministic_algorithms.html)

最终修订将权重总数和加权特征和改为稳定排序后的分段求和，保留原`scatter_reduce_(amax)`、输出形状与11,377,660参数。修订后的两次完整验证重复中，所有预测数组逐位一致；1000张最终决策仍与原保存结果一致。`[verified: src/adaptive_astc/models/unity_quality.py pool_features；r0-stable-sum-replay.json observations；tests/test_unity_quality.py 参数检查]`

中间修订曾使用分段max，复核发现其在本机PyTorch中的负向并列最大值梯度为每份−1，旧实现为每份−1／3。已恢复原max路径并新增该反例回归；中间小样本及源码单独归档，完整训练采用修订后的实现。55项接口／梯度／CUDA重复检查通过，修订后32／16图CUDA闭环完成4次更新及最佳权重重载，训练器10.82秒。`[verified: pool-repair-review.json finding、fix；r0-stable-sum-smoke.json status、training_updates、checkpoint_audit、wall_seconds；pytest输出“55 passed in 3.98s”]`

## 冻结预测归因入口

`script/attribute_unity_errors.py`仅接收成功终态训练及通过的最佳权重重载审计，绑定训练报告、原语料、源码及三份最佳产物SHA。分别替换通道MSE、零通道、二者联合、MS-SSIM、法线角度及全部实测指标，报告修复／破坏图数、类型／尺寸／原分支分组、资产组宏平均、逐类precision／recall和残差。`[verified: script/attribute_unity_errors.py run、grouped_metrics、residual_metrics]`

修订后小样本的保存预测完全重放，全部实测指标替换恢复100%块大小及完整配置匹配，模型forward次数为0；完整1000图归因也已完成。`[verified: attribution-stable-smoke.json variants、model_forward_calls；r0-attribution.json status、validation_images]`

## 成功结束的完整原生基线

修订后基线训练8轮、4996次实际更新、4次AMP跳步，选中epoch5，最佳权重重载和保存预测一致性审计通过。同一选中权重的验证Top-1为73.9%、balanced accuracy为58.48%、近阈值RMSE为2.9747dB，完整配置匹配率38.1%。训练过程的最低近阈值RMSE来自其他轮，汇总采用选中权重的结果。`[verified: baseline-result.json epochs、optimizer_updates、amp_skipped_steps、selected_checkpoint_epoch、selected_checkpoint_metrics；r0-stable-sum.json history]`

所选候选的归档严格质量通过率为61.7%，原标签严格合格而模型选择不合格的图有257张；块大小选大153张、选小108张。mip0 payload为31,661,760字节，相对fixed8／medium为52.9801%、相对原标签为100.0008%。训练器全程529.26秒，其中首次准备80.51秒、训练321.22秒、逐轮验证97.32秒；部署计时单列。`[verified: baseline-result.json selected_checkpoint_metrics、quality_regression_images、larger_block_errors、smaller_block_errors、payload_ratio_to_fixed8、payload_ratio_to_original、trainer_wall_seconds、preparation_seconds、training_seconds、validation_seconds、deployment_timings]`

## 完整验证集的实测量替换归因

以下对照固定同一权重保存的1000张验证预测，逐项替换为实测质量；修复／破坏图数均相对冻结预测，全部实测量替换恢复100%块大小及完整配置匹配。`[verified: r0-attribution.json variants、model_forward_calls]`

| 替换分量 | 块大小Top-1 | 修复图数 | 破坏图数 |
|---|---|---|---|
| 冻结预测 | 73.9% | 0 | 0。`[verified: r0-attribution.json variants.frozen_predictions]` |
| 通道MSE | 84.3% | 104 | 0。`[verified: r0-attribution.json variants.true_channel_mse]` |
| 零通道掩码 | 73.9% | 0 | 0。`[verified: r0-attribution.json variants.true_zero_mask]` |
| 通道MSE及零通道 | 84.3% | 104 | 0。`[verified: r0-attribution.json variants.true_channel_mse_and_zero]` |
| MS-SSIM | 86.4% | 127 | 2。`[verified: r0-attribution.json variants.true_ms_ssim]` |
| 法线角度 | 76.6% | 27 | 0。`[verified: r0-attribution.json variants.true_angles]` |
| 全部实测质量 | 100.0% | 261 | 0。`[verified: r0-attribution.json variants.all_true_metrics]` |

冻结预测的sRGB小图为612张／66.50%正确，sRGB大图326张／91.72%，法线45张／40.00%，Linear17张／88.24%；487个资产组的宏平均为80.01%。MS-SSIM实测替换的条件性增量最大，通道误差也影响最终选择。`[verified: r0-attribution.json variants.frozen_predictions.groups、variants.true_ms_ssim、variants.true_channel_mse；opinion: 后续排序]`

## MS-SSIM loss权重单项对照

该项将`ssim_weight`从0.1改为0.03，其他训练配方字段逐项比较一致，采用独立实验身份。32／16图CUDA预检完成4次更新及最佳权重重载，正式10000／1000训练完成6轮、3749次更新，最佳权重重载通过。`[verified: ssim-weight003-smoke.json status、training_updates、checkpoint_audit；ssim-weight003.json status、history、training_updates、checkpoint_audit；对应job launch-preflight.json changed_training_fields]`

选择0.03的依据是选中基线轮的patch loss为0.06739、未加权MS-SSIM loss为2.35299；权重0.1时后者贡献约0.2353，权重0.03对应参考量级约0.0706。该系数作为观察任务权衡的单项对照，结果按实际验证评价。`[verified: ssim-weight003-design.json basis；opinion: 系数选择及实验目的]`

## 验证结果与决策余量

| 运行 | 选中权重验证Top-1 | 同权重近阈值RMSE | 同验证集余量拟合Top-1 |
|---|---|---|---|
| 原生基线 | 73.9% | 2.9747dB | 76.0%。`[verified: comparison.json results.baseline]` |
| MS-SSIM loss权重0.03 | 72.7% | 3.6068dB | 74.3%。`[verified: comparison.json results.ssim_weight003]` |
| 仅均值池化 | 75.0% | 3.3833dB | 77.4%。`[verified: comparison.json results.mean_pooling]` |
| ImageNet初始化 | 81.3% | 3.4176dB | 82.5%。`[verified: comparison.json results.imagenet_mean]` |
| 随机初始化完整30轮 | 81.3% | 2.1585dB | 81.5%。`[verified: comparison.json results.mean_full30]` |
| ImageNet完整30轮 | 85.7% | 1.9217dB | 86.4%。`[verified: comparison.json results.imagenet_full30]` |
| EMA启用后的raw／EMA选模 | 81.3% | 2.1585dB | 81.5%。`[verified: comparison.json results.mean_ema099]` |
| 冻结编码器，整图头sampled4再训练 | 81.2% | 2.1532dB | 81.3%。`[verified: comparison.json results.mean_head_sampled4]` |
| 冻结编码器，整图头全部patch再训练 | 81.1% | 2.1432dB | 81.4%。`[verified: comparison.json results.mean_head_all]` |
| ImageNet初始化，整图头sampled4再训练 | 86.3% | 1.9180dB | 86.7%。`[verified: comparison.json results.imagenet_head_sampled4]` |
| PSNR组件准备，再训整图头sampled4 | 76.4% | 2.0084dB | 77.1%。`[verified: comparison.json results.psnr_head_sampled4]` |
| 每资产族每轮上限64张 | 78.0% | 2.8970dB | 79.0%。`[verified: comparison.json results.mean_familycap64]` |
| 法线每图每轮重复2次 | 79.2% | 2.2757dB | 79.8%。`[verified: comparison.json results.mean_normalrepeat2]` |
| ResNet-34随机初始化 | 79.2% | 2.7386dB | 79.4%。`[verified: comparison.json results.mean_resnet34_full30]` |
| ResNet-34 ImageNet初始化 | 86.2% | 1.6128dB | 86.8%。`[verified: comparison.json results.imagenet_resnet34_full30]` |

前三组完成时，仅均值池化作为初始化对照的参照。三组训练器时长分别529.26／421.97／630.16秒，各自按8／6／10轮早停记录，部署成本另测。`[verified: comparison.json reference_model、results；opinion: 参照选择]`

余量拟合使用`script/calibrate_unity_decisions.py`，绑定已完成归因、原检查点产物和完整1000张validation预测。五个全局参数分别为零通道概率门槛、PSNR／MS-SSIM dB余量、平均／p95角度余量，执行两轮显式网格坐标搜索，仅在Top-1严格提高时更新。正PSNR／MS-SSIM余量从预测dB中扣除，正角度余量加到预测度数，再交原规则选参。结果属于同验证集拟合。`[verified: script/calibrate_unity_decisions.py；r0-calibration-config.json；r0-calibration.json scope、margin_convention]`

基线拟合选择的门槛为0.5，PSNR余量−1dB、MS-SSIM余量0.25dB、平均角度余量0°、p95余量−1.5°；权重0.03组为0.5、0.5dB、0dB、0°、−1°。这些参数保存在诊断报告中，生产决策接入及确认评价按后续选模和封存结果执行。`[verified: r0-calibration.json best_parameters；ssim-weight003-calibration.json best_parameters；opinion: 后续接入顺序]`

## 仅均值池化对照

整图头采用按有效像素数加权的均值，输入维度从1032变为520，模型参数从11,377,660降至11,305,980。初始化先构造配对整图头，再取前512列均值特征和末8列元数据；seed20261112下的共享初始权重、保留列及后续RNG抽样均逐位相同。`[verified: mean-pooling-design.json pooling、parameters、baseline_parameters、paired_initialization_seed、shared_initial_weights_equal、retained_image_head_columns_equal、next_rng_draw_equal]`

训练、重载及五个原生推理／确认消费者统一从检查点配置恢复池化方式；历史配置缺少该字段时使用mean_max。61项组件及71项调用方检查通过，32／16图CUDA预检完成4次更新及重载，训练器10.78秒、峰值分配显存1,218,372,096字节。正式10000／1000训练完成10轮、6246次更新，选中epoch9，最佳权重重载通过。`[verified: UnityQualityRegressor.from_checkpoint；mean-pooling-design.json component_tests、consumer_tests；mean-pooling-smoke.json status、training_updates、wall_seconds、peak_vram_bytes、checkpoint_audit；mean-pooling.json status、history、training_updates、checkpoint_audit]`

仅均值池化的原始／拟合Top-1为75.0%／77.4%，原始／拟合严格质量通过率为52.0%／61.2%。原始选择的质量回退354张，拟合选择262张；报告同时保留balanced accuracy、逐类结果及payload。实测通道MSE替换为87.7%、MS-SSIM替换为87.1%，全部实测质量替换为100%。`[verified: comparison.json results.mean_pooling；mean-pooling-attribution.json variants]`

扩展前17份相关源码已按SHA归档。冻结归因复用既有`PatchNormalizationAudit.bind_training_sources`，通过显式配置验证历史源码，同时记录当前执行源码；完整基线的全部归因指标与归档前逐项相同。`[verified: .local/unity-v2-20261112/source-archive-before-mean/manifest.json；r0-attribution-archive.json training_source_binding；mean-pooling-design.json attribution_archive_replay_exact]`

## ImageNet初始化独立对照

本轮使用Torchvision的`ResNet18_Weights.IMAGENET1K_V1`，本机缓存文件为`resnet18-f37072fd.pth`，46,830,571字节，实测SHA-256为`f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec`。官方权重来源及文件身份记录于[初始化设计](imagenet-mean-design.json)。`[verified: imagenet-mean-design.json weights_name、official_url、cached_file_bytes、cached_file_sha256；Torchvision0.23 resnet18文档 L43–47]` [Torchvision权重说明](https://docs.pytorch.org/vision/0.23/models/generated/torchvision.models.resnet18.html)

初始化先载入RGB骨干，再把首层RGB卷积核复制到五通道卷积的前3通道，新增Alpha与mask通道初始为0。100个骨干张量逐项验证通过，原生质量头及后续RNG抽样与seed20261112的配对scratch模型逐位一致。模型输入为Unity原生RGBA变换、有效像素mask和8项导入属性，模型参数11,305,980。`[verified: imagenet-mean-design.json transferred_backbone_tensors_verified、rgb_kernel_exact、alpha_mask_initial_weights_zero、shared_head_initial_weights_equal、next_rng_draw_equal、input_preprocessing、parameters]`

训练配置显式绑定初始化文件与SHA，读取前、读取后及最终审计后复核。检查点恢复直接加载已保存的完整模型状态，相关离线恢复与历史默认配置检查通过。64项组件和71项调用方检查通过，CUDA32／16图预检完成4次更新、最佳权重重载通过，训练器11.19秒。正式10000／1000图训练完成8轮、4998次更新、2次AMP跳步，选中epoch8，完整重载审计通过。`[verified: UnityQualityTrainer.verify_pretrained_weights、fit；UnityQualityRegressor.from_checkpoint；imagenet-mean-verification.json；imagenet-mean-result.json epochs、updates、amp_skips、selected_checkpoint_epoch、checkpoint_audit]`

本轮为计划内初始化对照，主线晋级按V2待决定事项在验证证据完成后处理。`[verified: experiment plan/V2/README.md 待决定事项“初始化”；imagenet-mean-design.json mainline_promotion]`

选中权重Top-1为81.3%，balanced accuracy为69.70%，完整配置匹配53.1%，同权重近阈值RMSE为3.4176dB，严格质量通过率67.1%，质量回退203张。payload为31,366,736字节，训练器669.33秒。最低近阈值RMSE为3.1267dB，发生于另一轮次。`[verified: imagenet-mean-result.json selected_checkpoint_metrics、quality_regression_images、trainer_wall_seconds；imagenet-mean.json best_color_near_threshold_rmse_db、history]`

冻结预测分别用实测通道MSE、MS-SSIM和角度替换后，Top-1为90.3%、89.1%和83.1%，全部实测指标为100%。同验证集余量拟合为82.5%，严格质量70.3%，回退171张；这些结果记录条件替换和验证拟合的表现。`[verified: imagenet-mean-attribution.json variants；imagenet-mean-calibration.json best_accuracy、selected_metrics、scope]`

## 完整30轮训练对照

ImageNet对照在第8轮达到本组最高Top-1时，触发颜色近阈值RMSE连续5轮未改善的早停。增加随机初始化均值池化的完整30轮对照，仅将patience5改为0，保留30轮上限、学习率日程和选模规则。此项用于检查提前停止的影响。`[verified: imagenet-mean.json history、stop_reason；mean-full30-config.json；.local/unity-v2-20261112/jobs/mean-full30/launch-preflight.json changed_training_fields；opinion: 实验顺序]`

32／16图CUDA预检完成4次更新及重载，训练器10.83秒，峰值分配显存1,218,372,096字节；完整任务随后串行启动。预训练主线晋级已按计划的待决定事项向用户提出，后续依赖该决定的实验按回复执行。`[verified: mean-full30-smoke.json status、training_updates、wall_seconds、peak_vram_bytes、checkpoint_audit；progress.json status、pretrained_mainline_promotion]`

完整30轮对照已完成18,741次更新，AMP跳步9次，选中epoch29，Top-1为81.3%、balanced accuracy为70.86%、完整配置匹配48.8%，同权重近阈值RMSE为2.1585dB，最佳权重重载通过。原始严格质量64.4%，质量回退231张，payload31,177,648字节；训练器1651.94秒。原早停均值池化对照Top-1为75.0%，原始选模规则相同。`[verified: mean-full30-result.json；comparison.json results.mean_pooling]`

同验证集余量拟合Top-1为81.5%，严格质量63.9%，回退236张。实测MSE、MS-SSIM和角度单项替换分别为90.0%、89.2%和82.9%。当前随机初始化完整30轮与ImageNet早停对照的Top-1均为81.3%，后续增加ImageNet完整30轮独立对照，仅关闭其patience5早停，补齐配对训练预算。`[verified: mean-full30-calibration.json；mean-full30-attribution.json variants；comparison.json；imagenet-full30-config.json；opinion: 后续实验顺序]`

## 原生BN重估诊断

入口为`script/audit_unity_normalization.py`，复用`PatchNormalizationAudit.recalibrate`。以已完成训练的选中权重为起点，先重放完整1000图原预测与决策，用训练图按原4patch抽样重估BN统计量，逐项核对学习参数保持，再保存新权重并重载1000图预测。抽样patch索引、输入／配置／源码／原产物哈希全部保存，确认集接入按后续选模处理。`[verified: script/audit_unity_normalization.py UnityNormalizationAudit.run、calibration_inputs、verify_sources；native-bn-design.json]`

审阅发现语料清单的运行结束身份核验缺口后，已将corpus.json及预期SHA加入准备与结束复核，并增加漂移拒绝回归。真实检查点的配置包含tuple，JSON报告对应list，配置比较复用训练器的规范指纹。9项CPU检查和静态检查通过，原生CUDA预检按单GPU串行执行。`[verified: native-bn-design.json cpu_tests、config_serialization_probe、review；tests/test_unity_normalization.py test_native_normalization_rejects_manifest_drift；script/audit_unity_normalization.py checkpoint配置比较；opinion: 执行顺序]`

原生CUDA预检用32张训练图／128patch重估，原始和重估后的1000图数值／完整决策均重载通过，学习参数逐项保持，完整进程120.49秒。随后完整10000图／40000patch重估通过，统计重估88.68秒，完整进程208.80秒。Top-1从81.3%降至80.1%，近阈值RMSE为2.3486dB，严格质量58.9%、回退285张、完整匹配48.0%，因此保留原权重。`[verified: mean-full30-bn-smoke.json；mean-full30-bn.json；native-bn-verification.json full_result；opinion: 保留权重决定]`

## ImageNet完整30轮独立对照

此项从ImageNet早停配置仅改patience5为0，学习率日程仍为30轮。32／16图CUDA预检完成4更新及完整重载，训练器10.69秒；正式任务随后单GPU启动。实验保留初始化对照身份，主线晋级等待计划中的用户决定。`[verified: imagenet-full30-config.json；imagenet-full30-smoke.json status、training_updates、checkpoint_audit、wall_seconds；progress.json status、pretrained_mainline_promotion]`

正式30轮已完成18,743次更新、7次AMP跳步，选中epoch22，最佳权重重载通过。Top-1为85.7%，balanced accuracy76.31%，完整匹配58.4%，同权重近阈值RMSE1.9217dB，严格质量64.5%，质量回退230张，payload31,150,304字节。训练器1647.19秒；末轮近阈值RMSE1.8697dB单独记录。`[verified: imagenet-full30-result.json；imagenet-full30.json history、checkpoint_audit]`

同验证集余量拟合为86.4%，严格质量61.6%，回退258张。实测通道MSE、MS-SSIM和角度单项替换分别为93.0%、91.1%和87.1%，全部实测指标为100%。前8轮loss、更新数、Top-1、完整匹配及近阈值RMSE与原ImageNet早停对照逐项一致。`[verified: imagenet-full30-calibration.json；imagenet-full30-attribution.json variants；progress.json paired_prefix_check]`

## 随机初始化EMA对照

在完整30轮随机初始化参照上增加EMA，decay选0.99作为单项启发式设置。复用已有`PatchTrainer`的`AveragedModel`与optimizer后置hook，用实际完成的更新平均参数及buffer；AMP跳步保持EMA计数。每轮分别评价raw／EMA，同Top-1下看同一颜色近阈值RMSE，完全相同时保留raw。best.pt保存所选模型，last.pt保存训练模型及EMA状态。`[verified: src/adaptive_astc/training/patch_trainer.py L189–198、L284–290、L380–415；src/adaptive_astc/training/unity_quality_trainer.py；mean-ema099-design.json；opinion: decay选择]`

EMA默认关闭，历史配置继续恢复其完整保存权重。73项组件和71项调用方CPU检查及静态检查通过，旧完成实验19份相关源码已冻结；CUDA预检随后按单GPU串行执行。预训练主线晋级等待用户决定，当前EMA基于随机初始化参照。`[verified: mean-ema099-design.json component_tests、source_archive、mainline_initialization；本轮pytest“71 passed in 5.11s”；UnityTrainConfig.ema_decay、UnityQualityRegressor.from_checkpoint；opinion: 预检顺序]`

关闭／开启EMA的两组CUDA预检均完成4次优化器更新，开启组EMA更新同为4次。关闭组两轮loss及选模指标与扩展前预检逐项一致；开启组的raw训练路径也与关闭组逐项一致。CUDA预检选中raw并通过重载，实际EMA状态另在CPU完成126个张量的保存／恢复核对，且与raw权重存在差异。完整30轮EMA任务随后串行启动。`[verified: mean-ema099-design.json raw_legacy_smoke_exact、ema_smoke_raw_training_exact、cuda_smoke_selected_variant、cpu_actual_ema_checkpoint_round_trip；mean-ema099-smoke.json training_updates、ema_updates、checkpoint_audit；progress.json status]`

正式EMA对照完成30轮、18,741次优化器及EMA更新，最终选中epoch29的raw，验证81.3%／2.1585dB，重载通过。所选模型全部参数／buffer及保存预测与原完整30轮参照逐项一致。EMA分支自身最高80.7%，发生于epoch30，近阈值RMSE2.2188dB；后续使用原参照。训练器2107.69秒，训练累计1244.16秒，raw／EMA验证分别354.48／390.92秒。`[verified: mean-ema099-result.json；mean-ema099-verification.json；opinion: 参照选择]`

## 冻结编码器后的整图头输入对照

入口为`script/refit_unity_image_head.py`，当前已完成150项CPU检查、静态检查和只读审阅，CUDA预检等待EMA任务结束。初始模型按已完成随机初始化对照的审计Top-1及同权重近阈值RMSE选择，两个分支从同一完整检查点开始。方案见[对照配置](image-head-refit-design.json)，执行核验见[检查记录](image-head-refit-verification.json)。`[verified: image-head-refit-design.json source_model_selection、paired_initial_weights；image-head-refit-verification.json status、cpu_checks、review、cuda_smoke_status；opinion: 后续顺序]`

编码器、FiLM、逐通道误差头和BN统计量冻结，训练／验证特征取实际RGBA、mask与导入属性的原生编码。图像头分别使用每图有放回抽4patch、每图全部patch，依原有效像素数聚合；图像访问顺序与patch抽样使用独立generator。零通道、MS-SSIM与角度监督复用原生损失定义。两组均计划30轮、batch16、AdamW lr0.0003及weight decay0.05，图像头阶段使用恒定学习率。`[verified: script/refit_unity_image_head.py NativeFeatureCache.prepare、predict、UnityImageHeadRefit.image_losses、run；image-head-refit-design.json；opinion: 训练配方选择]`

训练前要求缓存完整重放原1000图预测与决策；选模后使用既有`UnityQualityTrainer.audit_best`重新读取原生验证输入，核对保存预测、决策与权重，逐项检查全部非图像头状态。阶段报告绑定初始训练、代码、语料和特征缓存。BN入口支持显式`training_config_path`及历史单配置来源，并从原编码器训练配置确定重估patch数。`[verified: script/refit_unity_image_head.py UnityImageHeadRefit.run；script/audit_unity_normalization.py training_config_path、run]`

两个分支的32图预检均完成4次更新及完整1000图重载，覆盖180个训练patch、30张多patch图，最大每图6patch。正式两组各完成30轮／18,746次更新，全部冻结状态和最佳权重原生重载通过，两个分支的完整训练／验证特征文件逐字节一致。各阶段仅训练72,940个图像头参数，阶段时长353.17／353.99秒，初始完整模型训练1651.94秒另计。`[verified: image-head-refit-verification.json；mean-head-sampled4-result.json；mean-head-all-result.json]`

sampled4原始／拟合Top-1为81.2%／81.3%，全部patch为81.1%／81.4%，原参照为81.3%／81.5%。ImageNet初始化独立对照使用同一sampled4再训练配方，32图预检完成4更新及完整重载，正式阶段随后启动。该模式按两项随机初始化头部对照的原始Top-1选择，预训练主线晋级仍待用户决定。`[verified: comparison.json；imagenet-head-sampled4-smoke.json；imagenet-head-sampled4-config.json；对应launch-preflight.json head_mode_selection；progress.json pretrained_mainline_promotion]`

ImageNet头部阶段完成30轮／18,746次更新，选中epoch25，原始／同集拟合Top-1为86.3%／86.7%，原生重载通过。原始严格质量68.2%、回退193张，拟合严格质量64.9%、回退225张，完整配置匹配57.9%，原始payload31,528,624字节；阶段时长356.51秒，初始模型1647.19秒另计。`[verified: imagenet-head-sampled4-result.json]`

## PSNR组件准备与整图头训练

下一项按两阶段方式执行，准备阶段保留通道log-MSE与零通道监督，zero权重0.1，MS-SSIM／角度权重0。准备权重按颜色近阈值RMSE、再按块大小Top-1选择；图像头阶段显式恢复三项附加权重为0.1，按块大小Top-1、再按近阈值RMSE选模。当前准备阶段采用随机初始化、均值池化、30轮及原学习率日程。`[verified: psnr-preparation-config.json；psnr-preparation-design.json；UnityTrainConfig.selection_metric、UnityImageHeadRefit.loss_config；opinion: 两阶段选模与训练顺序]`

默认accuracy选模保持旧配置行为，CUDA两轮的loss与选模指标逐项复现。PSNR准备分支预检完成4更新、所选权重重载通过，报告中的准确率与同一权重审计值一致。154项CPU检查、静态检查及只读审阅通过，完整准备训练已启动。前一版实现及输入共39份、623,924,481字节已按SHA归档。`[verified: psnr-preparation-verification.json；source-archive-before-psnr-warmup/manifest.json；psnr-preparation-smoke.json；对应launch-preflight.json]`

## 确认集准入与新版证据适配

完整近重复审计的11对跨划分候选均位于训练与确认之间，涉及10张确认图和11张训练图。精确RGBA跨确认／开发重复为0。已核对前10张冻结备用图的源文件、字节数及meta SHA，形成按原位置与备用顺序替换的[提案](<../.local/unity-v2-20261112/confirmation-near-replacement-proposal.json>)，当前名单修订待用户决定。提案只读取输入身份和像素审计，model forward为0。`[verified: confirmation-overlap-readiness.json overlap、unique_confirmation_images、unique_training_images、replacement_source_checks_all_passed、proposal、model_forward_calls]`

现有确认入口会拒绝跨确认／开发的精确或检测近重复，V2交接记录当前冻结名单的独立隔离尚未证明。新版修订像素证据与11000开发图全部匹配，旧管线的像素证据缺少18个新版资产身份。正式入口已支持批准的开发图替换和阶段训练证据，确认名单的近重复处理仍待用户决定。`[verified: confirmation_evidence.py pixel_audit、model；confirmation-v2-pixel-interface-verification.json；confirmation-stage-interface-verification.json；confirmation-overlap-readiness.json]`

已修复上游任务识别对UTF-8参数与绝对脚本路径的兼容。原有相对路径及`-u`命令可用，额外执行参数会被拒绝；三份实际已完成任务的命令／receipt身份核验通过，此项核验的forward为0。相关34项CPU检查和只读审阅通过，完整相关检查为152项。`[verified: confirmation-job-interface-verification.json completed_jobs、cpu_tests、model_forward_calls；tests/test_unity_confirmation_evaluation.py test_completed_job_binding；本轮pytest“152 passed in 6.96s”]`

阶段模型准入绑定整图头任务、完整初始训练、双方选中产物与源码归档，并核对语料身份、初始更新数和冻结状态。初始准备阶段允许低于90%，最终模型继续要求同一权重的1000图重载Top-1≥90%。历史配置缺少池化字段时按mean_max恢复，循环来源、归档差异及未完成初始训练均拒绝。实际86.3%模型的52份结构来源核验通过，最终准入因低于90%被拒绝，forward为0。`[verified: confirmation_evidence.py validate_training、_model；confirmation-stage-interface-verification.json]`

新版像素入口复用原审批、原始／补采像素及修订语料，重建13张训练图和5张验证图的批准替换，要求确认图身份及顺序一致。完整13000行核验通过，近重复阈值固定为RGBA8 RMSE 2.0；正式外层检查继续因11对训练—确认近重复拒绝。206项混合检查（205项CPU、1项CUDA）、ruff、basedpyright及只读审阅通过。`[verified: confirmation-v2-pixel-interface-verification.json；confirmation-stage-interface-verification.json cpu_tests、static_checks；confirmation_evidence.py revised_pixels、pixel_audit]`

## PSNR准备与整图头衔接

准备阶段完成30轮、18,742次更新及8次AMP跳步，选中epoch25，颜色近阈值RMSE为2.0060dB，所选权重重载通过，训练器1636.34秒。该准备权重按完整规则的Top-1为43.2%。整图头显式恢复zero／SSIM／angle权重均为0.1，使用sampled4、恒定lr0.0003及Top-1选模，32图CUDA预检完成4次更新、冻结状态和1000图原生重载通过，训练器117.64秒。`[verified: psnr-preparation-result.json；psnr-head-sampled4-smoke.json；psnr-head-sampled4-config.json]`

正式整图头完成30轮、18,747次更新及3次AMP跳步，选中epoch27。最终原始／同集拟合Top-1为76.4%／77.1%，同一权重近阈值RMSE为2.0084dB，完整配置匹配44.4%，原始严格质量60.1%、回退273张、payload30,835,712字节。阶段时长352.19秒，两阶段训练器合计1988.53秒，全部冻结状态及原生重载通过。当前随机初始化参照保持81.3%。`[verified: psnr-head-sampled4-result.json；comparison.json reference_model、results.mean_full30]`

冻结预测分别替换实测通道MSE、零通道、MS-SSIM和角度后，Top-1为86.1%、76.3%、87.2%和78.5%，全部实测指标为100%。同集余量拟合的严格质量为60.2%、回退272张。以上保留为本开发协议的条件替换和拟合结果。后续按计划继续固定容量的资产组限权与法线过采样对照。当前准备和头部阶段的22份源码／输入已按SHA归档，共317,919,625字节。`[verified: psnr-head-sampled4-result.json；progress.json source_archives.before_image_sampling；source-archive-before-image-sampling/manifest.json；opinion: 后续实验顺序]`

## 资产族限额与法线重复采样

训练语料包含2325个直接父目录。采样器复用`DatasetSplitter.asset_group`并统一结果大小写，得到1318个资产族，合并SD／HD／FHD及角色子目录；原语料的group字段保持其原始定义。每轮每族上限64张的对照均匀无放回选取5622张，单族最多64张；法线重复2次的对照保留全部10000图，再为299张法线各增加一次访问，共10299次。64与2为本轮单项对照的参数选择。`[verified: image-sampling-design.json；unity_image_sampling.py；opinion: 参数选择]`

两项沿用随机初始化均值池化参照的30轮学习率配方，记录各自实际图像访问、优化器更新和耗时。启用控制时，逐批收集实际original_image_index，每轮与计划顺序逐项比对，保存独立SHA绑定的回执；终态及确认入口核验其身份。整图头再训练明确恢复其每图一次的采样字段。`[verified: unity_quality_trainer.py；unity_image_sampling.py receipt；confirmation_evidence.py；refit_unity_image_head.py]`

关闭控制的两轮CUDA检查完成4次更新，损失、Top-1、完整配置匹配和近阈值RMSE逐项复现旧记录。cap2预检每轮实际11张、完成2次更新；法线重复预检每轮36次访问、完成6次更新，全部重载及实际顺序检查通过。223项混合检查（222项CPU、1项CUDA）、静态检查和只读审阅通过。两项正式采样对照均已完成。`[verified: image-sampling-verification.json；mean-familycap2-smoke.json；mean-normalrepeat2-smoke.json；progress.json]`

cap64完成30轮、10,553次更新及7次AMP跳步，选中epoch30，原始／同集拟合Top-1为78.0%／79.0%，同权重近阈值RMSE为2.8970dB。完整配置匹配46.1%，严格质量58.3%，回退291张，payload30,620,160字节；训练器1319.44秒，原生重载通过。30份访问回执独立重算通过，共168660次访问、9055张不同训练图，10000张可用图中945张未在本次限额训练中被访问。验证资产族宏平均83.44%，直接父目录宏平均84.69%；保留81.3%的随机初始化参照。`[verified: mean-familycap64-result.json；image-sampling-verification.json；comparison.json reference_model]`

冻结预测分别用实测通道MSE、MS-SSIM及角度替换后，Top-1为87.5%、88.8%和79.7%，全部实测指标为100%。同集拟合严格质量65.1%、回退223张。该模型的52份结构证据及30份采样回执通过绑定，最终确认准入继续因Top-1低于90%拒绝。`[verified: mean-familycap64-result.json；image-sampling-verification.json familycap_bound_evidence_files、familycap_final_admission]`

既有归因报告中的asset_group_macro使用原语料的487个验证父目录。本轮另外按相同资产族规则补算189组，随机初始化参照的资产族宏平均为84.75%，ImageNet加整图头对照为88.53%。后者45张法线中34张块大小正确；固定其余预测、把法线块大小全部替换为原标签时，总体Top-1为87.4%。这些数值由冻结决策重算，forward为0，后续先完成共享模型采样对照。`[verified: sampling-group-normal-diagnostics.json；opinion: 后续顺序]`

法线重复2次完成30轮、19,310次更新及10次AMP跳步，选中epoch30，原始／同集拟合Top-1为79.2%／79.8%，同权重近阈值RMSE为2.2757dB，严格质量62.2%、回退252张。训练器1707.89秒，原生重载通过。30份回执均独立重算，每张普通图每轮一次、每张法线两次，共308970次访问、10000张不同图及17940次法线访问；验证资产族宏平均84.30%。保留81.3%的随机初始化参照。`[verified: mean-normalrepeat2-result.json；image-sampling-verification.json]`

## ResNet-34容量对照

已执行的固定容量对照未达到90%，后续选择计划中的ResNet-34，以随机初始化均值池化参照为起点，只改变backbone_name。参数从11,305,980增至21,414,140，特征维度为512；共同预测头及后续CPU RNG与原ResNet-18配对。历史配置缺少架构字段时恢复ResNet-18，实际旧检查点的全部张量恢复一致。采样阶段23份源码／测试快照已归档，共208843字节。`[verified: resnet34-design.json；resnet34-legacy-initialization-probe.json；source-archive-before-resnet34/manifest.json；opinion: 容量选择]`

229项混合检查（228项CPU、1项CUDA）、ruff、basedpyright及只读审阅通过。旧默认CUDA检查逐项复现原损失及验证指标，ResNet-34真实32／16图预检完成4次更新及原生重载，训练器11.74秒，峰值分配显存1,735,203,328字节。完整10000／1000、30轮容量训练已启动，推理成本在选中权重后测量。初始CPU合成探针的浮点mask被拒绝，改用bool后通过，初次记录及重试均保留。`[verified: resnet34-verification.json；mean-resnet34-smoke.json；mean-resnet34-full30-config.json；progress.json]`

## 版本同步状态

ImageNet早停对照与完整30轮启动记录已保存为本地提交`0f68d18`。自动审批拒绝向公开仓库`hamsterjiang23/AdaptiveASTC`的`main`推送，并要求明确外部发布授权；GitHub已核对登录账户及仓库所有者均为`hamsterjiang23`，授权请求待用户回复。`[verified: 本轮git commit输出；GitHub get_user_login、get_repo；git push自动审批拒绝理由；progress.json external_push]`

## 测试资源分类修正

此前包含`test_cuda_feature_pool_repeated_outputs_are_bit_identical`的整组检查曾统称CPU检查。该项实际在CUDA创建张量，已为206／223／229项记录补充CPU与CUDA数量。历史混合测试窗口的GPU独占性未完整证明，对应训练时间按实际观察保留。后续训练期间显式排除此项，训练结束后独立串行执行。`[verified: tests/test_unity_quality.py L356–360；confirmation-stage-interface-verification.json cpu_tests；image-sampling-verification.json cpu_tests；resnet34-verification.json cpu_tests]`

ResNet-34随机初始化正式对照完成30轮、18,740次更新及10次AMP跳步，选中epoch30 raw。原始／同验证集拟合Top-1为79.2%／79.4%，同一所选权重近阈值RMSE为2.7386dB，完整配置匹配48.1%、严格质量61.7%、质量回退257张，payload30,692,176字节。训练器耗时2019.32秒，参数21,414,140，重载通过。训练报告的best_color_near_threshold_rmse_db是跨轮追踪值，当前汇总使用checkpoint_audit.metrics中的所选权重误差。随机初始化参照保持81.3%均值池化ResNet-18。`[verified: mean-resnet34-full30-result.json；mean-resnet34-full30.json checkpoint_audit；comparison.json reference_model]`

更正资源分类后，显式排除CUDA项的完整套件230项通过、1项排除；GPU空闲后独立CUDA回归1项通过。两种骨干的16图／128patch推理smoke均通过，完整1000图成本测量按相同验证输入串行执行，计时按整批总成本除以图数报告。`[verified: test-resource-classification-correction.json cpu_only、cuda_serial；inference-cost-r18-smoke.json status、validation_images、input_patches；inference-cost-r34-smoke.json status、validation_images、input_patches；inference-cost-r18-full1000-config.json；inference-cost-r34-full1000-config.json]`

## 完整开发验证输入的推理成本

两组均完成1000图／7173patch，PNG路径及SHA、验证顺序完全一致，patch batch为16，先预热1次再测量3次，GPU串行。新预测四组数组最大绝对差均为0，全部选参重放一致。ResNet-18与ResNet-34的整批预处理／推理／决策中位成本分别为18.3130秒与18.8788秒，摊销18.3130与18.8788ms／图；其中patch forward／transfer分别摊销4.7695与5.3341ms／图。该口径按整批耗时除以图数，单纹理延迟分布未测。加载、输入绑定审计、最终编码和完整mip成本另计。`[verified: inference-cost-capacity-comparison.json；inference-cost-r18-full1000.json measurements；inference-cost-r34-full1000.json measurements]`

## ResNet-34预训练初始化独立对照

官方权重87,319,819字节，完整SHA256为`b627a593bcbe140c234610266fe4f8ae95ea42fc881d091c9b6052e6b1d0590f`。对照相对scratch ResNet-34只改变初始化及对应权重身份，路径字段另设新实验身份。真实权重RGB首卷积完全复制、Alpha／mask为零，6个公共预测头张量和后续CPU RNG与scratch配对。32／16图CUDA预检完成4次更新及重载，训练器11.70秒，峰值张量显存1,735,203,328字节，随后启动完整30轮。预训练主线晋级仍待用户决定。`[verified: imagenet-resnet34-weights.json；imagenet-resnet34-design.json；imagenet-resnet34-smoke.json；progress.json active_job]`

ResNet-34 ImageNet完整对照完成30轮、18,742次更新及8次AMP跳步，选中epoch29 raw，原始／同验证集拟合Top-1为86.2%／86.8%。同一所选权重近阈值RMSE1.6128dB，严格质量66.1%、质量回退213张，训练器2023.56秒，原生重载通过。冻结预测的真实通道MSE、MS-SSIM及角度替换分别为92.6%、92.2%、87.4%，全实测指标重放100%。后续采用既有sampled4整图头再训练协议，冻结encoder与channel head，作为独立预训练容量分支继续检查，主线初始化选择仍待决定。`[verified: imagenet-resnet34-full30-result.json；imagenet-resnet34-head-design.json；opinion: 后续单项对照选择]`

补测的ResNet-18 ImageNet整图头与ResNet-34 ImageNet两臂均完成相同1000图／7173patch的推理核验，摊销预处理／推理／决策成本分别18.5415与18.8399ms／图，四臂全部PNG身份与顺序一致，新两臂的四组预测数组差为0、选参一致，receipt证明串行。ResNet-34整图头32图预检完成4次更新、初始1000图Top-1复现86.2%，encoder与channel head逐位保持，重载通过；完整30轮头部单项对照已启动。`[verified: inference-cost-imagenet-verification.json；inference-cost-capacity-comparison.json；imagenet-resnet34-head-design.json smoke、status；progress.json active_job]`
