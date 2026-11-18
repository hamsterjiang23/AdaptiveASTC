# V3 ASTC 自动选参实验报告

## 实验结论

当前选定方案为 **Unity参考图输入、ResNet-34候选质量预测、20候选起点续搜**。在1000张开发验证图上，最终块大小与原Unity标签一致的比例为 **93.6%**，平均编码 **1.627次／图**，文件到内存mip0 ASTC的批量耗时为 **195.60 ms／图**。Blocksize与Quality均一致的完整配置匹配率为 **80.4%**，严格质量通过率为 **87.5%**，相对原标签的严格质量回退为 **0张**。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics、median_file_batch_seconds]`

原图输入路线通过配对训练和实际续搜达到 **92.1%**，耗时 **208.32 ms／图**。删除exhaustive后，Unity输入系统耗时下降到 **105.33 ms／图**，块大小准确率为 **86.7%**。按已经约定的准确率优先排序，最终采用20候选的Unity输入方案。`[verified: ../unity-v3-20261113/summary.json systems、recommendation；../../experiment plan/V3/README.md 第2节“选定与冻结”]`

上述结论覆盖本轮LDR、Tex2D、RGBA8、mip0、RDO关闭协议，以及用于开发、选模的10000张训练图和1000张验证图。2000张确认图的独立评价合同已准备，正式执行授权字段为false。`[verified: ../../experiment plan/V3/README.md 第1节；../unity-v3-20261113/source-input-audit.json counts；../unity-v3-20261113/confirmation-contract.json cohort、confirmation_execution_authorized、test_opened]`

## 一 实验目的

V2已经形成“预测候选起点，再按实际压缩质量续搜”的系统，开发验证块大小准确率为93.6%。V3沿用这一基础，验证输入来源、候选范围和处理成本的取舍。`[verified: ../../experiment plan/V3/README.md 第1节“继承基础与实验边界”]`

| 要回答的问题 | 实验目的 | 判断依据 |
|---|---|---|
| 当前流程实际需要多长时间 | 用实际预测、编码、解码和质量检查时间描述成本 | 同机、同DLL、同1000图比较原规则搜索、固定8×8、纯预测一次编码和预测起点续搜。`[verified: ../../experiment plan/V3/README.md 第2节“真实耗时基线”]` |
| exhaustive是否值得保留 | 量化删除最高搜索档后的耗时、准确率和质量变化 | 比较20候选与16候选，主评分沿用原20候选Unity标签。`[verified: ../../experiment plan/V3/README.md 第2节“exhaustive裁剪”及其后标签约定]` |
| 模型输入能否直接来自源图 | 检验源文件加明确导入配置能否预测Unity协议下的压缩质量 | 先冻结V2模型改变输入，再对Unity输入和尺寸对齐原图分别执行同配方训练。`[verified: ../../experiment plan/V3/README.md 第2、3节]` |

主准入条件为系统最终块大小Top-1达到90%。Quality档位匹配、实际质量、字节数、编码次数及耗时同时报告。本轮优先保证准确率，mask／MSAK的专项通道语义按既定范围暂缓。`[verified: ../../experiment plan/V3/README.md 第1、4节]`

## 二 实验如何实施

### 输入与质量监督

流程中涉及三种图像。源图是磁盘上的原始资产，Unity参考图是完成导入处理后、进入ASTC编码前的RGBA像素，解码图是ASTC数据重新解码得到的像素。本轮质量监督和最终质量计算，均比较Unity参考图与对应ASTC解码图。`[verified: ../../experiment plan/V3/README.md 第3节“监督仍来自Unity”；../../reproductions/unity_search_baseline/v3_deployment.py V3NativeQueries.measure；../../src/adaptive_astc/data/unity_v3_dataset.py UnityV3PatchDataset]`

```text
源文件与导入配置 → Unity导入处理 → Unity参考像素 → ASTC编码 → ASTC解码像素
                                     └──────── 质量比较 ────────┘
```

原图分支将“源图像素与明确提供的属性”送入模型，学习预测上面这条Unity编码链路的质量。首次候选起点确定后，实际编码和质量检查使用Unity参考像素及真实属性。原图分支的黑像素比例、Alpha恒定性由原图输入计算，真实质量门控再使用Unity参考像素对应的属性。`[verified: ../../src/adaptive_astc/data/unity_v3_input.py UnityV3InferenceInput；../../reproductions/unity_search_baseline/v3_deployment.py UnityV3DeploymentTrial.run]`

输入比较包含三种方式。`[verified: ../../experiment plan/V3/README.md 第2、3节]`

| 输入方式 | 具体处理 | 用途 |
|---|---|---|
| Unity参考图 | 读取原尺寸RGBA参考图 | 冻结模型对照及配对训练。`[verified: ../../src/adaptive_astc/data/unity_inference.py UnityInferenceInput；../../src/adaptive_astc/training/unity_v3_trainer.py]` |
| 原尺寸源图 | 解码为RGBA，按源尺寸切patch，导入目标尺寸由调用方明确提供 | 冻结V2模型的输入诊断。`[verified: ../../src/adaptive_astc/data/unity_v3_input.py SourceTextureSpec、UnityV3InferenceInput]` |
| 尺寸对齐原图 | 使用固定Pillow解码器转为RGBA，以BICUBIC缩放至Unity目标尺寸，再使用相同patch坐标和边缘填充 | 冻结模型诊断及原图配对训练。`[verified: ../../src/adaptive_astc/data/unity_v3_input.py pixels；../../src/adaptive_astc/data/unity_v3_dataset.py UnityV3PatchDataset]` |

源文件核验覆盖10000张训练图和1000张验证图，全部解码并匹配原采集MD4，失败0张。训练图有3167张、验证图有368张的源尺寸与Unity目标尺寸不同。在1000张验证图中，源图尺寸对齐后仍有653张与Unity参考图存在RGB差异，60张存在Alpha差异。这些分组可重叠。`[verified: ../unity-v3-20261113/source-input-audit.json counts、failures；../unity-v3-20261113/input-diagnostics.json pixel_differences、group_indices]`

### Unity选参和质量规则

20候选按12×12、10×10、8×8、6×6排列，每个块大小下依次为fastest、fast、medium、thorough、exhaustive。Quality控制编码器搜索档位，Blocksize决定所用块网格。16候选方案保留前四档Quality，模型输出维度保持20，决策、实际查询和回退共用明确的16候选集合。`[verified: ../../reproductions/unity_search_baseline/v3_policy.py NativeCandidateSet；../../reproductions/unity_search_baseline/supplement.py UnityASTCBackend.PRESETS、BLOCKS]`

本轮使用原采集绑定的规则与float32判定精度。验证图对应的质量阈值如下。`[verified: ../../reproductions/unity_search_baseline/v3_policy.py effective_threshold、_metrics、_strict；verification.json derived.policy_values]`

| 用途 | 严格质量条件 |
|---|---|
| sRGB颜色图 | PSNR达到有效阈值，同时MS-SSIM的原生dB表达达到21 dB，对应字段ms_ssim_db。基础PSNR为30 dB，纯黑像素比例大于40%时使用35 dB，大于80%时使用37 dB。`[verified: ../../reproductions/unity_search_baseline/v3_policy.py effective_threshold、_strict；verification.json derived.policy_values]` |
| Linear非法线图 | PSNR达到同一套有效阈值。`[verified: ../../reproductions/unity_search_baseline/v3_policy.py _strict、effective_threshold]` |
| 法线图 | 平均角度误差不超过3.2°，p95角度误差不超过9°。法线用途由导入配置或调用方normal字段提供。`[verified: ../../reproductions/unity_search_baseline/v3_policy.py _strict；verification.json derived.policy_values；../../src/adaptive_astc/data/unity_v3_input.py SourceTextureSpec]` |

原规则还包含大图锁块与放宽分支。sRGB非法线图面积达到512²时，首个PSNR合格候选锁定块大小，在同块寻找满足MS-SSIM的候选，必要时采用该块最后一个PSNR合格候选并记录size_first_relaxed。其余失败情况在已测候选中按最高PSNR回退，记录highest_psnr_fallback。V3继续使用这些分支，并核对原块大小、Quality、选择原因和测量次数。`[verified: ../../reproductions/unity_search_baseline/v3_policy.py search；verification.json derived.policy_values.sizeFirstMinSideLarge；../unity-v3-20261113/candidate-ablation.json status；../../reproductions/unity_search_baseline/v3_experiment.py offline]`

### 模型与配对训练

模型使用ImageNet初始化的ResNet-34。输入由RGBA patch、有效像素mask和8项属性构成，属性包括目标宽高、sRGB、法线用途、Alpha需求、Alpha恒定性、法线评价mip数及纯黑像素比例。图像按240×240切patch，边缘采用复制填充，训练每图抽取4个patch，验证和部署遍历整图patch。`[verified: ../../src/adaptive_astc/models/unity_quality.py encode；../../src/adaptive_astc/data/unity_v3_input.py UnityV3InferenceInput、__getitem__；../../experiment plan/V3/README.md 第3节；../unity-v3-20261113/train-unity-full-full-v1.json config]`

逐patch质量头输出20候选的RGBA四通道误差。推理将误差还原到MSE域并按有效像素聚合，用原生规则计算PSNR。整图质量头从聚合特征与属性预测零误差通道、MS-SSIM及法线平均／p95角度，再由规则层选出具体Blocksize和Quality。`[verified: ../../src/adaptive_astc/models/unity_quality.py encode、predict_images；../../src/adaptive_astc/evaluation/unity_quality.py UnityQualityPrediction]`

两条配对路线分别使用Unity参考图和尺寸对齐原图，均从相同ImageNet初始化开始，先训练全模型30轮，再冻结编码器与逐通道误差相关部分训练整图头30轮。沿用每批16图、每图4patch、学习率3e-4、weight decay 0.05和seed 20261112。每阶段按块大小准确率优先、近阈值PSNR RMSE次之选择权重，并重载复核预测。`[verified: ../../experiment plan/V3/README.md 第3节；../unity-v3-20261113/train-unity-full-full-v1.json、train-unity-head-full-v1.json、train-source_aligned-full-full-v1.json、train-source_aligned-head-full-v1.json 的config、history、checkpoint_audit]`

| 输入路线 | 全模型30轮最佳纯预测准确率 | 整图头30轮最佳纯预测准确率 | 两阶段进程时间 |
|---|---|---|---|
| Unity参考图 | 86.2% | 86.9% | 2227.99＋412.73秒。`[verified: ../unity-v3-20261113/train-unity-full-full-v1.json、train-unity-head-full-v1.json checkpoint_audit.metrics；summary.json training_costs.unity]` |
| 尺寸对齐原图 | 81.0% | 81.7% | 2767.52＋617.31秒。`[verified: ../unity-v3-20261113/train-source_aligned-full-full-v1.json、train-source_aligned-head-full-v1.json checkpoint_audit.metrics；summary.json training_costs.source_aligned]` |

Unity输入重训练的完整1000图质量预测存档与V2存档具有相同SHA。这组对照复现了V2的验证预测，配对训练后的系统计时另行实测。`[verified: ../unity-v3-20261113/summary.json unity_input_retraining_reproduction]`

### 从预测起点得到最终ASTC

```text
图片与属性 → 预测20候选质量 → 规则选择候选起点
                              ↓
                  按原规则真实编码、解码、检查质量
                              ↓
                  必要时继续查询后续候选 → 最终ASTC
```

续搜按候选顺序从预测起点向后执行，常规分支、大图锁块、放宽和最高PSNR回退均保留。最终输出复用搜索中已经生成的ASTC。所选系统在1000图上实际编码1627次，其中702张一次完成，编码次数P95为5次，最大16次。`[verified: ../../reproductions/unity_search_baseline/v3_policy.py search；../../reproductions/unity_search_baseline/v3_deployment.py UnityV3DeploymentTrial.run；../unity-v3-20261113/summary.json recommendation.metrics；selected-output-audit.json source_trace的measured_indices]`

真实编码及解码使用astcenc-avx2-shared.dll，质量计算使用unity_astc_quality.dll。每个正式组合保存查询轨迹、输出ASTC、解码PNG及SHA，并核对离线重放与实际查询，重新解码后复算原生质量。`[verified: ../../reproductions/unity_search_baseline/v3_benchmark.py audit、run；../../experiment plan/V3/evidence.json binaries；../unity-v3-20261113/selected-output-audit.json]`

### 计时与评价口径

所有正式组合使用同批1000图、同一机器和绑定SHA的DLL，固定图片与候选顺序，每路线先以8张图预热一次，再正式重复三次，GPU时间同步。分别测量文件读取到内存ASTC的files口径，以及RGBA像素就绪后的pixels_ready口径。files批量覆盖完整1000图，pixels_ready批量按8图分组汇总。单图模式逐图执行新的预测和编码，记录平均值、中位数与P95。`[verified: ../../reproductions/unity_search_baseline/v3_benchmark.py run、measure；../../reproductions/unity_search_baseline/v3_deployment.py _single_image_trials；各benchmark配置warmups、repetitions、measurement_modes]`

各路线在所需模型与DLL就绪后开始主计时。原规则搜索和续搜路线在真实质量门控完成、最终内存ASTC确定并保留时结束，纯预测一次编码与固定8×8路线在内存ASTC生成时结束，其质量指标由输出解码审计提供。Unity导入和监督标签构建使用已完成的采集归档，模型／DLL构造、训练、最终输出审计及ASTC／PNG写盘分别有独立记录。运行中的轨迹哈希与进度写盘也单列计时，end_to_end_seconds由运行墙钟时间扣除这两类记录成本得到。`[verified: ../../reproductions/unity_search_baseline/v3_deployment.py run 的scope_details、elapsed计算；../../reproductions/unity_search_baseline/v3_benchmark.py audit；../unity-v3-20261113/input-diagnostics.json model_setup_seconds、binary_setup_seconds；selected-output-audit.json audit_and_astc_png_write_seconds]`

原图pixels_ready口径接收已经解码的源尺寸RGBA，尺寸对齐操作仍在该口径计时内。两个批量口径分别按完整1000图和8图分组组织预测，使用各自的实测结果。`[verified: ../../reproductions/unity_search_baseline/v3_benchmark.py measure；../../src/adaptive_astc/data/unity_v3_input.py pixels]`

| 指标 | 本轮统计含义 |
|---|---|
| 块大小Top-1 | 最终Blocksize与原20候选Unity标签一致的图片比例，主准入条件为≥90%。`[verified: ../../experiment plan/V3/README.md 第4节；../../script/diagnose_unity_rules.py summarize]` |
| 完整配置匹配 | Blocksize与Quality档位同时一致的比例。`[verified: ../../script/diagnose_unity_rules.py summarize 的full_choice_accuracy]` |
| 严格质量通过 | 最终候选实际质量满足上文严格阈值的比例。`[verified: ../../script/diagnose_unity_rules.py prepare、summarize；../../reproductions/unity_search_baseline/v3_benchmark.py audit]` |
| 相对原标签质量回退 | 原标签严格合格、当前结果严格不合格的图数。`[verified: ../../script/diagnose_unity_rules.py summarize 的quality_regression_images]` |
| payload | 实际mip0 ASTC纹理块数据字节数，容器头另计。`[verified: ../../reproductions/unity_search_baseline/v3_benchmark.py audit 的len(container)-16核验]` |
| 批量耗时与单图延迟 | 前者为三次整集耗时中位数摊销，后者来自逐图独立计时序列。`[verified: ../../reproductions/unity_search_baseline/v3_benchmark.py run；../unity-v3-20261113/summary.json recommendation.single_image_latency_ms]` |

## 三 实验结果

### 原规则与固定参数基线

下表来自冻结V2模型的同批次对照，耗时均为files口径的批量摊销值。原规则搜索在同一DLL上实际逐候选执行，其块大小、Quality、原因及次数重现原标签。`[verified: ../unity-v3-20261113/benchmark-v2-full1000-v1.json；../../reproductions/unity_search_baseline/v3_experiment.py offline]`

| 路线 | 块大小匹配率 | 严格质量通过 | 编码次数／图 | ms／图 |
|---|---|---|---|---|
| 原20候选规则搜索重放 | 100.0% | 87.4% | 7.061 | 445.02。`[verified: ../unity-v3-20261113/benchmark-v2-full1000-v1.json results.original-full20]` |
| 固定8×8／medium | 14.3% | 81.1% | 1.000 | 23.70。`[verified: ../unity-v3-20261113/benchmark-v2-full1000-v1.json results.fixed8-full20]` |
| 模型纯预测后一次编码 | 86.9% | 68.2% | 1.000 | 128.38。`[verified: ../unity-v3-20261113/benchmark-v2-full1000-v1.json results.pure-unity-full20]` |
| 模型预测起点后续搜 | 93.6% | 87.5% | 1.627 | 200.84。`[verified: ../unity-v3-20261113/benchmark-v2-full1000-v1.json results.forward-unity-full20]` |

历史Unity原始采集的search_ms平均为1068.42 ms、中位数514.70 ms、P95为4219.77 ms，记录其原采集计时范围。本轮规则重放耗时按当前文件到ASTC测量口径记录。`[verified: ../unity-v3-20261113/summary.json historical_unity_capture_timings.search_ms；controls中original-full20]`

### 冻结模型改变输入

| 冻结V2权重的输入 | 纯预测准确率 | 续搜准确率 | 编码次数／图 | 续搜ms／图 |
|---|---|---|---|---|
| Unity参考图 | 86.9% | 93.6% | 1.627 | 200.84。`[verified: ../unity-v3-20261113/benchmark-v2-full1000-v1.json unity／full20结果]` |
| 原尺寸源图 | 76.9% | 92.8% | 2.382 | 239.33。`[verified: ../unity-v3-20261113/benchmark-v2-full1000-v1.json source_native／full20结果]` |
| 尺寸对齐原图 | 81.9% | 87.3% | 1.577 | 197.14。`[verified: ../unity-v3-20261113/benchmark-v2-full1000-v1.json source_aligned／full20结果]` |

原尺寸源图保留较高的续搜准确率，同时需要更多实际编码。尺寸对齐使纯预测准确率从76.9%变为81.9%，续搜准确率从92.8%变为87.3%。`[verified: 上表对应结果]` 评价输入变更时，应同时观察预测起点与续搜后的完整系统。`[opinion]`

### 配对训练后的候选组合

| 输入与候选 | 纯预测准确率 | 续搜准确率 | 编码次数／图 | 续搜ms／图 |
|---|---|---|---|---|
| Unity参考图，20候选 | 86.9% | 93.6% | 1.627 | 195.60。`[verified: ../unity-v3-20261113/benchmark-trained-unity-full1000-v1.json full20结果]` |
| Unity参考图，16候选 | 84.9% | 86.7% | 1.562 | 105.33。`[verified: ../unity-v3-20261113/benchmark-trained-unity-full1000-v1.json no_exhaustive16结果]` |
| 尺寸对齐原图，20候选 | 81.7% | 92.1% | 1.838 | 208.32。`[verified: ../unity-v3-20261113/benchmark-trained-source_aligned-full1000-v1.json full20结果]` |
| 尺寸对齐原图，16候选 | 80.9% | 85.3% | 1.693 | 121.26。`[verified: ../unity-v3-20261113/benchmark-trained-source_aligned-full1000-v1.json no_exhaustive16结果]` |

16候选原规则重放与原20候选标签的块大小变化率为6.2%。该值描述候选集合改变后原规则的选择变化，模型评价继续以原20候选标签计分。`[verified: ../unity-v3-20261113/candidate-ablation.json results.no_exhaustive16.oracle.accuracy；../../experiment plan/V3/README.md 第2节标签约定]`

### 所选系统的质量与体积

| 指标 | 结果 |
|---|---|
| 块大小匹配 | 936／1000，93.6%。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics.accuracy]` |
| Blocksize＋Quality匹配 | 804／1000，80.4%。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics.full_choice_accuracy]` |
| 严格质量通过 | 875／1000，87.5%。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics.actual_strict_quality_pass_rate]` |
| 相对原标签严格质量回退 | 0张。原标签874张严格合格图全部保留，另新增1张严格合格图。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics及原规则基线；quality_regression_images=0]` |
| mip0 payload | 32,067,120字节。固定8×8／medium为59,761,616字节，比例53.66%。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics payload_bytes、fixed8_medium_payload_bytes、payload_ratio_to_fixed8]` |
| 相对原搜索标签payload | 101.28%，即高1.28%。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics.payload_ratio_to_original]` |
| 编码次数 | 702张一次完成，平均1.627次，P95为5次，最大16次。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics；selected-output-audit.json source_trace的measured_indices]` |

### 实际时间花在哪里

所选系统的files／batch第2次正式重复正好对应三次总耗时的中位数，1000图耗时195.5956秒。以下为这一次重复的分段摊销，末位差异包含计时与循环开销。`[verified: ../unity-v3-20261113/benchmark-trained-unity-full1000-v1.json results.forward-unity-full20.measurements中scope=files、mode=batch、repeat=1的timings]`

| 分段 | ms／图 | 原始字段 |
|---|---|---|
| 模型输入准备 | 6.28 | input_preparation_seconds。`[verified: 同一重复timings]` |
| patch读取、推理、传输及聚合 | 12.72 | inference_wall_seconds。`[verified: 同一重复timings]` |
| 实际编码参考像素读取、属性与行序准备 | 6.85 | reference_load_metadata_and_flip_seconds。`[verified: 同一重复timings]` |
| 策略与簿记 | 0.78 | policy_and_bookkeeping_seconds。`[verified: 同一重复timings]` |
| ASTC编码 | 134.99 | native_encode_seconds。`[verified: 同一重复timings]` |
| ASTC解码 | 12.60 | native_decode_seconds。`[verified: 同一重复timings]` |
| 原生质量计算 | 21.33 | native_quality_seconds。`[verified: 同一重复timings]` |
| 文件到最终内存ASTC总时间 | 195.60 | end_to_end_seconds。`[verified: 同一重复timings]` |

纯预测一次编码与固定8×8一次编码各自使用对应的Blocksize和Quality，其总耗时包含各自参数的实际编码成本。模型输入准备和推理时间由上表的独立字段给出。`[verified: ../../reproductions/unity_search_baseline/v3_deployment.py UnityV3DeploymentTrial.run；../unity-v3-20261113/benchmark-v2-full1000-v1.json pure-unity-full20、fixed8-full20的timings]`

所选系统三轮逐图测量的平均延迟为228.48、229.12、230.49 ms，中位数为91.46、93.40、95.04 ms，P95为608.67、610.91、612.54 ms。`[verified: ../unity-v3-20261113/summary.json recommendation.single_image_latency_ms.files]` 批量调度成本可参考195.60 ms／图的摊销，单图等待预算可参考逐图延迟分布。`[opinion]`

计时过程中记录到并发Blender CPU活动，原规则搜索单图模式的三次整集时间分别为468.65、522.54、640.14秒。冻结V2与Unity重训练对照的完整验证预测存档SHA相同，两批续搜实测摊销分别为200.84与195.60 ms／图。`[verified: ../unity-v3-20261113/resource-observations.jsonl；benchmark-v2-full1000-v1.json original-full20的files／single重复；summary.json unity_input_retraining_reproduction、systems]` 该5.24 ms差值的模型归因具有不确定性，当前结果支持同一预测路线及其实际运行成本的复现。`[opinion]`

## 四 最终结论如何解读

### 原图入口可用于本轮开发目标，完整流程依赖明确的Unity协议

原图模型只读取源图和调用方提供的源尺寸、目标尺寸、sRGB、normal、need_alpha与normal_metric_mips等信息，颜色和Alpha统计从该输入计算。配对训练后的原图20候选续搜准确率为92.1%，达到90%的开发准入条件。训练质量目标及实际质量门控均来自Unity参考像素对应的压缩结果。`[verified: ../../src/adaptive_astc/data/unity_v3_input.py SourceTextureSpec；../unity-v3-20261113/summary.json 原图训练系统；../../reproductions/unity_search_baseline/v3_deployment.py run]`

这项结果支持在已知导入配置下，使用源图完成本轮验证图的模型起点预测。当前原图系统以1.838次平均编码、208.32 ms／图获得92.1%，Unity输入系统以1.627次、195.60 ms／图获得93.6%，按准确率优先排序选定Unity输入。`[verified: ../unity-v3-20261113/summary.json systems、recommendation]`

### 预测错误的方向会影响续搜效果

相对于原标签，选了更小的ASTC块通常会增加payload，以下称为“起点偏小”；选了更大的块称为“起点偏大”。后缀续搜沿12→10→8→6的顺序查询，查询范围由起点和后续候选确定。`[verified: ../../reproductions/unity_search_baseline/v3_policy.py NativeCandidateSet.GRID、search；../../src/adaptive_astc/training/unity_v3_trainer.py UnityV3Prediction.score的payload计算]`

| 原图输入与模型 | 纯预测起点偏小 | 纯预测起点偏大 | 续搜后偏小 | 续搜准确率 |
|---|---|---|---|---|
| 原尺寸源图，冻结V2 | 70 | 161 | 72 | 92.8%。`[verified: ../unity-v3-20261113/summary.json controls、systems中的source_native／full20]` |
| 尺寸对齐原图，冻结V2 | 125 | 56 | 127 | 87.3%。`[verified: ../unity-v3-20261113/summary.json controls、systems中的冻结V2 source_aligned／full20]` |
| 尺寸对齐原图，配对训练 | 77 | 106 | 79 | 92.1%。`[verified: ../unity-v3-20261113/summary.json controls、systems中的原图训练source_aligned／full20]` |

尺寸对齐原图重训练的纯预测准确率从81.9%变为81.7%，续搜准确率从87.3%变为92.1%。本组数据中，偏小起点由125张下降至77张。起点偏大的图可以沿后续候选尝试更小的块，起点偏小的图则已跳过前面的更大块候选。`[verified: 上表及../unity-v3-20261113/summary.json；../../reproductions/unity_search_baseline/v3_policy.py search]` 这组错误方向分布与续搜收益相符，评价重训练效果时应结合完整系统。`[opinion]`

将两组同序1000图逐张配对，续搜结果中纠正了65张旧错误，同时新增17张错误，净增加48张正确。纯预测则纠正63张、增加65张错误，净减少2张正确。该逐图统计给出上述准确率变化的组成。`[verified: 两份benchmark的pure-source_aligned-full20、forward-source_aligned-full20，files／batch／repeat=0的trace_archive与原验证标签逐张配对；verification.json derived.source_training_paired_transitions]`

颜色候选近阈值PSNR RMSE在冻结V2的尺寸对齐输入下为2.0300 dB，在原图重训练后为2.4997 dB。因此，本次原图重训练的收益体现在续搜后的标签匹配率，纯预测块大小准确率和该RMSE分别保留其实际结果。`[verified: ../unity-v3-20261113/input-diagnostics.json controls[2]、controls[4]；summary.json 对应系统结果]`

### exhaustive裁剪节省时间，当前主指标选择20候选

配对训练后的Unity系统从20候选改为16候选，平均编码次数从1.627变为1.562，耗时从195.60降至105.33 ms／图，约减少46.15%。块大小准确率从93.6%降至86.7%，相对原标签出现14张严格质量回退。当前约定的90%准入条件下，这组裁剪系统得分为86.7%。`[verified: ../unity-v3-20261113/benchmark-trained-unity-full1000-v1.json full20、no_exhaustive16结果；按files_batch_median_seconds比值计算]`

Quality档位改变了每次实际编码的成本，因而编码次数相近时，耗时仍会明显变化。`[opinion]` 本轮按准确率优先规则保留20候选，16候选的新规则参照单独记录其6.2%的标签变化率。`[verified: ../unity-v3-20261113/summary.json recommendation；candidate-ablation.json results.no_exhaustive16.oracle]`

### 块大小一致率、完整配置和严格质量各有明确含义

0张相对质量回退的比较集合为原标签已严格合格的874张。所选结果另有125张严格未通过图，选择原因为92张size_first_relaxed、33张highest_psnr_fallback。原标签严格未通过的126张则为93张放宽、33张最高PSNR回退。87.5%反映当前规则、候选范围和输出的实际质量状态，开发准入主指标按约定使用块大小Top-1。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics、原规则基线；selected-output-audit.json source_trace与原1000图严格质量逐项重算；../../experiment plan/V3/README.md 第4节；verification.json derived.strict_quality_outcomes]`

### 相对原搜索节省处理成本，固定8×8保留其速度参照

同批数据的原规则实际重放为445.02 ms／图，所选系统为195.60 ms／图，本轮实测耗时相差56.05%。固定8×8／medium为23.70 ms／图，所选系统耗时约为其8.25倍。固定8×8的严格质量通过率为81.1%，所选系统为87.5%，同时payload为固定8×8的53.66%。这组数值描述逐图选参在质量、体积和处理成本之间的取舍。`[verified: ../unity-v3-20261113/summary.json controls、recommendation.metrics；按对应median_file_batch_seconds比值计算]`

### 法线用途通过显式属性接入，独立确认按后续合同执行

法线用途由外部normal属性提供。验证集45张法线图中，所选系统40张块大小匹配、42张严格角度合格，对应88.89%和93.33%。这些结果评价带明确用途信息的法线选参效果。mask／MSAK专项通道语义沿用本轮暂缓约定。`[verified: ../unity-v3-20261113/summary.json recommendation.metrics.groups.normal；../../src/adaptive_astc/data/unity_v3_input.py SourceTextureSpec；../../experiment plan/V3/README.md 第1节]`

最终合同绑定了所选权重、Unity输入方式、20候选、规则、DLL、计时范围和2000图确认集身份，共享确认封存检查通过。当前状态为prepared_for_execution_review，正式执行授权为false，test_opened为false。后续一次独立确认以原Unity标签块大小Top-1≥90%验收，执行需要单独授权。`[verified: ../unity-v3-20261113/confirmation-contract.json；final-integrity-verification.json confirmation_registry_unopened；../../experiment plan/V3/README.md 第5节]`

## 实施与证据入口

全套执行完成24组正式对照、288次正式测量、120轮训练及74979次实际优化器更新。最终完整性核验覆盖11000条源文件SHA、2035项benchmark绑定，以及1000张开发验证图对应的1000份ASTC和1000份解码PNG，还核对了验证封存记录和原标签936张匹配。四组V3 CPU测试共122项通过，21个Python文件的Ruff和basedpyright检查通过。`[verified: ../unity-v3-20261113/final-integrity-verification.json；../unity-v3-20261113/verification.json final_checks]`

- 实验约定及矩阵见[V3实验计划](<../../experiment plan/V3/README.md>)。`[verified: 该计划第1至5节]`
- 完整数值、分组与权重选择见[结果汇总](../unity-v3-20261113/summary.json)和[输入诊断](../unity-v3-20261113/input-diagnostics.json)。`[verified: summary.json systems、controls、recommendation；input-diagnostics.json controls、group_indices]`
- 每轮真实计时、查询轨迹及ASTC审计见[完整执行记录](../unity-v3-20261113/README.md)。`[verified: 该记录“真实耗时基线”“系统组合”“计时口径与单图延迟”]`
- 正式确认范围与执行开关见[确认合同](../unity-v3-20261113/confirmation-contract.json)。`[verified: cohort、confirmation_execution_authorized、test_opened]`
- 本报告的数值核对、逐图配对统计与文档检查见[报告核验记录](verification.json)。`[verified: verification.json checks、derived、reader_review]`
- 编码与解码库为[astcenc-avx2-shared.dll](<F:/MLBB_Test/haijiangli1_HAMSTERMLBB/Assets/Editor/Astc/Plugins/astcenc-avx2-shared.dll>)，质量计算库为[unity_astc_quality.dll](<E:/ASTC_Compression/experiment report/.local/unity-accuracy90-20261111/unity-quality-native-retry1/build/Release/unity_astc_quality.dll>)，路径和SHA绑定见[V3来源证据](<../../experiment plan/V3/evidence.json>)。`[verified: evidence.json binaries、files_sha256；../../reproductions/unity_search_baseline/v3_deployment.py V3NativeQueries.measure]`
