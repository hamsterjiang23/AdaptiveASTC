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

规则诊断、完整原生基线、权重0.03及仅均值池化对照、冻结预测归因及同验证集余量拟合已完成。ImageNet初始化对照已启动。后续状态与结果写入[本轮进度](progress.json)。`[verified: rules.json status；comparison.json；imagenet-mean.json status；progress.json]`

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

按当前验证Top-1，仅均值池化作为下一项初始化对照的参照。三组训练器时长分别529.26／421.97／630.16秒，各自按8／6／10轮早停记录，部署成本另测。`[verified: comparison.json reference_model、results；opinion: 参照选择]`

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
