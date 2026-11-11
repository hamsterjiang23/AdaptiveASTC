# Unity 分批原生 patch 目标准备

后续已启动[3906图扩展](unity-patch-batches3906-config.json)：冻结17个已发布候选批次，目标3904 train／2 validation，复用已完成的2370图目标，并为另外1536张图提取监督。[扩展状态](unity-patch-batches3906.json)仍在运行，新的统一清单和完整Dataset遍历尚待本批完成；不把已选范围计为已完成范围。`[verified: unity-patch-batches3906-config.json run_ids、previous_completed_report；jobs/unity-patch-batches3906/launch-preflight.json frozen_counts、additional_images；unity-patch-batches3906.json status；opinion: 状态口径]`

已通过64张训练图与2张验证图的分批准备检查，生成781／13个patch，并核对已有训练目标的SHA未变。随后完成冻结快照中的11个已发布批次，实际2368 train／2 validation、15606／13patch；最终记录见[扩展记录](unity-patch-batches2370.json)。这只是完整10000／1000开发集的部分覆盖。`[verified: unity-patch-batches-smoke-v2.json counts、patch_counts；unity-patch-batches2370-config.json run_ids；jobs/unity-patch-batches2370/launch-preflight.json；opinion: 覆盖范围]`

## 来源与复用

入口为 [prepare_unity_patch_batches.py](../../script/prepare_unity_patch_batches.py)，实现为 [UnityPatchBatchPreparation](../../reproductions/unity_search_baseline/patch_batches.py)。输入冻结候选队列的配置和已发布状态快照，逐批重新核对原始参考像素／搜索标签及候选归档，再调用原生误差提取器生成单批语料。已完成语料通过独立配置、报告和corpus哈希及Dataset检查复用，保持原有目标文件；这次没有重新编码或新增GPU训练。`[verified: patch_batches.py prepare、prepare_shard；unity-patch-batches-smoke-v2-config.json；opinion: 执行范围]`

共享输出目录使用独占文件锁，拒绝并行写同一批目标；每批开始检查至少20GiB空闲RAM和40GiB磁盘。读取对象仅为快照中已经发布的批次，正在写入的参考采集／候选批次不进入本次选择。后续增加批次时使用新的快照、配置和报告，已完成目标可复用。`[verified: patch_batches.py run、select_batches、prepare；opinion: 后续用法]`

单批语料各自保留原始划分、路径、20候选图级质量和逐通道patch监督。分批输出随后通过[统一清单组装](unity-patch-assembly.md)，原划分与单批来源保持；完整生产训练尚未完成。`[verified: patch_batches.py state.shards；UnityPatchCorpus.prepare_image；opinion: 待办范围]`

## 实测发现与修复

- 首次检查在原生Dataset身份核对处失败：同一资产在Unity日志中记录为`...020_d.tga`，源清单为`...020_D.tga`。现改为与Windows资产身份一致的分隔符规范化及casefold比较；corpus外部SHA约束保留，不同资产路径仍拒绝。旧失败及源码归档保留，已生成64图语料被复用而未重写。`[verified: unity-patch-batches-smoke.json error；unity-patch-batches-smoke-v2-config.json prior_attempt；unity_patch_dataset.py original_selection比较；test_unity_patch_dataset.py test_original_selection_uses_windows_asset_identity]`
- 独立审查发现，选完一个小型selected计划不能代表完整源语料。修复后只有原计划与快照均为complete、选择全部计划批次且计划计数等于完整源划分，才将coverage设为complete。coverage表示所选范围；只有status=passed、coverage=complete且实际counts等于完整源划分，才认定完整语料准备完成。计划计数与完整源计数分别记录，相关回归已覆盖。`[verified: patch_batches.py coverage、expected_plan_counts、expected_full_counts、prepare末段；test_unity_patch_batches.py test_small_complete_plan_is_not_full_corpus；review C1复查]`
- 新增批次检查21项，连同原生Dataset21项，共42项通过。覆盖未发布／重复／跨划分批次、来源快照改变、不可覆盖文件、完成目标篡改、小计划覆盖范围及Windows路径身份。代码复查未发现剩余问题。`[verified: test_unity_patch_batches.py；test_unity_patch_dataset.py；pytest 42 passed；review回执]`

## 成本与限制

| 执行 | 结果与成本 |
|---|---|
| 首次64＋2检查 | 64图目标提取已完成，后续身份检查失败；循环59.57秒，进程63.53秒。这些成本包含已复用的数据准备，不能全部算作无效工作。`[verified: unity-patch-batches-smoke.json；jobs/unity-patch-batches-smoke/receipt.json；opinion: 成本解释]` |
| 修复后64＋2检查 | passed，循环9.48秒，进程12.81秒；复用已有64图目标，补齐验证图，不能与首次执行直接解释为速度改进。`[verified: unity-patch-batches-smoke-v2.json；jobs/unity-patch-batches-smoke-v2/receipt.json；opinion: 比较边界]` |
| 扩展到2370图 | 启动前空闲RAM25.25GiB、磁盘917.53GiB，单CPU进程；完成循环1205.56秒、独立进程1208.54秒，包含归档重验与已完成目标复用。`[verified: jobs/unity-patch-batches2370/launch-preflight.json、receipt.json；unity-patch-batches2370.json wall_seconds；opinion: 计时范围]` |

完整Unity语料、图级MS-SSIM／角度学习、原生模型训练与独立测试90%验收仍待完成。这里的passed只说明相应范围的数据准备检查通过。`[verified: unity-patch-batches-smoke-v2.json training_updates、test_opened；opinion: 验收边界]`
