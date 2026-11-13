# 修订确认集的原生采集与完整像素复审

## 结果

用户批准的10个位置已完成替换与Unity原生补采，确认主名单为2000张，其中1990张复用原采集记录，备用名单余431张。完整10000／1000／2000图的精确RGBA和同尺寸对齐RGBA近重复复审通过，检测到的跨划分关系均为0。结构化结果见[数据交付结果](confirmation-cohort-v3-result.json)。`[verified: confirmation-cohort-v3-result.json status、counts、replacements、retained_confirmation_images、reserves_remaining、exact_rgba_cross_split_groups、near_identity_pairs_cross_split]`

检查命令、来源归档、运行guard和独立复核结果保存在[验收记录](confirmation-cohort-v3-verification.json)。`[verified: confirmation-cohort-v3-verification.json focused_cpu_tests、data_source_archive、protocol_source_archive、independent_data_review]`

| 核验项 | 实际结果 |
|---|---|
| 原位置与冻结备用顺序 | 替换位置为25、29、59、168、760、1314、1371、1384、1549、1732，依次使用原备用前10张。`[verified: confirmation-cohort-v3-result.json approved_primary_positions_one_based；confirmation2000-near-revision-v3.json replacements]` |
| 源资产身份与准入 | 2441份当前主名单／备用源资产检查通过，修订10张、保留1990张、备用余431张。`[verified: confirmation2000-near-revision-v3.json inspected_sources、replaced_primary、retained_primary、reserve_images]` |
| 新采集 | 实际分为1＋2＋7图三批，候选编码回调57次，原搜索实测候选合计57次。三批managed源码恢复收据均通过。`[verified: confirmation-cohort-v3-result.json new_native_capture_batch_sizes、new_native_candidate_callbacks、new_native_original_candidates_measured；三批采集报告managed_source_restoration]` |
| 完整确认采集来源 | 原9批与新3批共12批，111份实际规则来源文件与24个合法缺失可选项通过核验，2000个origin唯一对应实际归档。`[verified: confirmation2000-near-capture-v4.json native_batch_receipts_verified、native_policy_source_files_verified、native_policy_optional_absent_verified、used_images_per_batch；对应manifest.origins]` |
| 开发语料 | 11000张开发像素记录逐字段保持，语料SHA为`560094e9d87b220b037ed37574e5941f0eff0675ffb43f34737f904e1f895c57`。`[verified: confirmation-cohort-v3-result.json development_corpus；独立metadata复核all_development_pixel_rows_field_exact=11000]` |
| 精确RGBA | 13000张逐图重算，12991个唯一身份、9个重复组、跨划分重复组0。`[verified: confirmation-revised-pixels13000-v3.json counts、rgba]` |
| 近重复 | 全尺寸RGBA、同尺寸同坐标、RMSE≤2/255，共14条内部关系，训练6条、验证2条、确认6条，跨划分0。`[verified: confirmation-revised-near13000-v3.json near_identity_pairs、cross_split_near_identity_pairs；独立near_pair_splits复核输出]` |
| 原生输入 | 修订后2000张确认图通过实际回调、导入属性与RGBA像素投影验证，输入指纹保存在完整精确审计报告。`[verified: confirmation-revised-pixels13000-v3.json native_confirmation_input_images、native_confirmation_input_fingerprint]` |
| 模型与训练 | 模型forward、训练更新和正式确认模型评价均为0，test_opened=false。完整精确审计的模型构造、优化器及CUDA初始化guard计数也为0。`[verified: confirmation-cohort-v3-result.json model_forward_calls、training_updates、formal_confirmation_model_evaluations、test_opened；jobs/confirmation-revised-pixels13000-v3/guard.json]` |

此次独立隔离证据覆盖原生精确RGBA与同尺寸对齐RGBA近重复筛查，报告沿用`independent_test_isolation_proven=false`的范围限定。`[verified: confirmation-cohort-v3-result.json scope、independent_test_isolation_proven]`

## 执行成本

| 阶段 | 实际耗时 |
|---|---|
| 范围修订与2441份源检查 | 57.08秒。`[verified: confirmation2000-near-revision-v3.json wall_seconds]` |
| 新10图原生采集 | Editor进程合计691.00秒，采集内部wall合计718.43秒。`[verified: confirmation-cohort-v3-result.json new_native_capture_editor_seconds、new_native_capture_internal_wall_seconds]` |
| 首次完整来源重组 | 348.61秒，以合法缺失可选来源的FileNotFoundError结束，原报告、源码与guard保留。`[verified: confirmation2000-near-capture-v3.json wall_seconds、error；confirmation2000-near-capture-v3-guard.json]` |
| 修正后的完整来源重组 | 291.20秒，12批核验通过。`[verified: confirmation2000-near-capture-v4.json wall_seconds、native_batch_receipts_verified]` |
| 完整精确像素及2000图输入投影 | 内部231.54秒，完整进程234.38秒。`[verified: confirmation-revised-pixels13000-v3.json wall_seconds；对应job receipt.wall_seconds]` |
| 完整近重复复审 | 内部210.08秒，完整进程210.78秒。`[verified: confirmation-revised-near13000-v3.json wall_seconds；对应job receipt.wall_seconds]` |

## 实现修正与来源保留

- 原拟逐张启动10次Editor。首图实际Editor耗时375.21秒后，剩余9张采用有父名单绑定的采集子清单，执行2图预检与7图批次，共完成1＋2＋7图采集。子清单的9行逐字段对应完整主名单的批准位置。`[verified: confirmation-near-v3-capture-plan-v4.json；confirmation-replacement-capture-selection9-v3.json parent_primary_indices_zero_based；三批实际capture报告]`
- C16补齐像素档案与原生采集行的六项属性交叉核验，profile／sRGB及need_alpha矛盾的拒绝回归通过。首版合成预检与7份来源按原SHA归档。`[verified: confirmation_revision_pixels.py observed比较；tests/test_unity_confirmation_revision_pixels.py observed_profile、observed_alpha；confirmation-pixels-before-c16/manifest.json]`
- C17将实际文件SHA与合法缺失来源分别核验，缺失项后来出现时拒绝。C18补齐原UnitySearchPolicy源码SHA并固定21份执行来源。修正后的独立身份完成完整重组，原失败轮次保留。`[verified: assemble_confirmation_near_revision_v4.py verify_file_bindings、execution_sources；confirmation2000-near-capture-v4.json；confirmation2000-near-capture-v3.json]`
- 当前确认集数据访问按用户本次授权执行，模型评价计数为0。最初只读身份核验中曾额外显示首条原选参字段，修订选择依据持续为既有像素关系和冻结备用顺序。`[verified: confirmation-scope-revision-approval-v3.json；confirmation-identity-metadata-review-v1.json initial_structure_preview_included_first_capture_native_selection、selection_uses_model_predictions_quality_or_native_labels；confirmation-cohort-v3-result.json]`

## 系统确认协议接入

新增入口为`script/evaluate_unity_revised_forward_confirmation.py`，复用已冻结的ResNet34原始预测＋B1候选索引起点续搜执行器。来源适配读取修订后的12批原生上下文，并沿用原v2预留cohort的共享封存身份；v3输入、规则、协议及完整来源另行绑定。`[verified: revised_forward_confirmation.py；revised_confirmation_evidence.py pixel_audit、captures；confirmation_evaluation.py contract.cohort_fingerprint、inputs_fingerprint、files_sha256]`

新准备配置的正式执行开关为false。公开准备入口已通过，绑定2000张确认图、12个原生规则上下文与完整来源，内部177.75秒、完整进程181.96秒。模型构造／forward、优化器构造、编码器构造、CUDA初始化及检查点反序列化六项guard计数为0。`[verified: forward-system-protocol-config-v4.json confirmation_execution_authorized；forward-system-protocol-readiness-v4.json；jobs/forward-system-protocol-prepare-revised-v4/guard.json、receipt.json]`

C19补齐采集报告配置SHA与guard源码SHA的交叉绑定，针对性回归通过。156项相关CPU检查通过，生产代码与测试目录ruff、全仓basedpyright通过。无参数ruff还扫描到并发新增的`tmp/pdfs/chat-export-20261113`脚本并报34项诊断，检查范围已在验证记录中单列。`[verified: revised_confirmation_evidence.py validate_capture_execution；tests/test_unity_revised_confirmation_evidence.py test_capture_execution_cross_binds_report_config_and_guard_source；本轮pytest、ruff、basedpyright输出]`

```powershell
uv run python script/evaluate_unity_revised_forward_confirmation.py --config "experiment report/unity-v2-20261112/forward-system-protocol-config-v4.json" --prepare-only
```

该配置的准备报告使用独占新身份创建，上述入口的本轮结果已保存。后续正式确认执行需取得单独授权并使用新的实际执行配置，训练更新保持0。`[verified: forward-system-protocol-readiness-v4.json execution_authorized、formal_confirmation_ready、pending；revised_forward_confirmation.py prepare；forward_confirmation.py run]`
