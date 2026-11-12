# 独立确认集评价入口

已实现完整2000张预留确认图的评价入口，75项CPU检查及已有66图报告的字段一致性核验通过。当前没有运行确认集模型推理；正式原生训练仍等待开发数据，2000图采集和完整像素审计也未完成。此交付是评价代码与前置检查，不是90%准确率结果。`[verified: unity-confirmation-evaluation-readiness.json cpu_tests、real_report_schema、live_reports、test_opened；opinion: 完成边界]`

## 准入与数据边界

- 训练须完成完整10000／1000原生开发数据，已选最佳权重、验证预测和决策记录均与训练回执绑定；smoke模型、训练子集、未完成训练及曾打开测试的训练记录被拒绝。实际旧smoke8报告已触发预期拒绝。`[verified: confirmation_evidence.py validate_training/model；readiness.json smoke_model_rejected]`
- 新增开发集准入条件：同一个选中权重在1000张验证图上Top-1至少90%，再打开确认集。该条件用于避免拿确认集反复选模；验证达标不代表独立测试必然达标，也不替代质量评价。`[verified: confirmation_evidence.py validate_training；opinion: 准入设计及解释]`
- 原始采集与精确／近重复检查必须覆盖10000训练、1000验证、2000确认图；开发图必须与模型训练语料的参考像素、callback哈希和原选参一致。确认图必须与预留主名单及各批次原采集顺序一致，跨开发／确认划分的精确RGBA或已检测近重复会阻止推理，保留原名单供调查。`[verified: confirmation_evidence.py pixel_audit/captures/overlaps]`
- 近重复报告只保留精确报告的九字段投影。比较按这些字段及原行顺序进行，不能直接比较完整字典；已用实际64训练／2验证图的两份完成报告核验兼容性。这66图没有确认样本，不证明完整确认集隔离。`[verified: near_duplicates.py rows；readiness.json real_report_schema；opinion: 覆盖边界]`
- 隔离范围仍是预留资产组／源哈希、当前原生像素的精确RGBA及同尺寸同坐标近重复；历史裁剪、缩放与语义近似未获完整证明。`[verified: confirmation_evaluation.py run state.cohort_isolation_scope；opinion: 证据边界]`

## 固定模型、失败重试与完整输出

首次forward之前，使用按预留主名单身份索引的共享封存目录，固定权重、输入、原生策略、决策参数、运行库及来源文件。更换输出目录不能切换模型或规则重新打开同一确认集。`[verified: confirmation_evaluation.py run contract；unity_evaluation_seal.py acquire]`

每次执行使用新的产物目录和公开报告。技术失败后可用相同协议的新目录重试，旧失败产物和尝试记录保留；协议指纹排除的只有output／report位置，其余配置内容全部封存。当前尝试的完整配置另以SHA绑定，在执行前后核验，已有输出禁止覆盖。CPU检查覆盖失败后重试成功及更改preset后被拒绝。`[verified: confirmation_evaluation.py __init__/seal_files/run；tests/test_unity_confirmation_evaluation.py test_failed_attempt_can_retry_only_same_protocol_at_new_output]`

评价按最多8图一批执行一次预热、三次正式重复，预测后编码与固定8×8对照交替先后顺序；每轮每个分支每图只编码一次，再进行ASTC解码与原生质量测量。完整四轮结束后才写最终质量和准确率汇总，进度只记录数量与最近分批回执。`[verified: confirmation_evaluation.py evaluate；capture_output.py run]`

最终报告绑定`outputs.json`的SHA；清单按顺序绑定全部分批回执和`repetitions.json`，各分批回执再绑定预测数组、ASTC、解码PNG及逐图质量结果。结束前复核完整覆盖与所有产物，CPU检查覆盖首批回执、首批ASTC、重复统计和清单成员被修改时的拒绝。`[verified: confirmation_evaluation.py verify_outputs/evaluate；tests/test_unity_confirmation_evaluation.py test_chunked_trial_counts_orders_and_measured_quality]`

## 指标与成本

正式输出包括块大小Top-1、完整blockSize＋preset匹配、逐类结果、实际解码质量达标、payload、原搜索耗时，以及预测／固定8×8两条路径的三次配对计时；模型参数量和权重buffer张量字节单列。逐批记录保留输入准备、推理、决策和原生编码的分阶段时间。`[verified: confirmation_evaluation.py evaluate/run；capture_output.py summarize；deployment.py run timings]`

计时范围是参考PNG到内存mip0 ASTC，模型／DLL加载单列或位于计时外，解码评分及产物写入位于两个分支计时之后；完整mip链与Unity导入集成尚未完成。只真实编码选中候选，所以近阈值误差只覆盖被选颜色候选，20候选整体RMSE保留为空。`[verified: confirmation_evaluation.py run state.cost_scope；capture_output.py summarize；opinion: 验收范围]`

## 运行与当前状态

[入口](../../script/evaluate_unity_confirmation.py)、[前置证据核验](../../reproductions/unity_search_baseline/confirmation_evidence.py)、[执行与产物校验](../../reproductions/unity_search_baseline/confirmation_evaluation.py)、[只读检查记录](unity-confirmation-evaluation-readiness.json)。正式配置必须绑定完成产物的实际SHA；当前没有生成可运行正式配置，也没有排队打开确认集。`[verified: 对应实现；readiness.json formal_confirmation_ready、model_forward_calls；opinion: 启动边界]`

配置需包含：`split=confirmation`、`images=2000`、`warmups=1`、`repetitions=3`、1–8的`image_chunk_size`、明确的`fixed8_preset`、新`output/report`、`execution_sources()`取得的`sources_sha256`、`quality_build`的path／sha256，以及`training`和`pixel_audit`各自的config／report（path、sha256）和job（job_config、sha256）。training必须绑定实际`train_unity_quality.py`的正式job，不能绑定等待训练的队列job。`[verified: confirmation_evaluation.py __init__/validate_config/quality；confirmation_evidence.py model/pixel_audit/job]`

```powershell
uv run python script/evaluate_unity_confirmation.py --config "<已完成证据绑定的配置绝对路径>"
```

截至2026-11-12 03:25 UTC的只读快照：原参考图／标签完成9792训练＋2验证图；全候选补测完成8768训练＋2验证图。七个上游／等待进程身份均已核验，正式训练等待数据、确认采集0图。活动任务冻结的14／23／15／17／25份源码及V1原始evidence SHA保持，后续以检查记录时间戳为准。`[verified: unity-confirmation-evaluation-readiness.json verified_utc、live_reports、jobs、unchanged_active_sources、v1_evidence_sha256]`

Verification: 75项相关CPU检查通过；ruff format／check和basedpyright通过；实际66图报告读取、smoke模型拒绝、活动源码及V1哈希核对通过；本地链接与锚点结果见readiness.json local_links。没有进行真实2000图推理或新增CUDA训练。`[verified: 本轮检查输出；unity-confirmation-evaluation-readiness.json]`
