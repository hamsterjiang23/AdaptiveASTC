# Unity导入参考像素与原搜索标签的串行采集

全量队列已启动，目标为冻结划分的train10000／validation1000，配置共45批，每批不超过256张。启动时已核验320张train和2张validation；剩余42批按顺序采集。完整覆盖、补充候选目标和Unity模型验收分别记录，目前未完成全量。实时计数及current_batch见[队列报告](unity-reference-series.json)，冻结批次及来源见[计划记录](unity-reference-series-plan.json)。`[verified: unity-reference-series-plan.json expected_counts、batches；unity-reference-series.json counts、current_batch；opinion: 验收范围]`

| 已完成部分 | 样本／实际回调 | 核验与成本 |
|---|---|---|
| 先期实际参数采集 | train64／558 | 参考RGBA哈希、实际参数、原源码与meta恢复通过，进程637.63秒。`[verified: unity-actual-options64.json；.local对应jobs/unity-options64/receipt.json]` |
| 新训练批次 | train256／1432 | 240张Default、16张NormalMap；与先期64张不重叠；恢复通过，Editor阶段901.88秒，完整进程963.42秒。`[verified: unity-train256-batch001.json；.local对应batch-receipt.json、jobs/unity-train256-batch001/receipt.json；series frozen paths]` |
| 验证采集探针 | validation2／7 | 保留validation划分，恢复通过，进程370.06秒；40候选补测另行保存。`[verified: unity-validation2.json；unity-validation2-supplement.json；.local对应jobs/unity-validation2/receipt.json]` |
| 合并入口实际检查 | train64＋validation2 | 重新核对实际归档的参考像素、源MD4、原策略标签、实际参数和采集身份，合并通过；不新开Editor、不编码。`[verified: unity-reference-series-smoke.json status、counts、manifest_sha256；collection.py verify_batch]` |

原Unity候选顺序、提前停止和原始策略标签保持；每张图的参考像素与标签来自同次原搜索。合并记录保留RGBA路径／SHA、源MD4、尺寸、导入信息、实际needAlpha／profile／normal-pack、批次身份和source_split。原生报告中的selection逐字段复核，补测不会覆盖该标签。这个语料尚不是完整的20候选回归监督。`[verified: collection.py verify_batch L154–243；benchmark.py、metadata.py原搜索采集；opinion: 语料边界]`

入口为`script/collect_unity_references.py`，实现位于`reproductions/unity_search_baseline/collection.py`。`validate`只核对计划和环境；`collect`串行采集缺失批次并复核已完成批次；`assemble`要求全部已有产物完整，不新开Editor。正式配置保存在.local的`reference-series-plan-v2/complete.json`，SHA-256为`519df9a08a326067bd5a6467a3be355b648acf92709afb21539e596feff004b8`。`[verified: script/collect_unity_references.py；collection.py run/execute；unity-reference-series.json configuration_sha256]`

```powershell
uv run --frozen python script/collect_unity_references.py validate --config "experiment report/.local/unity-accuracy90-20261111/reference-series-plan-v2/complete.json"
uv run --frozen python script/run_reproduction_job.py --config "experiment report/.local/unity-accuracy90-20261111/jobs/unity-reference-series-v2/job.json"
```

以上正式job正在运行，命令用于记录可复跑入口；重用同一个活动身份会被拒绝。新进程不应与当前同工程Editor并行启动。运行日志、30秒心跳、进程退出记录在.local的同名job目录，单轮失败和已成功批次均保留。`[verified: jobs/unity-reference-series-v2/receipt.json；ReproductionJob；collection.py project_lock/execute；opinion: 操作要求]`

计划冻结manifest、Editor、两个编码DLL、每批配置SHA和全量覆盖。每个新批次开始前重新核对配置与来源，至少要求20GiB空闲RAM及相关卷40GiB空闲磁盘。OS文件锁放在共享Unity工程`Library/ASTCReproductionLocks/series.lock`，跨仓库checkout互斥，异常进程退出由OS释放；不得在活动进程期间手动删除锁文件或恢复其临时hook。`[verified: collection.py validate、verify_environment、require_resources、project_lock、execute；opinion: 操作边界]`

CPU验证覆盖：完整与选择子集的不同覆盖要求、实际Windows互斥锁、篡改reference receipt、MD4／原策略绑定、非法资源门槛、失败后重入身份保留等；16项测试通过。实际66张合并再检查通过。上述测试证明合并和身份检查范围，不代表剩余采集已成功。`[verified: tests/test_unity_reference_series.py；pytest 16 passed；unity-reference-series-smoke.json；opinion: 验证边界]`

当前进程允许与读取冻结GDC语料的CUDA开发实验并行，两者不共享写入目录。采集包含Editor启动、刷新、PNG导出及哈希开销；本轮时长作为数据准备成本单列，不代替此前10000图的原搜索基线，也不据并发运行推断部署加速。完整采集后，未覆盖候选的离线补测、原生指标监督与Unity模型训练继续按V1执行。`[verified: reference-series scope；UnityOptionCapture.run；opinion: 并发与计时解释]`
