# 同图 patch 成组采样与聚合损失

同图成组采样与有效像素加权MSE损失已接入训练器，两组CUDA小样本检查及最佳权重重载通过，正式成对训练已串行启动。资产组cap512训练先结束并归档其原始源码，再修改训练器；旧检查点与结果保持原身份。正式进度见[训练汇总](scratch-bag4-summary.json)，当前不能据小样本检查声明准确率收益。`[verified: scratch-bag4-smoke-summary.json；scratch-bag4-summary.json；jobs/scratch-group512/receipt.json；pre-bag-training-source归档；opinion: 结果边界]`

接入后默认bag_size=1、aggregate_loss_weight=0保持旧抽样序列与损失；bag_size=4采用同图成组DataLoader，按返回的patch索引读取有效像素数和图身份。历史日志新增局部／聚合损失分项，配置记录采样、目标范围和loss源码SHA。集成检查覆盖成对采样完全一致、像素索引映射、有限梯度、非法配置与完整组预算。`[verified: patch_trainer.py training_batches、fit；test_patch_training_bags.py；opinion: 记录要求]`

小语料两组均使用48训练图／16验证图，各2轮、4次实际更新，参数11,178,564不变，峰值分配显存约2.12GB；完整suite29.52秒。权重0的聚合分项为0，权重1的两轮聚合损失分别0.10687／0.09386，输出有限、权重重载一致；只证明执行链路可用。`[verified: scratch-bag4-smoke-loss0.json、scratch-bag4-smoke-loss1.json history、peak_vram_bytes；scratch-bag4-smoke-summary.json；opinion: 小样本检查范围]`

## 假设与对照

现有训练对各 patch 的 log-MSE 单独计算 Huber，验证时先按实际像素数平均 MSE，再转成整图 PSNR。新增损失检验在同图几个 patch 上直接约束聚合 MSE 是否改善最终决策；它不增加网络参数，不预设改善幅度。`[verified: patch_trainer.py fit；patch_dataset.py aggregate；patch_loss.py forward；opinion: 实验假设]`

| 对照 | 采样 | 训练损失 |
|---|---|---|
| 历史标准采样 | 每张图期望权重相同，各 patch 独立抽取 | 原逐 patch Huber；已完成验证80.7%。`[verified: scratch-lr0003-result.json；patch_trainer.py fit]` |
| 同图成组、权重0 | 每组4个同图 patch，图与组内 patch 均有放回抽取 | 保留原逐 patch 损失，隔离采样变化。`[verified: scratch-bag4-suite.json trials[0]；patch_bags.py __iter__；opinion: 对照用途]` |
| 同图成组、权重1 | 与上一行相同的seed、采样与总patch预算 | 原损失加聚合损失，隔离新增损失项。`[verified: scratch-bag4-suite.json trials[1]；patch_loss.py forward；opinion: 对照用途]` |

两组保留 ResNet-18、随机初始化、标准 stem、单调输出、lr0.0003、AdamW／weight decay0.05、EMA0.999、batch128、每轮40000次patch抽样、最多30轮和近阈值RMSE patience5。组权重恢复cap0；两组之间只有聚合损失权重变化，输出身份分别保存。比较历史标准采样时必须同时说明训练输入的相关性和每轮覆盖变化。`[verified: scratch-bag4-suite.json trials；scratch-lr0003-suite.json；opinion: 比较边界]`

## 聚合口径与实际抽样

每组以有效像素数加权平均预测 MSE 和真实 MSE，然后取 log10 并计算同样的阈值加权 Huber。预测采用与现有推理相同的log-MSE截断[-10,0]及epsilon1e-10；用logsumexp完成计算。目标仅描述实际抽到的patch，多次抽到同一patch也按实际次数进入该组，不能称为完整整图监督。`[verified: patch_loss.py aggregate_log_mse、forward；patch_dataset.py aggregate；opinion: 监督范围]`

训练集10000图、40000次patch抽样组成10000组，共313个batch，最后一批64个patch；该seed实际覆盖6336张不同图、19254个不同patch。3718张训练图只有一个patch，7276组包含重复patch。与原方法的期望图权重一致不代表每轮覆盖或batch内独立样本数一致，权重0对照用于检验这部分影响。`[verified: bag-sampling-analysis.json images、patch_draws、bag_draws、batch_count、last_batch_patches、distinct_images_this_epoch、distinct_patches_this_epoch、single_patch_images、within_bag_repeated_index_bags；opinion: 对照解释]`

在所有10000组上，用整数SSE导出的真实MSE直接重算与新聚合函数比较，最大log10(MSE+epsilon)差为1.26e-6以内。完整训练语料读取与这次核验合计81.95秒，没有运行新模型。`[verified: bag-sampling-analysis.json max_log_mse_aggregation_error、wall_seconds、scope]`

## 现有错误并非只有聚合问题

对冻结的最佳权重预测按验证图实际patch数量分组，不拟合校准参数、不重新训练、不访问test。结果见[分组诊断](patch-coverage-diagnosis.json)。随机初始化使用lr0.0003的epoch7 raw；预训练使用原V1 epoch9 raw。`[verified: patch-coverage-diagnosis.json groups、scope、test_opened]`

| 每图patch数 | 验证图数 | 随机初始化准确率／近阈值RMSE | 预训练准确率／近阈值RMSE |
|---|---:|---|---|
| 1 | 246 | 79.27%／2.5102dB | 89.02%／1.4837dB。`[verified: patch-coverage-diagnosis.json groups.*.strata.one_patch]` |
| 2–4 | 184 | 77.17%／1.7086dB | 80.43%／1.0843dB。`[verified: patch-coverage-diagnosis.json groups.*.strata.two_to_four]` |
| 5–16 | 265 | 81.13%／1.0600dB | 91.32%／0.6601dB。`[verified: patch-coverage-diagnosis.json groups.*.strata.five_to_sixteen]` |
| >16 | 305 | 83.61%／1.0873dB | 91.48%／0.6574dB。`[verified: patch-coverage-diagnosis.json groups.*.strata.over_sixteen]` |

单patch图也存在明显误差，聚合损失不能预期解决全部差距。后续按上述分组报告对照结果，再决定有效区域／元数据输入或其他结构实验；当前仍不扩大ResNet容量。`[verified: patch-coverage-diagnosis.json groups；opinion: 后续判断]`

## 检查与运行门槛

14项组件检查覆盖同图身份、预算／seed、组权重、边缘像素、无损／截断、有限梯度和关闭新增损失时的旧损失／梯度逐项一致；连同已有组采样检查共23项通过。独立审查没有发现问题。CPU数学检查不代表CUDA训练已经运行。`[verified: test_patch_bags.py；test_patch_sampling.py；本轮pytest 23 passed、14 passed；review回执；opinion: 检查边界]`

准备配置为[两轮小样本](scratch-bag4-smoke-suite.json)与[正式成对对照](scratch-bag4-suite.json)。小样本使用原48训练图／16验证图，先检查CUDA更新、保存预测与最佳权重重载；正式实验只用GDC train10000／validation1000，Unity生产训练和独立测试另行验收。`[verified: 两份suite trials.config、scope；opinion: 启动与验收门槛]`
