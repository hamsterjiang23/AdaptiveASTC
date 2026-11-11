# 尺寸元数据的原尺寸 patch 回归对照

尺寸元数据对照完成27轮CUDA训练，选中epoch27 raw，验证Top-1为84.2%、同一权重近阈值RMSE1.5334dB；比原cap512低0.3个百分点，8×8／10×10召回分别下降2.60／7.81个百分点。新增16参数，总11,178,580，完整进程6244.32秒；本次保留原84.5%模型作为scratch对照。这是GDC开发集单次对照，完整Unity独立测试尚未完成。`[verified: scratch-group512-metadata-result.json metrics、recall_change_pp、process_seconds；opinion: 选模与解释范围]`

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

运行期间绑定的12份训练源码保持，原15份执行源码归档于`experiment report/.local/unity-accuracy90-20261111/pre-size-metadata-training-source`。训练器6206.63秒、完整进程6244.32秒，与Unity参考采集和候选补测并行；开发训练成本不作为部署性能。`[verified: scratch-group512-metadata-result.json training_wall_seconds、process_seconds；metadata-integration.json prior_execution_source_archive；opinion: 计时范围]`
## 完整验证结果

[终态结果](scratch-group512-metadata-result.json)与最佳权重重载绑定。选中权重的逐类召回为6×6 87.16%、8×8 70.31%、10×10 63.28%、12×12 94.37%；balanced accuracy为78.78%。其质量通过率86.4%、payload为90,951,984字节。最小训练期RMSE1.4847dB属于其他检查点，不能与84.2%拼成同一模型的结果；本次联合晋级条件未通过。`[verified: scratch-group512-metadata-result.json metrics、minimum_rmse_across_training、metric_pair_scope、v1_development_gate_passed]`

原cap512仍作为scratch准确率基准。此次仅检验一个seed、当前16参数线性尺寸修正与现有配方，不能推断尺寸信息对所有结构都无用；后续优先完成原生Unity数据和训练。`[opinion]`
