# AdaptiveASTC V5 实验执行记录

[V5 实验报告](../V5/README.md)

32 张开发验证图的 640 份候选解码图已按 V5 的底对齐 8×8 网格复算。候选 PNG SHA、参考图的 Unity callback 方向、原选解码图方向与原生 RGBA 每通道 SSE 总和逐图检查通过。详细记录见[标签审计](label-audit32.json)及其中绑定的逐图产物。`[verified: label-audit32.json images、candidate_decodes、candidate_png_sha256_verified、native_pixel_orientation_verified、native_channel_sse_exact]`

| 已知案例（ASTC 8×8 fastest，显示视图） | 最低平滑小块 PSNR | PSNR < 28 dB 的小块 |
|---|---|---|
| 0615 白色渐隐弧 | 23.68 dB | 全图 15/256，平滑区 2/39。`[verified: label-audit32.json known_cases.615]` |
| 0616 蓝色光晕 | 34.22 dB | 全图 8/256，平滑区 0/75。`[verified: label-audit32.json known_cases.616]` |
| 0617 灰色环形光晕 | 24.61 dB | 全图 24/256，平滑区 18/52。`[verified: label-audit32.json known_cases.617]` |

0616 平滑区在 30 dB 门槛下同样是 0/75。显示视图最终由人工校准选中，并在留出组复核。`[verified: label-audit32.json known_cases.616.known_display_fastest.bad_tiles；human-review-result.json frozen_rule、holdout]`

560 张原生 PSNR≥35 dB 的 sRGB 图已独立重算。`8×8 fastest` 的平滑区坏块率为 0.06024%，其他内容小块为 1.82787%。35,112 个显示视图 PSNR<28 dB 的坏块中，92 个位于平滑区。全量标签按同一排序和掩膜重放，计数与归档 PNG 复算逐项一致。`[verified: full-label-verification.json label_oracle_parity；gradient-pool-exact560-v1.json counts]`

标签按原图网格保存有效像素数、内容及平滑掩膜、原生 RGBA 四通道及显示 RGB 的精确整数 SSE。完整语料已发布，覆盖 10,000 张训练图、1,000 张验证图、220,000 个图像候选和 41,572,480 个分析小块。所有逐图写回和输入身份核验通过，语料大小 16,764,643,440 字节，生成及回读耗时 6,534.57 秒。`[verified: full-label-verification.json counts、candidate_images、tiles、bytes、wall_seconds]`

## 冻结编码器原型

原型使用 512 张固定种子抽取的训练图和全部 198 张原生 128×128 验证图。原始对数 MSE 目标与 45 dB 单侧截断目标采用相同数据、种子和五轮预算。两组各完成 160 次更新，V3 参数与缓冲区保持一致，最佳权重严格重载通过。原始目标重复运行的最佳验证输出一致。`[verified: prototype128.json counts、variants、uncensored_repeat_validation_bit_identical、对应训练报告]`

| 显示视图，128×128 原型 | 原始对数 MSE | 45 dB 单侧截断 |
|---|---|---|
| `8×8 fastest` 28 dB 附近小块 PSNR RMSE | 17.80 dB | 7.85 dB `[verified: prototype128.json variants.*.thresholds.28]` |
| `8×8 fastest` 30 dB 附近小块 PSNR RMSE | 17.45 dB | 6.90 dB `[verified: prototype128.json variants.*.thresholds.30]` |
| `8×8 fastest` 内容坏块占比 MAE，30 dB | 12.45 个百分点 | 12.10 个百分点 `[verified: prototype128.json variants.*.thresholds.30]` |
| 全候选对数 MSE RMSE | 2.57 | 3.27 `[verified: prototype128.json variants.*.all_candidate_display_log_mse_rmse]` |

45 dB 单侧截断作为全量冻结训练的候选配置。它在 30 dB 的平均坏块占比仍明显偏低，预测 3.89%，真实 15.81%。阈值附近误差的改善与整体误差和排序表现分别记录。`[verified: prototype128.json variants.cap45.thresholds.30；opinion: 全量训练配置选择]`

全量步进对照已重算 938 张 sRGB 验证图，其中 554 张具备有效窗口。原生 PSNR≥35 dB 且步进有效的 361 张中，0615／0616／0617 分别排第 2／43／6，与历史运行一致。原型四路排序在 196 张匹配颜色图上比较，待人工复核渐变可见性。`[verified: prototype128.json step_baseline、variants.*.screening_images、human_recall]`

## 全量训练与回归验收

全量冻结训练完成五轮、21,075 次更新。按显示视图内容坏块占比在 28／30 dB 的平均 MAE 选中第一轮，误差为 4.48 个百分点。最佳检查点重载通过，V3 原生参数及缓冲区保持一致。第五轮的显示对数 MSE RMSE 为 2.39，第一轮为 2.52。`[verified: full-frozen-result.json per_epoch、best_epoch、checkpoint_reloaded、native_parameters_and_buffers_unchanged]`

选中的冻结模型在 8×8 fastest 的 30 dB 附近，预测 PSNR RMSE 为 3.68 dB。按 30 dB／5% 口径，切换至 6×6 fastest 实测使 315 张图落到门槛以下，模型命中其中 202 张。此次观测使用的验证产物 SHA 与重载后的冻结检查点一致。`[verified: full-frozen-epoch1-observation.json display、first_epoch_oracle_comparison；full-frozen-result.json validation]`

全量联合微调完成三轮、25,290 次更新及 7,500 个原生监督批次。第二轮满足 V3 回归门槛，最佳检查点重载通过。用导出的原生分支独立回放后，1,000 张图的选参轨迹和训练中该轮记录逐图一致。相对 V3，第二轮多获得 6 张块大小匹配和 2 张严格通过，新增严格质量回退为 0。`[verified: full-development-result.json joint_job、joint_epochs、joint_native_replay、joint_checkpoint_reloaded]`

| 轮次 | 块大小匹配 | 严格质量通过 | 28／30 dB 平均坏块占比 MAE | 回归门槛 |
|---|---|---|---|---|
| 冻结基线 | 93.6% | 87.5% | 4.48 个百分点 | 基线。`[verified: full-frozen-result.json per_epoch；joint-review-readiness.json native_parent_replay]` |
| 联合第 1 轮 | 91.2% | 87.7% | 4.38 个百分点 | 未通过。`[verified: full-development-result.json joint_epochs 第 1 轮]` |
| 联合第 2 轮 | 94.2% | 87.7% | 4.08 个百分点 | 通过并入选。`[verified: full-development-result.json joint_epochs 第 2 轮、best_epoch]` |
| 联合第 3 轮 | 90.8% | 87.8% | 3.81 个百分点 | 未通过。`[verified: full-development-result.json joint_epochs 第 3 轮]` |

## 人工筛查与独立确认

联合模型第二轮通过开发集数值比较。30 dB 下，在步进指标可用的 252 张留出分组图上，内容坏块占比 MAE 为 2.51 个百分点，步进分数单调映射对照为 7.82 个百分点。留出图用于评估步进映射与人工规则，稠密模型轮次选择使用全部开发验证图。全量评价同时报告 361 图历史步进口径与各方法 Top-20 重叠。`[verified: full-development-result.json model_metrics；unity_dense_tile_trainer.py fit；unity_dense_review_scoring.py step_baseline]`

正式盲评包已绑定联合模型，包含 71 组校准图、64 组留出图和 3 组已知示例，五路 Top-20 候选取并集后分别评审。71 组校准中 52 组有台阶、18 组无台阶、1 组不确定。按真实小块 PSNR 与校准评分的覆盖调整平衡准确率选规则，冻结为 `8×8 fastest` 在显示视图中，PSNR < 28 dB 的内容小块占比 ≥ 10%。`[verified: human-review-result.json calibration、frozen_rule、screening_candidate；calibration-human-v1.json selection_metric]`

留出 64 组中 54 组有台阶、10 组无台阶。沿用冻结阈值，V5 预测筛中 37 组，36 组确有台阶，精确率 97.3%、召回率 66.7%，有 18 组漏检。真实小块 PSNR 对照筛中 46 组，43 组确有台阶，精确率 93.5%、召回率 79.6%。`[verified: human-review-result.json holdout.threshold]` [人工复核与重算](human-review-result.json)

| 留出 Top-20 排序 | 人工确认有台阶 | 队列内精确率 |
|---|---:|---:|
| V5 稠密预测 | 20/20 | 100% `[verified: human-review-result.json holdout.top20.methods.dense]` |
| 真实小块 PSNR | 20/20 | 100% `[verified: human-review-result.json holdout.top20.methods.exact_tile_psnr]` |
| 原规则选中配置 | 18/20 | 90% `[verified: human-review-result.json holdout.top20.methods.fixed_rule_selected_exact_tiles]` |
| 亮度步进 | 14/20 | 70% `[verified: human-review-result.json holdout.top20.methods.l_p95_primary]` |
| 平滑区真实小块 PSNR | 18/20 | 90% `[verified: human-review-result.json holdout.top20.methods.exact_smooth_tile_psnr]` |

这些比例适用于五路 Top-20 取并集得到的开发留出样本。全库筛查的精确率和召回率仍需独立确认。`[verified: human-review-result.json scope、holdout；confirmation-frozen-protocol-v1.json planned_checks]`

[网页留出盲评](http://127.0.0.1:48765/)每次点击自动保存到 `development-evaluation-v1/holdout-ratings-web.csv`。正式留出计分使用提交时冻结的 `holdout-ratings-frozen-v1.csv`。留出页只在校准回执与盲评包、模型输出和评分快照一致时开放。`[verified: serve_unity_v5_review.py verify_calibration、main；progress.json human_review.frozen_holdout_ratings]`

盲评页可用 `＋`／`−` 或在图片上按住 `Ctrl` 滚动来同步缩放，拖动图片可同步平移。点击倍率恢复到原始尺寸。`[verified: unity_v5_review.html setZoom、pointermove]`

如果页面未收到保存确认，当前选择会暂存在原标签页中，可点「重试保存」。服务恢复后，在同一标签页刷新也能找回待提交的选择。`[verified: unity_v5_review.html storeDraft、restoreDraft、save]`

按 30 dB／5% 口径，切换至 6×6 fastest 实测使 315 张图的内容坏块占比降到门槛以下。冻结模型命中 202 张，联合模型命中 209 张，联合模型共预测 295 张会跨过门槛。该结果衡量 PSNR 筛查规则。`[verified: full-development-result.json model_metrics.*.6x6_upgrade_30db_x5_percent；exact-candidate-controls.json comparisons.content@30]`

[全量精确候选对照](exact-candidate-controls.json)覆盖 938 张 sRGB 验证图，逐候选比较三类区域和两档 Y。在 936 张含内容小块的图上，Y=30 dB 时，8×8 fastest／8×8 thorough／6×6 fastest 的平均坏块占比分别为 14.20%／10.56%／5.56%。8×8 fastest 下有 517 张达到 5% 门槛，切换到 8×8 thorough 或 6×6 fastest 后，分别有 102 张或 315 张落到门槛以下。原生规则选中配置的平均坏块占比为 15.69%，其中 642 张达到门槛。该对照衡量归档候选的真实小块 PSNR，人工可见性另行评审。`[verified: exact-candidate-controls.json comparisons.content@30；human_rating_count]`

## 参考图直接推理

独立入口 [predict_unity_dense_tiles.py](../../script/predict_unity_dense_tiles.py) 使用已重载的 V5 检查点、Unity 导入后参考 PNG 和实际导入属性。输出覆盖原图底对齐的 8×8 小块与全部 20 个候选，保存预测 PSNR、有效像素、区域掩膜及按 X／Y 计算的筛查结果。原型和小样本检查点各完成一张图的逐项对照。`[verified: input-only-inference-verification.json images；predict_unity_dense_tiles.py main]`

使用全量联合模型第二轮权重复核时，单张独立推理在 0616 和 0901 上分别与归档的 360／360 和 356／360 项计数一致。用相同的 CUDA 批大小 8 重放验证输入，两图均为 360／360。0901 有两个小块在批大小 1 与 8 之间越过 28 或 30 dB 门槛，分别位于 10×10 exhaustive 和 10×10 medium。两张图的 8×8 fast、8×8 fastest 计数均一致。`[verified: selected-joint-input-inference.json images.*.count_differences、tile_threshold_crossings]`

下面的命令使用入选联合模型评估一张 sRGB 不透明参考图。实际导入启用 Alpha 时加 `--need-alpha`。`[opinion: 调用示例；predict_unity_dense_tiles.py 参数定义]`

```powershell
uv run --no-sync python script/predict_unity_dense_tiles.py `
  --training-run "experiment report/.local/unity-v5-20261119/dense-joint-full-v1" `
  --reference "reference.png" --color-space srgb --y-db 28 30 --x-share 0.05 `
  --output "experiment report/.local/unity-v5-20261119/input-only-example"
```

## 确认集

新确认集原预留 1,000 张主名单、250 张备用，主名单覆盖 614 个资产组。[冻结协议](confirmation-frozen-protocol-v1.json)绑定稠密模型及原生选参权重、筛查规则、两份人工评分、源码和原始有序资产名单。`[verified: confirmation-source1000-reserve250-v1-verification.json；confirmation-frozen-protocol-v1.json]`

用户已授权正式运行，并批准将主名单中 1 张 GUI、1 张 Cube 用原备用顺序前两张合格图原位替换。修订后的 1,000 张均已完成 Unity 导入和归档。末批一张 16 位 PSD 的源 RGB 对照无法由 Pillow 读取，归档改用同次采集导出的 Unity 参考像素，并将该源 RGB 对照记为空值。恢复再次核验原生回调、归档及导入属性，Unity 重新导入次数为 0。`[verified: confirmation-execution-preflight-v1.json；unity-v5-confirmation1000-v1-from00770-recovered-v1.json；unity-v5-confirmation1000-v1-series-recovered-v1.json]` [完整采集回执](unity-v5-confirmation1000-v1-series-recovered-v1.json)

跨开发集的精确 RGBA 与同尺寸对齐 RGBA RMSE≤2 审计通过后，才会执行冻结模型评价。确认集的人工指标使用机器评价后生成的独立盲评包。`[verified: audit_unity_v5_confirmation_pixels.py main；evaluate_unity_v5_confirmation.py main]` [正式确认运行状态](confirmation-execution-recovered-v1.json) · [首次运行回执](confirmation-execution-v1.json)

本轮对 1,000 张确认图与 11,000 张开发图完成像素隔离审计。发现 1 组精确重复和 5 组同尺寸对齐近重复，共涉及 6 张确认图。六组逐像素复算与报告一致，五组近重复的 8 位 RGBA RMSE 为 0.0181–1.2937。隔离关口未通过，冻结模型的正式评价未开启。`[verified: confirmation-pixel-isolation-v1.json counts、exact_cross_cohort_groups、near_cross_cohort_groups、test_opened；confirmation-execution-recovered-v1.json]` [像素隔离报告](confirmation-pixel-isolation-v1.json)

用户批准将这 6 张按原顺序用备用名单原位替换。修订主名单仍为 1,000 张，锁定原主名单索引 229、255、272、394、592、947，使用原备用索引 2–7。复用 994 个已归档 Unity 输入，采集 6 张替补，随后用相同隔离规则复审全部 1,000 张。`[verified: confirmation-pixel-revision-preflight-v2.json approved_pixel_replacements、source_isolation；run_unity_v5_pixel_revision.py assemble、main]` [修订采集与复审状态](confirmation-execution-v2.json)

修订确认集的 1,000 张 Unity 输入已全部归档；对 11,000 张开发图重新复算后，跨集精确重复和同尺寸对齐近重复均为 0。正式评价由通过的复审回执触发，继续使用冻结权重和 28 dB／10% 规则。`[verified: confirmation-complete-capture-v2.json；confirmation-pixel-isolation-v2.json counts、exact_cross_cohort_groups、near_cross_cohort_groups；confirmation-execution-v2.json phase]` [像素隔离复审](confirmation-pixel-isolation-v2.json)

### 独立确认集正式机器评价

1,000 张均已完成冻结模型推理和真实编码对照。冻结规则为在 `8×8 fastest` 的显示视图中，PSNR 严格低于 28 dB 的内容小块占比至少为 10%。4 张没有内容小块，其余 996 张参与筛查统计。`[verified: confirmation-evaluation-v1.json images、seal、screening_rule、screening_all；evaluate_unity_v5_confirmation.py L137–L150]` [正式评价回执](confirmation-evaluation-v1.json)

| 确认范围 | 预测筛中 | 实测筛中 | 两者均筛中 | 相对实测的精确率 | 相对实测的召回率 | 坏块占比 MAE |
|---|---:|---:|---:|---:|---:|---:|
| 全部 1,000 张 | 120 | 172 | 117 | 97.5% | 68.0% | 2.23 个百分点 `[verified: confirmation-evaluation-v1.json screening_all]` |
| 991 张 sRGB 彩色图 | 119 | 171 | 116 | 97.5% | 67.8% | 2.24 个百分点 `[verified: confirmation-evaluation-v1.json screening_srgb_color]` |

原生选参块大小匹配率由 V3 的 98.4% 升至 V5 的 99.1%。严格质量通过率由 86.2% 降至 86.0%，确认图索引 22 和 713 从 V3 通过变为 V5 未通过。`[verified: confirmation-evaluation-v1.json native_policy、native_strict_regressions_from_v3]`

### 独立确认集人工可见台阶盲评

1,000 组全部完成标注，有台阶 190 组、无台阶 809 组、不确定 1 组。按冻结的 `8×8 fastest` 显示视图内容小块 28 dB／10% 规则计分，不确定项从指标分母排除，4 张没有内容小块的图均标为无台阶。盲评回执绑定评分 CSV 快照、机器评价和对照图清单的 SHA-256。`[verified: confirmation-human-v1.json all_inputs、human_ratings、ratings_snapshot；冻结评分 CSV；逐行复算]` [独立盲评回执](confirmation-human-v1.json)

| 筛查输入 | 筛中 | 命中人工有台阶 | 误筛 | 漏筛 | 精确率 | 召回率 |
|---|---:|---:|---:|---:|---:|---:|
| V5 预测小块 PSNR | 120 | 68 | 52 | 122 | 56.7% | 35.8% `[verified: confirmation-human-v1.json all_inputs.threshold_metrics_with_abstentions_unflagged.v5]` |
| 实测小块 PSNR | 172 | 90 | 82 | 100 | 52.3% | 47.4% `[verified: confirmation-human-v1.json all_inputs.threshold_metrics_with_abstentions_unflagged.exact_tiles]` |

991 张 sRGB 彩色图中，V5 精确率为 68/119（57.1%）、召回率为 68/189（36.0%），同规则实测 PSNR 分别为 90/171（52.6%）和 90/189（47.6%）。`[verified: confirmation-human-v1.json srgb_color_inputs]`

以实测 PSNR 规则为参照时，V5 的精确率为 97.5%、召回率为 68.0%。以人工可见台阶为参照时，同一条规则的召回在使用实测 PSNR 后仍为 47.4%，说明这条固定门槛对可见台阶的覆盖有限。`[verified: confirmation-evaluation-v1.json screening_all；confirmation-human-v1.json all_inputs]` `[opinion]`

[实验计划](<../../experiment plan/V5/README.md>) · [实现笔记](implementation-notes.md) · [原型对照](prototype128.json) · [全量标签核验](full-label-verification.json) · [冻结训练结果](full-frozen-result.json) · [全量开发集结果](full-development-result.json) · [标签入口](../../script/prepare_unity_tile_labels.py) · [稠密头训练](../../script/train_unity_dense_tiles.py) · [筛查比较](../../script/compare_unity_dense_screening.py)
