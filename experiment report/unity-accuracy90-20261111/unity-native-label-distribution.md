# Unity原生训练标签分布

已完成9,792张训练图的原始搜索标签统计，12×12占55.07%，其余三类各占13.75%–16.32%。类别确有不均衡，但本次没有模型预测，不能据此把中间类别识别差归因于配比，也不能估计最终准确率。正式训练保持冻结配置，待完整数据和验证结果后再决定采样或loss对照。`[verified: unity-native-labels9792-v1.json summary.block_counts、model_forward_calls；opinion: 因果与实验边界]`

## 数据与证据

本次使用[原始搜索记录的冻结统计](unity-native-labels9792-v1.json)，覆盖计划10,000张训练图中的9,792张，不包含尚未发布的最后208张。仅分析train；验证与确认标签分析数均为0，未读取图片、运行模型或新增编码。`[verified: 同文件 expected_train、summary.images、validation_labels_analyzed、confirmation_labels_analyzed、image_files_read、model_forward_calls]`

逐批核对冻结配置、参考图回执、实际回调参数回执、成功退出和metadata恢复记录；选参字段与原生JSONL逐项相同，源MD4与冻结训练清单相符。输入SHA、脚本路径／SHA及逐图派生记录SHA均在JSON中保留。此次核验对象是已发布记录，没有重新读取全部图片复核像素。`[verified: native_label_diagnostic.py NativeLabelDiagnostic.rows；unity-native-labels9792-v1.json inputs_sha256、script_sha256、rows_sha256、scope]`

## 类别、preset与选参分支

| 原搜索选中块大小 | 数量 | 占比 |
|---|---:|---:|
| 6×6 | 1,598 | 16.32%。`[verified: summary.block_counts、block_share]` |
| 8×8 | 1,456 | 14.87%。`[verified: 同上]` |
| 10×10 | 1,346 | 13.75%。`[verified: 同上]` |
| 12×12 | 5,392 | 55.07%。`[verified: 同上]` |

最大类约为最小类的4.01倍；全部预测12×12只能在这批训练标签上获得55.07%的匹配率。这个数是常量分类器的训练标签统计，不是验证准确率。8×8与10×10合计2,802张，后续需分别看召回和质量违规，不能只看总Top-1。`[verified: summary.largest_to_smallest_class_ratio、majority_class_training_accuracy、block_counts；opinion: 评价安排]`

| 块大小 | fastest | fast | medium | thorough | exhaustive |
|---|---:|---:|---:|---:|---:|
| 6×6 | 639 | 220 | 292 | 66 | 381。`[verified: summary.joint_counts.6x6]` |
| 8×8 | 258 | 96 | 571 | 386 | 145。`[verified: summary.joint_counts.8x8]` |
| 10×10 | 73 | 24 | 372 | 591 | 286。`[verified: summary.joint_counts.10x10]` |
| 12×12 | 1,874 | 92 | 1,101 | 1,386 | 939。`[verified: summary.joint_counts.12x12]` |

同一块大小对应多种preset。只预测块大小并统一采用某个preset，无法自动等同于原始策略选中的完整配置；仍须复算实际质量和编码成本。当前原生模型保留20候选质量输出与原规则决策。`[verified: summary.joint_counts；src/adaptive_astc/evaluation/unity_quality.py UnityQualityPrediction.GRID/select；opinion: 对照解释]`

| 选参分支 | 数量 | 说明 |
|---|---:|---|
| first_valid | 7,198 | 原记录中的常规首个合格候选。`[verified: summary.by_selection_reason.first_valid；policy.py select]` |
| size_first_strict | 1,757 | 原记录中的大图严格接受分支。`[verified: summary.by_selection_reason.size_first_strict；policy.py select]` |
| size_first_relaxed | 497 | 大图放宽分支，其中453张选12×12。`[verified: summary.by_selection_reason.size_first_relaxed]` |
| highest_psnr_fallback | 340 | 最高PSNR回退；338张选6×6，2张选8×8。`[verified: summary.by_selection_reason.highest_psnr_fallback]` |

因此6×6标签包含常规选择和回退两种情况，回退也并非全部选择6×6。分支计数不能直接替代逐图严格质量测量；标签匹配、规则接受和实际质量仍分开评价。`[verified: summary.by_selection_reason；opinion: 评价边界]`

## 用途、尺寸和资产目录

- 实际用途为Default／profile0共9,438张，Default／profile1共50张，NormalMap／profile1共299张，Sprite／profile0共5张。这里按导入器用途与实际profile联合分组。全部回调的`normal_pack`均为false，因此不能以该编码参数判断纹理是否为法线图。`[verified: summary.by_usage、encoder_normal_pack_flag；opinion: 字段使用边界]`
- NormalMap的四类数量为99／78／40／82，与全体类别分布不同；完整训练后的法线角度质量须单独评价。本次299张只描述该训练快照。`[verified: summary.by_usage.NormalMap/profile1；opinion: 评价范围]`
- 按导入后长边分为≤128、129–256、257–512、513–1024、>1024，数量为4,379／2,449／1,927／809／228；最后一组有220张选12×12。JSON中的`le256`等字段表示互斥区间，不是累计计数。尺寸关联同时受到像素内容与原规则分支影响，不能解释为尺寸单独决定标签。`[verified: summary.by_long_side；native_label_diagnostic.py summarize bucket；opinion: 因果边界]`
- 本次以资产路径的直接父目录分组，共2,282组，最大目录`Effects/Texture/Common/Special/SD`有1,206张。此定义保留SD／HD／FHD目录，不能直接与早期GDC报告的资产族计数作比较，也没有自动转成训练采样权重。`[verified: summary.asset_group_count、largest_groups；native_label_diagnostic.py summarize；opinion: 分组与训练边界]`

原搜索每图尝试候选的均值为7.66、中位数为5；388张尝试20组，其余图尝试更少。共记录74,965次候选测量，说明原搜索标签完成与20候选训练目标补测完成需要分别记录。这是采集记录统计，不是无插桩搜索baseline计时，也没有重跑搜索。`[verified: summary.candidate_attempts；unity-reference-series.json scope；opinion: 数据与计时边界]`

## 下一步与复跑

继续等待完整原生训练／验证采集和20候选补测，按冻结配置先完成第一轮CUDA训练。根据同一最佳权重的逐类召回、用途、尺寸及回退分支误差再设计单项对照；这份统计不触发正在运行任务的配置变更。`[opinion: 执行安排]`

分析脚本和冻结snapshot均归档于`experiment report/.local/unity-accuracy90-20261111/`；复跑时使用新输出目录和报告，原始snapshot保留。JSON中的`script`、`inputs_sha256`和`rows`给出本机实际位置及来源。`[verified: unity-native-labels9792-v1.json script、inputs_sha256、rows；native_label_diagnostic.py main]`

```powershell
uv run python -u "experiment report/.local/unity-accuracy90-20261111/native_label_diagnostic.py" `
  --snapshot "experiment report/.local/unity-accuracy90-20261111/unity-native-labels9792-v1-snapshot.json" `
  --config "experiment report/.local/unity-accuracy90-20261111/reference-series-plan-v2/complete.json" `
  --output "<新的逐图产物目录>" --report "<新的汇总报告路径>"
```

Verification: ruff format／check、basedpyright通过；9,792条记录的来源、选参、范围与唯一性断言通过；V1原始证据SHA保持。未进行新训练、模型评价或图片质量重算。`[verified: 本轮检查输出；unity-native-labels9792-v1.json]`
