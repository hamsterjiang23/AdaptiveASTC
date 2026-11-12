# Unity V2 数据交接完成

V2 数据采集与完整性验收已完成：训练10000张、验证1000张、确认2000张。开发集已按批准的18个位置补采并生成新语料，220000组候选、74609个patch；11000张完整读取和原规则四字段重放通过。13,000张实际输入、精确RGBA和同尺寸对齐近重复检查完成，确认集未运行模型。`[verified: unity-data-delivery-v3-verification.json counts、development_candidate_count、development_patch_counts、exact_policy_replay、native_input_eligibility_verified、full_pixel_audit_complete、test_opened]`

## 当前数据入口

读取[统一数据入口配置](unity-v2-data-inputs.json)，它绑定以下本机文件及SHA-256；图片、逐图目标和原始日志按`.local/`规则留在本机，Git保存代码、配置和公开报告。`[verified: unity-v2-data-inputs.json development、confirmation、verification、large_artifacts_location；.gitignore]`

| 数据 | 数量与内容 |
|---|---|
| 训练 | 10000张，67436个240像素patch，每张20候选。`[verified: unity-data-delivery-v3-verification.json counts、development_patch_counts、development_candidate_count]` |
| 验证 | 1000张，7173个patch，每张20候选。`[verified: 同上]` |
| 确认 | 2000张；参考像素、实际导入属性及同次原搜索标签，11209次原搜索候选测量；不补测20候选。`[verified: unity-data-delivery-v3-verification.json confirmation_original_candidate_measurements、confirmation_supplemental_candidates]` |

- [新版开发语料](<../.local/unity-accuracy90-20261111/development-corpus11000-v2/corpus.json>)：`560094e9d87b220b037ed37574e5941f0eff0675ffb43f34737f904e1f895c57`。`[verified: 最终验收 development_corpus_sha256]`
- [确认集清单](<../.local/unity-confirmation-series2000-data-v2/manifest.json>)：`906e5b7f27e3f01a15f02e51d6fbdb689a69c28374fd4496034282355471db33`。`[verified: 最终验收 confirmation_manifest_sha256]`
- [总验收与来源哈希](unity-data-delivery-v3-verification.json)、[Dataset全读](unity-development-corpus11000-v2-dataset.json)、[原规则重放](unity-development-corpus11000-v2-interface.json)、[完整训练／验证分布](unity-development-v2-distribution.json)。`[verified: 对应报告 status、counts、results、splits]`

## 修订与保留

开发集保留10982张，替换13张训练Cube和5张验证Cube；全部11000张满足V2实际输入约定。确认集另按此前批准的备用顺序替换47张范围外图片，保持2000张。旧名单、语料、失败记录、原搜索与补测成本均保留；补采期间有同机审计活动，其耗时不作为新的独占性能基线。`[verified: unity-development-corpus11000-v2.json retained_images、replaced_images、input_eligibility_images、original_data_modified；unity-confirmation-v2-readiness.json retained_primary、replaced_primary；unity-development-replacement18-completion.json timing_context]`

## 像素审计与使用边界

精确RGBA重复9组，跨划分0组；同尺寸对齐RGBA RMSE≤2的近重复25对，其中跨划分11对。保留原划分及全部问题记录，没有自动删图。审计不覆盖裁剪、缩放或语义近重复，不能据此声称确认集完全独立；模型90%验收仍由后续V2执行。`[verified: unity-data-delivery-v3-verification.json pixel_audit、model_accuracy、v2_training_started；opinion: 审计与模型结论边界]`

实测指标代入原规则后，块大小、preset、选择原因及候选测量次数全部匹配；这是数据与规则复核结果，模型准确率仍为null。确认集只作采集与数据身份检查，模型评价未打开。后续训练须使用新版语料和新实验身份，不恢复已取消的V1正式训练队列。`[verified: unity-data-delivery-v3-verification.json exact_policy_replay、model_accuracy、test_opened；unity-data-handoff-v1.json training_auto_start；opinion: 后续实验使用约定]`

## 本次收尾检查

完整验收核对13000份参考PNG、11000份目标NPZ、清单和来源哈希，11个必需任务均成功退出；完整像素审计及新版成员关系通过。语料修订与新版像素检查的19项测试通过。数据goal的工具状态在仓库交付后关闭，历史验收快照中的`goal_tool_completion_pending`保留其生成时含义。`[verified: unity-data-delivery-v3-verification.json verified_reference_files、verified_development_target_files、processes、pixel_stage_cohort_membership_verified；2026-11-12 pytest输出“19 passed”]`
