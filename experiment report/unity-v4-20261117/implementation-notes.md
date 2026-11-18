# V4实施记录

## Deviations

- 执行日志、状态和来源绑定使用独立V4目录。当前处于策略实现与开发档案重放阶段。`[opinion]`
- 本机pueue CLI未找到，长任务使用仓库现有ReproductionJob串行运行，保存进程回执和stdout／stderr，后台窗口隐藏。`[verified: launch-preflight-development-v2.json scheduler；development-v2/job.json]`

## Discovered edge cases

- exhaustive直接起搜时，门控需要测量序列前一项thorough。该探测纳入真实查询计数和当前图片缓存。`[verified: v4_policy.py UnityV4Policy.search gate分支]`
- 删除跨块前瞻只适用于已经锁块的退出，最高PSNR回退所需测量保持完整。`[verified: v4_policy.py UnityV4Policy.search locked分支]`
- 起点预筛最高匹配方案相对V3严格回退1张。按既定预筛排序保留该独立对照，最终推荐阶段执行严格回退0张要求。`[verified: offline.json selected_start.metrics；matrix.json recommendations]`
- 首次32图闭环通过后，完善来源绑定、恢复核查和类型标注，使用v2身份再次闭环后进入完整计时。`[verified: smoke32-v1/result.json；script/execute_unity_v4.py main]`
- v2首次逐图计时在开发图901的查询轨迹核查失败。批量／逐图预测的6×6 fastest PSNR为30.0008／29.9913 dB，最终均选同一6×6 fast。旧核查强制对齐冻结批量预测，已修正为用每轮实际预测重放并审计当轮轨迹。冻结预测继续用于参数选择，差异单列记录。`[verified: runtime-mismatch901-diagnosis.json；v4_benchmark.py audit]`
- 真实基线按相同scope、mode和repeat配对，重复输出一致性按相同输入模式检查。v2源码、失败回执和已完成三轮批量结果保留，v3重新执行完整矩阵。32图闭环加入图901，并覆盖四种输入模式。`[verified: v4_benchmark.py _run；failed-execution-sources/manifest.json；v4_experiment.py select_smoke]`

- 最终解读入口补充分段耗时、四口径三重复统计、推荐方案分组和混淆矩阵，并完成9000行CSV与实际轨迹、质量及逐图延迟核对。完整108单元、216000份原生产物、108000份payload几何核查通过，七份派生产物重建后SHA一致。前期8组聚合及合成结构检查保留。`[verified: script/finalize_unity_v4_report.py finalize、write_report；report-finalizer-precheck.json；complete-artifact-audit.json；delivery-verification.json；report-rebuild-verification.json]`

- 起点扫描中PSNR／MS-SSIM补偿1／0.5 dB的离线块匹配为96.7%、相对V3严格回退0张；按既定匹配率排序，正式矩阵选用1／1 dB。报告保留全部19项扫描及已测方案边界。`[verified: offline.json start_scan、selected_start]`
- 门控已完成文件输入批量及逐图三轮，平均耗时的三轮中位数分别185.73／212.52 ms，严格通过率均87.5%、严格回退0张。首轮47张跳过图的MS-SSIM平均下降0.270 dB、最大下降2.184 dB，作为连续质量代价单列。`[verified: gate-files-scope-summary.json；gate-first-native-quality.json]`

- 开发图226为6×6终点，next_block与proposed_payload_bytes为空。一次性预算检查在此触发TypeError，按终点分支修正后，2000份实际payload尺寸、1000条唯一候选轨迹及92个解锁事件核查通过。独立验收入口补充终点、预算禁止、失败保留和ASTC容器字节数核验。`[verified: unlock-first-native-budget-audit.json；script/verify_unity_v4.py]`
- 首轮真实大图解锁出现75次预算允许的尝试，52次成功替换、23次失败保留，另有16次预算禁止和1次6×6终点。相对V3新增52张严格合格，实际payload增加1,093,680字节。`[verified: unlock-first-native-budget-audit.json]`

- 候选缓存命中由门控probe_cached标记和解锁前瞻复用轨迹重建，最终payload复用单列。真实1000图的主搜索轨迹配对一致，310次解锁候选请求对应235次新增实际编码及75次缓存命中。逐图CSV已补充缓存字段并保留原CSV摘要，全部9000行共35列完成核验。`[verified: cache-reuse-precheck.json matched_native_unlock_check；script/finalize_unity_v4_report.py candidate_cache_reuse、finalize；delivery-verification.json；verification.json original_per_image_csv_sha256]`

- 终稿一次性结构检查把CSV布尔字段selected_payload_reused按文本1比较，实际9000行均使用True。修正检查条件后，九组覆盖、缓存合计、117行表格列数、七个本地链接和两份新确认协议全部通过，原生测量保持原身份。`[verified: delivery-audit-checker-recovery.json；delivery-verification.json]`
- 删除前瞻的逐图平均耗时降低0.49%，批量平均摊销从201.96升至218.25 ms，逐图P95从656.91升至669.16 ms，报告保留四口径波动。大图解锁在1780×1000三张图上均补救失败，平均耗时升至7274.04 ms。`[verified: interpretation.json controls.v3_baseline、controls.remove_lookahead；summary.json controls.bounded_unlock.groups.resolution_1780x1000]`

## Questions for review

V4开发实验与两份独立确认协议准备已完成，新资产名单及原生采集身份等待后续绑定。`[verified: delivery-verification.json；confirmation-protocol-compatibility.json status、new_cohort；confirmation-protocol-quality.json status、new_cohort]`
