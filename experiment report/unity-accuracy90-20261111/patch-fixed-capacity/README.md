# 固定容量的学习率对照

首批回归与BN诊断结束后，启动随机初始化学习率单项对照。正式配置与原V1 scratch相比只将lr从1e-3改为3e-4，输出身份另建；数据、seed、ResNet-18、标准stem、单调输出、EMA0.999、batch128、AdamW/WD0.05、warmup1、最多30轮、RMSE patience5均保持。配置见[scratch-lr0003-suite.json](scratch-lr0003-suite.json)，启动时逐字段核对仅learning_rate变化。`[verified: 两份suite config；启动字段差异检查输出learning_rate]`

这项实验检验较低学习率是否改善随机初始化配方的泛化及阈值误差，也补齐与预训练lr3e-4相同超参数的初始化比较；不预设能达到90%。仍只使用GDC train10000／validation1000，CUDA串行，未打开test。`[opinion: 单项假设；verified: suite scope、PatchTrainer.fit]`

先在48训练图／16验证图上完成[两轮小样本检查](scratch-lr0003-smoke-summary.json)，最佳权重重载通过。该检查完整遍历小语料，每轮2步、共4次更新；建配置时可选max_steps字段赋值未生效，最终显式采用epochs=2及小语料限制，实际配置保留在[smoke suite](scratch-lr0003-smoke-suite.json)，不将该小样本指标用于效果判断。`[verified: scratch-lr0003-smoke.json history、config；smoke-summary.json；配置生成工具输出；opinion: 证据范围]`

正式训练状态见[scratch-lr0003-summary.json](scratch-lr0003-summary.json)。每轮与最终报告由现有训练入口写入，完成后自动进行最佳权重重载核验。日志和检查点保存在.local的同名目录；后续BN重估另立实验身份，不覆盖原训练选择结果。`[verified: PatchExperimentSuite.run；scratch-lr0003-suite.json；opinion: 后续记录]`

第7轮阶段记录：验证Top-1为80.7%，阈值附近RMSE为1.6040dB；此前原scratch配方最佳为76.0%／1.7681dB。当前状态仍是running，最终早停、权重重载和完整成本尚未产生。逐轮记录见[scratch-lr0003.json](scratch-lr0003.json)，不能把阶段提升当作Unity独立验收。`[verified: scratch-lr0003.json history[6]、status；../patch-v1/scratch-result.json；opinion: 完成边界]`
