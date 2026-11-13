# Unity V2 原生实验执行

本轮执行 [V2 计划](<../../experiment plan/V2/README.md>)，使用已交付的新版 train10000／validation1000；独立确认集为2000张。主验收为确认集块大小 Top-1≥90%，质量、完整配置匹配、payload和各阶段耗时一并报告。`[verified: experiment plan/V2/README.md L11–13；launch-binding.json development、confirmation_identity_only]`

## 当前结果

用户选定的ResNet34原始预测＋预测候选索引起点向后续搜已完成真实validation1000评估。块大小Top-1为93.6%，平均1.627次实际编码，严格质量通过87.5%，相对原标签质量回退0张。一次预热和三次正式配对运行均通过预测、候选编码、解码像素、原生质量和查询顺序审计；三轮整集计时的中位数摊销到每图为续搜195.80ms、fixed8／medium 21.34ms。训练更新0，确认集文件访问0。`[verified: forward-search-full1000-v1.json status、summary、measurements；forward-search-verification.json runtime_reports]`

系统变体离线评估已完成3模型×2预测口径×39变体。ResNet34原始预测的预测preset双向探测K=2达到94.0%、平均1.547次编码；向后续搜达到93.6%、平均1.627次且相对原标签质量回退0张。模型调用、训练更新、实际编码与确认集文件访问均为0。`[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw；system-variants-verification.json runtime_guards]`

当前单次预测＋原规则决策的独立预训练对照最佳原始validation1000 Top-1为86.9%，来自ResNet-34 ImageNet加sampled4整图头再训练，选中epoch15／image_head_refit；同一验证集拟合余量后为87.1%。所选权重近阈值RMSE1.6135dB，重载和冻结参数审计通过。单次预测模型的开发90%准入尚未达到，确认集模型推理保持封存。随机初始化参照保持81.3%的ResNet-18均值池化模型。`[verified: imagenet-resnet34-head-sampled4-result.json；imagenet-resnet34-head-evidence.json final_model_admission、model_forward_calls；comparison.json reference_model]`

## 预测起点向后续搜的真实运行

冻结的ResNet34原始预测用于选择具体候选起点，随后按canonical20向后进行实际编码、解码与原生质量判定。最终输出复用已经生成的ASTC。所有1000图输入与7173patch的训练端输入一致，四个完整运行的新预测数组与保存数组逐位一致，模型参数与buffer保持。`[verified: forward-search-full1000-v1.json input_parity_patches、measurements、model_parameters_and_buffers_unchanged；forward_deployment.py UnityForwardSearchTrial.run、NativeForwardQueries.measure]`

| 指标 | 真实续搜结果 |
|---|---|
| 块大小Top-1／balanced accuracy | 93.6%／92.00%。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics]` |
| 块大小与preset完整匹配 | 80.4%。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics.full_choice_accuracy]` |
| 严格质量通过／相对原标签质量回退 | 875／1000，0张。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics.actual_quality_pass_rate、quality_regression_images]` |
| 块大小选大／选小 | 0／64张。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics.larger_block_images、smaller_block_images]` |
| 候选编码平均／中位／P95／最大 | 1.627／1／5／16次。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics.candidates_measured]` |
| mip0 payload | 32,067,120字节，为fixed8／medium的53.6584%、原标签的101.2811%。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics.payload_bytes、payload_ratio_to_fixed8、payload_ratio_to_original]` |
| sRGB小图612／大图326 | 91.34%／98.47%。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics.groups.srgb_small、srgb_large]` |
| 法线45／Linear17 | 88.89%／94.12%。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics.groups.normal、linear]` |
| 487直接父目录／189资产族宏平均 | 95.34%／93.51%。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics.groups.direct_parent_macro、asset_family_macro]` |

702张图一次编码完成，873张两次内完成，926张三次内完成。实际选择包括643张first_valid、232张size_first_strict、92张大图放宽及33张最高PSNR回退，后两组共125张未通过严格质量门槛。完整混淆矩阵和逐类precision／recall保存在结构化报告。`[verified: forward-search-verification.json encoding_count_distribution、selection_reason_distribution；forward-search-full1000-v1.json summary.forward.validation_metrics.confusion_matrix、per_class]`

三次正式测量的整集耗时分别为续搜195.795／194.446／197.245秒，fixed8为21.306／21.341／21.335秒。参考PNG到内存mip0 ASTC路径包含新推理与候选实际质量门控，模型／DLL加载、同步trace哈希、进度写入、计时后真值审计和产物写入分别记录。计时使用预热后的模型、DLL与文件系统，评估内部wall为1867.74秒，完整进程1872.12秒。`[verified: forward-search-full1000-v1.json measurements、scope、wall_seconds；forward-search-verification.json runtime_reports.full.job.wall_seconds]`

归档原搜索平均7.061次、search_ms均值1068.42ms；历史均值与本次续搜摊销中位数的比值为5.457。本次配对实测参照为fixed8／medium，续搜耗时为其9.177倍，二者严格质量通过率为87.5%／81.1%。`[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B1_candidate_idx.original_candidates_measured、encoding_cost_estimate；forward-search-verification.json historical_original_mean_over_measured_forward、forward_seconds_over_fixed8；forward-search-full1000-v1.json summary]`

先期8图编码pilot保留完整1000图新推理形状，完整进程168.08秒。pilot与全量合计执行6次完整验证预测、10576次实际编码，包含预热与fixed8配对；训练更新0，确认集访问0。9436次输入／源码SHA绑定检查、8050份输出产物SHA检查，以及1000份QA target的后置SHA复核全部通过。运行前Dataset逐项核验target SHA，后置verification补全了运行报告inputs_sha256中省略的target路径清单。`[verified: forward-search-smoke8-v1.json；forward-search-verification.json hash_verification、qa_target_source_evidence、encoding_calls_including_pilot_and_warmups、fresh_full1000_prediction_passes_including_pilot_and_warmups、runtime_reports]`

## 开发系统冻结

已使用现有UnityEvaluationSeal以validation身份冻结选定ResNet34模型、原始零余量、0.5零通道门槛、逐图原生规则、候选索引起点及无固定预算的canonical20向后续搜。合同绑定8238份文件、1000张有序验证输入与7173patch运行形状，指纹为`218fe31a56c94b32f946121063cf8c82533074d4e53cf2eb25e5d8231e216d27`。封存与重开同一合同核验通过。`[verified: forward-search-validation-freeze.json identity、bound_files、seal_fingerprint]`

此次封存forward尝试为0，模型／编码／CUDA初始化／优化器构造／确认集文件访问计数均为0。独立确认的评估对象及准入协议处于待决定状态，原单次预测模型准入证据为86.9%，系统真实验证为93.6%。既有封存类及封存推理的24项检查通过，冻结脚本ruff与basedpyright通过。`[verified: forward-search-validation-freeze.json seal_forward_attempts、runtime_guards、independent_confirmation_admission、validation_pure_model_accuracy、validation_system_accuracy；pytest输出24 passed in4.20s；ruff和basedpyright输出]`

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

规则诊断、完整原生基线、初始化与固定容量对照、冻结预测归因及同验证集余量拟合已完成。当前随机初始化参照Top-1为81.3%，最佳独立ImageNet对照为86.9%，PSNR两阶段为76.4%。后续状态与结果写入[本轮进度](progress.json)。`[verified: rules.json status；comparison.json；progress.json]`

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
| ResNet-34 ImageNet整图头再训练 | 86.9% | 1.6135dB | 87.1%。`[verified: comparison.json results.imagenet_resnet34_head_sampled4]` |
| ResNet-50随机初始化 | 80.5% | 2.6311dB | 81.1%。`[verified: comparison.json results.mean_resnet50_full30]` |
| ResNet-50 ImageNet初始化 | 85.6% | 1.6411dB | 85.9%。`[verified: comparison.json results.imagenet_resnet50_full30]` |
| ResNet-50 ImageNet整图头再训练 | 86.0% | 1.6389dB | 86.3%。`[verified: comparison.json results.imagenet_resnet50_head_sampled4]` |
| ResNet-50 IMAGENET1K_V2初始化 | 85.4% | 1.9043dB | 85.4%。`[verified: comparison.json results.imagenet1k_v2_resnet50_full30]` |
| ResNet-50 IMAGENET1K_V2整图头 | 85.3% | 1.8845dB | 85.5%。`[verified: comparison.json results.imagenet1k_v2_resnet50_head_sampled4]` |

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

ResNet-34 sampled4整图头完整对照完成30轮、18,746次更新及4次AMP跳步，选中epoch15／image_head_refit，原始／同验证集拟合Top-1为86.9%／87.1%。同权重近阈值RMSE1.6135dB，严格质量68.2%、质量回退192张，payload31,392,800字节。整图头训练器357.66秒，与初始完整训练合计2381.22秒；72940参数参与头部更新，encoder与channel head保持，原生重载通过。当前39份模型血缘证据通过只读核验，正式准入以低于90%拒绝，forward为0。`[verified: imagenet-resnet34-head-sampled4-result.json；imagenet-resnet34-head-evidence.json；imagenet-resnet34-head-verification.json]`

新头部权重的1000图／7173patch成本测量完成，批量摊销18.8732ms／图，PNG身份与顺序同前四臂，预测数组差为0、选参一致。下一项按V2容量路线准备ResNet-50，当前实现尚未启动；已归档53份当前源码和绑定输入，共333,226,055字节，全部SHA核对通过，并通过24份头部及13份初始原生源码／输入的归档绑定核验。`[verified: inference-cost-imagenet-r34-head-full1000.json；imagenet-resnet34-head-verification.json；resnet50-source-readiness.json；opinion: 后续容量选择]`

## ResNet-50容量对照

ResNet-50采用Torchvision Bottleneck的[3,4,6,3]布局，编码特征为2048维，FiLM、patch头及整图头按该宽度配套；均值池化模型24,003,068参数，整图头287,980参数。训练验证、流式推理及特征缓存三处缓冲区按模型宽度分配。完整配置相对scratch ResNet-34只改变backbone_name及输出位置。`[verified: resnet50-design.json；resnet50-legacy-cpu-verification.json resnet50_capacity；opinion: 容量实现选择]`

四组ResNet-18／34与mean／mean_max的初始化状态及后续CPU RNG逐位复现，两个实际历史检查点的CPU状态和探针输出一致。旧ResNet-18 CUDA预检全部逐轮损失与非计时指标复现，旧ResNet-34的1000图／7173patch新运行库预测数组及选参均完全一致。238项CPU检查、2项独立CUDA池化检查和静态检查通过，代码只读审阅CLEAN。`[verified: resnet50-legacy-cpu-verification.json；resnet50-verification.json cpu_tests、cuda_pool_tests、static_checks、independent_readonly_code_review]`

ResNet-50原生32图CUDA预检完成4次更新与重载，峰值张量显存3,749,087,232字节，训练器11.98秒；16图／128patch实际流式CUDA推理与原保存数组、选参一致。随后启动10000／1000图、30轮随机初始化容量对照，当前训练效果等待终态结果。接口核对使用已安装Torchvision0.23.0及对应官方源码。`[verified: mean-resnet50-smoke.json；resnet50-inference-smoke.json；resnet50-verification.json full_training_started；resnet50-verification.json api_documentation]`

ResNet-50随机初始化完整对照完成30轮、18,740次更新及10次AMP跳步，选中epoch26／raw。原始／同验证集拟合Top-1为80.5%／81.1%，同一权重近阈值RMSE2.6311dB，严格质量66.6%、质量回退208张、payload31,720,688字节。训练器2974.96秒，峰值张量显存3,749,087,232字节，完整重载通过。22份模型证据通过只读核验，正式准入以低于90%拒绝、forward为0。`[verified: mean-resnet50-full30-result.json；mean-resnet50-full30-verification.json；mean-resnet50-evidence.json]`

同1000图／7173patch的实际推理数组与选参完全重放，批量摊销19.1192ms／图。原始Top-1低于81.3%的随机初始化参照，本次负结果保留。冻结预测分别替换真实通道MSE、MS-SSIM和角度得到88.8%、89.0%、82.6%，全实测指标重放100%。`[verified: inference-cost-r50-full1000.json；mean-resnet50-full30-result.json attribution_accuracy；comparison.json reference_model、results.mean_full30]`

独立初始化对照显式使用官方ResNet50_Weights.IMAGENET1K_V1，102,530,333字节，SHA256为`0676ba61b6795bbe1773cffd859882e5e297624d384b6993f7c9e683e722fb8a`。真实RGB首卷积和深层权重迁移、Alpha／mask置零、六个共同头张量及CPU RNG配对通过，CUDA预检4更新、0跳步、重载通过，随后启动同配方完整30轮。主线初始化晋级仍待用户决定。`[verified: imagenet-resnet50-weights.json；imagenet-resnet50-design.json；imagenet-resnet50-smoke.json；progress.json active_job]`

ImageNet IMAGENET1K_V1初始化的ResNet-50完成30轮、18,741更新与9次AMP跳步，选中epoch25／raw，原始／同验证集拟合Top-1为85.6%／85.9%，所选权重近阈值RMSE1.6411dB。严格质量68.1%、质量回退196张、payload31,248,448字节，训练器2974.38秒，原生重载通过。22份血缘通过只读核验，正式准入以低于90%拒绝、forward为0。`[verified: imagenet-resnet50-full30-result.json；imagenet-resnet50-full30-verification.json；imagenet-resnet50-evidence.json]`

同1000图／7173patch批量摊销19.3270ms／图，实际PNG身份／顺序、预测数组与选参复核通过。冻结预测分别替换真实通道MSE、MS-SSIM和角度，Top-1为92.8%、91.2%、87.0%，全实测指标100%。287,980参数的整图头32图CUDA预检复现初始1000图85.6%，完成4更新、冻结及重载，完整30轮头部对照已启动。`[verified: inference-cost-imagenet-r50-full1000.json；imagenet-resnet50-full30-result.json attribution_accuracy；imagenet-resnet50-head-design.json]`

ResNet-50 IMAGENET1K_V1整图头完成30轮、18,747更新及3次AMP跳步，选中epoch7／image_head_refit，原始／同验证集拟合Top-1为86.0%／86.3%，所选近阈值RMSE1.6389dB。严格质量68.7%、质量回退190张、payload31,441,648字节，头部训练器367.67秒，两阶段合计3342.04秒。287,980参数参与训练，非头部状态与重载核验通过，39份血缘通过只读核验，正式90%准入拒绝，forward为0。`[verified: imagenet-resnet50-head-sampled4-result.json；imagenet-resnet50-head-evidence.json；imagenet-resnet50-head-verification.json]`

同1000图／7173patch推理数组及选参精确重放，批量摊销19.0296ms／图。下一初始化版本对照仅将权重来源从IMAGENET1K_V1切换为官方IMAGENET1K_V2，同模型、数据及训练配置的四项差异为权重路径／SHA和输出位置。实际CPU权重迁移、六份共同头及后续RNG配对通过，32图CUDA预检4更新、0跳步、重载通过，同配方完整30轮已启动。`[verified: inference-cost-imagenet-r50-head-full1000.json；imagenet1k-v2-resnet50-design.json；imagenet1k-v2-resnet50-smoke.json；opinion: 权重版本对照选择]`


## IMAGENET1K_V2权重版本结果

同配方ResNet-50完成30轮、18,741更新及9次AMP跳步，选中epoch19／raw。原始与同验证集余量拟合Top-1均为85.4%，所选权重近阈值RMSE1.9043dB，完整配置匹配57.1%、严格质量66.3%、质量回退213张、payload31,436,016字节。训练器2996.74秒，原生重载和22份来源绑定通过。`[verified: imagenet1k-v2-resnet50-full30-result.json；imagenet1k-v2-resnet50-evidence.json]`

冻结预测分别替换实测通道MSE、MS-SSIM和角度后，Top-1为91.9%、91.9%和86.5%，全部实测指标为100%。这些数值来自固定预测的条件替换诊断。后续按原sampled4配方执行整图头对照，先做32训练图预检。`[verified: imagenet1k-v2-resnet50-full30-attribution.json variants；imagenet1k-v2-resnet50-head-sampled4-smoke-config.json；opinion: 后续实验顺序]`

完整验证1000图／7173patch推理完成1预热与3次测量，四份预测数组和选参全部精确复现。批量摊销参考PNG准备、输入组装、CUDA推理和规则决策为20.3587ms／图，模型加载与身份审计成本单列。整图头32训练图预检已串行启动。`[verified: inference-cost-imagenet1k-v2-r50-full1000.json measurements、amortized_preprocess_inference_decision_seconds_per_image；imagenet1k-v2-resnet50-full30-verification.json；progress.json active_job]`


## IMAGENET1K_V2整图头结果

32训练图预检完成4更新、0跳步、初始结果复现及冻结状态／原生重载核验，训练器126.02秒。正式整图头完成30轮、18,745更新及5次AMP跳步，选中epoch20／image_head_refit，原始／同验证集拟合Top-1为85.3%／85.5%，所选权重近阈值RMSE1.8845dB。完整配置匹配57.4%、严格质量69.1%、质量回退185张、payload31,739,888字节。阶段训练器370.73秒，两阶段合计3367.47秒，287,980参数参与训练，全部非头部状态及原生重载通过。`[verified: imagenet1k-v2-resnet50-head-sampled4-smoke.json；imagenet1k-v2-resnet50-head-sampled4-result.json]`

冻结预测分别替换实测通道MSE、MS-SSIM和角度后，Top-1为92.1%、91.8%和86.5%，全部实测指标为100%。39份来源绑定通过只读核验，正式90%准入拒绝，模型forward为0。后续先比较当前最佳ResNet34整图头模型在训练与验证上的全patch表现，固定权重、原规则和输入口径。`[verified: imagenet1k-v2-resnet50-head-sampled4-attribution.json variants；imagenet1k-v2-resnet50-head-evidence.json；opinion: 后续诊断选择]`

完整验证1000图／7173patch的四份预测数组及选参精确复现，1预热3测量的批量摊销准备、推理与决策为19.6064ms／图，单列加载和身份审计成本。资源监控首个受限CIM内存查询失败，原样本与错误说明保留，后续使用通过权限核验的采样，正式训练与计时均成功退出。`[verified: inference-cost-imagenet1k-v2-r50-head-full1000.json；imagenet1k-v2-resnet50-head-verification.json]`


## 系统变体离线评估（validation1000）

三个冻结模型的原始和既有校准预测各评估39个系统变体，共234组；147组非参照系统变体达到块大小Top-1≥90%，原搜索六组参照均为100%。运行守卫的模型调用、优化器构造、编码器构造、CUDA初始化及确认集文件访问均为0。`[verified: system-variants-verification.json evaluated_arms、qualifying_system_variant_arms_excluding_reference、runtime_guards]`

输入为冻结的validation1000和开发语料20候选归档。四组计数为srgb_small612、srgb_large326、normal45、linear17，直接父目录487组、资产族189组。逐类precision／recall、混淆矩阵、分组及宏平均、体积与成本详见[完整结果](system-variants-result.json)，输入身份见[配置](system-variants-config.json)，运行与检查见[核验记录](system-variants-verification.json)。`[verified: system-variants-verification.json group_counts、direct_parent_groups、asset_family_groups]`

### ResNet34整图头原始预测

| 系统变体 | 块大小Top-1 | 完整匹配 | 严格质量 | 质量回退图数 | 编码均值／P95／最大 | 证据 |
|---|---|---|---|---|---|---|
| `0_pure_model` | 86.9% | 58.8% | 68.2% | 192 | 1.000／1／1 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.0_pure_model]` |
| `original_search` | 100.0% | 100.0% | 87.4% | 0 | 7.061／18／20 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.original_search]` |
| `normal_native_search` | 87.9% | 61.8% | 69.3% | 181 | 1.437／1／20 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.normal_native_search]` |
| `B1_candidate_idx` | 93.6% | 80.4% | 87.5% | 0 | 1.627／5／16 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B1_candidate_idx]` |
| `B1_block_start` | 93.9% | 93.9% | 87.4% | 0 | 3.404／7／20 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B1_block_start]` |
| `B2_candidate_idx_predicted_preset_K2` | 94.0% | 70.1% | 77.3% | 101 | 1.547／2／2 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K2]` |
| `B2_candidate_idx_predicted_preset_K3` | 95.3% | 75.0% | 81.9% | 55 | 1.712／3／3 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K3]` |
| `B2_candidate_idx_predicted_preset_K5` | 98.5% | 79.6% | 85.7% | 17 | 1.837／5／5 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K5]` |
| `B2_candidate_idx_predicted_preset_unlimited` | 99.3% | 82.1% | 87.5% | 0 | 1.914／5／16 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_unlimited]` |
| `B2_candidate_idx_canonical_block_K2` | 88.6% | 68.6% | 77.3% | 101 | 1.547／2／2 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_canonical_block_K2]` |
| `B2_candidate_idx_canonical_block_K3` | 89.8% | 73.5% | 81.9% | 55 | 1.923／3／3 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_canonical_block_K3]` |
| `normal_native_search+B2_candidate_idx_predicted_preset_K2` | 94.5% | 72.5% | 78.0% | 94 | 1.948／2／20 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.normal_native_search+B2_candidate_idx_predicted_preset_K2]` |
| `normal_native_search+B2_candidate_idx_predicted_preset_K3` | 95.7% | 77.1% | 82.3% | 51 | 2.102／3／20 | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.normal_native_search+B2_candidate_idx_predicted_preset_K3]` |

原始模型131个块大小错误中125个为相邻档，占95.42%；向后续搜的702图只编码一次，171图编码两次。纯预测起点的严格质量通过率为68.2%。`[verified: system-variants-verification.json locality_diagnostics、raw_r34_encoding_count_distributions；system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.0_pure_model]`

### 各模型达到90%的最少平均编码方案

| 模型 | 预测口径 | 系统变体 | Top-1 | 平均编码 | 严格质量 | 回退图数 | 证据 |
|---|---|---|---|---|---|---|---|
| `imagenet-resnet34-head-sampled4` | raw | `B2_candidate_idx_predicted_preset_K2` | 94.0% | 1.547 | 77.3% | 101 | `[verified: system-variants-verification.json minimum_by_model]` |
| `imagenet-resnet34-head-sampled4` | calibrated | `B2_candidate_idx_predicted_preset_K2` | 93.8% | 1.547 | 78.2% | 93 | `[verified: system-variants-verification.json minimum_by_model]` |
| `imagenet-head-sampled4` | raw | `B2_candidate_idx_predicted_preset_K2` | 92.6% | 1.543 | 77.1% | 104 | `[verified: system-variants-verification.json minimum_by_model]` |
| `imagenet-head-sampled4` | calibrated | `B2_candidate_idx_predicted_preset_K2` | 91.7% | 1.549 | 74.8% | 126 | `[verified: system-variants-verification.json minimum_by_model]` |
| `mean-full30` | raw | `B2_candidate_idx_predicted_preset_K3` | 93.1% | 1.818 | 78.8% | 87 | `[verified: system-variants-verification.json minimum_by_model]` |
| `mean-full30` | calibrated | `B2_candidate_idx_predicted_preset_K3` | 92.9% | 1.815 | 78.6% | 89 | `[verified: system-variants-verification.json minimum_by_model]` |

全局最少平均编码方案是ResNet18预训练整图头原始预测配合预测preset的双向探测K=2，Top-1为92.6%、平均1.543次；ResNet34同策略为94.0%、平均1.547次。完整二维Pareto点保存在结果的pareto_frontier中。`[verified: system-variants-result.json minimum_encoding_solutions_at90、pareto_frontier]`

### 回溯成本估算

法线路由原搜索的图使用原始search_ms；模型路由的图累加归档编码耗时、实际需要门控的解码与质量评价耗时，以及已测PNG准备／输入／推理／原规则决策的批量摊销成本。选中ASTC复用；纯预测只计一次最终编码。原搜索主基准均值为1068.42ms，同归档重放基准为461.47ms。`[verified: system-variants-result.json timing_scope、models.imagenet-resnet34-head-sampled4.raw.original_search.encoding_cost_estimate]`

| ResNet34原始预测方案 | 主路径估算均值ms | 相对历史原搜索估算加速比 | 同归档匹配估算加速比 | 证据 |
|---|---|---|---|---|
| `original_search` | 1068.42 | 1.000× | 1.000× | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.original_search.encoding_cost_estimate]` |
| `0_pure_model` | 130.10 | 8.212× | 3.547× | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.0_pure_model.encoding_cost_estimate]` |
| `normal_native_search` | 294.48 | 3.628× | 2.439× | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.normal_native_search.encoding_cost_estimate]` |
| `B1_candidate_idx` | 201.12 | 5.312× | 2.295× | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B1_candidate_idx.encoding_cost_estimate]` |
| `B2_candidate_idx_predicted_preset_K2` | 215.57 | 4.956× | 2.141× | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K2.encoding_cost_estimate]` |
| `B2_candidate_idx_predicted_preset_K3` | 227.87 | 4.689× | 2.025× | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K3.encoding_cost_estimate]` |
| `B2_candidate_idx_predicted_preset_K5` | 234.05 | 4.565× | 1.972× | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_K5.encoding_cost_estimate]` |
| `B2_candidate_idx_predicted_preset_unlimited` | 240.97 | 4.434× | 1.915× | `[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw.B2_candidate_idx_predicted_preset_unlimited.encoding_cost_estimate]` |

这些时间来自归档候选耗时与既有批量摊销模型计时的组合估算，覆盖参考PNG到mip0 ASTC及实测门控所需的解码／质量评价，模型加载、Unity导入及完整mip链成本单列。`[verified: system-variants-result.json timing_scope；system-variants-config.json quality_query_cost、pure_model_cost；opinion: 成本估计范围]`

### 完整变体对照

下表单元格为块大小Top-1／平均编码次数，粗体表示达到90%。R34对应imagenet-resnet34-head-sampled4，R18预训练对应imagenet-head-sampled4，R18随机对应mean-full30；校准为已有同验证集余量拟合。`[verified: system-variants-config.json models；system-variants-result.json calibration_scope]`

| 系统变体 | R34原始 | R34校准 | R18预训练原始 | R18预训练校准 | R18随机原始 | R18随机校准 | 证据 |
|---|---|---|---|---|---|---|---|
| `0_pure_model` | 86.9%／1.000 | 87.1%／1.000 | 86.3%／1.000 | 86.7%／1.000 | 81.3%／1.000 | 81.5%／1.000 | `[verified: system-variants-result.json models各模型raw/calibrated的0_pure_model]` |
| `original_search` | **100.0%／7.061** | **100.0%／7.061** | **100.0%／7.061** | **100.0%／7.061** | **100.0%／7.061** | **100.0%／7.061** | `[verified: system-variants-result.json models各模型raw/calibrated的original_search]` |
| `normal_native_search` | 87.9%／1.437 | 88.1%／1.437 | 87.4%／1.437 | 87.8%／1.437 | 82.9%／1.437 | 83.0%／1.437 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search]` |
| `B1_candidate_idx` | **93.6%／1.627** | **93.0%／1.590** | **93.2%／1.661** | **95.3%／1.777** | **91.5%／1.868** | **91.9%／1.871** | `[verified: system-variants-result.json models各模型raw/calibrated的B1_candidate_idx]` |
| `B2_candidate_idx_predicted_preset_unlimited` | **99.3%／1.914** | **99.1%／1.894** | **98.8%／1.949** | **99.2%／2.021** | **99.0%／2.157** | **99.0%／2.150** | `[verified: system-variants-result.json models各模型raw/calibrated的B2_candidate_idx_predicted_preset_unlimited]` |
| `B2_candidate_idx_predicted_preset_K2` | **94.0%／1.547** | **93.8%／1.547** | **92.6%／1.543** | **91.7%／1.549** | 89.6%／1.585 | 89.3%／1.582 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_candidate_idx_predicted_preset_K2]` |
| `B2_candidate_idx_predicted_preset_K3` | **95.3%／1.712** | **95.2%／1.703** | **94.4%／1.712** | **93.6%／1.729** | **93.1%／1.818** | **92.9%／1.815** | `[verified: system-variants-result.json models各模型raw/calibrated的B2_candidate_idx_predicted_preset_K3]` |
| `B2_candidate_idx_predicted_preset_K5` | **98.5%／1.837** | **98.3%／1.821** | **97.3%／1.851** | **97.2%／1.897** | **96.9%／2.013** | **96.9%／2.011** | `[verified: system-variants-result.json models各模型raw/calibrated的B2_candidate_idx_predicted_preset_K5]` |
| `B2_candidate_idx_canonical_block_unlimited` | **99.5%／3.001** | **99.3%／3.041** | **99.2%／3.039** | **99.6%／2.964** | **99.3%／3.184** | **99.3%／3.143** | `[verified: system-variants-result.json models各模型raw/calibrated的B2_candidate_idx_canonical_block_unlimited]` |
| `B2_candidate_idx_canonical_block_K2` | 88.6%／1.547 | 88.1%／1.547 | 87.4%／1.543 | 88.0%／1.549 | 83.6%／1.585 | 83.7%／1.582 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_candidate_idx_canonical_block_K2]` |
| `B2_candidate_idx_canonical_block_K3` | 89.8%／1.923 | 89.4%／1.925 | 89.2%／1.918 | 89.9%／1.921 | 86.8%／2.013 | 87.0%／2.004 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_candidate_idx_canonical_block_K3]` |
| `B2_candidate_idx_canonical_block_K5` | **96.8%／2.543** | **96.4%／2.566** | **95.9%／2.551** | **96.4%／2.525** | **95.4%／2.682** | **95.4%／2.659** | `[verified: system-variants-result.json models各模型raw/calibrated的B2_candidate_idx_canonical_block_K5]` |
| `B1_block_start` | **93.9%／3.404** | **93.3%／3.346** | **93.6%／3.417** | **95.6%／3.554** | **91.9%／3.601** | **92.3%／3.618** | `[verified: system-variants-result.json models各模型raw/calibrated的B1_block_start]` |
| `B2_block_start_predicted_preset_unlimited` | **97.7%／3.528** | **97.5%／3.480** | **97.9%／3.554** | **98.4%／3.655** | **97.3%／3.746** | **97.5%／3.756** | `[verified: system-variants-result.json models各模型raw/calibrated的B2_block_start_predicted_preset_unlimited]` |
| `B2_block_start_predicted_preset_K2` | **90.7%／1.793** | **91.2%／1.793** | **90.4%／1.793** | 89.5%／1.793 | 86.1%／1.795 | 86.1%／1.795 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_block_start_predicted_preset_K2]` |
| `B2_block_start_predicted_preset_K3` | **90.7%／2.491** | **91.3%／2.485** | **90.6%／2.487** | 89.5%／2.492 | 86.6%／2.503 | 86.6%／2.507 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_block_start_predicted_preset_K3]` |
| `B2_block_start_predicted_preset_K5` | **90.7%／3.196** | **91.3%／3.170** | **90.6%／3.182** | 89.5%／3.228 | 86.7%／3.255 | 86.7%／3.267 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_block_start_predicted_preset_K5]` |
| `B2_block_start_canonical_block_unlimited` | **97.8%／3.975** | **97.6%／3.959** | **98.2%／4.044** | **98.7%／4.030** | **97.5%／4.211** | **97.7%／4.196** | `[verified: system-variants-result.json models各模型raw/calibrated的B2_block_start_canonical_block_unlimited]` |
| `B2_block_start_canonical_block_K2` | 87.1%／1.793 | 87.3%／1.793 | 86.5%／1.793 | 86.9%／1.793 | 82.2%／1.795 | 82.4%／1.795 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_block_start_canonical_block_K2]` |
| `B2_block_start_canonical_block_K3` | 87.1%／2.553 | 87.4%／2.551 | 86.7%／2.552 | 86.9%／2.551 | 82.4%／2.560 | 82.6%／2.561 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_block_start_canonical_block_K3]` |
| `B2_block_start_canonical_block_K5` | 89.6%／3.442 | **90.0%／3.434** | 89.6%／3.449 | 88.9%／3.447 | 85.6%／3.506 | 85.6%／3.505 | `[verified: system-variants-result.json models各模型raw/calibrated的B2_block_start_canonical_block_K5]` |
| `normal_native_search+B1_candidate_idx` | **94.1%／2.036** | **93.5%／1.999** | **93.8%／2.071** | **95.9%／2.187** | **92.5%／2.271** | **92.5%／2.260** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B1_candidate_idx]` |
| `normal_native_search+B2_candidate_idx_predicted_preset_unlimited` | **99.3%／2.296** | **99.1%／2.276** | **98.8%／2.330** | **99.2%／2.402** | **99.0%／2.526** | **99.0%／2.515** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_candidate_idx_predicted_preset_unlimited]` |
| `normal_native_search+B2_candidate_idx_predicted_preset_K2` | **94.5%／1.948** | **94.3%／1.948** | **93.1%／1.946** | **92.2%／1.952** | **90.1%／1.981** | **90.1%／1.980** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_candidate_idx_predicted_preset_K2]` |
| `normal_native_search+B2_candidate_idx_predicted_preset_K3` | **95.7%／2.102** | **95.6%／2.093** | **94.8%／2.101** | **94.0%／2.118** | **93.4%／2.200** | **93.4%／2.197** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_candidate_idx_predicted_preset_K3]` |
| `normal_native_search+B2_candidate_idx_predicted_preset_K5` | **98.6%／2.220** | **98.4%／2.204** | **97.4%／2.234** | **97.3%／2.280** | **97.1%／2.385** | **97.1%／2.380** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_candidate_idx_predicted_preset_K5]` |
| `normal_native_search+B2_candidate_idx_canonical_block_unlimited` | **99.5%／3.281** | **99.3%／3.321** | **99.2%／3.309** | **99.6%／3.234** | **99.3%／3.431** | **99.3%／3.420** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_candidate_idx_canonical_block_unlimited]` |
| `normal_native_search+B2_candidate_idx_canonical_block_K2` | 89.6%／1.948 | 89.1%／1.948 | 88.5%／1.946 | 89.1%／1.952 | 85.1%／1.981 | 85.1%／1.980 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_candidate_idx_canonical_block_K2]` |
| `normal_native_search+B2_candidate_idx_canonical_block_K3` | **90.7%／2.292** | **90.3%／2.294** | **90.2%／2.290** | **90.9%／2.293** | 88.1%／2.371 | 88.1%／2.368 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_candidate_idx_canonical_block_K3]` |
| `normal_native_search+B2_candidate_idx_canonical_block_K5` | **97.1%／2.859** | **96.7%／2.882** | **96.2%／2.871** | **96.7%／2.845** | **95.7%／2.974** | **95.7%／2.969** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_candidate_idx_canonical_block_K5]` |
| `normal_native_search+B1_block_start` | **94.4%／3.748** | **93.8%／3.690** | **94.2%／3.766** | **96.2%／3.903** | **92.9%／3.945** | **92.9%／3.940** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B1_block_start]` |
| `normal_native_search+B2_block_start_predicted_preset_unlimited` | **97.7%／3.857** | **97.5%／3.809** | **97.9%／3.884** | **98.4%／3.985** | **97.7%／4.072** | **97.7%／4.067** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_block_start_predicted_preset_unlimited]` |
| `normal_native_search+B2_block_start_predicted_preset_K2` | **91.2%／2.186** | **91.7%／2.186** | **90.9%／2.186** | **90.0%／2.186** | 87.1%／2.188 | 87.2%／2.188 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_block_start_predicted_preset_K2]` |
| `normal_native_search+B2_block_start_predicted_preset_K3` | **91.2%／2.853** | **91.8%／2.847** | **91.1%／2.847** | **90.0%／2.852** | 87.6%／2.865 | 87.7%／2.865 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_block_start_predicted_preset_K3]` |
| `normal_native_search+B2_block_start_predicted_preset_K5` | **91.2%／3.535** | **91.8%／3.509** | **91.1%／3.522** | **90.0%／3.568** | 87.7%／3.594 | 87.8%／3.594 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_block_start_predicted_preset_K5]` |
| `normal_native_search+B2_block_start_canonical_block_unlimited` | **97.8%／4.250** | **97.6%／4.234** | **98.2%／4.303** | **98.7%／4.289** | **97.9%／4.474** | **97.9%／4.469** | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_block_start_canonical_block_unlimited]` |
| `normal_native_search+B2_block_start_canonical_block_K2` | 88.1%／2.186 | 88.3%／2.186 | 87.6%／2.186 | 88.0%／2.186 | 83.8%／2.188 | 83.9%／2.188 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_block_start_canonical_block_K2]` |
| `normal_native_search+B2_block_start_canonical_block_K3` | 88.1%／2.906 | 88.4%／2.904 | 87.8%／2.905 | 88.0%／2.904 | 84.0%／2.914 | 84.1%／2.914 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_block_start_canonical_block_K3]` |
| `normal_native_search+B2_block_start_canonical_block_K5` | **90.3%／3.750** | **90.7%／3.742** | **90.3%／3.756** | 89.6%／3.754 | 86.7%／3.812 | 86.8%／3.812 | `[verified: system-variants-result.json models各模型raw/calibrated的normal_native_search+B2_block_start_canonical_block_K5]` |

### 执行约定与核验

- `candidate_idx`从预测的具体preset开始，`block_start`从预测块的fastest开始。双向探测仅在首次实测strict达标时向粗块推进，分别评估预测preset和canonical块内候选两种策略。`[verified: system_variant_policy.py replay_variant、preferred_preset；system-variants-result.json variants]`
- K计入起点和所有后续唯一编码，选中结果复用。A组合中的法线图按原搜索完整计数，K约束其余模型路由图；表中最大次数与max_model_route_candidates_measured同时报告。`[verified: system-variants-result.json budget_scope；system_variant_policy.py replay_variant]`
- 预算耗尽保留已测严格合格候选；大图已有锁块时保留最后实测PSNR合格者；其余情况取已测最高PSNR的首个候选。大图跨块多测一次按原生循环计数。未测前缀的PSNR比较只用于事后补测诊断。`[verified: system_variant_policy.py forward_search、CandidateQueries.outcome；system-variants-result.json budget_exhaustion_rule、large_rule]`
- 新模块25项CPU测试通过；完整套件967通过、6项原生环境集成检查跳过、2项CUDA检查排除，ruff和basedpyright通过。独立复核重算234臂，并检查180个原规则重放、7020个唯一预算和5400个未测指标扰动案例。`[verified: system-variants-verification.json cpu_tests、new_unit_tests、ruff、basedpyright、independent_readonly_review]`
- 首版费用把原搜索路由计为归档候选和，已用原search_ms修正并重跑小样本与全量；首版17份代码／配置／结果文件的SHA归档保留。此前训练集推理诊断在切换到本次范围时中止，原记录保留。`[verified: system-variants-verification.json cost_correction、preceding_development_fit_diagnostic]`
