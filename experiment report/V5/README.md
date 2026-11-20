# V5 ASTC 小块质量预测与可见台阶筛查实验报告

## 实验结论

2026-11-20，V5 完成 10,000 张训练图、1,000 张开发验证图的两阶段训练，以及 1,000 张新资产的独立机器评价和人工盲评。联合微调第 2 轮和 `8×8 fastest` 的 **28 dB／10%** 筛查规则在独立确认前冻结。 `[verified: full-label-verification.json counts；full-development-result.json best_epoch；confirmation-frozen-protocol-v1.json screening_rule、screening_candidate；confirmation-human-v1.json status、human_ratings]` [实验计划](<../../experiment plan/V5/README.md>) · [执行明细](../unity-v5-20261119/README.md)

**V5 对实测 PSNR 筛查规则的精确率为 97.5%，对人工可见台阶的精确率为 56.7%、召回率为 35.8%。** 两组数字分别以实测规则和人工标签为参照。使用实测 PSNR 套同一门槛，人工台阶召回率也只有 47.4%。冻结规则在这批新资产上对可见台阶覆盖有限。 `[verified: confirmation-evaluation-v1.json screening_all；confirmation-human-v1.json all_inputs]` [机器评价](../unity-v5-20261119/confirmation-evaluation-v1.json) · [人工评价](../unity-v5-20261119/confirmation-human-v1.json)

独立确认的原生选参对照中，V5 的块大小匹配率从 V3 的 98.4% 提升到 99.1%，严格质量通过率从 86.2% 降到 86.0%，有 2 张从通过变为未通过。开发集通过的联合微调回归门槛在独立确认上出现了严格质量回退。 `[verified: full-development-result.json joint_epochs；confirmation-evaluation-v1.json native_policy、native_strict_regressions_from_v3]`

## 研究问题和方法

V5 将 V3 的逐候选质量预测扩到图内小块。对一张 Unity 导入后的参考图和实际导入属性，模型输出每个固定 **8×8 像素分析小块**的 20 个候选误差。压缩候选由 **12×12、10×10、8×8、6×6** 四种编码块大小与 **fastest、fast、medium、thorough、exhaustive** 五种预设组成。相同的分析网格用来比较所有压缩候选。 `[verified: confirmation-frozen-protocol-v1.json analysis_grid、canonical_candidates；unity_dense_tile.py forward；predict_unity_dense_tiles.py main]` [模型实现](../../src/adaptive_astc/models/unity_dense_tile.py) · [单图推理](../../script/predict_unity_dense_tiles.py)

模型使用 240×240 输入 patch，从 ResNet-34 提取 30×30 浅层特征和 8×8 深层特征。深层特征经导入属性调制并上采样，与浅层特征拼接后由 1×1 卷积输出误差。每个分析小块在每个候选上有 5 个归一化对数 MSE 输出，分别对应原生 RGBA 四通道和显示 RGB 合成误差。分析网格锚定在原图底行，边缘小块用实际像素计分。 `[verified: unity_dense_tile.py L12–L72；unity_tile_errors.py UnityTileGrid；unity_dense_tile_inference.py screen]` [网格和视图实现](../../src/adaptive_astc/data/unity_tile_errors.py)

显示视图把启用的 Alpha 在线性光下合成到灰色背景，再转回显示 RGB。冻结规则取候选 `8×8 fastest`，在内容小块中计算 **PSNR 严格低于 28 dB** 的比例，比例 **至少 10%** 时筛中。内容小块按参考图块内 RGB 值的最大值与最小值之差至少为 2 定义。阈值在预测误差转成 PSNR 后施加。 `[verified: confirmation-frozen-protocol-v1.json screening_rule、screening_candidate；unity_tile_errors.py UnityTileViews.display；unity_dense_tile_inference.py L100–L109；evaluate_unity_v5_confirmation.py exact_count]` [冻结协议](../unity-v5-20261119/confirmation-frozen-protocol-v1.json)

## 训练和开发集结果

32 张验证图上的 640 份候选解码图通过方向、网格和逐通道 SSE 核验。全量标签覆盖 11,000 张开发图、220,000 个图像与候选组合及 41,572,480 个原图网格小块，档案约 16.76 GB。每个小块保存有效像素数、内容和平滑掩膜，以及全部候选的原生 RGBA 与显示 RGB 精确误差。 `[verified: 本地 label-audit32.json images、candidate_decodes、native_channel_sse_exact；full-label-verification.json counts、candidate_images、tiles、bytes；unity_tile_corpus.py L91–L104、L151–L160]` [全量语料核验](../unity-v5-20261119/full-label-verification.json)

在 560 张原生整图 PSNR≥35 dB 的 sRGB 开发图中，`8×8 fastest` 的显示视图平滑区有 0.060% 的小块低于 28 dB，其余内容区有 1.83%。35,112 个坏块中有 92 个位于平滑区。该诊断提示，基于坏块的筛查会受到其他图像区域的误差影响。 `[verified: progress.json historical_gradient_pool；V5 执行明细“560 张原生 PSNR≥35 dB”]` `[opinion]`

在 512 张训练图、198 张 128×128 验证图的原型上，45 dB 单侧截断使 `8×8 fastest` 的 28／30 dB 门槛附近小块 PSNR RMSE 由 **17.80／17.45 dB** 降至 **7.85／6.90 dB**，全候选显示对数 MSE RMSE 由 **2.57** 升至 **3.27**。全量训练使用截断目标。 `[verified: prototype128.json counts、variants、choice_for_full_frozen_stage]` [原型对照](../unity-v5-20261119/prototype128.json)

冻结阶段训练 5 轮、21,075 次更新，选中第 1 轮。联合阶段训练 3 轮、25,290 次更新，选中第 2 轮。下表的误差是显示视图下，跨开发图和 20 个候选的内容坏块占比 MAE，再对 28 和 30 dB 两个门槛取平均。 `[verified: unity_dense_tile_metrics.py L114–L122；unity_dense_tile_trainer.py L98–L106；full-frozen-result.json best_epoch、epochs、training_updates、selection_metric、per_epoch；full-development-result.json best_epoch、joint_training_updates、joint_epochs]` [冻结训练](../unity-v5-20261119/full-frozen-result.json) · [联合训练](../unity-v5-20261119/full-development-result.json)

| 开发验证对照 | 块大小匹配率 | 严格质量通过率 | 坏块占比 MAE | 选模结果 |
|---|---:|---:|---:|---|
| 冻结模型／V3 原生基线 | 93.6% | 87.5% | 4.48 个百分点 | 冻结第 1 轮 `[verified: full-frozen-result.json per_epoch；progress.json joint_full_training.initial_v3_parity]` |
| 联合第 1 轮 | 91.2% | 87.7% | 4.38 个百分点 | 未通过开发回归门槛 `[verified: full-development-result.json joint_epochs[0]]` |
| **联合第 2 轮** | **94.2%** | **87.7%** | **4.08 个百分点** | 通过并入选，严格质量回退 0 张 `[verified: full-development-result.json joint_epochs[1]、best_epoch]` |
| 联合第 3 轮 | 90.8% | 87.8% | 3.81 个百分点 | 未通过开发回归门槛 `[verified: full-development-result.json joint_epochs[2]]` |

开发人工评价在按资产组拆开的两个人工子集内，对五种排序的 Top-20 取并集。用 71 组校准图确定规则。在 64 组留出图中，V5 按冻结规则命中 36 张台阶图，精确率为 **36/37（97.3%）**、召回率为 **36/54（66.7%）**。V5 和实测 PSNR 排序的 Top-20 均为 20/20。这里的样本范围是排序后的候选并集，独立确认对整个新名单逐图盲评。 `[verified: human-review-result.json scope、calibration、holdout.threshold、holdout.top20；confirmation-human-v1.json human_ratings]` [开发人工评价](../unity-v5-20261119/human-review-result.json)

在 936 张含内容小块的 sRGB 开发验证图上，按 30 dB／5% 规则，切换到 `6×6 fastest` 实测有 315 张从不合格变为合格，联合模型命中其中 209 张。这组对照衡量候选间的小块 PSNR 变化。 `[verified: exact-candidate-controls.json comparisons.content@30；full-development-result.json model_metrics 中 6x6_upgrade_30db_x5_percent]` [候选对照](../unity-v5-20261119/exact-candidate-controls.json)

## 独立确认协议和执行

冻结协议绑定模型权重、筛查规则、开发盲评和确认名单。原主名单的 1 张 GUI 和 1 张 Cube 按批准的备用顺序原位替换。首次像素隔离审计再检出 1 张全 RGBA 精确重复和 5 张同尺寸对齐近重复。经授权按冻结备用顺序替换这 6 张，复用其余 994 张归档。完整复审对照 11,000 张开发图，确认图 1,000 张，跨集精确重复和同尺寸对齐近重复均为 **0**。近重复按 8 位 RGBA RMSE≤2 判定。 `[verified: 本地 confirmation-execution-preflight-v1.json、confirmation-pixel-isolation-v1.json、confirmation-pixel-revision-preflight-v2.json；confirmation-complete-capture-v2.json；confirmation-pixel-isolation-v2.json counts、scope、exact_cross_cohort_groups、near_cross_cohort_groups]` [通过的复审](../unity-v5-20261119/confirmation-pixel-isolation-v2.json)

复审通过后执行冻结模型推理和 `8×8 fastest` 真实编码解码。原生选参对照同时运行 V3、V5 的预测起点和配对续搜，并以实际解码核验严格质量。整次机器评价耗时 2,351.23 秒，实际编码调用 2,658 次，包含固定候选对照与两套原生选参测量，共 0 次训练更新。 `[verified: confirmation-evaluation-v1.json wall_seconds、native_encoding_calls、training_updates、seal；evaluate_unity_v5_confirmation.py score]` [正式执行回执](../unity-v5-20261119/confirmation-execution-v2.json)

## 独立确认结果

**和实测 PSNR 规则比。** 在 996 张含内容小块的图上，V5 筛中 120 张，实测筛中 172 张，二者重合 117 张。V5 对实测规则的精确率为 **117/120（97.5%）**，召回率为 **117/172（68.0%）**，逐图坏块占比 MAE 为 **2.23 个百分点**。另外 4 张没有内容小块。 `[verified: confirmation-evaluation-v1.json screening_all]` [机器结果明细](../unity-v5-20261119/confirmation-evaluation-v1.json)

**和人工可见台阶比。** 全部 1,000 张均已人工看过，190 张有台阶、809 张无台阶、1 张不确定。指标在明确标注的 999 张上计算，4 张没有内容小块的图均标为无台阶。190 张正例图册随贴图资源保存在本地。 `[verified: confirmation-human-v1.json all_inputs、human_ratings、ratings_snapshot；冻结评分和逐图记录复算；verification.json 本地图册核验]` [人工结果明细](../unity-v5-20261119/confirmation-human-v1.json)

| 同一冻结规则的输入 | 筛中 | 命中人工有台阶 | 误筛 | 漏筛 | 精确率 | 召回率 |
|---|---:|---:|---:|---:|---:|---:|
| V5 预测小块 PSNR | 120 | 68 | 52 | 122 | **56.7%** | **35.8%** `[verified: confirmation-human-v1.json all_inputs.threshold_metrics_with_abstentions_unflagged.v5]` |
| 实测小块 PSNR | 172 | 90 | 82 | 100 | **52.3%** | **47.4%** `[verified: confirmation-human-v1.json all_inputs.threshold_metrics_with_abstentions_unflagged.exact_tiles]` |

991 张 sRGB 彩色图子集上，V5 相对人工标签的精确率为 57.1%、召回率为 36.0%，实测 PSNR 同规则分别为 52.6% 和 47.6%。全量盲评和彩色子集得出相近的覆盖结果。 `[verified: confirmation-human-v1.json srgb_color_inputs、all_inputs]`

| 原生选参独立确认 | 与 Unity 原标签的块大小匹配 | 最终输出严格质量通过 |
|---|---:|---:|
| V3 | 984/1,000（98.4%） | 862/1,000（86.2%） `[verified: confirmation-evaluation-v1.json native_policy.v3]` |
| V5 联合第 2 轮 | 991/1,000（99.1%） | 860/1,000（86.0%） `[verified: confirmation-evaluation-v1.json native_policy.v5]` |

## 正式评价后的筛查诊断

以下门槛用已经标完的确认集回算。90% 召回对应至少覆盖 190 张正例中的 171 张。28 dB 下，52 张正例没有任何预测坏块，取任意非零坏块也只找回 138 张。同一组显示对照图重新计算实测坏块占比时，即使把门槛提高到 41 dB，在达到九成召回的操作点仍需保留 730 张。 `[verified: screening-diagnostic.json predicted_at_28_db、measured_psnr_at_90_recall]` [事后诊断证据](screening-diagnostic.json)

| 事后筛法 | 候选数 | 命中人工正例 | 召回率 |
|---|---:|---:|---:|
| V5 预测，28 dB／5% | 253 | 94 | 49.5% `[verified: screening-diagnostic.json predicted_at_28_db]` |
| V5 预测，28 dB 下至少一个坏块 | 829 | 138 | 72.6% `[verified: screening-diagnostic.json predicted_at_28_db]` |
| 实测 PSNR，41 dB／26.5625% | 730 | 172 | 90.5% `[verified: screening-diagnostic.json measured_psnr_at_90_recall]` |
| 原图最大连通主色区占比 ≥12.1% | 673 | 171 | 90.0% `[verified: screening-diagnostic.json reference_only_at_90_recall]` |
| 原图结合连续渐变、主色区和色彩边界排序 | 613 | 171 | 90.0% `[verified: screening-diagnostic.json reference_only_at_90_recall]` |

最大连通主色区占比的中位数在人工标为有台阶的图中为 51.3%，在无台阶图中为 15.1%。原图规则把大片近似同色背景作为结构线索，组合还考虑平滑区域的连续性、颜色跨度和相邻像素的强边界。它们可以用于初筛，PSNR 预测可提供压缩误差信号。原图筛查的 90% 是同一批数据上选出的操作点，新数据上的召回率需要另行验证。 `[verified: screening-diagnostic.json reference_only_at_90_recall、feature_definitions]` `[opinion]`

## 产物和结项

V5 已完成冻结协议规定的独立人工确认。当前交付包括可直接从 Unity 参考图推理的稠密头、冻结的正式规则、隔离审计、逐图机器评价、独立人工评分和 190 张正例图册。独立确认结果记录了两项边界，固定 PSNR 门槛的可见台阶召回有限，联合微调在独立集发生 2 张严格质量回退。 `[verified: progress.json status、formal_confirmation_execution；confirmation-evaluation-v1.json；confirmation-human-v1.json]` [当前状态](../unity-v5-20261119/progress.json) · [报告核验](verification.json)
