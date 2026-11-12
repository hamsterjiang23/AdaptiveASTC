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

CUDA预检和完整规则诊断已完成，完整原生基线已启动，使用单GPU串行调度。后续状态与结果写入[本轮进度](progress.json)。`[verified: r0-smoke-retry.json status；rules.json status；r0.json status；progress.json training_started]`

全量训练的首轮启动快照为验证Top-1 63.0%、近阈值RMSE 3.4667dB，实际624次更新、1次AMP跳步；训练47.43秒、验证11.67秒，首次数据准备170.30秒。这是训练过程记录，后续最佳权重仍按完整验证和重载审计确定。`[verified: r0.json history中epoch1、preparation_seconds；opinion: 过程与最终选模范围]`
