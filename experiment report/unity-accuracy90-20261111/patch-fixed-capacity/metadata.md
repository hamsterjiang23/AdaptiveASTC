# 尺寸元数据的原尺寸 patch 回归对照

尺寸元数据已接入训练、raw／EMA验证、最佳权重重载和BN重估。46项CPU检查、两轮4次更新的CUDA训练与重载、BN路径检查均通过；新增16个参数，总11,178,580。[完整对照](scratch-group512-metadata-suite.json)已启动，当前没有完整准确率结果；原组均衡模型84.5%仍作为随机初始化基准。`[verified: metadata-integration.json；scratch-group512-metadata-smoke-summary.json；normalization-metadata-smoke.json；scratch-group512-result.json metrics.accuracy；opinion: 对照与完成边界]`

## 输入与模型

| 特征 | 计算 | 来源 |
|---|---|---|
| 整图宽度 | log2(width)／12 | 当前patch所属参考图宽度。`[verified: PatchMetadata.encode]` |
| 整图高度 | log2(height)／12 | 当前patch所属参考图高度。`[verified: PatchMetadata.encode]` |
| patch有效宽度 | valid_width／240 | 边缘填充前的有效像素宽度。`[verified: PatchMetadata.encode；metadata-data-audit.json]` |
| patch有效高度 | valid_height／240 | 边缘填充前的有效像素高度。`[verified: PatchMetadata.encode；metadata-data-audit.json]` |

输入只使用尺寸，不使用候选PSNR、类别或实测压缩指标。除以12是固定尺度变换，4096像素对应1；大于4096时保留大于1的值，不做裁剪。这是V1元数据输入中的尺寸对照，尚未纳入Alpha、Unity用途或颜色空间分支。`[verified: patch_metadata.py encode；metadata-contract.json features_from；opinion: 实验范围]`

[MetadataPatchRegressor](../../../src/adaptive_astc/models/metadata_patch_regressor.py)在四个未约束输出上增加一个4×4线性修正，再执行原有单调变换。新增权重全零初始化，不消耗随机数，原骨干、原head和初始输出均保持一致；新增FP32参数占64字节。末端池化及输入RGB保持原模式，不合并此前的有效区域池化改动。`[verified: metadata_patch_regressor.py __init__/forward；metadata-contract.json；test_patch_metadata.py test_zero_metadata_correction_preserves_initial_model_and_rng；opinion: 单项对照范围]`

尺寸信息能否降低小图与边缘patch误差，需要实际训练检验。原cap512在单patch图上的误差较高只是分层相关性；有效区域池化已出现负结果，不能据此预先认定新增尺寸输入会改善泛化。`[verified: group512-geometry-diagnosis.json models.scratch_group512.strata.patch_count.one；scratch-group512-validpool-result.json；opinion: 假设与证据边界]`

## 已执行检查

- [组件记录](metadata-contract.json)：12项CPU检查覆盖尺寸合法性、原初始化及随机数状态保持、初始输出完全一致、16参数增量、梯度传播、单调性和形状拒绝；独立代码审查通过。`[verified: metadata-contract.json cpu_checks、review；test_patch_metadata.py]`
- [全量几何核验](metadata-data-audit.json)：读取冻结corpus与11000份目标文件，逐份核验SHA和patch边界，检查120276训练patch／12864验证patch的四项特征均有限；CPU耗时4.91秒。未运行预测或训练，未打开test。`[verified: metadata-data-audit.json splits、wall_seconds、test_opened、training_updates；audit_patch_metadata.py]`
- [训练接入](metadata-integration.json)：46项CPU检查覆盖raw／EMA中patch索引到原图尺寸的对应、历史默认输入路径、单项配置约束和权重重载；独立代码审查通过。训练、验证、重载及BN重估共用`PatchTrainer.model_inputs`，有效配置记录特征名及顺序。`[verified: metadata-integration.json checks；test_patch_training_metadata.py；patch_trainer.py model_inputs、fit、audit_best；patch_normalization.py run]`

## CUDA检查与完整对照

[小样本](scratch-group512-metadata-smoke.json)使用原48训练图／16验证图，asset group cap2、batch128，两轮4次实际更新，0次AMP跳步，全部16个新增权重均发生更新；最佳权重严格重载与保存预测一致，进程20.45秒、峰值分配显存2,118,428,672字节。后续[BN路径检查](../normalization-metadata-smoke.json)完成raw／EMA重估前后四种变体，使用训练patch、0次优化器更新，进程10.51秒。小样本只用于核验执行，不作准确率收益结论。`[verified: scratch-group512-metadata-smoke.json history、peak_vram_bytes；对应audit/summary；jobs/normalization-metadata-smoke/launch-preflight.json；normalization-metadata-smoke.json；metadata-integration.json；opinion: 验收范围]`

[完整配置](scratch-group512-metadata-suite.json)相对原cap512只启用`size_metadata`，保留scratch、标准stem、原池化、单调输出、lr0.0003、WD0.05、EMA0.999、batch128、每轮40000个patch、最多30轮及近阈值RMSE patience5。使用原冻结train10000／validation1000；维持原图内均匀采样，不混入此前两项负结果的改动。最终报告需比较同一选中权重的准确率、RMSE、质量、payload和完整成本。`[verified: scratch-group512-metadata-suite.json config、baseline；opinion: 比较要求]`

运行期间冻结绑定的12份训练源码，原15份执行源码已先行归档在`experiment report/.local/unity-accuracy90-20261111/pre-size-metadata-training-source`；旧权重与结果保持其原身份。启动前RAM空闲26.93GiB、GPU占用1172／12282MiB，单GPU训练，与Unity参考采集及候选补测并行。完整耗时待结束后记录，不把开发训练成本解释为部署性能。`[verified: metadata-integration.json source_files_sha256、prior_execution_source_archive；jobs/scratch-group512-metadata/launch-preflight.json；opinion: 运行与计时边界]`
