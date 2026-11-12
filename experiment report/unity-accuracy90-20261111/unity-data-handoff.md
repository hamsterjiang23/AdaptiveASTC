# Unity 数据采集收尾与 V2 交接

2026-11-12，用户将本 chat 的 goal 完成条件改为“完成数据采集”，随后执行 V2。本次指示覆盖旧 goal 正文中的继续训练与达到 90% 要求；旧实验结果保留，当前 goal 在完整数据及验收证据齐备后完成。V2 模型训练、调优和独立准确率验收另行执行。`[verified: 用户“完成数据采集之后goal就能完成了…我要执行V2了”]`

## 本 Goal 的完成条件

- train10000／validation1000：Unity 导入后参考 RGBA、实际导入属性、同次原搜索标签与计时全部归档；原搜索提前停止、缓存隔离及恢复记录保持。`[verified: experiment plan/V2/README.md“数据”“E0 数据就绪”；opinion: 数据交付验收]`
- 这 11000 张开发图的 20 候选补测完成，逐图解码产物和原生质量可追溯；patch 目标、合并语料、Dataset 全读和原规则重放通过。原搜索与额外补测成本分别记录。`[verified: experiment plan/V2/README.md“E0 数据就绪”；unity-native-pipeline-full-v3-config.json；opinion: 数据交付验收]`
- confirmation2000：按既定主名单完成参考图、实际属性和同次原搜索标签采集；确认集不做全候选补测或模型推理。10000／1000／2000 的精确 RGBA 与同尺寸对齐近重复审计完成，发现的问题列入交接，不据此自动删图或修改划分。`[verified: experiment plan/V2/README.md“确认集”“开发准入”；confirmation_series.py audit_batch；pixel_audit_pipeline.py；opinion: 数据交付范围]`
- 输出可供 V2 使用的清单、配置、哈希与结果入口，保留失败和取消记录，更新文档并同步仓库。数据尚未完成时 goal 保持 active。`[verified: 用户本轮范围调整及此前“记得有进展同步仓库”要求；opinion: 交接验收]`

## 队列调整

调整记录在 [unity-data-handoff-v1.json](unity-data-handoff-v1.json)。旧训练队列处于 `waiting_data`，已有 smoke32 成功记录，正式训练任务尚未生成；本轮取消的是等待中的正式训练安排。三个依赖该训练的等待任务同时取消，改用新的数据专用身份。原配置与日志保留，退出码 15 的四个任务在交接记录中明确标为用户缩减范围导致的取消。`[verified: unity-data-handoff-v1.json cancellation_record；对应 cancellation-result.json receipt_before、receipt_after、disposition；unity-native-training-full-v2/smoke-job/receipt.json]`

| 工作 | 当前入口与依赖 |
|---|---|
| 开发集原始采集 | 沿用 [reference series](unity-reference-series.json)，任务 `unity-reference-series-v2` 持续运行。`[verified: unity-data-handoff-v1.json retained_jobs]` |
| 开发集 20 候选补测 | 沿用 [candidate queue](unity-candidate-queue-sprite-v3.json)，持续消费已发布原始批次。`[verified: unity-data-handoff-v1.json retained_jobs]` |
| patch 整理与完整开发数据验收 | 沿用 [完整数据流水线](unity-native-pipeline-full-v3.json)；上游成功后自动执行。`[verified: unity-data-handoff-v1.json retained_jobs；unity-native-pipeline-full-v3-config.json dependencies]` |
| 确认集两图预检 | 新 [配置](unity-confirmation-capture-smoke2-data-v1-config.json) 与 [进度](unity-confirmation-capture-smoke2-data-v1.json)，只等待原始采集、补测和完整数据流水线，不再等待训练。`[verified: 对应配置 dependencies；unity-data-handoff-v1.json jobs]` |
| 确认集 2000 图 | 新 [配置](unity-confirmation-series2000-data-v1-config.json) 与 [进度](unity-confirmation-series2000-data-v1.json)，两图实际预检通过后，按原主名单补采其余 1998 张。`[verified: 对应配置 smoke_config、expected_images；unity-data-handoff-v1.json checks.series_plan]` |
| 完整像素审计 | 新 [配置](unity-pixel-pipeline-full13000-data-v1-config.json) 与 [进度](unity-pixel-pipeline-full13000-data-v1.json)，等待开发集和新确认采集完成，沿用已通过的 66 图检查与冻结源码。`[verified: 对应配置 development、confirmation、smoke_provenance；unity-data-handoff-v1.json checks.pixel_config]` |

只更新任务依赖与输出身份，没有改动活动数据流水线的源码或原配置。V1、V2 的原始 evidence.json 哈希保持。新配置已通过实际构造与只读校验，三个替代任务的真实进程已确认运行；这些证据不表示采集已完成。`[verified: unity-data-handoff-v1.json checks、jobs；opinion: 完成边界]`

## 数据交接状态

截至 2026-11-12T04:42:48.539732+00:00，原采集 train10000／validation514，完整候选 train10000／validation2。[全部训练候选核验](unity-training-candidates10000-v1.json)确认10000张唯一训练图及200000候选，原选择保持；本次没有重新解码全部图片，完整像素／patch验收仍由已排队数据流水线执行。动态状态见 [progress.json](progress.json) 的 `data_handoff` 及各队列报告。`[verified: unity-training-candidates10000-v1.json；progress.json data_handoff.latest_capture_milestone；opinion: 验收边界]`
