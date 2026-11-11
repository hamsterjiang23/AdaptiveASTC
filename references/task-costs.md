# 实验成本与读写依赖

启动较大实验前复核空闲内存、GPU、磁盘与现有任务；表中为本机已测样本，扩大输入规模后重新检查。内存峰值未记录的项目保留未知。`[opinion: 运行安排]`

| 任务 | 已测规模与耗时 | 资源记录与限制 |
|---|---|---|
| 原生patch目标提取 | train10000、validation1000，614.55秒 | 133140个patch，CPU／磁盘任务；峰值内存未记录。`[verified: ../experiment report/unity-accuracy90-20261111/patch-data-full.json]` |
| CUDA patch训练 | scratch 14轮2787.39秒，含数据检查、验证和保存 | 标准stem batch128的启动探针峰值分配显存2,118,429,184字节；正式训练和系统占用另测。单GPU队列，不并行启动其他训练。`[verified: ../experiment report/unity-accuracy90-20261111/patch-v1/scratch-result.json；patch-v1-smoke.json peak_vram_bytes；opinion: 调度]` |
| Unity实际参数采集 | 64训练图558回调，进程637.63秒 | 输入SHA耗时74.20秒；峰值内存未记录。包含导出／编译／哈希，不是搜索baseline。`[verified: ../experiment report/unity-accuracy90-20261111/unity-actual-options64.json；.local对应jobs/unity-options64/receipt.json]` |
| 颜色图候选补测 | 8图160候选，进程52.79秒／收集循环52.43秒 | 尺寸1至2048，奇数边缘／Alpha／大图分支；CPU任务，峰值内存未测，与CUDA训练重叠。`[verified: ../experiment report/unity-accuracy90-20261111/unity-color8.json；.local对应jobs/unity-color8/receipt.json]` |
| 法线候选解码与指标审计 | 一张4096²、20候选，进程21.40秒／循环15.93秒 | 0次新编码，复用原ASTC；峰值内存未测。mip0-only，不外推多mip。`[verified: ../experiment report/unity-accuracy90-20261111/unity-normal20-policy.json；.local对应jobs/unity-normal20-policy/receipt.json]` |

| 任务 | 读取 | 写入与互斥 |
|---|---|---|
| patch训练 | 冻结GDC源RGB patch corpus | 每个trial独立检查点、历史、预测与报告；完成前不读取活动checkpoint开展新诊断。`[verified: PatchTrainer.fit；opinion: 并发约束]` |
| Unity Editor采集 | Unity工程、源资产、manifest、编码DLL | 独立ASTC缓存、临时managed hook和meta；Editor退出后受保护恢复。与其他该工程Editor任务互斥。`[verified: UnityOptionCapture.run；ManagedCaptureHook.restore]` |
| 离线颜色补测 | 冻结参考图、实际参数记录、原DLL、指标DLL | 每次新output／report，不改原搜索产物；正式速度比较避免并发任务。`[verified: UnitySupplementalCapture.run；opinion: 计时约束]` |
| 法线审计 | 冻结参考图、原ASTC／解码图、原生tableConfig | 新目录归档和重算指标，要求Editor关闭，不改原缓存。`[verified: UnityNormalCandidateAudit.run]` |
| BN诊断 | 已完成last.pt、冻结train／validation | 固定train patch重新估计BN统计，独立保存raw／EMA前后变体；GPU训练完成后串行启动。`[verified: PatchNormalizationAudit.run；opinion: 调度]` |

新任务先跑小样本；聚合成本随批量和并发重新估算。同一工程、数据生成目录、模型保存目录出现读写冲突时先完成写入方，保留每次实验的独立身份。`[opinion]`
