# 尺寸元数据的原尺寸 patch 回归对照

已完成尺寸特征与模型组件检查：在原ResNet-18回归器上增加16个参数，总参数11,178,580；12项CPU检查及完整train10000／validation1000几何核验通过。组件尚未接入训练器或进行CUDA训练，当前没有准确率收益结论。原组均衡模型84.5%仍保留为随机初始化对照基准。`[verified: metadata-contract.json；metadata-data-audit.json；scratch-group512-result.json metrics.accuracy；opinion: 对照与完成边界]`

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
- 后续接入训练、raw／EMA验证、最佳权重重载和BN重估时，必须统一提供四项尺寸特征，并记录有效配置、权重结构及额外推理成本；先通过CUDA小样本再启动完整对照。`[opinion: 后续实施要求]`
