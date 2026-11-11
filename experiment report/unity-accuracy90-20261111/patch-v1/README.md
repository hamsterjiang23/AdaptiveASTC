# V1：原分辨率patch回归

正式CUDA队列已启动，先随机初始化，再预训练。结果更新在[汇总](summary.json)和各组同名报告，当前状态见[总进展](../progress.json)。尚无完成的正式回归结果。`[verified: jobs/patch-v1/receipt.json；summary.json]`

输入为240×240原分辨率patch，起点对齐120；边缘复制值仅用于模型输入，误差目标与整图聚合只按真实像素计量。训练10000图、验证1000图，共133140个可用patch；每轮按图等权期望抽4个patch，即40000训练样本，验证覆盖全部12864个patch。`[verified: ../patch-data-full.json；suite.json；NativePatchDataset.aggregate；PatchTrainer.fit]`

两组保留11,178,564参数的ResNet-18，标准stem、单调误差输出、AdamW、WD0.05、batch128、warmup1、EMA0.999，最多30轮，阈值附近RMSE patience5早停。scratch lr1e-3，pretrained lr3e-4，其他设置相同；这是两套V1训练配方对照。完整参数见[suite.json](suite.json)。`[verified: suite.json；../patch-v1-smoke.json config；opinion: 比较边界]`

损失为log10(MSE+1e-10)上的Huber，delta0.1对应1dB转折点，并增加阈值附近权重。输出单调结构约束MSE随块大小不减，整图先在MSE域按有效像素聚合，最后转换PSNR并应用35dB规则。报告保留原始与EMA结果、0–1dB余量、各类别／尺寸／资产组指标、真实候选payload和质量达标率。`[verified: PatchTrainer.fit；ASTCPatchRegressor.forward；PatchRegressionMetrics.compute]`

准确率最优与RMSE最优权重分别保存，两者可能不同。每组完成后重新加载准确率最优权重，在同一验证集重算所有预测，核对PSNR差异≤1e-5dB、标签顺序、准确率与SHA。选择的EMA／raw身份保存在checkpoint中。`[verified: PatchTrainer.audit_best；PatchExperimentSuite.run]`

## 已通过的启动检查

- [CUDA执行探针](../patch-v1-smoke.json)：48训练图／16验证图，两轮共6次更新，AMP跳步0，EMA更新6；batch128峰值显存2,118,429,184字节。小样本准确率仅验证执行，不能用于正式效果结论。`[verified: patch-v1-smoke.json history、peak_vram_bytes；opinion: 结论边界]`
- [权重重载核验](../patch-v1-smoke-audit.json)：选中epoch2的EMA权重，保存预测与重新计算结果一致。`[verified: patch-v1-smoke-audit.json status、selected_variant、selected_epoch]`
- [资源检查](preflight.json)：启动前GPU6%、显存1078／12282MiB、空闲RAM约39.7GB；单GPU任务，两名数据加载worker。正式耗时以实测轮次更新。`[verified: preflight.json]`

训练入口为`uv run --frozen python script/patch_regression.py suite --config <新的suite配置>`，复跑必须使用新的输出目录与summary，已有失败和完成工件保留。公开配置含本机绝对路径，换机时需根据冻结数据位置显式调整并生成新的实验身份。原始日志、权重和预测位于`experiment report/.local/unity-accuracy90-20261111/patch-v1/`及其jobs目录。`[verified: suite.json；PatchExperimentSuite.run；PatchTrainer.fit]`

本轮仅用GDC源RGB开发集；Unity的preset、MS-SSIM、法线和大图规则尚需单独迁移。test2000不参与选模，正式Unity独立90%验收未完成。`[verified: suite.json scope；V1“限制与待核实”]`
