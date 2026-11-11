# 固定容量的学习率对照

首批回归与BN诊断结束后，启动随机初始化学习率单项对照。正式配置与原V1 scratch相比只将lr从1e-3改为3e-4，输出身份另建；数据、seed、ResNet-18、标准stem、单调输出、EMA0.999、batch128、AdamW/WD0.05、warmup1、最多30轮、RMSE patience5均保持。配置见[scratch-lr0003-suite.json](scratch-lr0003-suite.json)，启动时逐字段核对仅learning_rate变化。`[verified: 两份suite config；启动字段差异检查输出learning_rate]`

这项实验检验较低学习率是否改善随机初始化配方的泛化及阈值误差，也补齐与预训练lr3e-4相同超参数的初始化比较；不预设能达到90%。仍只使用GDC train10000／validation1000，CUDA串行，未打开test。`[opinion: 单项假设；verified: suite scope、PatchTrainer.fit]`

先在48训练图／16验证图上完成[两轮小样本检查](scratch-lr0003-smoke-summary.json)，最佳权重重载通过。该检查完整遍历小语料，每轮2步、共4次更新；建配置时可选max_steps字段赋值未生效，最终显式采用epochs=2及小语料限制，实际配置保留在[smoke suite](scratch-lr0003-smoke-suite.json)，不将该小样本指标用于效果判断。`[verified: scratch-lr0003-smoke.json history、config；smoke-summary.json；配置生成工具输出；opinion: 证据范围]`

正式训练完成12轮，按阈值附近RMSE早停，选中第7轮raw权重；[训练汇总](scratch-lr0003-summary.json)与[最佳权重重载](scratch-lr0003-audit.json)均通过。学习参数11,178,564个、FP32参数字节44,714,256不变。训练墙钟2483.18秒，包含重载审计的完整进程2516.98秒。日志和检查点保存在.local的同名目录。`[verified: scratch-lr0003-result.json selected_epoch、completed_epochs、parameters、training_wall_seconds；scratch-lr0003-summary.json；.local对应jobs/scratch-lr0003/receipt.json]`

| 固定容量随机初始化配方 | 验证Top-1 | balanced accuracy | 阈值附近RMSE | 10×10召回 |
|---|---|---|---|---|
| lr0.001，原V1 | 76.0% | 69.54% | 1.7681dB | 59.38%。`[verified: ../patch-v1/scratch-result.json metrics]` |
| lr0.0003，本轮 | 80.7% | 74.50% | 1.6040dB | 54.69%。`[verified: scratch-lr0003-result.json metrics]` |

总准确率提高4.7个百分点，但10×10召回下降4.69个百分点，不能据此判断中间类别问题已经解决。新配方6×6／8×8／12×12召回为84.86%／66.67%／91.77%。零余量质量达标率84.6%，payload92,273,392字节；0.5dB余量使质量达标率升到88.4%，同时准确率降到78.9%、payload增到98,643,440字节。V1联合条件和Unity独立90%验收仍未达到。`[verified: scratch-lr0003-result.json metrics、accuracy_change_pp、recall_change_pp、v1_development_gate_passed；opinion: 结论边界]`

![固定参数量的随机初始化学习率对照](scratch-lr-comparison.png)

[完整结果与输入哈希](scratch-lr0003-result.json)由已保存的历史和最佳权重审计生成，没有重新推理或读取test。图中是同一开发validation1000的单seed对照，原配方训练14轮，本轮12轮；两者均按原定patience5停止。`[verified: scratch-lr0003-result.json scope、inputs_sha256、curves；两个训练报告stop_reason；opinion: 单次实验边界]`

后续保留两条独立身份：末轮raw／EMA的训练集BN统计量重估，以及只将remove_maxpool设为true的输入stem对照。后一组沿用lr0.0003、batch128和所有正式设置，[小样本配置](scratch-stem2-lr0003-smoke-suite.json)先检查CUDA更新及权重重载，[正式配置](scratch-stem2-lr0003-suite.json)在该检查通过后启动；移除无参数pool不改变参数数量，计算和显存成本另测。`[verified: 两份stem suite配置；ASTCPatchRegressor.__init__；opinion: 实验顺序与假设]`

上述后处理已完成，epoch12 EMA经训练集BN重估为80.9%／1.3716dB，四种变体详见[诊断报告](../normalization.md#后续随机初始化lr00003的末轮诊断)。去maxpool的[两轮CUDA检查](scratch-stem2-lr0003-smoke-summary.json)及重载通过，峰值分配显存4,677,542,400字节，进程23.27秒。正式队列随后启动，状态见[stem训练汇总](scratch-stem2-lr0003-summary.json)；启动前逐字段确认只改变remove_maxpool，空闲RAM26.79GiB、GPU占用1234MiB／12282MiB。尚无正式结果时不把小样本准确率用作收益判断。`[verified: normalization-scratch-lr0003.json；scratch-stem2-lr0003-smoke.json；.local对应jobs/scratch-stem2-lr0003-smoke/receipt.json、jobs/scratch-stem2-lr0003/preflight.json；opinion: 结果边界]`
