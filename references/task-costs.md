# 实验成本与读写依赖

Unity保存验证预测的最终编码检查：两图、两条路径共四次DLL编码，v2内部0.81秒／完整进程4.05秒，CPU单进程，无新模型forward／CUDA。启动前RAM余量和磁盘记录于对应`launch-preflight.json`；读取已完成smoke模型产物与不可变验证候选，写独立`unity-final-encoding-smoke2-v2`目录，与训练及Unity采集并行。首次v1成本3.85秒，源码身份修订后v2独立复跑；不能作为部署端到端加速。`[verified: unity-final-encoding-smoke2-v2.json；对应v1/v2 jobs receipts；opinion: 成本边界]`

尺寸元数据训练接入的46项CPU检查5.49秒，CUDA48train／16validation检查两轮4次更新、进程20.45秒、峰值分配显存2,118,428,672字节；后续BN路径检查10.51秒。正式启动前RAM空闲26.93GiB、GPU1172／12282MiB，batch128、workers2、单GPU，与Unity采集／补测并行，读冻结GDC语料并写独立训练目录。按既有10–30轮成本估计40–140分钟，实际早停轮数与完整成本待结束记录；旧15份源码预先归档，运行冻结12份训练源码。`[verified: metadata-integration.json；对应jobs receipts、launch-preflight.json；opinion: 预算与调度范围]`

组均衡cap512末轮BN诊断已完成，raw／EMA分别使用16384训练patch重估并各验证前后状态，0次优化器更新；内部424.57秒、完整进程429.16秒，观察到进程树RSS约2571MiB、GPU总占用2116MiB，非峰值。启动前RAM空闲27.37GiB，沿用单GPU串行、与Unity采集并行；原checkpoint及归档源码只读，写独立诊断目录。先期CUDA小样本进程10.52秒，原／当前执行源码分开绑定。`[verified: normalization-group512.json；对应job receipt及launch-preflight.json；本轮psutil/nvidia-smi观测；opinion: 资源与计时范围]`

尺寸元数据组件12项CPU检查4.40秒；完整11000图133140patch尺寸特征审计4.91秒，读取corpus及目标NPZ并核验SHA，不加载图片或运行模型。以上为先期组件检查成本，CUDA小样本成本见本节顶部；正式完整训练与部署推理成本尚待测量。`[verified: metadata-contract.json；metadata-data-audit.json；audit_patch_metadata.py；metadata-integration.json；opinion: 待测范围]`

3906图patch准备已完成，循环1684.91秒／进程1687.78秒；统一清单组装64.13／67.60秒，20832patch完整Dataset检查113.73／116.98秒。此范围仍为partial，旧11批目标哈希保持，6批新增目标单列；成本含重验与并发，不用于部署加速比。`[verified: unity-patch-batches3906.json；unity-patch-assembly3906.json；unity-assembly3906-dataset-audit.json；native3906-assembly-verification.json process_costs；opinion: 成本边界]`

3906图精确目标决策接口检查循环62.50秒／进程67.29秒，17个原策略来源核对，0次训练更新。4674图扩展已完成，复用17批3906图目标、新增3批768图，循环1845.25秒／进程1849.48秒，超过启动时10–20分钟估计。单CPU进程只读已发布归档，写共享shard目录并持有独占锁，运行期间与CUDA训练和参考采集并行；这些数据准备成本不用于部署加速比。`[verified: unity-prediction-interface3906.json；jobs/unity-prediction-interface3906/receipt.json；unity-patch-batches4674.json；jobs/unity-patch-batches4674/receipt.json、launch-preflight.json；opinion: 估时与并发范围]`

完整原生数据流水线等待时只检查上游进程和哈希，成功退出后按顺序调用原准备／组装／Dataset／决策检查，复用既有目标。三次66图进程依次71.14／24.85／22.70秒，后两次复用首次目标；最终源码阶段合计22.02秒。首个全量等待身份因退出竞态修复主动停止，226.26秒未进入数据阶段，记录单列；当前full-v2任务继续等待。执行阶段要求22GiB空闲RAM／40GiB磁盘；waiting_seconds、execution_seconds和总wall_seconds分开，等待时长不当作处理耗时或加速比。`[verified: unity-native-pipeline-smoke66-v1.json、v2.json、v3.json；对应jobs receipts；unity-native-pipeline-full-v2-config.json prior_attempt；opinion: 成本边界]`

像素比例采样10轮训练2389.30秒／完整进程2419.23秒，最佳82.0%。后续有效区域池化也完成10轮，训练2289.52秒／含重载进程2323.97秒，最佳78.0%，3126次实际更新、4次AMP跳步。两项均为负结果，早停轮数与原26轮基准不同，不解释为部署加速。有效区域池化先期CUDA检查2轮4更新、进程21.21秒；正式单GPU训练与Unity采集并行。`[verified: scratch-group512-pixels-result.json；scratch-group512-validpool-result.json；mask-pooling-integration.json；opinion: 调度与计时口径]`

有效区域mask的完整几何核对读取冻结GDC corpus及11000份目标NPZ，覆盖133140patch／986种宽高，CPU耗时55.73秒、2线程；不读取图片像素、不做训练。组件17项CPU测试8.76秒，后续CUDA检查成本见本节顶部，正式训练和推理成本另行测量。`[verified: patch-fixed-capacity/mask-pooling-data-audit.json；mask-pooling-contract.json unit_tests；opinion: 后续成本范围]`

3906图patch准备冻结17个已发布候选批次，复用2370图目标、提取新增1536图；只读已归档批次，持有共享shard独占锁。配置准备时空闲RAM24.57GiB／磁盘911.37GiB，实际启动前复查空闲RAM22.82GiB，每批20GiB内存门槛保持；准备阶段资源观测保留，完成耗时见本节顶部。与采集和CUDA训练重叠，不作为部署性能测量。`[verified: jobs/unity-patch-batches3906/launch-preflight.json；启动前psutil资源输出；unity-patch-batches3906-config.json；opinion: 成本范围]`

有效像素抽样对照的48train／16validation CUDA检查为2轮4次更新，进程21.54秒、峰值分配显存2,118,426,112字节。正式配置只改图内采样概率，仍单GPU、batch128、workers2；启动前RAM空闲28.87GiB、GPU1195／12282MiB。历史cap512进程7230.64秒仅为预算参照，新运行成本单列；只读冻结GDC语料，写独立.local训练目录，与Unity队列不共用写入。`[verified: scratch-group512-pixels-smoke.json；对应jobs/receipt和launch-preflight.json；opinion: 预算与并发边界]`

Unity原生CUDA训练链路的首次8train／2validation探针为2轮4次更新，准备17.07秒、训练器19.28秒、进程23.81秒；峰值分配显存446,280,192字节，image batch4、每图4patch、workers0。只读冻结2370图语料和已完成的原策略归档，写独立训练目录／公开报告；与参考采集及补测不共享写入，GPU训练串行。完整语料及更大batch资源成本须重新测量。`[verified: unity-native-smoke8-v1-result.json；unity-native-smoke8-v1-config.json；opinion: 规模与并发边界]`

GDC bag4的权重0／1配对训练分别1080.91／728.25秒，含两次重载的串行进程1869.71秒；与CPU采集并行，不视为独占部署时延。`[verified: patch-fixed-capacity/scratch-bag4-loss0-result.json、scratch-bag4-loss1-result.json、scratch-bag4-comparison.json；opinion: 计时口径]`

分批原生patch准备只读已完成的参考／候选归档，写独立.local单批语料及公开报告；共享shard目录独占锁，单进程，每批要求20GiB空闲RAM／40GiB磁盘。64train＋2validation首次进程63.53秒因路径大小写失败，保留其64图目标；修复后复用目标的检查用12.81秒。2370图处理成本单列，和CUDA训练／Unity采集重叠，不视作部署性能测量。`[verified: patch_batches.py run、prepare；jobs/unity-patch-batches-smoke、smoke-v2/receipt.json；unity-patch-batches2370-config.json；opinion: 成本边界]`

Unity原生Dataset检查使用CPU，未进行模型训练。7图小样本循环0.24秒／进程6.11秒，首次260图为17.18／22.00秒；补强重复patch目标检查后的最终复核为9.52／13.22秒。各次成本分别保留，缓存及并发状态不同，不据此声称速度改进。`[verified: unity-dataset-smoke.json、unity-dataset260.json、unity-dataset260-v2.json；对应jobs/receipt；opinion: 成本解释]`

启动较大实验前复核空闲内存、GPU、磁盘与现有任务；表中为本机已测样本，扩大输入规模后重新检查。内存峰值未记录的项目保留未知。`[opinion: 运行安排]`

| 任务 | 已测规模与耗时 | 资源记录与限制 |
|---|---|---|
| 同图patch抽样与聚合核验 | 10000训练图、40000patch抽样，81.95秒 | 包含冻结输入验证；仅CPU，未训练模型；内存峰值未测。`[verified: ../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/bag-sampling-analysis.json wall_seconds、scope]` |
| Unity原搜索规则重放 | 260开发图，审计循环0.9674秒／完整进程3.6460秒 | 消费已测20候选质量，核对完整原采集规则；没有编码或训练，不计为模型部署加速。`[verified: ../experiment report/unity-accuracy90-20261111/unity-policy260-bound-v2.json；.local对应jobs/unity-policy260-bound-v2/receipt.json；opinion: 计时范围]` |
| 原生patch目标提取 | train10000、validation1000，614.55秒 | 133140个patch，CPU／磁盘任务；峰值内存未记录。`[verified: ../experiment report/unity-accuracy90-20261111/patch-data-full.json]` |
| CUDA patch训练 | scratch 14轮2787.39秒，含数据检查、验证和保存 | 标准stem batch128的启动探针峰值分配显存2,118,429,184字节；正式训练和系统占用另测。单GPU队列，不并行启动其他训练。`[verified: ../experiment report/unity-accuracy90-20261111/patch-v1/scratch-result.json；patch-v1-smoke.json peak_vram_bytes；opinion: 调度]` |
| Unity实际参数采集 | 64训练图558回调，进程637.63秒 | 输入SHA耗时74.20秒；后续validation2启动刷新阶段观察Editor工作集11.08GiB，该次采样不是峰值。启动前按重内存任务检查余量，单工程串行。包含导出／编译／哈希，不是搜索baseline。`[verified: ../experiment report/unity-accuracy90-20261111/unity-actual-options64.json；.local对应jobs/unity-options64/receipt.json；2026-11-11 validation2进程33916 WorkingSetSize=11901513728；opinion: 调度]` |
| 颜色图候选补测 | 8图160候选，进程52.79秒／收集循环52.43秒 | 尺寸1至2048，奇数边缘／Alpha／大图分支；CPU任务，峰值内存未测，与CUDA训练重叠。`[verified: ../experiment report/unity-accuracy90-20261111/unity-color8.json；.local对应jobs/unity-color8/receipt.json]` |
| 法线候选解码与指标审计 | 一张4096²、20候选，进程21.40秒／循环15.93秒 | 0次新编码，复用原ASTC；峰值内存未测。mip0-only，不外推多mip。`[verified: ../experiment report/unity-accuracy90-20261111/unity-normal20-policy.json；.local对应jobs/unity-normal20-policy/receipt.json]` |
| 法线全候选重编码核验 | 一张4096²、20候选，进程174.18秒／循环170.15秒 | 纯编码124.20秒，20组压缩／解码字节一致。与CUDA训练重叠，峰值内存未测；不外推HDR／多mip或独立部署时延。`[verified: ../experiment report/unity-accuracy90-20261111/unity-normal-replay20.json；.local对应jobs/unity-normal-replay20/receipt.json]` |
| validation分批采集探针 | 2图7回调，进程370.06秒；另40候选补测循环3.8977秒 | Editor刷新阶段观察工作集11.08GiB，原meta／源码恢复通过；一图512²导入为256²。成本以工程启动／刷新为主，批量外推单列估计。`[verified: ../experiment report/unity-accuracy90-20261111/unity-validation2.json；unity-validation2-supplement.json；.local对应jobs/unity-validation2/receipt.json、batch-editor.log；opinion: 成本外推]` |
| 冻结权重BN诊断 | scratch末轮，整进程400.03秒 | raw／EMA各用16384训练patch重估，另有4次validation；学习参数未变，GPU串行，峰值内存未记录。`[verified: ../experiment report/unity-accuracy90-20261111/normalization-scratch.json；.local对应jobs/normalization-scratch/receipt.json]` |
| 随机初始化低学习率对照 | 12轮训练2483.18秒，含最佳权重重载的进程2516.98秒 | 与原scratch仅lr不同；另行末轮BN诊断419.26秒，参数不变。时长为本机开发成本。`[verified: ../experiment report/unity-accuracy90-20261111/patch-fixed-capacity/scratch-lr0003-result.json；normalization-scratch-lr0003.json；.local对应job receipts]` |
| 256张训练图原生采集 | 1432回调，Editor阶段901.88秒／完整进程963.42秒 | 16张NormalMap；源码／meta恢复通过。45批队列逐批检查至少20GiB空闲RAM与相关卷40GiB磁盘，允许独立冻结GDC语料的CUDA训练。包含刷新／导出／哈希，不用于替换搜索基线。`[verified: ../experiment report/unity-accuracy90-20261111/unity-train256-batch001.json；unity-reference-series-plan.json；collection.py require_resources；opinion: 并发与计时范围]` |
| 颜色／部分搜索法线补齐 | 256图5120编码，进程609.70秒；编码326.07秒、解码41.25秒、质量评价63.72秒 | 新增3688组覆盖，16法线均mip0-only；258图队列初次／复核46.20／43.16秒。与Editor采集和CUDA训练重叠，作为准备成本。`[verified: ../experiment report/unity-accuracy90-20261111/unity-candidates-train256-audit.json；unity-candidate-queue-smoke.json；.local对应jobs/receipt；opinion: 计时范围]` |

原生RGBA监督在258图上循环51.53秒／进程57.00秒，5160候选生成1677个patch。两张法线的四级评价补测循环6.67秒／进程6.99秒；原候选队列首轮1233.83秒包含已完成578图，不能全部记为无效重试。各项均与正在运行的采集／训练重叠，作为数据准备成本。`[verified: unity-patches-train256.json；unity-normal-multimip2.json；对应jobs/receipt；unity-candidate-queue-multimip-v2-config.json prior_queue；opinion: 成本范围]`

| 任务 | 读取 | 写入与互斥 |
|---|---|---|
| patch训练 | 冻结GDC源RGB patch corpus | 每个trial独立检查点、历史、预测与报告；完成前不读取活动checkpoint开展新诊断。`[verified: PatchTrainer.fit；opinion: 并发约束]` |
| Unity Editor采集 | Unity工程、源资产、manifest、编码DLL | 独立ASTC缓存、临时managed hook和meta；Editor退出后受保护恢复。与其他该工程Editor任务互斥。`[verified: UnityOptionCapture.run；ManagedCaptureHook.restore]` |
| 离线颜色补测 | 冻结参考图、实际参数记录、原DLL、指标DLL | 每次新output／report，不改原搜索产物；正式速度比较避免并发任务。`[verified: UnitySupplementalCapture.run；opinion: 计时约束]` |
| 法线审计 | 冻结参考图、原ASTC／解码图、原生tableConfig | 新目录归档和重算指标，要求Editor关闭，不改原缓存。`[verified: UnityNormalCandidateAudit.run]` |
| BN诊断 | 已完成last.pt、冻结train／validation | 固定train patch重新估计BN统计，独立保存raw／EMA前后变体；GPU训练完成后串行启动。`[verified: PatchNormalizationAudit.run；opinion: 调度]` |

新任务先跑小样本；聚合成本随批量和并发重新估算。同一工程、数据生成目录、模型保存目录出现读写冲突时先完成写入方，保留每次实验的独立身份。`[opinion]`

连续候选队列读取参考队列已发布批次的归档、原DLL和原生指标构建，写独立.local目录；候选队列持有工程级candidates.lock，参考队列持有series.lock。每批至少20GiB空闲RAM／40GiB输出磁盘，只启动一个补测工作进程；全11000图为重型批处理，256图测量用于预算参考，尺寸与用途分布不同会改变耗时。`[verified: candidate_queue.py lock、require_resources、run；unity-candidate-queue-full-config.json；opinion: 成本分类及外推边界]`

去maxpool正式训练15轮3345.85秒，包含权重重载的进程3385.97秒；末轮BN诊断另用599.74秒。下一项组限权训练的48train／16validation CUDA检查用34.44秒，正式启动前空闲RAM30.25GiB、GPU1229／12282MiB。训练继续单GPU串行，原生采集与候选补测的CPU／磁盘成本重叠，正式训练时间待结束后记录。`[verified: patch-fixed-capacity/scratch-stem2-lr0003-result.json；对应jobs/receipt；normalization-scratch-stem2-lr0003.json；jobs/scratch-group512/launch-preflight.json及启动前nvidia-smi输出；opinion: 成本范围]`
