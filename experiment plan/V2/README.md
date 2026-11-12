# 实验计划 V2：Unity 原生协议的质量预测与原规则决策

V2 初版记录于 2026-11-12，当时状态为待执行。开发、选模与验收全部使用 Unity 协议，即导入处理后的第一个 image／mip0 参考像素、同次原搜索标签、20 候选补测得到的原生质量，以及原规则重放。GDC 源图 RGB 协议的数据、标签、权重和结果不进入 V2 的训练、选模或验收。引用数字与来源 SHA-256 保存在 [evidence.json](evidence.json)，由归档脚本 `experiment report/.local/unity-accuracy90-20261111/plan_v2_evidence.py` 生成，脚本 SHA-256 记录在同一文件。`[verified: 用户本轮要求“按照我们的UNITY协议指定V2的expreiment plan，不需要使用GDC协议”；evidence.json script、inputs]`

[V1](../V1/README.md) 的历史方法与实测结果保留，执行状态按用户最新指示更新。V2 复用 V1 执行期间完成的 Unity 原生组件，包括采集、补测、Dataset、`UnityQualityRegressor`、训练器、规则重放和确认集入口，不复用 GDC 数据、权重或结果。用户最初选择只指定 V2；随后于 2026-11-12 明确数据 goal 在完成采集后结束，后续执行 V2。当时只继续[数据交接](<../../experiment report/unity-accuracy90-20261111/unity-data-handoff.md>)，V1 正式训练自动启动已取消；V2 的 R0 复用保留的配方，以新的实验身份启动。`[verified: 用户先前“先不切换，只是指定”及后续“完成数据采集之后goal就能完成了…我要执行V2了”；unity-data-handoff-v1.json training_auto_start]`

当前V2 goal已启动，完整原生基线、权重0.03、仅均值池化及ImageNet初始化对照、冻结预测归因和验证余量拟合已完成。完整30轮随机初始化原始／同集拟合Top-1为81.3%／81.5%，ImageNet为85.7%／86.4%，主线晋级等待用户决定；原生BN重估为80.1%，随机初始化EMA对照正在训练。结果与活动状态见[执行报告](<../../experiment report/unity-v2-20261112/README.md>)；计划初版源码哈希和归档位置见[执行绑定](<../../experiment report/unity-v2-20261112/plan-execution-binding.json>)。`[verified: 用户“查看V2版本的实验之后，创建一个goal开始实验”；experiment report/unity-v2-20261112/comparison.json、progress.json]`

核心做法：对每张图预测 20 个候选在 Unity 口径下的质量，交给原规则 `UnitySearchPolicy` 选出块大小和 preset，最后只编码一次。`[opinion]`

## 目标与验收

- **主验收**：独立确认集 2000 张上，块大小 Top-1≥90%，对照同次原搜索的选中配置。`[verified: unity-accuracy90 README“主验收保持…独立测试块大小Top-1≥90%”]`
- **开发准入**：同一个选中权重在 validation1000 上块大小 Top-1≥90%，且 10000／1000／2000 的完整像素审计和 2000 张确认采集都通过，才封存模型并打开确认集。`[verified: unity-confirmation-evaluation.md“准入与数据边界”]`
- **同时报告，不设门槛**：块大小＋preset 完整匹配；实际解码后的严格质量通过率；质量回退，即原标签严格合格而模型选择不合格的图数；错误方向（选大／选小）；相对固定 8×8／medium 和原搜索标签的 payload；预处理、推理、决策和最终编码耗时。质量约束不进入验收，preset 只报告完整配置匹配率，均由用户 2026-11-12 确认。`[verified: unity-confirmation-evaluation.md“指标与成本”；unity-deployment.md fixed8 路径；用户本轮选择“只看 Top-1≥90%，质量和字节全部报告但不设门槛”“只报告块大小＋preset 完整匹配率，不设门槛”] [opinion: 指标定义]`

## Unity 协议

以下内容固定，不随实验改变。完整源码规则见 [README 判定规则](../../README.md#自动选参的偏好与判定规则) 和 [规则重放报告](<../../experiment report/unity-accuracy90-20261111/unity-policy-replay.md>)。

| 项目 | 内容 |
|---|---|
| 输入 | 导入处理完成后、进入 ASTC 搜索前的第一个 image／mip0，原尺寸 RGBA32；导入属性取自实际编码回调 |
| 候选与顺序 | 12×12、10×10、8×8、6×6，每个块大小依次 fastest、fast、medium、thorough、exhaustive，共 20 个；常规分支在首个合格候选处停止 |
| 质量门槛 | PSNR 基础 30 dB，纯黑像素比例 >40% 时 35 dB、>80% 时 37 dB；sRGB 颜色图另需 MS-SSIM≥21 dB；法线图只看平均角度≤3.2° 且 p95≤9°。阈值从各批原缓存的 tableConfig 读取，按 float32 比较 |
| 大图与回退 | sRGB LDR 且面积≥512²：首个 PSNR 合格候选锁定块大小，同块继续找 MS-SSIM 也合格者，始终不合格时采用该块最后一个 PSNR 合格候选。没有有效候选时按最高 PSNR 回退 |
| PSNR 口径 | 只平均误差非零的参与通道，排除恒定 Alpha |
| 标签 | 同次原搜索的选中配置，即“当前策略选中配置”，不等同于候选最优或严格达标 |
| 本轮范围 | 颜色图为 Default／Sprite LDR，法线为 Linear RGBA8、normal-pack=false、Tex2D；只编码 mip0，RDO 关闭。HDR、完整 mip 链和 Unity 导入耗时不在本轮范围 |

`[verified: evidence.json capture_protocol.quality；unity-policy-replay.md“原规则与验收”；policy.py UnitySearchPolicy.__init__、select；AGENTS.md 判定规则与补测范围条目]`

## 数据

V2 数据采集与完整性验收已完成：训练10000张、验证1000张、确认2000张。开发集已按批准的18个位置补采并生成新语料，220000组候选、74609个patch；11000张完整读取和原规则四字段重放通过。13,000张实际输入、精确RGBA和同尺寸对齐近重复检查完成，确认集未运行模型。`[verified: unity-data-delivery-v3-verification.json counts、development_candidate_count、development_patch_counts、exact_policy_replay、native_input_eligibility_verified、full_pixel_audit_complete、test_opened]` 数据阶段E0完成，后续训练和模型验收尚待执行；入口见[最终交接](<../../experiment report/unity-accuracy90-20261111/unity-data-delivery-v3.md>)。`[verified: 最终验收 data_collection_complete、v2_training_started]`

精确RGBA重复9组，跨划分0组；同尺寸对齐RGBA RMSE≤2的近重复25对，其中跨划分11对。保留原划分及全部问题记录，没有自动删图。审计不覆盖裁剪、缩放或语义近重复，不能据此声称确认集完全独立；模型90%验收仍由后续V2执行。`[verified: unity-data-delivery-v3-verification.json pixel_audit、model_accuracy、v2_training_started；opinion: 审计与模型结论边界]` 原始evidence.json保持为计划建立时的快照。`[verified: 最终验收已核对V1/V2历史证据哈希]`

- **开发划分**：沿用已冻结的 coverage-v2 资产名单，train10000／validation1000。只复用名单和划分，像素、标签和候选质量全部按 Unity 协议采集。`[verified: evidence.json capture_protocol.manifest、source_split_count；unity-reference-series.md] [opinion: 复用边界]`
- **每张图的数据**：参考 RGBA；8 项导入属性，即 log2 宽、log2 高、sRGB、法线、需要 Alpha、Alpha 恒定、法线评价 mip 数和纯黑像素比例；原搜索标签和计时；20 候选补测的解码图与原生质量；非重叠 240×240 patch 的 RGBA 逐通道 SSE，patch 原点为 240 的倍数，四种块网格都对齐；整图 MS-SSIM 与法线角度。`[verified: unity_patch_dataset.py METADATA_NAMES；data/patch_targets.py boxes；unity-patch-targets.md]`
- **初版确认集预留（历史快照）**：2000 张主名单和 500 张备用，主名单覆盖 1227 个不在历史清单中的资产组；按种子化路径哈希选择，不按标签或质量筛样。详见 [确认集预留](<../../experiment report/unity-accuracy90-20261111/unity-confirmation-cohort.md>)。`[verified: evidence.json isolation.confirmation]`
- **初版进度快照**（2026-11-12 03:46 UTC）：参考图和原标签 train9792／validation2，20 候选补测 train9280／validation2；数据衔接等待上游，正式训练等待数据，确认采集等待预检，像素审计等待采集。`[verified: evidence.json live_snapshot]`
- **数据收尾进度**（2026-11-12 07:20 UTC）：train10000／validation1000的20候选、74187个patch、语料合并及Dataset全读通过，11000张的块大小、preset、选择原因和候选测量次数（candidates_measured）重放全部一致。确认集采集及完整像素审计继续执行，E0尚未完成；当前goal不启动训练。详见[开发语料验收](<../../experiment report/unity-accuracy90-20261111/unity-development-data11000-verification.json>)。`[verified: unity-development-data11000-verification.json counts、patch_counts、exact_policy_replay、e0_complete；用户数据收尾范围]`

### 已知分布

最新完整训练／验证分布见[新版分布](<../../experiment report/unity-accuracy90-20261111/unity-development-v2-distribution.json>)。下列3904张统计保留为计划初版快照，不作为完整数据分布。`[verified: unity-development-v2-distribution.json；evidence.json targets3904.scope]`

- **块大小**：12×12 2414 张（61.8%），10×10 549，8×8 512，6×6 429。始终预测 12×12 的 Top-1 为 61.8%，作为最低参照。
- **preset**：fastest 1159，fast 138，medium 956，thorough 929，exhaustive 722。
- **选择分支**：常规首个合格 2746，大图严格 756，大图放宽 319，最高 PSNR 回退 83。原标签严格质量通过 89.70%（3502 张），未通过的 402 张恰为放宽与回退之和；84 张没有任何严格合格候选。
- **输入属性**：sRGB 3604，法线 262（其中 21 张为四级角度评价），需要 Alpha 1287，面积≥512² 1318，单 patch 图 1382，纯黑比例 >40% 526、>80% 199。资产组 1118 个，最大组 257 张。
- **字节**：原标签 payload 是固定 8×8 的 65.95%（96,099,472／145,706,576 字节）。

`[verified: evidence.json targets3904]`

## 诊断依据

- **规则可以精确重放。** 3906 张图用实测质量代入，块大小和 preset 全部与原标签一致；260 张开发图另核对选择原因和候选尝试次数，也全部一致。模型训好后，决策误差只来自预测本身。`[verified: evidence.json targets3904.exact_reconstruction、policy_replay260.matching_fields、mismatches]`
- **只看 PSNR 不够。** 260 张图去掉 MS-SSIM、法线和大图分支后，块大小一致 79.62%，块大小＋preset 一致 42.31%。分组为 sRGB 小图 140／180、sRGB 大图 60／60、法线 5／18、Linear 2／2。`[verified: evidence.json policy_replay260.psnr_only_*]`
- **各指标影响的范围不同。** 大图分支按 PSNR 锁定块大小，MS-SSIM 只影响同块内的 preset，不影响字节；MS-SSIM 主要通过小图影响块大小，法线图只由角度决定。`[verified: policy.py select；AGENTS.md size-first 规则] [opinion: 对预测精度要求的推论]`
- **候选之间不单调。** 同一 preset 下换更小的块、PSNR 反而下降的图有 30–49 张，同一块大小下换更慢的 preset、PSNR 下降的有 86–179 张，因此不对 20 候选施加单调硬约束。`[verified: evidence.json targets3904.nonmonotone_psnr_image_counts] [opinion: 约束判断]`
- **零误差通道影响决策。** 给真实 MSE 加 1e-9 下限并去掉零通道识别后，6 张图块大小、36 张完整配置改变，严格通过率降到 88.93%。`[verified: evidence.json targets3904.positive_floor_without_zero_mask]`
- **原搜索成本分布偏斜。** 10000 张训练图的 search_ms 平均 406.0 ms，中位数 259.5 ms，P95 1262.1 ms；平均尝试 7.77 个候选，中位数 6。同步导入平均 2382.9 ms，单独计。首个候选就通过的图，原搜索本来只编码一次；模型路径的节省主要来自需要更小块或更慢 preset 的图。详见 [Unity 搜索基线](<../../experiment report/unity-search-baseline-lite-rdo-off/README.md>)。`[verified: evidence.json search_baseline10000] [opinion: 成本推论]`

## V2 方案

### 预测目标与决策

- **能直接算的不预测**：纯黑像素比例、尺寸、sRGB／法线／Alpha 用途既是模型输入，也直接决定规则分支与门槛。`[verified: unity_patch_dataset.py METADATA_NAMES；policy.py select] [opinion]`
- **patch 头**：每个 240 patch 输出 20 候选×RGBA 的 log-MSE，按有效像素数在 MSE 域合成整图通道 MSE，再按 Unity 口径算 PSNR。`[verified: models/unity_quality.py channel_head；evaluation/unity_quality.py aggregate_mse、psnr]`
- **整图头**：输出 20×4 零误差通道概率，以及 20 候选的 MS-SSIM（sRGB 非法线图）、平均角度和 p95 角度（法线图）。这些指标不能由 patch 平均得到。`[verified: models/unity_quality.py image_head、pool_features]`
- **决策**：每张图使用绑定其原采集的 `UnitySearchPolicy`，候选顺序、提前停止、锁块和回退原样执行。PSNR、MS-SSIM、角度的余量分别设置，零通道概率门槛同样在 validation 上选择。详见 [原生模型报告](<../../experiment report/unity-accuracy90-20261111/unity-native-model.md>)。`[verified: unity-native-model.md“监督与验收”] [opinion: 余量设置]`

### 模型与训练起点 R0

- **模型**：`UnityQualityRegressor`，ResNet-18 骨干（标准 stem，含 maxpool），5 通道输入（RGBA＋有效像素 mask），导入属性经 FiLM 调节特征并进入整图头，共 11,377,660 参数。随机初始化为主线。`[verified: evidence.json model；unity-accuracy90 README“随机初始化为主线，预训练为独立对照”]`
- **配方**：沿用原正式队列保留的配置；该队列已按用户数据收尾指示取消，V2 训练使用新身份。`[verified: unity-data-handoff-v1.json training_auto_start]` 30 轮，每批 16 张图，每图每轮有放回抽 4 个 patch；AdamW lr 3e-4、weight decay 0.05，1 轮 warmup 后余弦，FP16 AMP，patience 5，seed 20261112；三项附加 loss 权重均 0.1，零通道门槛 0.5。选模先看 validation 块大小 Top-1，再看颜色图近阈值 RMSE，见 [原生训练报告](<../../experiment report/unity-accuracy90-20261111/unity-native-training.md>)。`[verified: evidence.json model.queued_recipe；unity-native-training.md]`
- **已知风险**：训练时整图头只看到每图 4 个 patch 的均值和最大值，验证时用全部 patch，大图上两者分布不同；整图目标每图只有一组，法线图约占 6.7%；四项 loss 单位不同，附加权重尚未验证。`[verified: unity-native-training.md；models/unity_quality.py pool_features；evidence.json targets3904.input_conditions] [opinion: 风险判断]`

### 评估与选模

- **主指标**：validation 块大小 Top-1、balanced accuracy、逐类 precision／recall 与混淆矩阵。`[opinion]`
- **分组**：sRGB 小图、sRGB 大图、Linear、法线；原选择分支；长边量级；资产组宏平均。`[opinion]`
- **质量与字节**：实际解码的严格通过率，与原标签及固定 8×8／medium 对照；质量回退图数；错误方向；payload 相对固定 8×8 与原标签。`[opinion]`
- **预测精度**：颜色 PSNR 在有效门槛 ±3 dB 内的 RMSE，MS-SSIM 在 21 dB 附近的误差，角度在 3.2° 和 9° 附近的误差，零通道的混淆矩阵。`[opinion]`
- **余量曲线**：每类余量对 Top-1、严格通过率和 payload 的影响。`[opinion]`
- **成本**：预处理、推理、决策和最终编码分段计时，与原搜索 search_ms 及固定 8×8 编码配对比较，按标签块大小和 preset 分层，计时路径见 [同次预测与编码计时](<../../experiment report/unity-accuracy90-20261111/unity-deployment.md>)。`[verified: unity-deployment.md 计时路径] [opinion: 分层方式]`
- GDC test2000 和任何 GDC 结果不参与；确认集只在 E6 使用一次。`[opinion]`

## 实验步骤

| 编号 | 内容 | 完成或晋级判据 |
|---|---|---|
| E0 数据就绪 | 完成 train10000／validation1000 参考采集与 20 候选补测；patch 目标、合并和 Dataset 读取；全部 11000 张原规则重放；开发集精确与近重复审计 | 覆盖 complete 且 counts 等于完整划分；重放的块大小、preset、选择原因、候选测量次数（candidates_measured）全部一致；失败以新身份重试并保留原记录 |
| E1 规则侧诊断（不训练） | validation1000 上统计固定 6×6／8×8／10×10／12×12（medium）、始终 12×12、只看 PSNR 规则的 Top-1、严格通过率和 payload；在训练划分的实测指标上，分别和同时给 PSNR、MS-SSIM、角度加高斯误差并重放规则 | 得到各指标达到 90% 所需的精度，作为 E2–E4 的误差目标 |
| E2 原生基线 R0 | 按保留的 R0 配方，以新身份在完整开发集上 CUDA 训练，先跑小样本闭环 | validation Top-1≥90% 进入 E6，否则进入 E3 |
| E3 误差归因（不重训） | 冻结 R0 的 validation 预测，逐项把 PSNR 通道误差、零通道、MS-SSIM、角度换成实测值后重放规则；按分组统计错误 | 得到瓶颈排序，决定 E4 的顺序 |
| E4 单项改进 | 每次只改一项并使用新实验身份。候选项：整图头训练与推理的 patch 数一致，或只用均值池化；附加 loss 权重，含只训 PSNR 部分的 0 权重对照；两阶段训练，先训骨干和 patch 头，再训整图头；ImageNet 预训练初始化，RGB 卷积核照搬，Alpha 和 mask 通道置零；资产组限权与法线过采样；EMA 与 BN 重估；必要时法线专用模型 | 相对当前最优报告 validation Top-1、分组结果、瓶颈指标误差和推理成本 |
| E5 扩大容量 | E4 各项都没有增益时，再试 ResNet-34／50 或加宽 | 同 E4，另报告参数量和每图推理耗时 |
| E6 冻结与独立确认 | 在 validation 上定权重、余量和零通道门槛；满足开发准入后用 `UnityEvaluationSeal` 封存，确认集 2000 只运行一次，含配对计时 | 块大小 Top-1≥90% 为主验收，其余指标全部报告；不依据确认集结果回头选模 |

`[verified: unity-confirmation-evaluation.md；unity-native-pipeline.md；AGENTS.md“按固定容量诊断、单项训练改进、必要时扩大网络的顺序推进”] [opinion: 步骤与判据]`

## 待决定事项

用户 2026-11-12 已确认以下三项：

- **质量约束**：验收只看块大小 Top-1≥90%；严格通过率、质量回退和 payload 全部报告，不设门槛。`[verified: 用户本轮选择“只看 Top-1≥90%，质量和字节全部报告但不设门槛”]`
- **preset**：只报告块大小＋preset 完整匹配率，不设目标。preset 不影响字节，只影响质量和编码时间。`[verified: 用户本轮选择“只报告块大小＋preset 完整匹配率，不设门槛”；AGENTS.md“同图同尺寸同blockSize的payload容量相同”]`
- **执行依据**：此前数据goal已完成采集与验收，用户随后要求创建新goal执行V2；V1正式训练自动队列已取消。`[verified: 用户“查看V2版本的实验之后，创建一个goal开始实验”；unity-data-handoff-v1.json；unity-data-delivery-v3-verification.json]`

以下三项等 E4／E6 有结果再定：

1. **初始化**：维持随机初始化为主线；如果 E4 中 ImageNet 预训练在 validation 上明显更好，是否允许改为主线。`[opinion]`
2. **系统变体**：是否增加两个系统对照，一是把预测结果作为搜索起点、按原顺序实测续搜，二是法线图直接走原搜索。两者改变 Top-1 和成本的含义，需要单独报告。`[opinion]`
3. **确认失败后的处理**：确认集只能使用一次。完成本次V2范围修订后剩余441张备用，后续只用于身份或像素重复替换。E6 未达标时，是否另外预留新的独立确认集。`[verified: unity-confirmation-cohort.md；unity-confirmation2000-v2.json reserve_images] [opinion]`

## 运行约束

- 训练和推理使用 CUDA，GPU 任务与现有队列串行。`[verified: AGENTS.md CUDA 与串行调度条目]`
- 活动任务绑定的源码不热改；需要修订时使用新的实验身份，必要时先处理对应任务并保留原记录。`[verified: AGENTS.md“活动期间保持配置绑定的14个源码文件不变”]`
- 先小样本、再全量；输出和报告不可覆盖，失败保留。进度写入 [progress.json](<../../experiment report/unity-accuracy90-20261111/progress.json>)，阶段结果同步仓库。`[verified: AGENTS.md 实现与实验条目]`

## 限制与待核实

- 分布数字来自先完成的 3904 张训练图，是冻结采集顺序下的部分覆盖。`[verified: evidence.json targets3904.scope]`
- 原规则重放一致只说明规则复现无误。原标签包含大图放宽和回退，严格通过率 89.70%。`[verified: evidence.json targets3904]`
- 已检查的 7744 张训练图和 2 张验证图中，有 5 组精确 RGBA 重复和 6 对近重复，全部在训练划分内、不跨划分，报告中单列。确认集隔离限于资产组、源哈希、精确 RGBA 和同尺寸近重复，裁剪、缩放和语义相似性没有完整证明。`[verified: evidence.json isolation]`
- 计时范围是参考 PNG 到内存 mip0 ASTC，不含 Unity 导入和完整 mip 链；小样本计时不能外推。`[verified: unity-deployment.md 计时路径]`
- E1 的高斯误差模拟假设误差与图像无关，只作精度量级参考。`[opinion]`

## 版本记录

- V2（2026-11-12）：初版，只使用 Unity 协议，依据现有 Unity 原生数据、规则重放与已排队训练配置。`[verified: evidence.json]`
- V2 修订（2026-11-12）：记录用户对质量约束、preset 和执行依据的决定，验收与实验步骤不变。`[verified: 用户本轮选择]`
