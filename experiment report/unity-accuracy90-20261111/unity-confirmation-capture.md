# 独立确认集的原生参考与搜索标签采集入口

后续已新增[2000张串行采集入口](unity-confirmation-series.md)，绑定恢复后的smoke2-v2；两图真实预检成功后复用其结果，再采集剩余1998张。当前仅完成CPU与只读配置检查，原生全量采集和模型独立验收尚未完成。`[verified: unity-confirmation-series-readiness.json plan、dependency；opinion: 后续边界]`

当前使用[Sprite恢复后的smoke2-v2](unity-sprite-recovery.md)，原确认主名单前两项不变，绑定新依赖及当前补测源码；正在等待，没有新确认标签或模型测试。此前smoke2-v1因上游失败退出；下文v1排队记录为历史状态，当前见[v2报告](unity-confirmation-capture-smoke2-v2.json)。`[verified: 对应报告status、native_labels_collected、test_opened；opinion: 历史边界]`

独立入口已完成30项CPU检查和真实两图的只读配置核验，并启动等待队列。当前`waiting_dependencies`，尚未启动新的Editor、导出确认集参考图或运行模型预测。两图取自已冻结2000张主名单的前两项，不使用备用或压缩质量筛样。`[verified: unity-confirmation-capture-smoke2-v1.json status、images、native_labels_collected、test_opened；unity-confirmation-capture-readiness.json validation；unity-confirmation-capture-smoke2-v1-config.json start、images；本轮pytest30passed]`

## 独立身份与复用范围

[capture_unity_confirmation.py](../../script/capture_unity_confirmation.py)调用[UnityConfirmationCapture](../../reproductions/unity_search_baseline/confirmation_capture.py)，通过单独的`ConfirmationSearchBaseline`构造`confirmation`清单和原生批次协议。原开发入口继续仅允许train／validation；新入口不把确认集改名成开发数据，也不修改正在运行的开发采集源码。新清单只含源身份，准备阶段不需要blockSize、PSNR或训练类别。`[verified: confirmation_capture.py ConfirmationSearchBaseline.__init__、prepare；benchmark.py __init__；test_unity_confirmation_capture.py test_confirmation_does_not_weaken_development_constructor、test_prepare_has_explicit_confirmation_identity_and_no_quality_labels]`

实际执行复用原`UnitySearchBaseline.run`及其原策略审计、meta恢复，随后使用`UnityReferenceCapture.collect`归档参考像素和原winner，并使用`UnityOptionCapture.audit`核对真实回调参数。managed hook在同一工程锁内安装／恢复；原始失败、退出码和恢复记录保留。待实际Editor预检通过后，才能认定该新入口完成原生采集闭环。`[verified: confirmation_capture.py run；benchmark.py run、audit、restore_metadata；metadata.py audit；opinion: 实测验收边界]`

## 调度与冻结条件

两图任务绑定以下四项job，全部成功退出后才继续；每项都核对配置、进程身份和终态退出码。等待不初始化训练模型，也不提前安装hook。`[verified: unity-confirmation-capture-smoke2-v1-config.json dependencies；confirmation_capture.py run；native_data_pipeline.py dependency_status]`

| 前置任务 | 等待目的 |
|---|---|
| 原参考采集 | 共享Unity工程串行操作，保留开发集原搜索及恢复记录。`[verified: config.dependencies；opinion: 调度目的]` |
| 缺失候选补测 | 避免与开发集补测重叠。`[verified: config.dependencies；opinion: 调度目的]` |
| 完整数据四阶段核验 | 优先完成开发语料准备和审计。`[verified: config.dependencies；opinion: 调度目的]` |
| 首轮完整原生训练 | 将新确认集Editor采集排在该CUDA训练之后，减少运行干扰。成功训练不等于模型已达到90%。`[verified: config.dependencies；opinion: 调度及验收边界]` |

准备和执行前核对预留报告／配置、名单SHA、Editor及原DLL、实际源文件MD4／SHA和meta SHA。当前绑定15份执行源码；等待期间和结束时再次核对，活动任务期间禁止热改这些文件。源码变更应保留当前任务记录并以新身份重试。`[verified: unity-confirmation-capture-readiness.json source_files；confirmation_capture.py verify_bindings、verify_environment、verify_assets；opinion: 版本管理要求]`

取得原开发采集使用的同一个工程文件锁后，要求工程Editor已关闭、空闲RAM≥20GiB、相关卷空闲磁盘≥40GiB，才准备原生批次和安装hook。资源不足或来源改变时保留失败，不能删除活动锁或覆盖已有run／report。输出目录为`.local/unity-confirmation-capture-smoke2-v1/`，公开状态见[等待报告](unity-confirmation-capture-smoke2-v1.json)。`[verified: confirmation_capture.py run；collection.py project_lock；unity-confirmation-capture-smoke2-v1-config.json run_id、report、minimum_free_ram_gib、minimum_free_disk_gib]`

## 检查与扩展门槛

30项CPU检查覆盖新确认集协议及旧开发批次回归，包含源／meta变化、名单篡改、依赖失败、独占报告、工程锁、异常恢复、非batch拒绝和较大批次预检门槛。原生执行使用测试替身的检查只证明控制流，不替代真实Editor结果。只读真实两图配置核验用时0.108秒，未写入Unity工程。`[verified: 本轮pytest30passed；test_unity_confirmation_capture.py；unity-confirmation-capture-readiness.json validation、validation_seconds、reference_capture_started；opinion: 检查边界]`

超过两图的批次必须绑定已通过的两图smoke报告，并追溯同一预留名单、配置、执行源码和环境；重新核对原生退出码、meta及managed hook恢复、已有参考图归档和全部回调。只写一个`passed`摘要不能越过该门槛。入口最多接受主名单中连续256张，备用替换和完整2000张汇总仍需独立记录，当前没有自动启动全量确认集。`[verified: confirmation_capture.py __init__、validate；test_unity_confirmation_capture.py test_larger_batch_requires_matching_successful_smoke；opinion: 扩展范围]`

```powershell
uv run --frozen python script/capture_unity_confirmation.py --validate-only --config "experiment report/unity-accuracy90-20261111/unity-confirmation-capture-smoke2-v1-config.json"
uv run --frozen python script/run_reproduction_job.py --config "experiment report/.local/unity-accuracy90-20261111/jobs/unity-confirmation-capture-smoke2-v1/job.json"
```

第二条对应当前活动job，记录用于复跑说明，不应重复启动同一身份。实际阶段预计5–15分钟，依据历史validation2进程370.06秒外推；新资产、Editor刷新及I/O会影响耗时，等待时间和实际采集成本分开记录。`[verified: unity-confirmation-capture-readiness.json execution_estimate_seconds、estimate_basis；对应job receipt；opinion: 成本估计]`

最终还需确认集的导入后像素重复审计、完整标签覆盖、模型和决策冻结，以及独立预测、真实编码、质量／字节／成本评价。此任务只导出原始参考和搜索标签，`test_opened=false`指未打开模型评价；不将等待、CPU检查或两图采集当作90%验收。`[verified: confirmation_capture.py run state；opinion: 最终验收要求]`
