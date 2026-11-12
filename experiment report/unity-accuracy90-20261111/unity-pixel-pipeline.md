# 完整开发集与确认集的像素审计队列

原生像素审计已接入采集完成后的等待队列。当前完成真实64训练／2验证图检查，全量10000训练／1000验证／2000确认图任务处于`waiting_captures`；完整确认集像素隔离与模型90%验收仍未完成。`[verified: unity-pixel-pipeline-verification.json smoke、full_queue；opinion: 验收边界]`

| 项目 | 本轮实际状态 |
|---|---|
| 真实开发小样本 | 66图归档复核、精确RGBA身份和同尺寸同坐标近重复检查通过；0组精确重复、0对近重复。`[verified: unity-pixel-pipeline-smoke66-v2.json counts、rgba、near_identity_pairs]` |
| 实测成本 | 归档复核5.675秒，精确像素阶段1.276秒，近重复阶段1.963秒；内部总计8.976秒，完整进程12.709秒。同机采集／补测并行，此数仅记录该次审计成本。`[verified: unity-pixel-pipeline-verification.json smoke；opinion: 计时解释]` |
| 全量队列 | 25份源码／环境文件及运行库版本冻结；直接等待开发参考系列和2000图确认系列成功退出，之后复核完整覆盖并串行执行两种像素审计。`[verified: unity-pixel-pipeline-full13000-v2-config.json；pixel_audit_pipeline.py wait/run]` |
| 确认集适配 | 嵌套options报告转换为单独的平铺投影，保留原报告和配置SHA。目前用合成归档核验投影及来源变化拒绝行为，真实确认集适配尚待上游完成。`[verified: pixel_audit_pipeline.py confirmation_batches；test_unity_pixel_audit_pipeline.py test_confirmation_projection_binds_original_nested_report；opinion: 验证范围]` |
| CPU与静态检查 | 74项CPU检查通过，ruff格式／lint和basedpyright通过；包括归档缺失、上游失败、报告身份、清单替换、等待资源、真实像素阶段串联与待生成报告路径冲突。`[verified: unity-pixel-pipeline-verification.json cpu_tests；本轮检查输出；tests/test_unity_pixel_audit_pipeline.py]` |

## 执行协议

1. 完整范围固定为10000／1000／2000；全量入口要求同代码、同运行库的真实66图检查和进程均通过。任务命令绑定到冻结的系列配置，等待期间复查源码、配置、进程身份；上游失败时保留本次失败记录。`[verified: pixel_audit_pipeline.py __init__/verify_smoke/verify/wait]`
2. 采集完成后复查原生批次，逐批与已发布清单及绑定记录比对。归档receipt必须已经存在，否则报错；不会进入`collect()`缺归档时的导出分支。`[verified: pixel_audit_pipeline.py require_archive/development_batches/confirmation_batches]`
3. 确认集`options_audit`与恢复记录来自原报告，转换文件仅写入新的`.local/options-projections/`，标记`derived_flat_options_from_confirmation_capture_report`，保留原报告／配置SHA，执行结束时复查绑定。`[verified: pixel_audit_pipeline.py confirmation_batches/read/verify]`
4. 先运行[精确像素身份检查](unity-pixel-identity.md)，再运行[原生近重复筛查](unity-near-duplicates.md)：后者只检查相同尺寸、坐标对齐的RGBA全图RMSE≤2（8位数值，归一化为2/255），检索网格8×8，最多100000对候选，预算超限不作部分通过。`[verified: pixel_audit_pipeline.py run；near_duplicates.py candidates/run]`
5. 开始像素检查前要求至少8GiB空闲RAM及5GiB磁盘；每15秒检查依赖／资源。输出目录、主报告及两份阶段报告必须与已有或待生成的采集目录、配置和报告分离。`[verified: pixel_audit_pipeline.py wait/verify_destinations]`

此队列不运行模型forward、不更新参数、不修改划分，也不自动删除重复候选。`passed`只表示声明范围的像素诊断完成，即使发现跨划分重复也会报告它们；仍保留`independent_test_isolation_proven=false`。不同尺寸、裁剪／旋转、语义相似性，以及开发清单之外的历史语料像素未由这一步覆盖。`[verified: pixel_audit_pipeline.py run scope；near_duplicates.py run；opinion: 完成解释]`

## 产物与复跑

- [真实66图配置](unity-pixel-pipeline-smoke66-v2-config.json)、[结果](unity-pixel-pipeline-smoke66-v2.json)、[精确阶段](unity-pixel-pipeline-smoke66-v2-exact.json)、[近重复阶段](unity-pixel-pipeline-smoke66-v2-near.json)。`[verified: 对应文件]`
- [全量配置](unity-pixel-pipeline-full13000-v2-config.json)、[等待状态](unity-pixel-pipeline-full13000-v2.json)、[核验快照](unity-pixel-pipeline-verification.json)。`[verified: 对应文件]`
- 入口为[queue_unity_pixel_audit.py](../../script/queue_unity_pixel_audit.py)，核心class为[UnityPixelAuditPipeline](../../reproductions/unity_search_baseline/pixel_audit_pipeline.py)。逐图身份、近重复对、投影和生成的阶段配置放在本次运行独立`.local`目录。`[verified: 两个入口文件；pixel_audit_pipeline.py run/confirmation_batches]`

```powershell
uv run python script/queue_unity_pixel_audit.py --config "<新的冻结配置绝对路径>"
```

已执行的身份不会覆盖，复跑需新报告与输出目录。全量配置绑定上游job／配置和已通过的小样本；更改这些输入或执行源码后，需重新验证并使用新身份。`[verified: pixel_audit_pipeline.py run/verify/verify_smoke]`

首轮`smoke66-v1`已通过（完整进程15.941秒），随后审查发现错误配置可能占用尚未生成的单批报告路径。修复后新增6项冲突检查，并以`smoke66-v2`复跑；v1配置、报告、日志和旧源码保留，旧源码SHA为`dbdf2381999d58827cc20a32a3e8ec0493268e386c731190100ab2cc6fef9b17`，归档于`.local/unity-accuracy90-20261111/unity-pixel-pipeline-smoke66-v1/source/`。两轮时间不构成性能对照。`[verified: 两轮进程receipt；v1 source文件SHA；test_unity_pixel_audit_pipeline.py pending_*冲突用例；opinion: 时间解释]`
