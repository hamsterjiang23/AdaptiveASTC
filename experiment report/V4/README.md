# V4 ASTC 自动选参实验报告

## 当前结论

报告日期为2026-11-18。本轮完成1000张开发验证图、九组系统对照、108个正式计时单元、216000份ASTC／PNG文件复核和9000行逐图结果核验。使用冻结的ResNet-34与Unity导入后参考图，训练更新为0。`[verified: completion-audit.json formal_cells、images_per_cell、training_updates；complete-artifact-audit.json counts；delivery-verification.json csv_rows]`

**原规则兼容推荐为删除跨块前瞻，质量提升推荐为50%预算内大图解锁。** 两类方案在12个对应计时单元中相对同批V3的严格质量回退均为0张。参数选择与效果统计共用validation1000，V4新资产独立确认协议已准备，cohort待绑定。`[verified: summary.json recommendations、controls.*.metrics.max_strict_regressions_vs_v3_across_cells、independent_confirmation；confirmation-protocol-compatibility.json status、new_cohort；confirmation-protocol-quality.json status、new_cohort]`

| 方案 | 块大小匹配 | 完整配置匹配 | 严格质量通过 | 编码次数／图 | 总payload相对V3 | 文件逐图平均ms |
|---|---|---|---|---|---|---|
| V3基线 | 93.60% | 80.40% | 87.50% | 1.627 | +0.00% | 229.55。`[verified: interpretation.json controls.v3_baseline]` |
| 原规则兼容推荐——删除跨块前瞻 | 93.60% | 80.40% | 87.50% | 1.536 | +0.00% | 228.41。`[verified: interpretation.json controls.remove_lookahead]` |
| 质量提升推荐——50%预算大图解锁 | 88.40% | 75.20% | 92.70% | 1.862 | +3.41% | 297.05。`[verified: interpretation.json controls.bounded_unlock]` |

质量、配置和编码次数采用文件输入批量模式第一轮，耗时采用文件逐图模式的三轮平均值中位数。块大小匹配以原Unity搜索标签为参照，完整配置匹配还要求Quality相同。质量提升方案主动尝试更小块，以增加payload换取额外严格合格图。`[verified: interpretation.json primary_metric_scope、timing_summary；summary.json controls.bounded_unlock.metrics；experiment plan/V4/README.md 第2节、第4节]`

删除前瞻将每轮1000图查询数从1627减至1536，最终ASTC与V3逐图一致，文件逐图平均耗时降低约0.49%。本轮批量耗时及逐图P95均有上升，完整时间表保留各口径波动。大图解锁新增52张严格合格，总payload增加3.41%，文件逐图平均耗时由229.55升至297.05 ms。`[verified: lookahead-complete-comparison.json；interpretation.json controls.v3_baseline、controls.remove_lookahead、controls.bounded_unlock]`

本页数据引用默认指向[完整执行目录](../unity-v4-20261117/README.md)。原始汇总、解读数据、逐图CSV、失败记录和来源绑定均在该目录保存，正式报告的来源SHA见[报告核验](verification.json)。`[verified: verification.json source_files_sha256；../unity-v4-20261117/verification.json]`

## 研究问题与实验目的

V3系统先预测20候选的压缩质量，再由原规则选择搜索起点，随后实际压缩、解码并检查质量。V4研究三个问题，预测起点能否找回被跳过的配置，搜索执行能否减少真实处理成本，以及大图锁块结果能否在单图payload最多增加50%的预算内改善质量。`[verified: experiment plan/V4/README.md 第1节、第2节；offline.json controls]`

本轮保持Unity参考图输入、原有质量分支和20候选身份，模型训练更新为0。规则参数与候选测得的质量决定最终输出，模型预测用于起点及门控判断。真实选参入口使用输入、导入属性、模型预测及本次搜索已测质量，全候选档案用于开发重放、诊断与评分。`[verified: experiment plan/V4/README.md 第2节、第3节；complete-artifact-audit.json training_updates；reproductions/unity_search_baseline/v4_runtime.py UnityV4Trial；v4_policy.py UnityV4Policy.search]`

候选为12×12、10×10、8×8、6×6四种Blocksize，各含fastest、fast、medium、thorough、exhaustive五档Quality，共20个稳定候选。输入范围为LDR、Tex2D、RGBA8、mip0、RDO关闭，法线用途由Unity导入属性提供。`[verified: experiment plan/V4/matrix.json candidate_set；experiment plan/V4/README.md 第1节]`

## 怎么做及目的

先重放原规则并诊断20候选的质量可达性，扫描19种起点和4种门控余量。固定参数后执行九组对照，每组覆盖文件输入与像素就绪、批量与逐图，共四种口径，每种独立重复三次。每轮重新推理并实际压缩、解压、检查质量，最终输出另行解码审计。`[verified: offline.json original_policy_checks、start_scan、gate_scan；complete-artifact-audit.json cells]`

每个对照先用固定前8张图预热一次。文件批量口径一次调用1000张图，像素就绪批量按每组8张图调用，逐图口径每次调用1张图，四种口径独立计时。`[verified: v4_benchmark.py _run、measure]`

起点校准检验能否找回跳过的配置，删除跨块前瞻检验能否省去不影响结果的查询，exhaustive门控检验时间与连续质量的取舍，大图解锁检验单图payload最多增加50%时的质量补救。`[verified: ../../experiment plan/V4/matrix.json controls、unlock]`

## 实际对照怎么组成

| 方案 | 实际行为 |
|---|---|
| V3基线 | 原预测起点和原搜索规则，作为同批质量、体积与时间参照。`[verified: offline.json controls.v3_baseline]` |
| 删除跨块前瞻 | 已锁定块时，在编码下一块候选前退出，保留原选择。`[verified: offline.json controls.remove_lookahead；v4_policy.py UnityV4Policy.search]` |
| 起点校准 | 选中PSNR与MS-SSIM预测各补偿1 dB的配置，重新选择起点，实际质量仍按原阈值检查。`[verified: offline.json selected_start；v4_policy.py UnityV4Policy.start L70–82、search L100–101]` |
| exhaustive门控 | 使用选定的1 dB门控余量，实际探测同块thorough，再决定是否跳过exhaustive。`[verified: offline.json selected_gate_margin_db；v4_policy.py UnityV4Policy.search]` |
| 50%预算大图解锁 | 锁块放宽且严格未通过时，预算允许则尝试相邻更小块，找到严格合格候选才替换。`[verified: experiment plan/V4/matrix.json unlock；v4_policy.py UnityV4Policy.search]` |
| 起点校准＋删除前瞻 | 同时校准起点和提前退出跨块查询。`[verified: offline.json controls.calibrated_start_no_lookahead]` |
| 起点校准＋删除前瞻＋门控 | 在上述组合上启用exhaustive门控。`[verified: offline.json controls.calibrated_gate_no_lookahead]` |
| 起点校准＋删除前瞻＋解锁 | 在起点与执行优化上启用受限解锁。`[verified: offline.json controls.calibrated_unlock_no_lookahead]` |
| 完整组合 | 同时启用起点校准、删除前瞻、exhaustive门控和受限解锁。`[verified: offline.json controls.combined]` |

## 九组结果

质量与配置指标采用文件输入批量模式第一轮。时间采用三轮文件输入逐图平均值的中位数，各输入模式的指标范围和每轮数据保存在interpretation.json。`[verified: interpretation.json primary_metric_scope、timing_summary、controls]`

块匹配以原Unity搜索标签为参照，完整配置匹配同时要求Blocksize和Quality一致。严格通过要求最终ASTC实际解码质量满足该图全部适用门槛。原标签回退统计原Unity选择严格合格而新方案未通过的图片。V3回退统计同一计时单元中V3通过而新方案未通过的图片，最大值取12个单元。`[verified: ../../experiment plan/V4/README.md 第4节“两类推荐标准”；script/diagnose_unity_rules.py summarize；v4_report.py max_strict_regressions_vs_v3_across_cells]`

| 方案 | 块匹配 | 完整配置匹配 | 严格通过 | 原标签回退 | V3最大回退 | 编码次数／图 | payload相对V3 | 逐图平均ms |
|---|---|---|---|---|---|---|---|---|
| 当前V3 | 93.60% | 80.40% | 87.50% | 0 | 0 | 1.627 | +0.00% | 229.55。`[verified: interpretation.json controls.v3_baseline]` |
| 删除跨块前瞻 | 93.60% | 80.40% | 87.50% | 0 | 0 | 1.536 | +0.00% | 228.41。`[verified: interpretation.json controls.remove_lookahead]` |
| 起点校准 | 97.40% | 92.50% | 87.40% | 0 | 1 | 2.376 | -0.62% | 279.43。`[verified: interpretation.json controls.calibrated_start]` |
| exhaustive门控 | 93.70% | 76.00% | 87.50% | 0 | 0 | 1.580 | -0.04% | 212.52。`[verified: interpretation.json controls.exhaustive_gate]` |
| 50%预算大图解锁 | 88.40% | 75.20% | 92.70% | 0 | 0 | 1.862 | +3.41% | 297.05。`[verified: interpretation.json controls.bounded_unlock]` |
| 起点校准＋删除前瞻 | 97.40% | 92.50% | 87.40% | 0 | 1 | 2.284 | -0.62% | 276.60。`[verified: interpretation.json controls.calibrated_start_no_lookahead]` |
| 起点校准＋删除前瞻＋门控 | 97.60% | 88.20% | 87.40% | 0 | 1 | 2.283 | -0.82% | 246.26。`[verified: interpretation.json controls.calibrated_gate_no_lookahead]` |
| 起点校准＋删除前瞻＋解锁 | 92.10% | 87.20% | 92.70% | 0 | 0 | 2.599 | +2.84% | 327.75。`[verified: interpretation.json controls.calibrated_unlock_no_lookahead]` |
| 完整组合 | 92.30% | 84.40% | 92.70% | 0 | 0 | 2.608 | +2.63% | 301.90。`[verified: interpretation.json controls.combined]` |

payload按实际宽高补齐ASTC块后计算，每块16字节，完整ASTC容器另含16字节文件头。解锁的50%上限相对解锁前锁块输出计算，表中体积变化采用整集payload相对V3的比例。`[verified: supplement.py encode_decode、container；../../experiment plan/V4/README.md 第3节“受限大图解锁”]`

候选缓存命中表示同图同次搜索中重复请求已测候选的次数，由门控probe_cached标记与解锁前瞻复用轨迹重建。实际编码次数和耗时来自原生执行记录，最终payload复用记录为selected_payload_reused。逐图CSV包含candidate_cache_hits及两类来源计数。`[verified: interpretation.json cache_reuse_basis；per-image-results.csv；v4_policy.py query；finalize_unity_v4_report.py candidate_cache_reuse]`

## 门槛附近的预测误差

下表按实测质量距对应门槛不超过1 dB或1度筛选，计数单位为候选记录。偏差采用预测值减实测值，误判合格与误判失败按每图实际质量分支判定。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.*.within_1]`

| 指标 | 记录数 | 单位 | 平均预测偏差 | RMSE | 误判合格 | 误判失败 |
|---|---|---|---|---|---|---|
| psnr | 1648 | dB | +0.5624 | 1.4136 | 352 | 158。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.psnr.within_1]` |
| ms_ssim_db | 2337 | dB | +0.2455 | 2.2713 | 344 | 297。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.ms_ssim_db.within_1]` |
| normal_mean_deg | 419 | degrees | +0.0090 | 0.2740 | 19 | 32。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.normal_mean_deg.within_1]` |
| normal_p95_deg | 166 | degrees | -0.0760 | 0.8203 | 24 | 30。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.normal_p95_deg.within_1]` |

开发集196张完整配置不匹配图的原候选均位于预测起点之前，其中193张原候选严格合格。误判方向与偏差统计见[预测残差诊断](../unity-v4-20261117/diagnostic-analysis.md)。`[verified: diagnostic-analysis.json v3_config_mismatch_context]`

## 起点校准的结论

下表为冻结预测与已存20候选质量的离线重放。起点按块匹配、完整配置匹配、较少查询数预筛，门控优先筛选严格回退0张，再比较严格通过率、exhaustive查询和总查询数。正式九组对照采用选中的一个起点配置和一个门控余量。`[verified: offline.json start_scan、gate_scan、selected_start、selected_gate_margin_db；../../experiment plan/V4/README.md 第3节]`

| 起点方式 | PSNR补偿dB | MS-SSIM补偿dB | 块匹配 | 完整配置匹配 | 严格回退 | 查询数 |
|---|---|---|---|---|---|---|
| 原起点 | 0 | 0 | 93.6% | 80.4% | 0 | 1627。`[verified: offline.json start_scan[0]]` |
| 前移1候选 | 0 | 0 | 96.4% | 89.5% | 1 | 2248。`[verified: offline.json start_scan[1]]` |
| 前移2候选 | 0 | 0 | 96.8% | 94.5% | 1 | 2960。`[verified: offline.json start_scan[2]]` |
| 同块fastest | 0 | 0 | 93.9% | 93.9% | 1 | 3404。`[verified: offline.json start_scan[3]]` |
| 质量预测补偿 | 0 | 0.25 | 94.2% | 83.2% | 0 | 1707。`[verified: offline.json start_scan[4]]` |
| 质量预测补偿 | 0 | 0.5 | 95.2% | 85.8% | 0 | 1825。`[verified: offline.json start_scan[5]]` |
| 质量预测补偿 | 0 | 1 | 95.9% | 88.9% | 1 | 2100。`[verified: offline.json start_scan[6]]` |
| 质量预测补偿 | 0.25 | 0 | 94.0% | 82.0% | 0 | 1669。`[verified: offline.json start_scan[7]]` |
| 质量预测补偿 | 0.25 | 0.25 | 94.6% | 85.0% | 0 | 1750。`[verified: offline.json start_scan[8]]` |
| 质量预测补偿 | 0.25 | 0.5 | 95.6% | 87.6% | 0 | 1869。`[verified: offline.json start_scan[9]]` |
| 质量预测补偿 | 0.25 | 1 | 96.3% | 90.8% | 1 | 2150。`[verified: offline.json start_scan[10]]` |
| 质量预测补偿 | 0.5 | 0 | 94.8% | 82.7% | 0 | 1723。`[verified: offline.json start_scan[11]]` |
| 质量预测补偿 | 0.5 | 0.25 | 95.4% | 85.7% | 0 | 1809。`[verified: offline.json start_scan[12]]` |
| 质量预测补偿 | 0.5 | 0.5 | 96.4% | 88.3% | 0 | 1930。`[verified: offline.json start_scan[13]]` |
| 质量预测补偿 | 0.5 | 1 | 97.1% | 91.5% | 1 | 2215。`[verified: offline.json start_scan[14]]` |
| 质量预测补偿 | 1 | 0 | 95.1% | 83.7% | 0 | 1851。`[verified: offline.json start_scan[15]]` |
| 质量预测补偿 | 1 | 0.25 | 95.7% | 86.5% | 0 | 1945。`[verified: offline.json start_scan[16]]` |
| 质量预测补偿 | 1 | 0.5 | 96.7% | 89.1% | 0 | 2073。`[verified: offline.json start_scan[17]]` |
| 质量预测补偿 | 1 | 1 | 97.4% | 92.5% | 1 | 2376。`[verified: offline.json start_scan[18]]` |

零严格回退的离线起点中，最高块匹配为96.7%，对应PSNR补偿1 dB、MS-SSIM补偿0.5 dB。本轮真实矩阵采用按既定匹配率预筛选出的配置，其他起点的实际速度及逐模式质量留待验证。`[verified: interpretation.json highest_block_match_zero_regression_offline_start；offline.json selected_start]`

起点预筛选中PSNR与MS-SSIM各加1 dB的预测补偿。真实主口径下，完整配置匹配从80.4%提高到92.5%，编码从1.627增加到2.376次／图，相对V3严格质量回退1张。`[verified: offline.json selected_start；summary.json controls.calibrated_start.metrics]`

预测补偿用于重新选择起点，真实编码后的质量判定沿用每图原始门槛。`[verified: ../../experiment plan/V4/README.md 第3节“搜索起点校准”；calibration-native-regression.json measurements.*.choice.effective_psnr_threshold]`

逐图配对找回原先未匹配的完整配置121张，同时丢失原先匹配的0张，净增加121张。`[verified: interpretation.json controls.calibrated_start configuration_recovered_vs_v3、configuration_matches_lost_vs_v3]`

校准后整集payload变化-198,144字节，比例-0.62%，文件逐图平均耗时为279.43 ms。`[verified: interpretation.json controls.calibrated_start、controls.v3_baseline]`

已归档的开发图94展示了锁块状态变化。前移后12×12 thorough的PSNR达标，搜索锁定12×12并返回放宽结果，MS-SSIM为18.65 dB。V3从12×12 exhaustive起搜，该候选PSNR未达标，后续10×10 exhaustive达到21.37 dB。`[verified: calibration-native-regression.json measurements]`

该图原Unity标签为12×12 thorough放宽输出，校准后恢复了原标签配置，同时失去了V3在该图上的严格质量改善。`[verified: calibration-native-regression.json original_unity_selection、measurements]`

因此，起点校准需要同时核查锁块行为和严格回退，配置匹配率提高本身不足以进入零回退推荐。`[opinion]`

## 删除前瞻与门控的结论

| 门控余量dB | 离线严格通过 | 离线严格回退 | exhaustive查询 | 总查询 |
|---|---|---|---|---|
| 0 | 87.2% | 3 | 219 | 1549。`[verified: offline.json gate_scan[0]]` |
| 0.5 | 87.4% | 1 | 236 | 1568。`[verified: offline.json gate_scan[1]]` |
| 1 | 87.5% | 0 | 252 | 1580。`[verified: offline.json gate_scan[2]]` |
| 2 | 87.5% | 0 | 274 | 1600。`[verified: offline.json gate_scan[3]]` |

删除跨块前瞻后，平均查询从1.627降至1.536次／图。四种口径、三次重复的12000组逐图配对保持最终ASTC一致，每轮减少91次末尾跨块查询。`[verified: lookahead-complete-comparison.json；summary.json controls.remove_lookahead.metrics]`

文件逐图平均时间为229.55→228.41 ms，变化-0.49%。四种口径的时间表保留实际波动，较少查询与实际加速分别评价。`[verified: interpretation.json controls.v3_baseline.timing、controls.remove_lookahead.timing]`

独立exhaustive门控的文件逐图平均耗时为212.52 ms，相对V3变化-17.03 ms／图、-7.42%。其他计时口径的三轮结果见完整时间表。`[verified: interpretation.json controls.exhaustive_gate.timing、controls.v3_baseline.timing]`

在已校准并删除前瞻的组合中，门控前后平均编码次数为2.284→2.283，exhaustive查询总数为405→356。文件逐图平均时间为276.60→246.26 ms。`[verified: interpretation.json controls.calibrated_start_no_lookahead、controls.calibrated_gate_no_lookahead]`

| 门控方案 | 跳过exhaustive数 | 跳过严格合格候选数 | PSNR差均值／最小值dB | MS-SSIM差均值／最小值dB |
|---|---|---|---|---|
| exhaustive门控 | 47 | 0 | -0.107／-0.673 | -0.231／-0.640。`[verified: interpretation.json controls.exhaustive_gate.skipped_exhaustive]` |
| 起点校准＋删除前瞻＋门控 | 47 | 0 | -0.070／-0.673 | -0.230／-0.640。`[verified: interpretation.json controls.calibrated_gate_no_lookahead.skipped_exhaustive]` |
| 完整组合 | 47 | 0 | +0.485／-0.673 | +0.407／-0.640。`[verified: interpretation.json controls.combined.skipped_exhaustive]` |

表中差值为最终输出减去被跳过exhaustive的实测质量，负值表示该指标下降。严格回退另按同模式、同轮V3最终输出配对统计。`[verified: v4_report.py gate_changes；interpretation.json controls]`

exhaustive门控的跳过样本相对实际V3最终输出，PSNR平均差-0.182 dB、最小差-1.965 dB，MS-SSIM平均差-0.270 dB、最小差-2.184 dB。`[verified: interpretation.json controls.exhaustive_gate.skipped_exhaustive]`

起点校准＋删除前瞻＋门控的跳过样本相对实际V3最终输出，PSNR平均差-0.223 dB、最小差-2.006 dB，MS-SSIM平均差-0.310 dB、最小差-2.184 dB。`[verified: interpretation.json controls.calibrated_gate_no_lookahead.skipped_exhaustive]`

完整组合的跳过样本相对实际V3最终输出，PSNR平均差+0.332 dB、最小差-2.006 dB，MS-SSIM平均差+0.327 dB、最小差-2.184 dB。`[verified: interpretation.json controls.combined.skipped_exhaustive]`

## 50%体积预算内的质量补救

开发集125张V3严格未通过图中，同块严格合格候选为0张，其他候选存在合格结果的为91张。其中52张位于50%payload预算内，39张的全部合格候选超出预算，34张在20候选内均无严格合格结果。`[verified: diagnostic-analysis.json failed_reachability；offline.json reachability]`

单独解锁实际新增严格合格52张，严格通过率达到92.7%，总payload变化+3.41%。逐图预算核验覆盖实际替换事件。`[verified: summary.json controls.bounded_unlock.metrics；complete-artifact-audit.json]`

单独解锁的额外payload为+1,093,680字节，文件逐图平均耗时为297.05 ms，平均编码1.862次／图。`[verified: interpretation.json controls.bounded_unlock、controls.v3_baseline]`

| 解锁方案 | 解锁事件 | 6×6终点 | 预算阻止 | 预算允许 | 成功替换 | 允许但失败 |
|---|---|---|---|---|---|---|
| 50%预算大图解锁 | 92 | 1 | 16 | 75 | 52 | 23。`[verified: interpretation.json controls.bounded_unlock.unlock_outcomes]` |
| 起点校准＋删除前瞻＋解锁 | 93 | 1 | 16 | 76 | 53 | 23。`[verified: interpretation.json controls.calibrated_unlock_no_lookahead.unlock_outcomes]` |
| 完整组合 | 93 | 1 | 14 | 78 | 53 | 25。`[verified: interpretation.json controls.combined.unlock_outcomes]` |

预算允许的下一块仍可能无法满足严格质量，失败时保留解锁前输出，追加查询进入实际耗时。6×6终点以空的下一块及候选payload记录。`[verified: interpretation.json controls.*.unlock_events；complete-artifact-audit.json counts]`

## 两类推荐怎么选

**原规则兼容推荐为删除跨块前瞻**。块大小匹配93.60%，完整配置匹配80.40%，严格通过87.50%，相对同模式V3的最大严格回退数0，相对原Unity标签严格回退0张，文件逐图平均228.41 ms。`[verified: summary.json recommendations.compatibility；interpretation.json controls.remove_lookahead]`

配置为`{"start_mode": "original", "psnr_margin_db": 0.0, "ms_ssim_margin_db": 0.0, "remove_lookahead": true, "gate_margin_db": null, "unlock": false}`。`[verified: summary.json controls.remove_lookahead.options]`

**质量提升推荐为50%预算大图解锁**。块大小匹配88.40%，完整配置匹配75.20%，严格通过92.70%，相对同模式V3的最大严格回退数0，相对原Unity标签严格回退0张，文件逐图平均297.05 ms。`[verified: summary.json recommendations.quality；interpretation.json controls.bounded_unlock]`

配置为`{"start_mode": "original", "psnr_margin_db": 0.0, "ms_ssim_margin_db": 0.0, "remove_lookahead": false, "gate_margin_db": null, "unlock": true}`。`[verified: summary.json controls.bounded_unlock.options]`

原规则兼容按块匹配、完整配置匹配、真实时间、payload排序，质量提升按严格通过率、真实时间、payload排序。两类推荐均应用全部计时单元严格回退为0的筛选。`[verified: v4_report.py compatible、eligible_quality、recommendations]`

质量提升方案主动允许更小块，原标签匹配率与严格质量通过率分别反映配置一致性和质量达标。`[opinion]`

## 一次完整处理耗时怎么读

| 方案 | 文件批量摊销ms／图 | 文件逐图平均ms | 文件逐图中位数ms | 文件逐图P95 ms | 像素就绪批量ms／图 | 像素就绪逐图平均ms |
|---|---|---|---|---|---|---|
| 当前V3 | 201.96 | 229.55 | 84.56 | 656.91 | 202.20 | 228.17。`[verified: interpretation.json controls.v3_baseline.timing]` |
| 删除跨块前瞻 | 218.25 | 228.41 | 74.89 | 669.16 | 215.69 | 224.77。`[verified: interpretation.json controls.remove_lookahead.timing]` |
| 起点校准 | 256.34 | 279.43 | 112.43 | 918.24 | 255.32 | 279.25。`[verified: interpretation.json controls.calibrated_start.timing]` |
| exhaustive门控 | 185.73 | 212.52 | 89.23 | 642.08 | 180.80 | 209.71。`[verified: interpretation.json controls.exhaustive_gate.timing]` |
| 50%预算大图解锁 | 261.65 | 297.05 | 93.96 | 1142.19 | 269.29 | 296.61。`[verified: interpretation.json controls.bounded_unlock.timing]` |
| 起点校准＋删除前瞻 | 245.88 | 276.60 | 121.00 | 883.52 | 246.29 | 270.86。`[verified: interpretation.json controls.calibrated_start_no_lookahead.timing]` |
| 起点校准＋删除前瞻＋门控 | 213.43 | 246.26 | 113.57 | 725.79 | 212.52 | 241.50。`[verified: interpretation.json controls.calibrated_gate_no_lookahead.timing]` |
| 起点校准＋删除前瞻＋解锁 | 297.20 | 327.75 | 113.48 | 1241.86 | 297.91 | 327.57。`[verified: interpretation.json controls.calibrated_unlock_no_lookahead.timing]` |
| 完整组合 | 271.67 | 301.90 | 114.43 | 959.41 | 269.48 | 300.13。`[verified: interpretation.json controls.combined.timing]` |

每列先分别计算各轮统计，再取三轮中位数。批量数据报告整集摊销，逐图分位数来自实际单图调用。`[verified: finalize_unity_v4_report.py timing_summary]`

文件输入耗时包含PNG／属性准备、patch与模型推理、起点与搜索决策、每次ASTC编码、解码和质量门控，终点为最终内存mip0 ASTC。模型与DLL加载、输出审计及写盘另列，Unity导入与完整mip链处于本轮计时范围之外。`[verified: benchmark1000-v3/result.json measurements.timings.measurements.scope_details；interpretation.json separate_costs]`

分段时间保存在interpretation.json的component_ms_per_image_median3。各分段分别取三轮中位数，相加可能与端到端三轮中位数存在差异。`[verified: finalize_unity_v4_report.py timing_summary]`

| 推荐方案 | 输入准备 | 编码参考像素准备 | 推理 | 决策与记账 | 编码 | 解码 | 质量检查 |
|---|---|---|---|---|---|---|---|
| 当前V3 | 6.78 | 2.54 | 43.83 | 0.83 | 141.33 | 12.49 | 21.56。`[verified: interpretation.json controls.v3_baseline.timing.files_single]` |
| 删除跨块前瞻 | 7.25 | 2.75 | 30.56 | 0.82 | 154.31 | 12.75 | 19.84。`[verified: interpretation.json controls.remove_lookahead.timing.files_single]` |
| 50%预算大图解锁 | 7.05 | 2.68 | 51.18 | 1.07 | 189.49 | 15.06 | 30.60。`[verified: interpretation.json controls.bounded_unlock.timing.files_single]` |

分段表单位为ms／图，采用文件逐图口径。本轮模型加载0.279秒，DLL加载0.001秒，整个108单元基准流程耗时33232.04秒。逐单元输出审计成本见interpretation.json的output_audit_seconds。`[verified: interpretation.json separate_costs、controls.*.timing.*.repetitions]`

本轮采用固定对照顺序，在当前桌面负载下测量，阶段资源采样见resource-observations.jsonl。时间结论以记录的三轮范围共同解释。`[verified: benchmark1000-v3/result.json measurements；resource-observations.jsonl]`

## 类型与大图分组

各方案的颜色、Linear、法线、Alpha、尺寸、Quality、编码次数及分支指标保存在summary.json的groups。2048、4096与1780×1000独立列出覆盖情况，0样本组使用missing_in_validation标记。`[verified: summary.json controls.*.groups]`

| 方案 | 分组 | 图片数 | 严格通过 | 平均编码次数 | 平均ms | 中位ms | P95 ms |
|---|---|---|---|---|---|---|---|
| 当前V3 | sRGB小图 | 612 | 95.42% | 1.680 | 75.29 | 60.32 | 194.92。`[verified: summary.json controls.v3_baseline.groups.srgb_small]` |
| 当前V3 | sRGB大图 | 326 | 71.17% | 1.561 | 504.12 | 228.47 | 1640.92。`[verified: summary.json controls.v3_baseline.groups.srgb_large]` |
| 当前V3 | Linear | 17 | 100.00% | 1.000 | 115.67 | 79.38 | 283.19。`[verified: summary.json controls.v3_baseline.groups.linear]` |
| 当前V3 | 法线 | 45 | 93.33% | 1.622 | 320.95 | 176.94 | 683.47。`[verified: summary.json controls.v3_baseline.groups.normal]` |
| 当前V3 | 需要Alpha | 363 | 87.05% | 1.876 | 175.08 | 61.87 | 556.82。`[verified: summary.json controls.v3_baseline.groups.alpha_True]` |
| 当前V3 | 无需Alpha | 637 | 87.76% | 1.485 | 256.32 | 97.69 | 658.50。`[verified: summary.json controls.v3_baseline.groups.alpha_False]` |
| 当前V3 | 最大边2048 | 14 | 85.71% | 1.357 | 2281.75 | 1090.33 | 6887.91。`[verified: summary.json controls.v3_baseline.groups.max_side_exact_2048]` |
| 当前V3 | 最大边4096 | 0 | — | — | — | — | —。`[verified: summary.json controls.v3_baseline.groups]` |
| 当前V3 | 1780×1000 | 3 | 0.00% | 2.000 | 3259.72 | 3216.69 | 3390.06。`[verified: summary.json controls.v3_baseline.groups.resolution_1780x1000]` |
| 删除跨块前瞻 | sRGB小图 | 612 | 95.42% | 1.680 | 69.87 | 49.26 | 193.72。`[verified: summary.json controls.remove_lookahead.groups.srgb_small]` |
| 删除跨块前瞻 | sRGB大图 | 326 | 71.17% | 1.282 | 508.70 | 233.44 | 1761.65。`[verified: summary.json controls.remove_lookahead.groups.srgb_large]` |
| 删除跨块前瞻 | Linear | 17 | 100.00% | 1.000 | 100.44 | 73.74 | 284.59。`[verified: summary.json controls.remove_lookahead.groups.linear]` |
| 删除跨块前瞻 | 法线 | 45 | 93.33% | 1.622 | 308.39 | 148.76 | 715.42。`[verified: summary.json controls.remove_lookahead.groups.normal]` |
| 删除跨块前瞻 | 需要Alpha | 363 | 87.05% | 1.826 | 175.26 | 52.89 | 547.19。`[verified: summary.json controls.remove_lookahead.groups.alpha_True]` |
| 删除跨块前瞻 | 无需Alpha | 637 | 87.76% | 1.370 | 252.06 | 86.42 | 677.24。`[verified: summary.json controls.remove_lookahead.groups.alpha_False]` |
| 删除跨块前瞻 | 最大边2048 | 14 | 85.71% | 1.214 | 2353.07 | 1168.95 | 7453.95。`[verified: summary.json controls.remove_lookahead.groups.max_side_exact_2048]` |
| 删除跨块前瞻 | 最大边4096 | 0 | — | — | — | — | —。`[verified: summary.json controls.remove_lookahead.groups]` |
| 删除跨块前瞻 | 1780×1000 | 3 | 0.00% | 1.000 | 3271.40 | 3225.45 | 3428.72。`[verified: summary.json controls.remove_lookahead.groups.resolution_1780x1000]` |
| 50%预算大图解锁 | sRGB小图 | 612 | 95.42% | 1.680 | 82.25 | 66.97 | 205.70。`[verified: summary.json controls.bounded_unlock.groups.srgb_small]` |
| 50%预算大图解锁 | sRGB大图 | 326 | 87.12% | 2.282 | 702.01 | 281.46 | 2449.21。`[verified: summary.json controls.bounded_unlock.groups.srgb_large]` |
| 50%预算大图解锁 | Linear | 17 | 100.00% | 1.000 | 124.79 | 94.10 | 305.61。`[verified: summary.json controls.bounded_unlock.groups.linear]` |
| 50%预算大图解锁 | 法线 | 45 | 93.33% | 1.622 | 333.35 | 183.19 | 709.63。`[verified: summary.json controls.bounded_unlock.groups.normal]` |
| 50%预算大图解锁 | 需要Alpha | 363 | 89.81% | 2.000 | 218.00 | 67.90 | 850.41。`[verified: summary.json controls.bounded_unlock.groups.alpha_True]` |
| 50%预算大图解锁 | 无需Alpha | 637 | 94.35% | 1.783 | 340.94 | 111.82 | 1277.92。`[verified: summary.json controls.bounded_unlock.groups.alpha_False]` |
| 50%预算大图解锁 | 最大边2048 | 14 | 85.71% | 1.929 | 3087.57 | 1257.61 | 9198.19。`[verified: summary.json controls.bounded_unlock.groups.max_side_exact_2048]` |
| 50%预算大图解锁 | 最大边4096 | 0 | — | — | — | — | —。`[verified: summary.json controls.bounded_unlock.groups]` |
| 50%预算大图解锁 | 1780×1000 | 3 | 0.00% | 6.000 | 7274.04 | 7348.70 | 7406.78。`[verified: summary.json controls.bounded_unlock.groups.resolution_1780x1000]` |

分组时间先对每张图的三次文件逐图耗时取中位数，再在组内计算统计量。类型、Alpha与尺寸组存在交叉，逐组图片数用于说明覆盖范围。`[verified: v4_report.py latencies、group_indices、groups]`

sRGB大图组按原规则的面积分支统计，2048与4096尺寸组按最大边统计，1780×1000组按精确分辨率统计。`[verified: v4_report.py kind、side、group_indices]`

## 推荐方案的混淆矩阵与召回率

矩阵行对应原Unity标签的块大小，列对应当前系统选择。召回率为该行对角线数除以该行总数。`[verified: v4_report.py confusion、per_class_recall]`

### 当前V3

| 原标签 | 选6×6 | 选8×8 | 选10×10 | 选12×12 | 召回率 |
|---|---|---|---|---|---|
| 6×6 | 120 | 0 | 0 | 0 | 100.00%。`[verified: summary.json controls.v3_baseline.metrics.confusion、per_class_recall]` |
| 8×8 | 17 | 126 | 0 | 0 | 88.11%。`[verified: summary.json controls.v3_baseline.metrics.confusion、per_class_recall]` |
| 10×10 | 1 | 21 | 116 | 0 | 84.06%。`[verified: summary.json controls.v3_baseline.metrics.confusion、per_class_recall]` |
| 12×12 | 1 | 1 | 23 | 574 | 95.83%。`[verified: summary.json controls.v3_baseline.metrics.confusion、per_class_recall]` |

### 删除跨块前瞻

| 原标签 | 选6×6 | 选8×8 | 选10×10 | 选12×12 | 召回率 |
|---|---|---|---|---|---|
| 6×6 | 120 | 0 | 0 | 0 | 100.00%。`[verified: summary.json controls.remove_lookahead.metrics.confusion、per_class_recall]` |
| 8×8 | 17 | 126 | 0 | 0 | 88.11%。`[verified: summary.json controls.remove_lookahead.metrics.confusion、per_class_recall]` |
| 10×10 | 1 | 21 | 116 | 0 | 84.06%。`[verified: summary.json controls.remove_lookahead.metrics.confusion、per_class_recall]` |
| 12×12 | 1 | 1 | 23 | 574 | 95.83%。`[verified: summary.json controls.remove_lookahead.metrics.confusion、per_class_recall]` |

### 50%预算大图解锁

| 原标签 | 选6×6 | 选8×8 | 选10×10 | 选12×12 | 召回率 |
|---|---|---|---|---|---|
| 6×6 | 120 | 0 | 0 | 0 | 100.00%。`[verified: summary.json controls.bounded_unlock.metrics.confusion、per_class_recall]` |
| 8×8 | 17 | 126 | 0 | 0 | 88.11%。`[verified: summary.json controls.bounded_unlock.metrics.confusion、per_class_recall]` |
| 10×10 | 1 | 21 | 116 | 0 | 84.06%。`[verified: summary.json controls.bounded_unlock.metrics.confusion、per_class_recall]` |
| 12×12 | 1 | 1 | 75 | 522 | 87.15%。`[verified: summary.json controls.bounded_unlock.metrics.confusion、per_class_recall]` |

## 失败记录与证据边界

早期v2尝试在开发图901的逐图审计中失败。旧审计要求逐图新预测与冻结批量预测走相同轨迹，该图PSNR预测在30 dB门槛附近出现30.0008与29.9913 dB的模式差异。审计已改为用每轮实际预测重放当轮轨迹，冻结档案差异单列。v2失败源码、回执及三轮已完成数据保留，正式结论采用完整v3尝试。`[verified: runtime-mismatch901-diagnosis.json；runtime-mismatch901-recovery-check.json；implementation-notes.md]`

32图闭环已覆盖图901及四种输入模式，正式测量使用同scope、mode和repeat的实际V3结果配对。`[verified: smoke32-v3-artifact-audit.json；complete-artifact-audit.json replay_prediction_source]`

首轮一次性预算检查在开发图226的6×6终点遇到空值并触发TypeError。该图真实编码按协议保留6×6 exhaustive，检查程序加入终点分支后通过。独立验收入口同时核查预算禁止、解锁失败保留与完整ASTC容器字节数。`[verified: unlock-first-native-budget-audit.json checker_recovery、rows；script/verify_unity_v4.py unlock_event、native_payload_sizes_checked]`

开发集上的参数选择与效果统计共享1000张图，独立泛化效果留待新资产确认。`[verified: offline.json selection_split；summary.json independent_confirmation]`

## 后续训练与专项采集建议

后续专项采集宜覆盖法线、Linear以及2048、4096、1780×1000尺寸，按本轮分组表的实际覆盖安排优先级。新资产同步保留Unity导入属性与原始搜索标签。`[opinion]`

后续训练对照宜分别检查门槛附近的误判合格与误判失败样本，结合锁块轨迹确定采样或损失调整，再用冻结权重的完整系统对照验证。`[opinion]`

## 产物与复现

[逐图CSV](../unity-v4-20261117/per-image-results.csv)、[原始汇总](../unity-v4-20261117/summary.json)、[解读数据](../unity-v4-20261117/interpretation.json)、[独立产物核验](../unity-v4-20261117/complete-artifact-audit.json)、[原规则兼容确认协议](../unity-v4-20261117/confirmation-protocol-compatibility.json)与[质量提升确认协议](../unity-v4-20261117/confirmation-protocol-quality.json)绑定本轮结果。`[verified: verification.json；interpretation.json source_bindings]`

新确认协议已绑定模型、候选、参数、执行源码、DLL与计时口径。新资产名单、原生采集、像素隔离和首次forward前冻结由cohort_requirements列明，执行授权状态保持待后续安排。`[verified: confirmation-protocol-compatibility.json；confirmation-protocol-quality.json]`

在项目根目录核验和重建解读报告。`[opinion]`

```powershell
uv run --no-sync python -u script/verify_unity_v4.py --attempt v3
uv run --no-sync python script/finalize_unity_v4_report.py --attempt v3
```

重新执行实验采用新的attempt身份，完整入口为`script/execute_unity_v4.py --attempt <新身份>`，离线扫描按当前已绑定开发数据重建，历史结果保留。`[verified: script/execute_unity_v4.py main；v4_benchmark.py run]`

## 当前交付状态与复现条件

| 项目 | 当前状态 |
|---|---|
| V4开发实验 | 九组、四口径、三重复共108个正式计时单元已完成，11项goal要求逐项通过。`[verified: completion-audit.json requirements、formal_cells]` |
| V4独立确认 | 两类推荐的协议已准备，新资产cohort为空，协议执行授权为false。`[verified: confirmation-protocol-compatibility.json status、new_cohort、confirmation_execution_authorized；confirmation-protocol-quality.json 对应字段]` |
| 输入及模型来源 | 冻结检查点SHA-256为783c69281d127362882a6a84935d928857f33745bb90e282cfb4b648062ada85，来源路径和DLL摘要由协议绑定。`[verified: confirmation-protocol-quality.json checkpoint、binaries]` |
| 本地复现实验依赖 | 编码与质量DLL、冻结模型、Unity参考像素及候选档案按绑定清单准备，原生ASTC／PNG和模型等本地数据位于现有.gitignore定义的.local目录。公开报告、CSV、源码、配置和来源摘要随仓库交付。`[verified: ../../.gitignore；../unity-v4-20261117/benchmark1000-v3/execution-binding.json files_sha256；confirmation-protocol-quality.json checkpoint、binaries]` |

独立验证已覆盖当轮实际预测重放、候选唯一查询、预算边界、失败保留、最终ASTC及解码PNG身份。缓存命中由保存的轨迹重建，实际编码计数与耗时按原生运行记录统计。`[verified: complete-artifact-audit.json replay_prediction_source、counts；interpretation.json cache_reuse_basis]`

终稿结构检查曾把CSV布尔字段按文本1比较，实际9000行均为True。检查条件修正后，报告表格、链接、CSV覆盖及两份协议核验通过，修复记录已保存。`[verified: delivery-audit-checker-recovery.json；delivery-verification.json]`
