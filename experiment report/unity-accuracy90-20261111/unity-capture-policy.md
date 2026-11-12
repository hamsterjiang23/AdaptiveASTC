# 原始Unity采集记录的规则来源绑定

新增 `UnityCapturePolicyBinding`，直接读取完成的原始采集回执、原生搜索记录与参数缓存，构造对应的 `UnitySearchPolicy`，不依赖候选补测目录。64张训练图与2张验证图的真实记录核验通过；此次只验证规则来源与选参记录的一致性，没有模型forward、重新编码或独立确认集评价。`[verified: capture_policy.py UnityCapturePolicyBinding.__init__；unity-capture-policy66-v2.json status、bindings、model_forward_calls、scope]`

## 核验范围

- 绑定参考回执、完成回执、原采集配置、身份、协议、启动记录、源清单、原生搜索日志、Editor和编码DLL的SHA。要求进程成功、metadata恢复无冲突，重新执行原生baseline审计并与两份回执的provenance比对。`[verified: capture_policy.py UnityCapturePolicyBinding.__init__；benchmark.py audit]`
- 同时绑定参数缓存的JSON快照与JSONL追加日志；缺失文件的状态也保留，后续出现同名文件会拒绝继续使用。恢复批次另绑定assembly引用的输入与输出，避免构造后证据变化未被发现。`[verified: capture_policy.py watch_optional、verify；test_unity_capture_policy.py test_snapshot_and_journal_are_both_bound、test_recovery_evidence_changes_after_binding_are_rejected]`
- 核对参考图记录、缓存和原生选择的资产集合、顺序、源MD4、块大小、preset及真实搜索标志。保留train／validation／confirmation身份；历史训练回执缺少逐行split时仅按train兼容，并单列数量，验证集与确认集仍要求显式split。`[verified: capture_policy.py UnityCapturePolicyBinding.__init__；test_unity_capture_policy.py test_legacy_missing_split_is_only_compatible_with_train]`
- 原生缓存表与转换为float32后的有效规则表分别保存指纹。调用方使用前可执行 `verify()` 复查来源文件和有效规则未变化；本入口不替代参考像素隔离、完整采集恢复审计或模型封存。`[verified: capture_policy.py binding、verify；opinion: 独立评估接入边界]`

## 真实开发数据结果

| 采集批次 | 范围 | 结果 |
|---|---|---|
| `unity-actual-options64-20261111`／smoke1 | train64，64条历史记录无逐行split | 原始规则和搜索选择绑定通过。`[verified: unity-capture-policy66-v2.json bindings[0]]` |
| `unity-validation2-20261111`／batch | validation2，均有显式split | 原始规则和搜索选择绑定通过。`[verified: unity-capture-policy66-v2.json bindings[1]]` |
| 合计 | 66张开发图、两个采集阶段、18份执行源码绑定 | 内部核验1.03秒，含进程启动4.23秒，退出码0。`[verified: unity-capture-policy-verification.json counts、source_files_sha256、internal_seconds、process_seconds；任务receipt process_exit_code]` |

两批原生规则表一致：基础PSNR 30 dB、MS-SSIM 21 dB，黑像素分档PSNR 35／37 dB，法线mean／p95门槛3.2°／9°，大图size-first面积门槛512² texel，RDO关闭。这是当前冻结的Unity LITE配置；GDC开发实验的35 dB协议另行保留。有效规则中的部分小数按C++ float32精度转换，原表与有效表均保存在报告中。`[verified: unity-capture-policy66-v2.json bindings native_table、policy_table；benchmark.py audit required；policy.py UnitySearchPolicy.__init__/select；experiment plan/V1/README.md“目标与开发数据”]`

## 首次失败与修复

首次 `unity-capture-policy66-v1` 在遇到历史train64回执缺少 `source_split` 时以 `KeyError` 退出，未产生通过记录。按既有采集器对历史train的处理补齐兼容，同时增加遗漏validation／confirmation时拒绝的用例；使用新的v2配置和输出重跑。v1配置、失败报告、原进程日志与当时源码均保留，后续核验检查其SHA。`[verified: unity-capture-policy66-v1.json error、status；collection.py verify_batch；unity-capture-policy-verification.json prior_failure]`

44项相关CPU测试通过，其中新增入口29项；覆盖来源变化、划分错误、缓存快照／追加日志、恢复证据变化、probe及历史train兼容。confirmation／probe／恢复assembly分支目前在本入口内由合成测试覆盖；本次真实运行仅覆盖上述train64和validation2。没有把该核验计作模型准确率、质量提升或90%验收。`[verified: pytest tests/test_unity_capture_policy.py tests/test_unity_search_policy.py 44 passed；独立复核新入口29 passed；unity-capture-policy-verification.json scope；opinion: 结果边界]`

## 文件与复跑

- [冻结配置](unity-capture-policy66-v2-config.json)、[真实绑定结果](unity-capture-policy66-v2.json)、[核验记录](unity-capture-policy-verification.json)。`[verified: 对应JSON config_sha256、bindings、report_sha256]`
- [首次配置](unity-capture-policy66-v1-config.json)与[首次失败报告](unity-capture-policy66-v1.json)保留失败来源。原始进程日志及旧源码归档在本实验的 `.local/`。`[verified: unity-capture-policy-verification.json prior_failure]`
- 入口：`uv run python script/audit_unity_capture_policy.py --config <新配置>`。配置显式区分development和confirmation采集，绑定来源回执与执行源码；新运行使用新report路径，拒绝覆盖既有报告。`[verified: audit_unity_capture_policy.py main；capture_policy.py UnityCapturePolicyAudit.baseline、verify、run]`

活动数据、训练、确认采集及串行队列的14／23／15／17份源码绑定、V1原始evidence哈希保持一致；六个后台任务的进程身份在本次核验时仍有效。最终独立评估还需完成原生数据采集、像素隔离、模型与决策冻结、真实预测及最终编码测量。`[verified: unity-capture-policy-verification.json unchanged_active_sources、v1_evidence_sha256、jobs；opinion: 剩余验收]`
