# 原生RGBA同尺寸近重复筛查

对冻结的7744张训练图和2张验证图，按原生尺寸、相同像素坐标及完整RGBA计算距离。固定阈值为8位数值RMSE≤2，即归一化后的2/255；找到6对数值接近候选、共12张图，全部在训练集内。此次未修改划分、删除图片、运行模型或打开确认集测试。`[verified: unity-near-duplicates-completed7746-v1.json counts、rgba_rmse_8bit、near_image_pairs、test_opened、splits_modified；unity-near-duplicates-verification.json results.completed7746.near_pair_unique_images、image_pair_split_counts]`

## 结果与范围

| 检查项 | 结果 |
|---|---|
| 输入与精确重复 | 7746张图、7741个精确RGBA像素身份；沿用此前5组精确重复，不重复计入近重复配对。`[verified: unity-near-duplicates-completed7746-v1.json counts、unique_rgba_identities、exact_duplicate_groups]` |
| 可比较范围 | 全部像素身份有29,957,670对，其中7,363,957对尺寸相同；本次仅处理后者。`[verified: 同文件 all_identity_pairs、eligible_identity_pairs]` |
| 分格均值过滤 | 检索出92对候选，92对均计算完整原生像素误差，6对满足阈值。`[verified: 同文件 retrieved_candidate_pairs、measured_candidate_pairs、near_identity_pairs]` |
| 跨划分情况 | 6对均为train＋train，当前两张validation未发现满足本次判据的配对。完整validation1000和confirmation2000尚未覆盖。`[verified: unity-near-duplicates-verification.json results.completed7746.counts、image_pair_split_counts；opinion: 覆盖限制]` |
| 独立重算 | 对6对结果用float64数组直接计算全图RMSE，与报告差异为0。`[verified: unity-near-duplicates-verification.json independently_recalculated_pairs、max_rmse_difference；归档verify_near_duplicate_stage.py recalculate_pair]` |
| 耗时 | 66图预检：内部2.32秒／进程2.99秒；7746图：内部121.48秒／进程122.28秒。只有CPU及文件读取成本。`[verified: unity-near-duplicates-verification.json results.*.internal_seconds、process_seconds；任务回执scope]` |

**这些是数值接近候选，不能直接认定为同一素材的复制。** 六对中的最大单通道差分别可达8至110个8位数值级别；全图RMSE较小仍可能掩盖局部差异。本次筛查不作语义判断，也不据此解释模型准确率或自动排除样本。`[verified: 原始near-duplicates.json near_pairs.maximum_absolute_error_8bit；opinion: 解释与处置边界]`

## 判据与实现

距离定义为所有位置、所有RGBA通道的等权RMSE：`sqrt(sum((A-B)^2)/(4*width*height))`。包含透明区RGB及Alpha，不做缩放、裁剪、旋转或颜色变换，尺寸不同的图不比较。该阈值是本次数据诊断设置，不改变Unity/GDC质量目标或选参标签。`[verified: near_duplicates.py UnityAlignedPixelDistance.measure；冻结配置rgba_rmse_8bit；opinion: 阈值用途]`

预过滤将每个通道分成最多8×8个区域，计算按区域像素数加权的均值距离。它在实数计算下是全图RMSE的下界，因此用于排除明显不满足阈值的配对；边缘区域按实际像素数计算。KDTree使用精确检索eps=0和1e-9检索容差，最终判据仍对完整像素使用原阈值2。均值相近但像素不同的情况必须经过最终计算，测试中包含均值完全相同而RMSE为255的反例。`[verified: near_duplicates.py descriptor、candidates、measure；test_unity_near_duplicates.py test_weighted_cell_distance_is_a_lower_bound_even_at_uneven_edges、test_full_resolution_check_rejects_equal_cell_means；opinion: 下界解释]`

读取SHA绑定的已完成精确像素审计及其来源回执，逐张复查PNG哈希、原生尺寸和解码RGBA身份。精确重复先合并为像素身份，比较后再统计对应图片对；监督标签不进入筛查输入。运行结束再次核验输入文件，候选预算超限则失败，禁止以部分结果标记通过。`[verified: near_duplicates.py rows、load、verify、run；test_unity_near_duplicates.py 对应证据变化与预算用例]`

47项相关CPU测试通过，覆盖距离下界、穷举配对、Alpha与整数溢出、阈值边界、尺寸不同、来源变化、划分保持和输出保护。代码复核通过；实际6对匹配另完成独立数值重算。`[verified: pytest tests/test_unity_near_duplicates.py tests/test_unity_pixel_identity.py 47 passed；本轮代码复核No bugs found；unity-near-duplicates-verification.json]`

## 文件与复跑

- [66图配置](unity-near-duplicates-smoke66-v1-config.json)与[预检结果](unity-near-duplicates-smoke66-v1.json)。`[verified: 对应JSON config_sha256、counts、status]`
- [7746图配置](unity-near-duplicates-completed7746-v1-config.json)、[完整结果](unity-near-duplicates-completed7746-v1.json)和[核验记录](unity-near-duplicates-verification.json)。原始逐图身份、配对索引、各通道误差及日志保存在对应`.local`目录，公开报告保存其SHA。`[verified: 对应JSON details、details_sha256、process_receipt_sha256]`
- 入口：`uv run python script/audit_unity_near_duplicates.py --config <新配置>`。新配置绑定精确像素审计、5份源码／依赖文件和实际库版本，使用新的公开report及`.local`输出；既有输出拒绝覆盖。`[verified: audit_unity_near_duplicates.py main；near_duplicates.py execution_sources、runtime、run]`

这是同尺寸、同坐标、低像素RMSE的有限筛查，没有缩放、裁剪、旋转或语义近重复保证，也未覆盖历史全部模型输入。`independent_test_isolation_proven`继续为false；最终独立确认集还需完整范围的隔离审计、模型与决策冻结，以及真实质量／字节数／完整成本验收。V1原始证据及活动队列的14／23／15／17份源码绑定未改变。`[verified: unity-near-duplicates-completed7746-v1.json scope、independent_test_isolation_proven；unity-near-duplicates-verification.json unchanged_active_sources、v1_evidence_sha256；opinion: 后续验收边界]`
