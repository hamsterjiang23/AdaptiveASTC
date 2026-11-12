# AGENTS.md

## 适用范围与研究定位

- 本文件适用于 `E:\ASTC_Compression` 全目录，执行任务时同时遵循用户提供的全局规则。`[opinion]`
- 当前研究主题为ASTC纹理压缩块大小自动选择，关注质量、真实字节数与处理成本的权衡。`[verified: README.md“当前状态”“已核实的方法与待核实问题”]`
- 以固定8×8为当前生产基线，研究机器学习预测参数后执行一次最终压缩。PSNR 35 dB按项目经验判据记录，法线与MSAK贴图的标准和Unity导入后训练数据的获取方式按待明确事项处理。`[verified: README.md“项目需求与优化目标”]`
- 2026-11-12 用户将当前 goal 改为**完成 Unity 数据采集及完整性验收后结束**，后续模型训练和 90% 准确率验收交给 V2。数据范围为 train10000／validation1000 的原始采集、20 候选补测、patch 语料与规则重放，以及 confirmation2000 原始采集和完整像素审计。V1 未启动的正式训练已取消；任务依赖与完成条件见[数据交接](<experiment report/unity-accuracy90-20261111/unity-data-handoff.md>)。`[verified: 用户“完成数据采集之后goal就能完成了…我要执行V2了”；unity-data-handoff-v1.json]`
- 开始任务先读 [README.md](README.md)，按任务需要读取对应资料和检查记录。研究题目、算法路线与新增实验范围以用户确认的内容为准。`[opinion]`

## 文献发展路线与研究定位

- 完整问题链见[README的发展路线](README.md#文献发展路线与问题演进)，每项工作按“已有问题 → 方法改进 → 剩余限制”阅读和维护。`[verified: README.md“文献发展路线与问题演进”]` `[opinion]`
- **编码加速路线**。昂贵配置搜索 → FasTC／SegTC的结构近似和Web ASTC的启发式 → TexNN的块内部配置预测；Pruned ASTC另以配置裁剪和下游重训练换取低延迟。记录格式、质量损失和任务用途。`[verified: README.md“编码器加速，从昂贵搜索到近似与学习”]` `[opinion]`
- **自动选参路线**。固定参数与人工设置 → 2022年目标PSNR搜索 → 2023年astcenc内部集成。GDC 2023另展示离线试压缩标签与ResNet整图选参；本项目保留分类基线，当前以V1的质量预测和规则决策推进。VBTC作为图内可变分配的系统分支记录。`[verified: README.md“自动选参，从统一配置到质量约束与学习式决策”“研究顺序与分类校准”；experiment plan/V1/README.md]`
- **质量评价路线**。贴图误差 → 多视点渲染比较 → diffuse／normal掩蔽的主观实验、任务专用可见性指标与FLIP误差图。分别记录纹理指标、渲染指标、观看条件和人类接受标准。`[verified: README.md“质量评价，从贴图误差到渲染可见性”]` `[opinion]`
- **表示与部署路线**。NTC联合材质通道与mip，后续分别研究BC特征／NBC的表示、DBC的任务损失、cooperative vectors的硬件加速、hypernetwork的逐材质优化成本及共享解码器的执行分歧。NTBC加载重建、高斯、JPEG和TexF分支分别保留其存储、采样与运行时条件。`[verified: README.md“神经纹理，从联合表示到硬件、训练与解码效率”“其他表示与系统分支”]`
- 直接继承关系以作者明确表述为依据，跨论文的问题链标为综述归纳。Multi-output ASTC归入解码电路，ASTC Encoding Survey作为技术地图；本项目的新颖性与质量／字节收益以进一步文献核实和独立实验评价。`[verified: README.md对应路线及“AdaptiveASTC在这些路线中的位置”]` `[opinion]`

## 目录与资料维护

- `README.md` 汇总项目定位、进展、资料入口、相关研究和综述完整书目。新增研究资料时优先补入已有分类。`[verified: README.md“从这里阅读”“学术综述与相关研究”]` `[opinion]`
- `materials/gdc2023-astc-parameter-selection/source/` 保存视频、原始双语字幕和元数据。按原件维护，校订内容写入 `transcripts/` 并保留字幕条目及时间戳映射。`[verified: README.md“资料目录”]` `[opinion]`
- `materials/gdc2023-astc-parameter-selection/frames/` 保存定时截图和关键页截图。新增截图使用能识别视频时间点的文件名。`[verified: README.md“资料目录”“视频与处理口径”]` `[opinion]`
- `notes/` 保存阅读笔记，`implementation-notes.md` 记录取舍与边界问题，`verification.json` 保存已执行检查的结果。`[verified: README.md“从这里阅读”]`
- Obsidian副本位置由README记录，跨目录同步按用户本次授权范围执行。`[verified: README.md“资料目录”末段]` `[opinion]`

## 文献与证据要求

- 技术结论优先引用论文原文、作者项目页、官方规范与对应代码。引用定位到章节、页码、表格、视频时间戳或代码行。`[opinion]`
- 每项事实、推断和建议使用行内标记。实际读取的证据使用 `[verified: 可定位来源]`，推断、研究设想和建议使用 `[opinion]`。`[verified: 用户提供的全局规则“Output Style — Epistemic Markers”]`
- 分别标明原文结果、综述转述、本地复现结果和研究提议。摘要阅读、全文阅读、书目转录与原文访问失败分别记录核实深度。`[opinion]`
- 综述完整书目保留原编号和书目信息。新增独立论文放入相应导读分类，并附稳定论文链接、DOI或arXiv编号。`[opinion]`
- 演讲正文当前整理为有标签的块大小分类流程。官网简介中的强化学习表述与正文机制的关系，继续按待核实问题记录。`[verified: README.md“需要保留的证据边界”]`
- 分开描述整张纹理的块大小选择、块内部编码配置预测、存储侧压缩和运行时解码，分别说明格式、硬件与过滤要求。`[opinion]`

## 实现与实验

- Unity测试中的`tests/test_unity_quality.py::test_cuda_feature_pool_repeated_outputs_are_bit_identical`实际使用GPU。GPU训练活动期间用`-k "not test_cuda_feature_pool_repeated_outputs_are_bit_identical"`排除，训练完成后独立串行运行；整组测试按实际资源分类记录。`[verified: tests/test_unity_quality.py L356–360；opinion: 执行顺序]`

- 后续V2实验使用[新版数据入口](<experiment report/unity-accuracy90-20261111/unity-v2-data-inputs.json>)绑定的10000／1000开发语料。18张Cube补采、新语料、20候选、Dataset、原规则和完整像素审计均已完成；旧语料仅保留为历史，确认集保持封存。`[verified: unity-data-delivery-v3-verification.json counts、revised_development_replacements、full_pixel_audit_complete、test_opened；opinion: 后续实验约定]`

- 当前数据采集goal的确认集使用[新版V2范围名单](<experiment report/unity-accuracy90-20261111/unity-confirmation-v2-revision.md>)，用户已批准排除39GUI、7Cube及另1HDR源图，保持原主名单位置并按原备用顺序补47张；旧名单与失败记录保持。源文件准入不替代实际导入类型及像素审计，确认集不做全20候选补测、训练或推理。`[verified: 用户本次范围替换选择；unity-confirmation2000-v2.json；opinion: 完成边界]`

- [原生训练标签分布](<experiment report/unity-accuracy90-20261111/unity-native-label-distribution.md>)已覆盖全部10000张训练图／40批次，208个输入SHA、原生选参与回执一致；四类计数1710／1490／1366／5434，放宽大图498、最高PSNR回退377，旧9792条保持。training_complete仅表示训练图原始标签覆盖，不代表验证／20候选目标或模型训练完成。法线按导入用途识别，299张NormalMap的normal_pack均为false；直接父目录分组与历史资产族分组分开解释。统计不使用验证／确认标签或模型预测，不把配比直接当作错误原因，不热改活动训练配置。`[verified: unity-native-labels10000-v1.json summary、model_forward_calls；unity-native-labels10000-verification.json；opinion: 解释与实验边界]`

- [独立确认集评价](<experiment report/unity-accuracy90-20261111/unity-confirmation-evaluation.md>)使用`script/evaluate_unity_confirmation.py`，要求完整原生训练、同一最佳权重的1000图验证Top-1≥90%、原始2000确认图和完整13000图像素审计。候选补测不参与部署输入或最终输出评分；以原始采集验证标签、完整主名单、顺序与原生规则。75项CPU检查与实际66图报告接口通过，正式确认集推理尚未执行。`[verified: confirmation_evidence.py validate_training/model/pixel_audit/captures；unity-confirmation-evaluation-readiness.json]`
- 正式确认共用按预留cohort身份索引的seal，模型、规则及全部非输出配置保持；失败可在新输出目录重试，旧失败记录保留，改变模型／协议不能重开同一cohort。最终报告绑定全部有序chunk receipt、预测、ASTC、PNG与重复统计；只测最终选择候选的误差，未测20候选整体RMSE明确为空。当前计时仅覆盖参考PNG到mip0 ASTC，完整mip集成及独立90%验收继续单列。`[verified: confirmation_evaluation.py __init__/seal_files/verify_outputs/evaluate/run；capture_output.py summarize；opinion: 验收范围]`
- 原生采集输入的最终输出评分使用`UnityCaptureOutputAudit`，从实际ASTC解码复算原生质量，标签asset必须与输入匹配，不读取候选补测档案；`benchmark_unity_capture_deployment.py`目前仅运行已观察validation2。旧smoke8权重完成16份ASTC／PNG一致性及57项CPU检查，完整mip成本和90%验收仍待完成。`[verified: capture_output.py run；capture_deployment.py run；unity-capture-deployment-verification.json]`

- [原生推理封存](<experiment report/unity-accuracy90-20261111/unity-sealed-inference.md>)使用`UnityEvaluationSeal`固定模型、输入、策略、决策、运行库和文件身份，并在forward前持久化尝试；竞争或失败不能覆盖已有合同。验证smoke使用运行内seal，正式confirmation调用方使用共享cohort registry并核验完整采集／隔离，当前正式执行尚未完成。验证2图／13patch CUDA预测及选参与原保存结果完全一致，73项CPU检查通过，初次tuple／list失败与旧源码保留。`[verified: unity_evaluation_seal.py acquire/forward；sealed_inference.py prepare/run；confirmation_evaluation.py run；unity-sealed-inference-verification.json]`

- [完整像素审计队列](<experiment report/unity-accuracy90-20261111/unity-pixel-pipeline.md>)使用`script/queue_unity_pixel_audit.py`，须等待开发与确认采集成功退出，完整范围固定10000／1000／2000，并要求同代码的真实66图检查通过。缺归档直接拒绝；确认集options转换只写派生文件，保留原报告／配置SHA。25份文件冻结，待生成的采集报告和目录同样受路径保护。真实66图及74项CPU检查通过，全量仍等待；禁止把诊断passed解释为完整隔离或模型验收，不自动改变划分。`[verified: pixel_audit_pipeline.py verify_smoke/verify_destinations/require_archive/confirmation_batches/run；unity-pixel-pipeline-verification.json；opinion: 验收解释]`

- [原生RGBA近重复筛查](<experiment report/unity-accuracy90-20261111/unity-near-duplicates.md>)使用`script/audit_unity_near_duplicates.py`读取冻结的精确像素审计；按原尺寸、同坐标及完整RGBA的RMSE≤2/255筛查，不读取监督标签或自动调整划分。7744训练／2验证图发现6对、12张训练图候选，47项CPU检查与6对独立重算通过。候选只表示低全图误差，仍可能存在局部大差异；不同尺寸、裁剪／旋转与语义相似性未覆盖，不能作为完整确认集隔离证明。`[verified: near_duplicates.py rows/measure/run；unity-near-duplicates-verification.json；pytest 47 passed；opinion: 解释与接入边界]`

- [原始采集规则绑定](<experiment report/unity-accuracy90-20261111/unity-capture-policy.md>)使用`UnityCapturePolicyBinding`直接读取原采集完成回执、原生搜索与缓存规则，不依赖候选补测文件。缓存快照／追加日志及恢复assembly证据均绑定SHA，保留显式划分；缺split仅兼容历史train，不能用作validation／confirmation默认值。真实train64／validation2通过，44项CPU检查通过，首次失败保留；该入口不替代像素隔离、完整恢复审计或独立forward前的模型封存。`[verified: capture_policy.py __init__/verify；unity-capture-policy-verification.json；pytest 44 passed；opinion: 接入边界]`

- [原生采集输入对齐](<experiment report/unity-accuracy90-20261111/unity-capture-inputs.md>)新增`data.unity_capture_input.UnityCaptureInputAdapter`，从参考图／实际回调／导入属性构造输入，保留显式划分；不读取搜索标签和候选监督。按资产路径去重的68张开发图／812patch与训练端张量、决策输入一致，49项CPU检查通过；真实Sprite输入未在本次开发语料覆盖。调用方仍须核验采集来源、像素隔离并在独立forward前冻结模型，本接口不自动开启测试。`[verified: unity-capture-input-verification.json；unity_capture_input.py；pytest 49 passed；opinion: 接入约束]`

- [独立确认集2000张串行采集](<experiment report/unity-accuracy90-20261111/unity-confirmation-series.md>)使用`script/collect_unity_confirmation_series.py`，绑定两图预检及17份源码。真实预检通过并追溯原生证据后复用首两张，剩余1998张分8批；逐批核对原名单、回调、原搜索与恢复，失败保留partial并停止，不自动换用备用图。50项CPU检查与真实配置只读核验通过，实际全量采集和模型测试尚未验收；活动期间保持绑定源码不变。`[verified: confirmation_series.py audit_batch/publish/run；unity-confirmation-series-readiness.json；pytest 50 passed；opinion: 执行边界]`

- 第30批Sprite触发旧补测Default限制后，已验证20候选并以新身份恢复：候选sprite-v3、数据full-v3、训练full-v2、确认smoke2-v2。当前颜色补测仅放行Default／Sprite LDR，Sprite必须绑定实际回调；保留原类型、标签和失败产物。旧32批7744／2图通过原SHA复核后复用，新队列计数是本轮重新核验进度；不得覆盖旧失败身份。`[verified: experiment report/unity-accuracy90-20261111/unity-sprite-recovery.md；reproductions/unity_search_baseline/supplement.py validate_color_input；opinion: 恢复约束]`

- 原生重复像素用[像素审计入口](script/audit_unity_pixel_identity.py)读取SHA绑定的已完成归档，精确身份包含RGBA和尺寸，RGB相同／Alpha不同单列。PNG显示顺序用于重复分组，callback哈希需翻转上下行核对。已完成7744训练／2验证图部分审计，不改冻结划分；完整开发／确认集及近重复审计仍待完成。报告与明细路径分离并独占创建，失败保留原身份。`[verified: reproductions/unity_search_baseline/pixel_identity.py；experiment report/unity-accuracy90-20261111/unity-pixel-identity.md；opinion: 验收边界]`

- 历史首次启动记录（该队列后因上游Sprite失败结束）：[独立确认集采集入口](<experiment report/unity-accuracy90-20261111/unity-confirmation-capture.md>)已通过30项CPU检查及两张真实源图的只读协议核验，并启动等待任务；保留confirmation身份，开发入口仍只允许train／validation。绑定15份源码，等原采集、补测、完整数据和首轮原生训练成功后才启动Editor；当前尚未采到新确认集像素或标签，也未打开模型测试。`[verified: unity-confirmation-capture-readiness.json；unity-confirmation-capture-smoke2-v1.json status、dependencies、native_labels_collected；opinion: 验收边界]` 活动期间保持采集配置绑定源码不变；超过两图的扩展先追溯smoke原生收据、参考归档和恢复证据。`[opinion]`

- [独立确认集预留](<experiment report/unity-accuracy90-20261111/unity-confirmation-cohort.md>)已预留2000张主名单、500张备用，主名单覆盖1227个未出现于9份历史清单的资产组；2500份实际源文件及meta身份复核通过。仅完成源资产隔离，后续仍需Unity参考像素、同次原搜索标签、像素重复审计，以及模型和决策冻结后的独立测试；当前未打开模型测试。`[verified: unity-confirmation2000-v1.json primary_images、primary_groups、reserve_images、native_pixels_audited、native_labels_collected、model_sealed；unity-confirmation-reservation-verification.json；opinion: 后续验收]` 主名单和备用顺序冻结；任何身份或像素重复替换须在预测前留痕，禁止按质量或错误筛样。`[opinion]`

- 冻结预测的[残差与余量诊断](<experiment report/unity-accuracy90-20261111/patch-fixed-capacity/README.md#固定预测的残差与阈值诊断>)只使用原cap512验证1000。101点全局余量扫描最高84.5%；逐候选平均偏移修正RMSE为1.3372dB、准确率83.9%，不进入部署。校正参数和计分使用同一验证集，不能称独立泛化收益或准确率上限；候选PSNR误差分组与最终标签召回分别解释，继续保留原模型和终态训练验收。`[verified: scratch-group512-residuals.json；opinion: 使用与解释要求]`

- 历史首次启动记录（该队列后因上游Sprite失败结束）：[完整Unity训练衔接](<experiment report/unity-accuracy90-20261111/unity-native-training-queue.md>)已完成32训练图／2验证图的CUDA预检：两轮4次实际更新、0次AMP跳步、最佳权重重载通过，完整进程83.45秒。当时等待完整10000／1000数据四阶段核验，正式训练尚未启动；后续GPU任务继续纳入串行调度，独立测试90%仍待验收。`[verified: native-training-full-v1/smoke.json training_updates、checkpoint_audit；unity-native-training-full-v1.json status、stages；opinion: 验收与调度边界]` 配置绑定23份源码，活动期间禁止热改；预检与正式输出分开。`[opinion]`

- [同次预测与编码计时](<experiment report/unity-accuracy90-20261111/unity-deployment.md>)已完成两图、一次预热及三次配对重复，共16次真实编码。两图合计参考PNG到内存mip0 ASTC的中位数为预测路径48.81ms、fixed8路径38.34ms；质量通过率分别1／2与2／2，payload分别59168与81920字节。使用原生smoke8权重，此小样本没有速度或等质量收益结论，也不代表完整Unity验收。`[verified: unity-deployment-smoke2-v1.json summary、measurements；opinion: 解释边界]` 模型／DLL加载、解码质量核验及写盘单列；不包含Unity导入和完整mip链。`[verified: deployment.py run timings.scope]`

- [原生推理输入与计时](<experiment report/unity-accuracy90-20261111/unity-inference.md>)已完成两张验证图／13patch的CUDA计时，一次预热、三次正式测量，新预测与原生smoke8权重的已保存预测完全一致。两图合计预处理＋推理＋决策中位数27.50ms；等待3932.86秒与活动2.39秒分开记录。只验证小样本推理，完整Unity模型效果及最终编码另行评价。`[verified: unity-inference-smoke2-v1.json measurements、median_preprocess_inference_decision_seconds、active_seconds；v1-completed-runtime-verification.json stages；opinion: 解释范围]` 推理输入仅参考PNG和导入属性，禁止读取监督；配置／来源核验、CUDA同步及预热重复继续保留。`[opinion]`

- 保存原生验证预测的[最终编码核验](<experiment report/unity-accuracy90-20261111/unity-final-encoding.md>)使用`UnityFinalEncoding`和`script/encode_unity_predictions.py`。绑定完成训练、三个最佳产物、重载审计和原策略，先重放冻结预测再各编码一次，固定8×8的preset显式配置；完整ASTC、解码像素和原生质量与归档候选核对。质量build receipt必须等于原候选记录中的完整`quality_build`，不能只自校验当前DLL。两图／四次编码通过，进程4.05秒；仅为mip0编码阶段，推理和端到端成本不能从旧预测补算。`[verified: final_encoding.py；unity-final-encoding-smoke2-v2.json；对应job receipt；opinion: 使用与解释要求]`

- 历史patch模型的BN重估可显式指定`--training-source-archive`，逐份匹配原训练绑定SHA，并单列当前执行源码；缺失或不符时拒绝。仍要求raw／EMA原验证结果复现、学习参数不变、运行后源码与检查点身份复核。group512末轮已完成，重估EMA84.4%／1.4284dB，低于原最佳84.5%／1.3869dB，后续保留原权重；本次重估按图等权而非资产组限权，成本单列。`[verified: patch_normalization.py bind_training_sources/run；normalization-group512.json；scratch-group512-result.json；opinion: 来源与比较边界]`
- V1尺寸元数据对照完成27轮CUDA训练，选中epoch27 raw，验证Top-1为84.2%、同一权重近阈值RMSE1.5334dB；比原cap512低0.3个百分点，8×8／10×10召回分别下降2.60／7.81个百分点。新增16参数，总11,178,580，完整进程6244.32秒；本次保留原84.5%模型作为scratch对照。这是GDC开发集单次对照，完整Unity独立测试尚未完成。`[verified: scratch-group512-metadata-result.json metrics、recall_change_pp、process_seconds；opinion: 选模与解释范围]` `size_metadata`默认关闭，与`valid_area_pooling`互斥；训练／EMA／验证／重载／BN仍统一使用`model_inputs`。`[verified: patch_trainer.py validate、model_inputs]`
- 后续输入对照新增`MaskedPatchRegressor`和`PatchGeometry`，只按有效区域加权末端特征，参数量仍为11,178,564，RGB与边缘填充及卷积保持。54项检查、完整开发集133140patch几何检查及两轮CUDA检查通过；正式10轮完成并重载，最佳78.0%／同权重近阈值RMSE1.7141dB，比原cap512低6.5个百分点，保留负结果并沿用原池化。训练、EMA、验证及重载必须一致传mask；仍保留卷积感受野受填充影响的边界。`[verified: scratch-group512-validpool-result.json；mask-pooling-integration.json；mask-pooling-data-audit.json；masked_patch_regressor.py forward；opinion: 后续选择与解释要求]`
- 原生决策接口已扩展到3906图，精确目标全部重建原块大小／preset；不得称为模型准确率。先完成的3904训练图含262法线、319大图放宽样本，类别／preset分布和非单调情况只作部分覆盖诊断，原生20候选不强加单调硬约束。4674图目标准备已完成，复用3906图并新增768图，实际4672训练图／2验证图、23255patch、93480候选；coverage仍为partial，正式训练门槛保持。`[verified: unity-prediction-interface3906.json；unity-native3906-target-diagnostics.json；unity-patch-batches4674.json counts、patch_counts、shards、coverage；opinion: 解释与约束]`
- [完整原生数据衔接](<experiment report/unity-accuracy90-20261111/unity-native-pipeline.md>)的`UnityNativeDataPipeline`等待已绑定上游job成功退出，复用原准备／组装／Dataset／决策接口class；完整模式必须10000训练／1000验证，smoke单列。25项检查及最终66图四阶段闭环通过，全量等待任务已启动。活动期间保持配置绑定的14个源码文件不变；如需修订，先处理该任务身份及原始记录，不能热改运行版本。主报告原子占用，失败使用新身份重试，等待与执行成本分开。`[verified: native_data_pipeline.py；unity-native-pipeline-smoke66-v3.json；unity-native-pipeline-full-v2-config.json sources_sha256；opinion: 运行版本要求]`

- 原生patch扩展使用独立[3906图配置](<experiment report/unity-accuracy90-20261111/unity-patch-batches3906-config.json>)和冻结17批快照，目标3904训练图／2验证图，复用2370图不可变目标。提取、合并和全部20832patch读取已通过，保持partial；正式训练门槛不随部分覆盖降低。冻结预测的几何／阈值分层只作描述性诊断，不把相关性归因为填充或采样。`[verified: unity-patch-assembly3906.json；unity-assembly3906-dataset-audit.json；group512-geometry-diagnosis.json limits；unity_quality_trainer.py validate_coverage；opinion: 使用与验收边界]`

- GDC原尺寸patch支持[按有效像素抽样](<experiment report/unity-accuracy90-20261111/patch-fixed-capacity/pixel-sampling.md>)：`pixel_weighted_sampling`默认false保持旧序列，开启后只改变图内分配，每图／资产组总权重保持。该项仅支持独立patch抽样，和bag模式组合显式拒绝；不改图级标签或loss。26项检查与两轮CUDA小样本通过，正式10轮完成，最佳82.0%／1.4580dB，比原cap512低2.5个百分点，后续保留原图内均匀采样；Unity验收另计。`[verified: patch_sampling.py weights；patch_trainer.py validate、training_batches；scratch-group512-pixels-result.json；opinion: 使用边界]`

- Unity原生模型接口见[模型适配报告](<experiment report/unity-accuracy90-20261111/unity-native-model.md>)。patch误差先在MSE域聚合，零通道与Alpha条件按原生规则处理；MS-SSIM／角度由整图特征头预测，不取patch分数平均。导入属性必须影响patch误差与整图预测，测得质量及原选择只进监督／评价。原型35项CPU检查及8训练图／2验证图的CUDA闭环通过；完整训练及独立测试另行验收，实际参数与GDC四输出模型分别记录。`[verified: models/unity_quality.py encode、predict_images；training/unity_quality_loss.py；evaluation/unity_quality.py；unity-native-smoke8-v1-result.json；unity-native-training-verification.json；opinion: 接入与验收要求]`

- 原生训练入口为[train_unity_quality.py](script/train_unity_quality.py)，协议见[训练报告](<experiment report/unity-accuracy90-20261111/unity-native-training.md>)。每轮各图一次、组内patch有放回；整图质量监督与抽样输入的差异明确记录。CUDA必需，正式训练拒绝部分语料；保存时绑定模型／预测／决策SHA，结束后重建冻结验证集、复核训练输入及原策略来源，失败时保留实际更新数。`[verified: unity_quality_trainer.py fit、validate_coverage、verify_input_files、audit_best；unity_image_bags.py；test_unity_quality_training.py；opinion: 使用与验收要求]`

- 原生patch统一清单使用[组装入口](script/assemble_unity_patch_corpus.py)，只接收passed准备报告及外部SHA，按冻结源清单恢复顺序。保留单批来源和原标签，拒绝重复／跨划分／held-out资产；目录、corpus和报告均不可覆盖。完整覆盖需实际counts等于源开发划分；2370图结果仍为partial，不能代替完整Unity训练验收。`[verified: patch_assembly.py run L60–80、L152–155；unity-patch-assembly2370.json；test_unity_patch_assembly.py；opinion: 使用与验收要求]`

- 原生patch批次准备见[分批目标报告](<experiment report/unity-accuracy90-20261111/unity-patch-batches.md>)。只读取冻结快照中已发布的候选批次，重新验证原始参考／选择及候选归档；已完成单批语料绑定配置、报告、corpus哈希后复用。原计划为selected或仅选择部分批次时保留partial；coverage只表示所选范围，完整准备完成须同时满足status=passed、coverage=complete与实际counts等于完整源划分。Windows资产身份统一分隔符及大小写比较，原始文件哈希约束不变。`[verified: patch_batches.py select_batches、coverage、prepare_shard、prepare末段；unity_patch_dataset.py original_selection比较；opinion: 使用要求]`

- Unity训练输入使用[原生RGBA Dataset](<experiment report/unity-accuracy90-20261111/unity-dataset.md>)的独立接口，外部配置绑定corpus SHA，保留20×4通道误差与精确零误差目标、有效区域mask和8项输入属性。实测质量与原策略选择仅作监督，不进入输入属性；MS-SSIM／法线角度保持整图监督。跨语料合并同时检查划分和目标文件SHA／patch尺寸，不能只比较整图SSE。260图数据检查通过，生产模型尚未训练。`[verified: unity_patch_dataset.py；dataset_audit.py；unity-dataset260-v2.json；opinion: 使用边界]`

- 同图patch聚合实验见[成组损失报告](<experiment report/unity-accuracy90-20261111/patch-fixed-capacity/bag-loss.md>)。`ImagePatchBatchSampler`每组只抽同图patch、保留有效像素数；`PatchRegressionLoss`先加权MSE再取log，目标只对实际抽样组精确。权重0／1配对隔离loss，另比较成组采样本身；不能把期望权重一致称为每轮图覆盖一致。正式两组完成10／7轮，最佳验证71.2%／71.7%，均低于独立采样80.7%；完整串行进程1869.71秒。结果按GDC开发协议记录，不外推Unity效果。`[verified: patch_bags.py；patch_loss.py；bag-sampling-analysis.json；scratch-bag4-comparison.json；opinion: 对照与归因边界]`

- 当前 goal 的最新完成条件为[数据采集与 V2 交接](<experiment report/unity-accuracy90-20261111/unity-data-handoff.md>)，优先于旧 goal 正文的 V1 训练及 90% 要求。保留 V1 历史结果和 evidence.json；完成开发集采集、20 候选、patch／规则验收及独立确认图采集、像素审计后交付并完成本 goal。后续 V2 训练使用新实验身份，不恢复已取消的 V1 自动训练。`[verified: 用户2026-11-12最新范围调整；unity-data-handoff-v1.json]`
- V2 数据采集与完整性验收已完成：训练10000张、验证1000张、确认2000张。开发集已按批准的18个位置补采并生成新语料，220000组候选、74609个patch；11000张完整读取和原规则四字段重放通过。13,000张实际输入、精确RGBA和同尺寸对齐近重复检查完成，确认集未运行模型。`[verified: unity-data-delivery-v3-verification.json counts、development_candidate_count、development_patch_counts、exact_policy_replay、native_input_eligibility_verified、full_pixel_audit_complete、test_opened]` 当前入口见[最终交接](<experiment report/unity-accuracy90-20261111/unity-data-delivery-v3.md>)；旧74187个patch语料保留为修订前历史记录。`[verified: unity-development-data11000-verification.json patch_counts]`
- V1分类五组最高验证Top-1为68.6%；正式随机初始化／预训练patch回归各14轮完成，最佳Top-1为76.0%／88.8%，阈值附近RMSE为1.7681／0.9736dB，两组最佳权重重载通过。各11,178,564参数，继续固定容量诊断；V1开发联合晋级条件及最终Unity90%均未达到。详见[回归状态](<experiment report/unity-accuracy90-20261111/patch-v1/README.md>)。`[verified: classification-controls/comparison.json；patch-v1/summary.json；scratch-result.json；pretrained-result.json；opinion: 后续顺序]`
- Unity回归采集保留原搜索提前停止、标签及baseline计时，另行补测块大小×preset缺失候选并记录解码图及原生质量分支。抽样真实编码先作为独立成本／质量对照，主路径保持预测后一次最终编码。方案差异、未完成配置和实际测量分别写入执行记录。`[verified: V1“待决定事项”；opinion: 本轮执行决定]`
- 实际编码参数采集入口为`script/capture_unity_options.py`，通过临时受保护的managed回调记录Alpha、profile、normal pack及输入RGBA哈希，结束后恢复源码。两图实际参数绑定的40候选补测通过，64图采集另记录558回调，包含63 Default和1 NormalMap，恢复无冲突。NormalMap样本的normal-pack实际为false，用途与pack标志分别记录；真实mip0法线20候选重编码也已通过，HDR／多mip及最终Unity90%均未验收。`[verified: unity-supplement2-actual.json；unity-actual-options64.json；smoke1-receipt.json；metadata.py；unity-normal-replay20.json]`
- 颜色补测已扩展到8图160候选，原52组指标和8个winner复核一致；真实4096² NormalMap的20原候选重新解码和原生角度评价通过，后续另立身份重新编码20组并核对完整ASTC和RGBA字节一致。法线20组均未过角度门槛，保留最高PSNR回退身份。门槛取真实tableConfig并按float32还原，报告状态允许Valid后附BEST标记；HDR／多mip及全量采集未验收。成本和读写依赖见[实验成本表](references/task-costs.md)。`[verified: unity-color8.json；unity-normal20-policy.json；unity-normal-replay20.json；tests/test_unity_normal_audit.py]`
- 开发参考图支持显式`source_split=train/validation`、`capture_paths`和`phase=batch`，每批1至256个唯一路径，路径必须属于冻结划分且不能跨划分重复。输出manifest保留原划分，禁止test／calibration；原搜索baseline仍要求10000张训练图及原smoke门槛。批次各用独立协议锁、缓存和恢复记录。`[verified: benchmark.py prepare/verify_protocol；unity_reference.py collect；tests/test_unity_reference_batches.py]`
- 强制中断后的batch导入设置恢复使用`script/reproduce.py recover --phase batch`，按原run_id／project／editor／manifest绑定冻结协议；managed源码另用`capture_unity_options.py restore --journal`恢复。两者要求工程Editor关闭，保留冲突且不覆盖独立改动。`[verified: script/reproduce.py recover；benchmark.py restore_metadata；metadata.py ManagedCaptureHook.restore；test_unity_reference_batches.py]`
- 冻结末轮权重的BN诊断入口为`script/patch_normalization.py`，只用train抽样patch重估统计量，再评价validation；参数不更新，保留独立权重和成本。两组完成，随机初始化／预训练EMA为76.7%／89.2%，近阈值RMSE1.6467／0.9512dB；这是末轮后处理对照，与训练中最佳raw的76.0%／88.8%分别记录，仍未达V1／Unity验收。`[verified: normalization-scratch.json；normalization-pretrained.json；scratch-result.json；pretrained-result.json；PatchNormalizationAudit.run]`
- 固定容量学习率单项对照已完成：原scratch仅lr1e-3→3e-4，12轮早停，选中epoch7 raw，验证80.7%／近阈值RMSE1.6040dB，最佳权重重载通过。10×10召回下降4.69个百分点需保留；同LR去maxpool对照也已完成15轮，为74.6%／2.5459dB，下降6.1个百分点，保留标准stem作为后续基准。详见[固定容量对照](<experiment report/unity-accuracy90-20261111/patch-fixed-capacity/README.md>)，BN后处理单列，去maxpool重估EMA为78.6%／2.1127dB。下一项固定容量训练只把组抽样改为cap512，沿用标准stem／scratch／lr0.0003，CUDA小样本通过后启动；cap0保留原图等权分布，test不参与选模。`[verified: scratch-lr0003-result.json、scratch-stem2-lr0003-result.json；normalization-scratch-stem2-lr0003.json；PatchSampling.weights；scratch-group512各suite／smoke-summary；opinion: 后续基准]`
- 完整参考采集由`script/collect_unity_references.py validate/collect/assemble`驱动，45个冻结批次覆盖train10000／validation1000，单批不超过256。已完成train320／validation2，66张已有数据的真实合并检查通过，全量队列运行中；状态见[串行采集报告](<experiment report/unity-accuracy90-20261111/unity-reference-series.md>)。使用Unity工程Library下OS文件锁，逐批校验配置／manifest／Editor／DLL身份、恢复记录、参考SHA和原标签；旧失败不得静默覆盖。活动队列期间不得另开同工程Editor或恢复其临时hook。候选补测和训练验收分别记录。`[verified: collection.py UnityReferenceSeries；unity-reference-series-plan.json、unity-reference-series-smoke.json、unity-reference-series.json；opinion: 运行约束]`
- 持续记录该目标的实验进展，统一入口为[执行报告的progress.json](<experiment report/unity-accuracy90-20261111/progress.json>)。保存配置差异与调整原因、逐epoch训练／验证指标、实际更新数、失败重试和耗时。运行中日志与heartbeat保存在.local，阶段结果同步仓库。`[verified: 用户本轮“时刻记录实验进展”；experiment report/unity-accuracy90-20261111/progress.json；ReproductionJob.run与Trainer.fit；opinion: 记录要求]`
- 当前执行顺序为Unity搜索baseline、Nah 2023、Nah 2022、TexNN、GDC，再研究新模型与校准。新增方法代码集中在`reproductions/`，启动入口仍放`script/`。先完成10,000张训练图的真实搜索计时报告，再启动正式文献实验。缺作者代码时允许论文重实现，原文设置、补全假设和实际完成状态分别记录。`[verified: 用户2026-11-10实施请求及复现标准选择]`
- 正式文献实验通过`BaselineGate`检查10,000张覆盖、原生搜索记录、源图哈希核验、退出码与metadata恢复。Unity基线按实际进入ASTC的目标格式测量，临时Android覆盖与恢复、参数缓存隔离和计时区间见[复现入口](reproductions/README.md)。`[verified: reproductions/common/upstream.py BaselineGate；reproductions/unity_search_baseline/benchmark.py]`
- 技术失败补测使用独立空缓存，保留初次失败记录与退出码，合并结果使用`passed_with_retries`并校验来源SHA-256。初次批次、补测批次、逐图计时与整轮墙钟分别记录。`[verified: reproductions/unity_search_baseline/recovery.py；reproductions/common/upstream.py BaselineGate]`
- Nah 项目适配实验使用固定训练子集的源图 RGB8、原始尺寸、Linear LDR、无 mip 和单编码线程。Nah 2022 按完整 RGBA PSNR 搜索，Nah 2023 保留作者的随机块抽样 RGBA 估计。报告分别复查全图 RGB、RGBA 质量，保留原始 receipt，并通过 `report --method ... --run-id ...` 生成结果。`[verified: reproductions/common/nah_experiment.py protocol/_measure；common/reporting.py write；script/reproduce.py main]`
- Nah 2022／2023 已完成各 64 张项目适配闭环，公开报告保留质量达标率和同方法固定 8×8 控制。两者的原文设置、Unity 导入像素及当前源图适配分别记录。Nah 2022 本轮计时期间存在同机检查活动。后续性能结论按明确输入、计时范围和运行背景解释。`[verified: experiment report/nah2022_psnr_search/source-rgb64-game/summary.json；experiment report/nah2023_adaptive_astcenc/source-rgb64-target40/summary.json；reproductions/README.md]`
- 阶段结果形成后提交并推送仓库，原始逐图日志、图片和二进制按 `.local/` 忽略规则保存，公开报告保留来源标识与原始记录 SHA-256。`[verified: 用户要求“记得有进展同步仓库”；reproductions/common/reporting.py quality_audit；.gitignore]`
- TexNN 主文及用户补充的 13 页 Appendix 已归档，六个网络层尺寸取自 Appendix 第1页 Tables 1–2，并保存于 `architectures.json`。历史参考编码器固定到 `ddadf547770ddbe8261cfd854b2a5f21b3a9074c`，该版本选择按论文引用的访问日期补全。数据收集入口为 `collect --method texnn`，核对原生块数据、坐标与源码的 PNG Y 翻转，完整训练及预测配置回填按实际结果验收。`[verified: reproductions/texnn/source.json、architectures.json、data.py；script/reproduce.py TexNN 分支]`
- TexNN 项目适配已完成 64 源图块标签、六网络训练及独立 validation 8 图／48 次编码的闭环，报告保留质量损失和全部阶段耗时。训练 DEM 特征固定 `partition_single_plane_rgb24_v2`，只用像素与分区拟合端点，禁止采用教师尚未预测的双平面／编码模式生成推理特征。早期 v1 探针只作标签配对证据。`[verified: reproductions/texnn/native/labels.cpp texnn_ideal_endpoints；corpus.py rows；实测 validation8-patch128.json]`
- TexNN 的 `dataset`、`train`、`evaluate`、`benchmark`、`report` 入口统一在 `script/reproduce.py`。P-NN 和 DEM-NN 的 top-k 配置进入真实历史编码器，非法组合回退原始搜索并计时；恒色块走原始快速路径。原文百万块数据规模及论文性能复现仍未完成，当前项目适配不能作为等质量生产收益。`[verified: script/reproduce.py TexNN 分支；native/prediction.cpp texnn_process_block；实测报告 limits、groups]`
- TexNN 已扩展到 1,024 张源图，三种 footprint 共 310,355 个非恒色块，六网络训练总计 1,865.59 秒。扩展报告使用与先期相同的 validation 8 图裁剪协议，保留 48 次编码及 96 次重新解码。按实际输入规模和单个项目 validation 子集解释结果。`[verified: experiment report/texnn/source-rgb1024-patch64-v2/data.json、validation8-patch128.json]`
- 新 GDC 路径使用源 RGB8、原始尺寸、Linear LDR、无 mip／RDO、固定 astcenc 3.3 medium，候选为 6／8／10／12 四种方块；完整演讲候选与编码设置未公开，这些是项目重建设置。标签严格 PSNR >35 dB、最小实际 payload，同字节取更大 footprint，无可行候选则保留最高 PSNR 并标记违规。`[verified: reproductions/gdc2023/dataset.py GDCLabelSelection、collect protocol；gdc2023/source.json]`
- GDC 的 `dataset／assemble／train／evaluate／report --method gdc2023` 共用冻结源划分。缓存与组装校验四候选、实际 ASTC 和重建质量，训练核对 RGB224 缓存及标签；评估核对完成状态，在首次 test forward 前通过 `EvaluationSeal` 绑定模型。概率评估保留原 arms／temperature，压缩评估扩展 compression_models。`[verified: gdc2023/dataset.py、training.py、evaluation.py；utils/evaluation_seal.py；evaluation/evaluator.py]`
- 训练记录区分梯度累积后的 step 尝试、实际 optimizer_updates 与 amp_skipped_steps；scheduler 及 best 选择要求本轮实际更新。正式 14k 标签及组装通过，10k 图 30 轮 CUDA 训练已完成，独立test2000最终编码与报告审计通过，RGB>35dB达标1540/2000，违规率23%。GDC 训练计时绑定 checkpoint／完成记录，未记账的恢复前史保留未知。`[verified: training/trainer.py train_epoch/fit；gdc2023/training.py；正式 training_complete.json、wall-clock.json、test2000/pretrained-test.json]`
- 模型训练使用 CUDA，GDC Trainer 与 TexNN 训练入口均检查 CUDA 设备。正式 ResNet18 使用 RTX4070、CUDA12.8 和 FP16 AMP。`[verified: 用户本轮要求“训练优先用CUDA，不要用CPU”；training/trainer.py fit；texnn/training.py train；正式 pretrained/config.json]`
- 分类调优参考[准确率提升调研](<experiment report/classification-accuracy-research-20261111/README.md>)。当前GDC复现CLI未透传learning_rate，effective_batch与micro_batch分别记录。报告中的新loss、骨干和搜索范围为待实验提案，原始冻结结果与新的输入协议分别维护。`[verified: script/reproduce.py GDC train；GDCTraining.train；调研报告及diagnostics.json]`
- 调研按用户补充覆盖影响最终结果的全流程因素，包含导入、Alpha／颜色、mip、编码器／候选、规则、数值精度、随机性、缓存身份、部署计时和渲染评价。当前源码静态快照与历史Editor／DLL实测使用各自版本身份。`[verified: 用户本轮范围补充；准确率提升调研“导入、编码与部署的全流程因素”；diagnostics.json current_engine_source_inspection]`
- 源图64对照和Unity参考像素64对照均已完成，后者核验各方法RGB PNG字节一致，按完整RGB>35dB及真实payload评价。GDC源图训练模型在导入后参考像素上属于输入变化诊断，64图均来自训练划分，独立test2000用于泛化评价。原生目标、Alpha及计时范围分别保留。`[verified: experiment report/reproduction-shared64/comparison.json；reproduction-unity-reference64/comparison.json；GDC正式test2000报告]`
- GDC 报告保留固定 6／8／10／12 的离线候选质量、真实 payload 与原采集计时；部署延迟以单独实测的 fixed8 配对流程为对照。共享 Unity64 属于训练集诊断，冻结 config 经 protocol-lock 与 baseline receipt 双层哈希核验，名称／配置 SHA／路径顺序写入 binding；独立 test2000 用于泛化评价。Nah/GDC 源 RGB 输入逐图核对，Unity 导入像素和 mip 范围分别保留，不据此声称等质量加速。`[verified: common/cohort.py；common/comparison.py；gdc2023/reporting.py；gdc2023/README.md]`
- GDC 的 collection 计时覆盖候选采集，完整数据准备成本另由进程启动／退出时刻覆盖清单验证与缓存组装。`preparation-process.json` 的完整记录经评估 SHA 绑定，报告核对协议、collection 和 manifest。缺失或不完整的可选计时保留未知成本。`[verified: gdc2023/costs.py；evaluation.py；reporting.py；正式运行的 preparation-process.json]`
- 进程与重启恢复保留原始失败日志，RGB224 缓存异常副本先归档，再校验可写临时文件、fsync 并原子替换。长任务由 `script/run_reproduction_job.py` 记录命令、存活心跳和退出码。原始进程的未知部分耗时与已测成功／失败阶段分别记录。`[verified: gdc2023/dataset.py copy_classifier_cache；common/jobs.py；classifier-cache-recovery.json；preparation-process.json]`
- Unity 参考图采集使用 `--capture-references`，预热后开启原生导出，完整成功及 metadata 恢复后通过 `collect` 归档。原生解码 PNG 垂直翻转后与参考图统一方向，缓存复查包含镜像 PNG。已测固定 64 图中 38 图源 RGB 完全相同、26 图不同，全部选参配置与原基线一致。`[verified: common/unity_reference.py；BenchmarkRunner.cs；experiment report/unity-reference64-lite-rdo-off/summary.json]`
- 实验协议、数据、训练、校准、成本及验证报告统一保存在`experiment report/`，逐图清单、缓存、原始日志、预测和检查点保存在该目录的`.local/`并Git忽略。`[verified: 用户确认的GDC复现计划及报告目录要求]`
- Python环境和依赖统一使用uv，提交`pyproject.toml`、`uv.lock`与`.python-version`；安装使用`uv sync --frozen`，实验和检查使用`uv run`。`[verified: 用户要求“仓库里使用uv进行python依赖管理”；pyproject.toml]`
- 实施前检查已有文件、工具和入口，采用完成任务所需的最小修改，保留用户已有工作。Git状态在实际操作前重新查询。`[opinion]`
- 先运行小样本压缩、解压、质量测量和字节统计，再扩大到完整数据集、训练或批处理。`[verified: 用户提供的全局规则“Smoke test first”；README.md“后续研究方向”]`
- 实验协议记录编码器版本、preset、候选块集合、颜色空间、通道用途、Alpha、mip、尺寸取整、容器与硬件。`[opinion]`
- 质量目标、标签生成规则、训练目标和部署质量复检分别定义。记录无可行候选、编码失败、质量违规及回退处理。`[opinion]`
- 对照优先覆盖当前生产使用的固定8×8，补充固定6×6、固定12×12和同质量目标下的搜索选参，学习方法与搜索方法使用一致的编码和测量口径。`[verified: README.md“当前生产基线与优化空间”]` `[opinion]`
- 分别报告数据准备、训练、预测和最终编码耗时，以及体积、质量分布和失败率。跨资产或跨项目划分时检查近重复数据泄漏。`[opinion]`
- 实验状态以本次运行日志和产物为依据。`verification.json` 中的历史资料检查与新增实验验证分别记录。`[opinion]`

## Unity训练数据采集与源码定位

- Unity规则重放入口为`script/replay_unity_policy.py --config ...`，固定完整20候选顺序、float32阈值、黑像素分档、法线／MS-SSIM、大图锁组和回退；保留切组前已测候选的计数。缓存必须来自冻结原采集phase并重做LITE完整来源审计，不能仅信任调用者提供的SHA。260张开发图的块大小、preset、原因和尝试次数全部一致；PSNR-only诊断仅207张块大小一致，不作为模型准确率或上限。后续质量预测必须按完整规则单独验收，详见[规则重放报告](<experiment report/unity-accuracy90-20261111/unity-policy-replay.md>)。`[verified: policy.py select；policy_audit.py verify_policy_origin、run；unity-policy260-bound-v2.json；opinion: 模型验收要求]`

- 原搜索提前停止的颜色／mip0法线候选可用`script/complete_unity_candidates.py --config ...`补齐，256图5120候选及原winner审计已通过。全量跟随入口为`script/complete_unity_candidate_series.py --config ... --follow`，仅消费已发布的参考批次；归档复核后复用已完成结果，部分失败使用新retry身份并保留原始成本，最终按原划分生成完整清单。258图实跑检查通过。法线限定Linear RGBA8、Profile1、normal-pack=false和Tex2D；角度评价层数按已归档mipmaps与尺寸推导并clamp1–4，每个原候选须复现原指标。两张mipmaps=true法线40候选实测通过；这仍是mip0编码，不是完整mip压缩链。HDR单独验证。详见[补测进展](<experiment report/unity-accuracy90-20261111/unity-supplement.md#连续补测队列与训练清单>)。`[verified: candidate_completion.py verify_actual_options、verify_normal_imports；candidate_queue.py run、prepare_attempt；candidate_archive.py verify；unity-candidates-train256-audit.json；unity-candidate-queue-smoke.json]`

- Unity监督提取入口为`script/unity_patch_targets.py --config ...`，RGBA各通道SSE按240patch保存，整图聚合后排除零误差通道及不参与的Alpha；MS-SSIM和法线角度保留整图指标。258图5160候选重建检查通过，另两张四级法线评价数据通过；原标签不变，未开始Unity正式训练。数据身份及恢复要求见[原生监督报告](<experiment report/unity-accuracy90-20261111/unity-patch-targets.md>)。`[verified: patch_targets.py UnityChannelErrors、UnityPatchCorpus；unity-patches-train256.json；unity-patches-multimip2.json]`

- 离线候选补测入口为`script/unity_supplement.py`，其质量函数从本机引擎原样提取到.local并编译，编码DLL沿原采集协议锁与identity核验。当前两张LDR Default开发图的40候选与原16项质量重放通过；needAlpha等仍是重放核验的推定设置，正式采集要记录实际回调参数。参见[补测报告](<experiment report/unity-accuracy90-20261111/unity-supplement.md>)。`[verified: unity-supplement2-bound.json capture_binding、rows、config.items；quality.py]`

- 面向 Unity 生产选参的训练与评估使用导入处理完成后、进入 ASTC 搜索前的第一个 image／mip0 参考图。RGB224限定为历史分类输入，当前V1开发回归使用原分辨率240patch；Unity迁移保留RGBA、用途及原生质量分支，质量测量使用原尺寸导入后参考像素。参考图与同次导入和原始搜索标签配对，缺图时补采或标记缺失；原图用于来源核验、对照及明确标注的历史／文献复现。`[verified: README“Unity导入结果与训练数据准备”；experiment plan/V1/README.md“输入与数据”；LITE训练协议L21；opinion: Unity迁移要求]`
- LITE／RDO 关闭的 64 张实测配对中，19 张尺寸变化（例如 4096×4096 → 128×128、240×390 → 256×512），7 张同尺寸但 RGB 变化，38 张尺寸和 RGB 相同。7 张中有 5 张只在两侧均完全透明的像素改变 RGB，另 2 张是原因待核实的 JPEG。当前模型只读取 RGB，透明区域的差异也会进入模型。按这批样本解释差异，Alpha 等价性和全量比例分别核实。详见[README 实测差异](README.md#导入前后的实测差异)。 `[verified: 64 张配对图尺寸和 RGBA 逐像素复查；LITE 训练协议 L21]`
- 训练数据导出任务先读[README源码导航](README.md#unity训练数据导出与源码导航)，再核对本机引擎文件哈希、函数和行号。README保存完整位置表、调用链、字段与采集条件。`[verified: 用户要求“全部整理到readme和agent里面”；README对应小节]` `[opinion]`
- 输入取自`ImageOperations.cpp`的`CompressTextureWithMultipleImages`取得的第一个image／mip0，经`PrepareOriginalImageData`转换／绑定为RGBA32。参考图采集从`SetupTestEnvironment → ExportImageToPNG`读取，源图与参考像素的等价性按样本实测。`[verified: ImageOperations.cpp L2947–2964；ASTCCompressor.cpp L2675–2694、L1999–2010]` `[opinion]`
- 主链为`FindOptimalASTCFormat → FindOptimalParameters → TestAllParameterCombinations → SelectBestParameter → SaveBestParametersToCache → SaveCacheEntryToFile`，分别定位到`ASTCCompressor.cpp`的L3738、L3435、L2958、L3364、L1935、L1836。`[verified: ASTCCompressor.cpp L3767、L3499–3522、L1975]`
- 采集前核对ASTC目标格式、自动选参开关、第三方编码／解码接口和磁盘调试开关。缓存命中在图片导出前返回，采集方式需显式记录缓存复用、重新测量、cache-hit及导出结果。`[verified: ImageOperations.cpp L2958–2968；ASTCCompressor.cpp L428–478、L2963–2970、L3437–3462]` `[opinion]`
- 维护资产路径、源MD4、参考图及其哈希、导入配置、尺寸、颜色空间、用途、Alpha、mip、Editor／DLL版本与tableConfig的对应关系。调试目录的纹理名和进程内计数用于定位产物，批量数据集通过清单建立稳定样本身份。`[verified: ASTCCompressor.cpp L2001–2009、L1964–1973、L3466–3499]` `[opinion]`
- 记录实际候选覆盖、编码／解码失败、earlyExit、valid与回退原因。常规搜索提前停止，大图允许MS-SSIM失败时采用PSNR通过候选，全部不合格时按最高PSNR回退。标签称为“当前策略选中配置”，最优性与质量达标分别评价。`[verified: ASTCCompressor.cpp L3121–3125、L3157–3158、L3262–3269、L3337、L3348–3419]` `[opinion]`
- 字段采用源码口径，PSNR仅平均误差非零的参与通道且排除恒定Alpha，msSsimDb为亮度MS-SSIM的dB转换，fileSize为本次参考尺寸payload，timestamp为写缓存时刻，rdo为最终采用精炼payload。法线角度、候选表与RDO尝试状态单独保存。`[verified: ASTCCompressor.cpp L2238–2304、L2456–2478、L3067–3072、L1964–1973、L657–666]` `[opinion]`
- 核对实际缓存目录、tableConfig、JSONL新增记录和快照合并，保留历史LITE与主包协议差异。锁或写入失败、源文件缺失及哈希失败需要纳入采集完整性检查。`[verified: ASTCCompressor.cpp L1178–1205、L1372–1397、L1836–1899、L1937–1939、L3506–3523；README对应小节]` `[opinion]`
- 源码静态定位、图片导出实测、候选压缩质量和训练效果分别报告。先验收小样本，再按用户授权范围扩展批量采集。`[verified: 用户“Smoke test first”要求]` `[opinion]`

### 术语口径

- 术语解释沿用[README完整术语表](README.md#压缩参数与图像术语)，分别记录压缩参数、亮度范围、颜色编码及贴图用途。`[verified: 用户要求“这些所有的术语的解释也放到agents和readme里面”；README对应小节]` `[opinion]`
- blockSize／block footprint为每个ASTC块覆盖的texel宽高，texel为纹理像素，块输出固定128 bit／16字节。4×4、8×8、12×12分别为8、2、约0.89 bpp，payload为原始块数据，mip链、容器与打包大小分别计量。`[verified: Arm《ASTC Format Overview》“Block compression”；ASTCCompressor.cpp L3067–3072；ImageOperations.cpp L2975–2985]` `[opinion]`
- preset统一称编码预设／编码档位，原交流“present速度”按preset解释。fastest至exhaustive控制编码搜索投入与时间／质量取舍，同图同尺寸同blockSize的payload容量相同，编码耗时和最终质量分别测量。`[verified: ASTCCompressor.cpp L620–625、L3067–3108；Arm astc-encoder README “Experimenting”]` `[opinion]`
- LDR为Low Dynamic Range，低动态范围，常见8位颜色分量0～255归一化到0～1。整数除以255只描述归一化，光强解释还取决于颜色编码。`[verified: Unity 2019.4《High dynamic range》“How HDR works”；《Color space》“Linear and gamma color space”]`
- HDR为High Dynamic Range，高动态范围，在线性光照表示中可保留超过1的值，常见浮点表示与EXR／HDR输入。亮度范围、数值精度、实际存储格式分别记录。`[verified: Unity 2019.4《High dynamic range》L159–180；Arm astc-encoder README “Encoder feature support”]` `[opinion]`
- sRGB是常用颜色空间标准，本项目重点区分其非线性颜色编码与Linear数值解释。线性渲染流程可使用sRGB颜色纹理，并在采样时转换，项目渲染色彩空间与逐纹理sRGB属性分别核对。`[verified: Unity《Color space》L170–182；《Gamma Textures with linear rendering》L160–180；ASTCCompressor.cpp L3466–3472]` `[opinion]`
- Linear对颜色表示线性光强，对遮罩／查找表等数据图保留存储值的数学含义并绕过sRGB转换。Normal Map是贴图用途，按线性数据采样，通道值用于还原方向，质量按法线角度分支评价。`[verified: Unity《Working with linear Textures》L174–183；ASTCCompressor.cpp L2552–2559、L3198–3204]`
- LDR／HDR与sRGB／Linear按两个维度记录，可组合为Linear LDR、sRGB LDR和HDR模式。isHDR来自输入格式，useSRGB来自stored color space，isNormalMap来自usage；blockSize和preset来自候选配置。`[verified: Arm astc-encoder README “Compressing an image”L259–264；ASTCCompressor.cpp L3746–3747、L3466–3475、L620–625]`
- PSNR衡量像素误差，SSIM比较局部亮度／对比度／结构，MS-SSIM跨尺度组合，本地msSsimDb为亮度MS-SSIM的dB值。RDO为率失真优化，质量测量、编码优化及打包后收益分别描述，保留本地通道、单位、分支与DLL核实深度。`[verified: ASTCCompressor.cpp L2181–2304、L2456–2541、L2754–2956；Wang等MS-SSIM论文§2–3；Arm ASTC RDO讨论“Approaches”]` `[opinion]`

### 自动选参偏好与标签判定规则

- 修改选参、采集、分类标签或质量评价前，读取[README完整判定规则](README.md#自动选参的偏好与判定规则)，按当前源码复核，区分C++默认值、运行时有效配置和历史快照协议。`[verified: 用户要求“偏好规则…全部写入到readme和agent里面”；ASTCCompressor.cpp L627–643、L1178–1205、L3590–3665]` `[opinion]`
- 候选顺序固定为12×12、10×10、8×8、6×6，每组依次fastest、fast、medium、thorough、exhaustive，共20组。顺序是标签协议的一部分，当前循环顺序执行，扫描阶段RDO关闭。`[verified: ASTCCompressor.cpp L618–625、L2979–2981、L3026–3028、L3088–3108]`
- 按贴图类型判断质量，法线默认meanWavg≤2.5°且p95Wavg≤7°，LDR sRGB默认PSNR≥有效门槛且msSsimDb≥24，其他分支按PSNR门槛。法线角度为从mip0构造的最多四级法线图中各级统计量的像素数加权。`[verified: ASTCCompressor.cpp L627–631、L2622–2673、L3198–3225]`
- 纯黑RGB像素比例≤40%时采用基础PSNR默认35，>40%且≤80%时默认40，>80%时默认42 dB，强档优先。数值随运行配置核对，LITE与主包协议分别保留。`[verified: ASTCCompressor.cpp L628、L634–637、L3166–3175、L3704–3709；README配置调查入口]` `[opinion]`
- 常规分支接受顺序中的首个合格候选后break。源码中的比较次序为payload更少、同字节下PSNR更低、字节与PSNR相同时qualityValue更低，解读时保留首个有效结果立即退出的控制流。`[verified: ASTCCompressor.cpp L3293–3337]`
- 大图size-first触发条件为LDR sRGB颜色图且width×height≥默认512²。首个PSNR通过候选锁定块大小，同块依preset继续尝试，PSNR与MS-SSIM都通过时立即接受。该组始终MS-SSIM失败时，采用最后一个PSNR通过候选并将valid置true。`[verified: ASTCCompressor.cpp L2988–2990、L3241–3284、L3348–3359]`
- size-first锁组后的切组判断发生在候选测量及allResults追加之后，报告中的下一块候选按实际执行记录解释。保留候选覆盖、失败跳过与提前停止状态。`[verified: ASTCCompressor.cpp L3121–3125、L3157–3158、L3238–3256]` `[opinion]`
- 无有效bestResult但有已测结果时，统一按最高PSNR回退，包括法线分支，PSNR并列保留先出现者并返回成功。已测结果为空且bestResult无效时返回失败，success、valid、逐项阈值通过和fallback原因分别记录。`[verified: ASTCCompressor.cpp L3371–3380、L3390–3422]` `[opinion]`
- RDO精炼要求全局开启、正余量、接口可用、有效选中参数和payload，且winnerPSNR≥保存的有效PSNR门槛+默认1 dB余量。沿用块大小与preset重编码，复测质量且payload≤原结果才采用，保留精炼前后指标、attempted、status和最终rdo。`[verified: ASTCCompressor.cpp L643、L2754–2833、L2878–2953、L657–666]` `[opinion]`
- 规则变化同步README与本节，记录候选、阈值、黑像素、大图、回退和RDO协议及源码／DLL版本，复核旧标签与缓存。已有标签称为当前策略选中配置，候选最优性、严格质量通过和实际训练效果分别评价。`[verified: ASTCCompressor.cpp L1178–1205、L1372–1446、L3437–3462；用户本次文档要求]` `[opinion]`

#### 关键判定源码摘录

以下保留质量判断、常规接受和大图回退的实际语句，完整候选表、黑像素分级、锁组、通用回退与RDO代码见[README完整源码片段](README.md#自动选参的偏好与判定规则)。片段只省略纯注释、空行和公共左缩进。`[verified: ASTCCompressor.cpp下列行范围；README对应小节]`


质量判定分支对应源码L3195–3226。`[verified: ASTCCompressor.cpp L3195–3226]`

```cpp
bool isValid = false;
float distance = psnr - effectivePSNRThreshold;
if (isNormalMap)
{
    NormalAngularResult ang = CalculateNormalAngularErrorMip0To3(originalDataPtr, decompressedRGBA32.data(), origWidth, origHeight, mipCount);
    angleMeanWavg = ang.meanWavgDeg;
    angleP95Wavg = ang.p95WavgDeg;
    isValid = (angleMeanWavg <= kTargetNormalAngleMeanWavgDeg) && (angleP95Wavg <= kTargetNormalAngleP95WavgDeg);
}
else if (!isHDR && useSRGB)
{
    if (psnr >= effectivePSNRThreshold)
    {
        msSsimDb = CalculateMSSSIMDb_Luma(originalDataPtr, decompressedRGBA32.data(), origWidth, origHeight);
        isValid = (msSsimDb >= kTargetMSSSIMDb);
    }
    else
    {
        msSsimDb = 0.0f;
        isValid = false;
    }
}
else
{
    isValid = (psnr >= effectivePSNRThreshold);
}
```

常规保存候选并提前停止对应源码L3324–3338。`[verified: ASTCCompressor.cpp L3324–3338]`

```cpp
if (isBetter)
{
    sharedResult.bestDistanceToTarget = distance;
    sharedResult.bestResult = result;
    sharedResult.bestCompressedData = std::move(compressedData);
    sharedResult.bestTextureFormat = textureFormat;
    sharedResult.bestWidth = width;
    sharedResult.bestHeight = height;
    sharedResult.hasCompressedData = true;
    sharedResult.earlyExit = true;
    break;  // Exit the for loop immediately: we can stop testing other parameters since they will have larger file sizes or same size with higher quality
}
```

size-first回退采用对应源码L3349–3359。`[verified: ASTCCompressor.cpp L3349–3359]`

```cpp
if (useSizeFirstOnLargeTexture && !selectedBySizeFirst && lockedBlockSizeValue >= 0 && hasSizeFirstFallback)
{
    sharedResult.bestResult = sizeFirstFallbackResult;
    sharedResult.bestDistanceToTarget = sizeFirstFallbackResult.psnr - sizeFirstEffectivePSNRThreshold;
    sharedResult.bestCompressedData = std::move(sizeFirstFallbackCompressedData);
    sharedResult.bestTextureFormat = sizeFirstFallbackTextureFormat;
    sharedResult.bestWidth = sizeFirstFallbackWidth;
    sharedResult.bestHeight = sizeFirstFallbackHeight;
    sharedResult.hasCompressedData = true;
    sharedResult.earlyExit = false;
}
```

## 代码组织与Class规范

- 核心实现使用独立class，按[README的目录职责](README.md#目录职责)分包。`models/`维护模型，`data/`维护数据准备、Dataset和DataModule，`training/`维护Trainer，`calibration/`、`evaluation/`、`reporting/`分别维护校准、推理评估和报告。`[verified: 用户要求“MODEL，DATA，TRAIN这些按照规范需要全部分开”“全部以class的形式分开”及本次规范入文档要求]`
- 新功能优先归入已有目录和class，文件围绕一种主要职责组织，紧密相关的类可同文件维护。有状态组件通过实例持有配置、依赖及运行状态，纯计算方法可使用`staticmethod`。`[opinion]`
- 类名使用`PascalCase`，模块和方法使用`snake_case`，新增接口复用现有表示和调用方式，所有Python函数遵循下节的类型注解要求。`[opinion]`
- 依赖按配置与工具 → 数据／模型／推理与指标 → 训练／校准／评估 → CLI组织。数据准备和CLI帮助路径保持CPU依赖，Torch Dataset与DataModule从`data.dataset`按需导入。`[opinion]`
- 新业务逻辑放入对应class，CLI构造组件并调用公开方法。包入口负责导出和薄兼容，既有函数入口委托给class实现。`[opinion]`
- 结构调整时核对CLI、检查点键与严格加载、初始化随机数顺序、resume状态、数据清单指纹及测试封存。先运行小样本回归，再扩大运行范围，报告写入`experiment report/`。`[opinion]`
- 修改架构时同步[README规范](README.md#代码组织与class规范)和本节，具体实现与兼容性记录见[重构报告](<experiment report/class-refactor-20261110/README.md>)。`[opinion]`
- 可维护的启动脚本统一放在根目录`script/`，调用src中的class，阶段之间共享同一TOML的实验目录。历史运行脚本与原始日志按实验工件归档在`experiment report/.local/`。`[verified: 用户要求“用脚本启动的脚本全部放到script里面”；opinion: 入口与历史工件的维护边界]`
- 训练配置使用`TrainConfig`，SwanLab设置使用`SwanLabConfig`，命令行显式值覆盖TOML。添加配置项时同步参数校验、有效配置快照和resume兼容性检查。`[opinion]`
- 实验跟踪逻辑放入`tracking/`的class，上传已有可计算指标与聚合图表。创建跟踪run前检查训练目录与resume条件，保存run ID，失败时正确结束跟踪；历史导入保留来源指纹与historical_import标记。接入和验证记录见[脚本与SwanLab报告](<experiment report/script-swanlab-20261110/README.md>)。`[opinion]`

## 工具与代码风格

- 文本检索优先 `rg`，Python依赖与执行优先 `uv`、`uv run`，采用用户全局规则中的工具偏好。`[verified: 用户提供的全局规则“Available CLI Tools”]`
- 所有Python函数参数和返回值都写类型注解，无返回值显式使用 `-> None`，优先现代类型语法。`[verified: 用户提供的全局规则“Python Preferences”]`
- Python格式与静态检查优先 `ruff`、`basedpyright`，长任务使用无缓冲输出。依赖、检查命令和运行入口以实际代码为准。`[verified: 用户提供的全局规则“Python Preferences”]` `[opinion]`
- 遇到连续3–5次无收敛的排查，汇总已观察的输出与剩余未知项，再调整方法。`[verified: 用户提供的全局规则“Bound investigation”]`

## 修改后验证与交付

- GDC压缩评估使用`--resume`核验同一binding和逐图原始产物后续跑。已有progress中的receipt SHA必须匹配，缺失进度文件时单独核验源图、候选payload、解码图、质量与计时。技术失败及未知历史耗时保留在报告中。JSON写入采用唯一临时文件、fsync和Windows替换重试。`[verified: reproductions/gdc2023/recovery.py、evaluation.py、costs.py；src/adaptive_astc/utils/artifacts.py]`

- Markdown修改后检查本地链接、内部锚点、书目编号及新增内容的来源定位。外部URL格式检查与网络可访问性检查分别报告。`[opinion]`
- 修改原始资料或处理流程时，按影响范围复查哈希、字幕覆盖、截图时间点和元数据一致性。修改代码时先运行对应的小规模入口与相关检查。`[opinion]`
- 检查结果中记录实际命令、输入范围和结果，沿用已有验证记录时注明历史来源。`[opinion]`
- 最终回复列出交付文件、需要用户核对的选择与限制，并以 `Verification:` 汇报实际执行的检查和结果。`[verified: 用户提供的全局规则“Verification after changes”]`
