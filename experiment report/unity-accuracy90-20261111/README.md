# Unity 90%目标执行记录

当前方案以用户提供的 [V1：原分辨率 patch 误差回归](<../../experiment plan/V1/README.md>) 为准，诊断依据见 [V1 evidence.json](<../../experiment plan/V1/evidence.json>)。用户清除旧goal后，已按V1重新创建active goal。原来的树模型优先实验和24组SGD搜索不再作为当前执行顺序。`[verified: 用户本轮V1与重建goal要求；create_goal返回active]`

- [Unity原生质量模型与接口](unity-native-model.md)后续完成[CUDA训练链路](unity-native-training.md)：8训练图／2验证图、2轮4次实际更新、权重重载通过、进程23.81秒；35项CPU检查通过。原型11,377,660参数，2370图精确目标重放与小样本训练分别记录，完整Unity训练和独立测试90%尚未完成。`[verified: unity-native-smoke8-v1-result.json；unity-native-training-verification.json；unity-prediction-interface2370.json；opinion: 完成边界]`

## 验收与执行顺序

[Sprite补测恢复](unity-sprite-recovery.md)通过20候选实测，原16项指标及选中输出一致；候选sprite-v3、数据full-v3、训练full-v2和确认smoke2-v2已启动，复核复用旧7744／2图候选。旧等待任务因上游Sprite限制失败，原记录保留，以下先前状态按历史阅读；当前进度见progress.json与恢复验证。`[verified: unity-sprite-recovery-readiness.json；unity-sprite-recovery-verification.json；opinion: 状态边界]`

[原生像素重复审计](unity-pixel-identity.md)完成7744训练／2验证图核验：5组RGBA精确重复、10张均在训练集内，当前两张验证图未见重复；仅RGB的18组中13组Alpha不同。进程74.64秒，最终21项CPU测试及66图复跑通过。开发划分保持，完整验证／确认集及近重复隔离尚未完成。`[verified: unity-pixel-identity-completed-v1.json；unity-pixel-identity-verification.json；opinion: 覆盖边界]`

[独立确认集采集入口](unity-confirmation-capture.md)完成30项CPU检查及两图只读配置核验，独立confirmation身份不进入开发划分。两图任务已启动等待原采集、补测、完整数据和首轮原生训练成功；15份源码冻结，当前没有新确认集像素／标签或模型测试。后续需要真实Editor预检、全量采集、像素重复审计和最终冻结评价。`[verified: unity-confirmation-capture-readiness.json；unity-confirmation-capture-smoke2-v1.json status、native_labels_collected、test_opened；opinion: 后续验收]`

[独立确认集预留](<unity-confirmation-cohort.md>)已预留2000张主名单、500张备用，主名单覆盖1227个未出现于9份历史清单的资产组；2500份实际源文件及meta身份复核通过。仅完成源资产隔离，后续仍需Unity参考像素、同次原搜索标签、像素重复审计，以及模型和决策冻结后的独立测试；当前未打开模型测试。`[verified: unity-confirmation2000-v1.json primary_images、primary_groups、reserve_images、native_pixels_audited、native_labels_collected、model_sealed；unity-confirmation-reservation-verification.json；opinion: 后续验收]`

[原cap512冻结预测诊断](patch-fixed-capacity/README.md#固定预测的残差与阈值诊断)已完成：全局余量101点扫描最高84.5%，逐候选平均偏差修正后的近阈值RMSE为1.3372dB、准确率83.9%。没有新推理或训练，也没有test访问；这是同验证集拟合／计分的描述性结果，当前不更换部署参数。`[verified: patch-fixed-capacity/scratch-group512-residuals.json；opinion: 结果范围和执行选择]`

[完整Unity训练衔接](<unity-native-training-queue.md>)已完成32训练图／2验证图的CUDA预检：两轮4次实际更新、0次AMP跳步、最佳权重重载通过，完整进程83.45秒。当前等待完整10000／1000数据四阶段核验，正式训练尚未启动；后续GPU任务继续纳入串行调度，独立测试90%仍待验收。`[verified: native-training-full-v1/smoke.json training_updates、checkpoint_audit；unity-native-training-full-v1.json status、stages；opinion: 验收与调度边界]`

[同次预测与最终编码](<unity-deployment.md>)已完成两图、一次预热及三次配对重复，共16次真实编码。两图合计参考PNG到内存mip0 ASTC的中位数为预测路径48.81ms、fixed8路径38.34ms；质量通过率分别1／2与2／2，payload分别59168与81920字节。使用原生smoke8权重，此小样本没有速度或等质量收益结论，也不代表完整Unity验收。`[verified: unity-deployment-smoke2-v1.json summary、measurements；opinion: 解释边界]`

[原生独立输入与推理计时](<unity-inference.md>)已完成两张验证图／13patch的CUDA计时，一次预热、三次正式测量，新预测与原生smoke8权重的已保存预测完全一致。两图合计预处理＋推理＋决策中位数27.50ms；等待3932.86秒与活动2.39秒分开记录。只验证小样本推理，完整Unity模型效果及最终编码另行评价。`[verified: unity-inference-smoke2-v1.json measurements、median_preprocess_inference_decision_seconds、active_seconds；v1-completed-runtime-verification.json stages；opinion: 解释范围]`

[原生保存预测的最终编码](unity-final-encoding.md)完成两图检查：预测与固定8×8／medium各编码两次，完整ASTC、解码像素及质量一致，进程4.05秒。预测质量通过1／2，固定8×8通过2／2，保留失败；这是小样本mip0编码验证，没有新forward或端到端加速结论。`[verified: unity-final-encoding-smoke2-v2.json summary；对应job receipt；opinion: 完成边界]`

[尺寸元数据对照](<patch-fixed-capacity/metadata.md>)完成27轮CUDA训练，选中epoch27 raw，验证Top-1为84.2%、同一权重近阈值RMSE1.5334dB；比原cap512低0.3个百分点，8×8／10×10召回分别下降2.60／7.81个百分点。新增16参数，总11,178,580，完整进程6244.32秒；本次保留原84.5%模型作为scratch对照。这是GDC开发集单次对照，完整Unity独立测试尚未完成。`[verified: scratch-group512-metadata-result.json metrics、recall_change_pp、process_seconds；opinion: 选模与解释范围]`

[组均衡末轮BN重估](normalization.md)已完成，EMA从79.4%变为84.4%／1.4284dB，0次优化器更新，原六份源码与当前14份执行源码分别核验；原训练最佳为84.5%／1.3869dB，继续保留原权重。完整进程429.16秒，Unity独立测试验收仍未完成。`[verified: normalization-group512.json；normalization-group512-plan.json；对应job receipt；scratch-group512-result.json；opinion: 选模与完成边界]`

[全量原生数据衔接](unity-native-pipeline.md)已通过25项检查及三次66图四阶段闭环，最终复跑22.70秒；完整任务启动后等待原采集、候选补测和当前4674图准备全部成功，再执行11000图数据准备／合并／读取／原规则重放。数据就绪与模型90%验收仍分开，当前仅为等待状态。`[verified: unity-native-pipeline-smoke66-v3.json；unity-native-pipeline-full-v2.json；opinion: 完成边界]`

[3906图原生决策接口](unity-native-model.md)已复核通过，精确误差目标重建全部原块大小／preset；262张法线图及319张大图放宽样本继续按各自规则记录。该结果不是模型准确率。数据准备已[扩展到4674图](unity-patch-batches.md)，实际4672训练图／2验证图、23255patch，复用3906图目标并新增768图，进程1849.48秒；coverage仍为partial。`[verified: unity-prediction-interface3906.json；unity-native3906-target-diagnostics.json；unity-patch-batches4674.json counts、patch_counts、coverage；对应job receipt；opinion: 完成边界]`

有效区域汇总正式对照已完成10轮CUDA训练与最佳权重重载，验证78.0%／同权重近阈值RMSE1.7141dB，比原cap512低6.5个百分点；质量达标率77.4%，参数11,178,564不变。保留负结果，后续沿用原池化，详见[完整结果及边界](patch-fixed-capacity/pixel-sampling.md)。`[verified: patch-fixed-capacity/scratch-group512-validpool-result.json metrics、accuracy_change_pp、parameters；opinion: 后续选择与状态边界]`

原生patch准备新增[3906图冻结扩展](unity-patch-batches.md)，3904／2图的提取、合并及20832patch读取全部通过，见[完成记录](unity-patch-assembly3906.json)；旧2370图产物保持。新增[cap512错误分层](patch-fixed-capacity/pixel-sampling.md#cap512模型的剩余错误)只读取完成训练的冻结验证预测，未做新拟合或访问test。`[verified: unity-patch-batches3906-config.json；group512-geometry-diagnosis.json scope、test_opened；opinion: 状态边界]`

固定容量实验新增[按有效像素抽样](patch-fixed-capacity/pixel-sampling.md)，两轮CUDA检查与重载通过，完整GDC开发集对照已完成；网络、资产组权重和其他设置沿用cap512基准，只有图内patch概率变化。正式10轮结束并重载通过，最佳82.0%／1.4580dB，较原cap512低2.5个百分点，后续保留原采样。`[verified: scratch-group512-pixels-result.json；opinion: 结果边界]`

主验收保持Unity导入后参考像素与同次原始搜索标签，独立测试块大小Top-1≥90%。GDC源RGB train10000／validation1000用于开发，test2000保持已观察身份，不参与新选模。训练全部使用CUDA，随机初始化为主线，预训练为独立对照。`[verified: 用户既有数据口径确认、CUDA和初始化要求；V1“目标与开发数据”]`

| 顺序 | 当前工作 | 判据 |
|---|---|---|
| patch目标与编码核验 | 从四候选解码图提取真实像素SSE，核对整图PSNR，检查独立patch编码及变换敏感性 | V1 E1的三项分别记录，数据提取通过不能替代独立编码检查。`[verified: V1“实验步骤”E1]` |
| 正则化分类对照 | 固定ResNet-18/RGB224，比较label smoothing、weight decay、学习率、早停和有序loss | 记录验证Top-1、NLL与逐类结果，增强先通过编码核验。`[verified: V1 E2]` |
| 原生patch回归 | 固定ResNet-18容量，scratch与pretrained对照，MSE域整图聚合，验证集选择余量 | 验证Top-1≥90%且阈值附近RMSE≤0.75 dB后进入Unity复核。`[verified: V1 E3]` |
| 按错误分布改进 | 元数据、资产组权重、stem、图级loss逐项比较，仍不足再增大网络 | 每次报告独立增益与成本，最终在Unity数据上验收。`[verified: V1 E4及“限制与待核实”]` |

## 已完成与当前状态

下列条目保留各阶段的检查规模和当时状态；最新采集计数与运行状态见[progress.json](progress.json)，原生CUDA最新结果见本页开头。`[opinion: 历史与当前记录口径]`

- [Unity分批patch准备](unity-patch-batches.md)通过64train／2validation检查，781／13个patch；2370图冻结子集已完成，2368／2图、15619patch，并已[合并统一清单](unity-patch-assembly.md)；逐批证据见[逐批结果](unity-patch-batches2370.json)。保留首次大小写身份检查失败、修复及已生成语料；42项测试和独立复查通过。`[verified: unity-patch-batches-smoke-v2.json；unity-patch-batches2370.json；pytest与review输出]`

- [Unity原生RGBA Dataset](unity-dataset.md)完成260张真实开发图的输入、20候选逐通道目标和原生PSNR重建检查；19项测试通过。最终复核包含重复patch监督冲突修复，进程13.22秒；Unity模型训练与独立测试仍未完成。`[verified: unity-dataset260-v2.json；jobs/unity-dataset260-v2/receipt.json；pytest 19 passed；opinion: 完成边界]`

- [同图patch聚合损失](patch-fixed-capacity/bag-loss.md)的正式两组已完成，权重0／1为71.2%／71.7%，最佳权重重载通过，完整进程1869.71秒；均低于历史独立采样80.7%。此前冻结诊断中单patch图也存在误差，这项实验未支持采用当前成组配方，采样变化与新增loss分别解释。`[verified: scratch-bag4-comparison.json；patch-coverage-diagnosis.json；opinion: 结果与归因边界]`

- [Unity 原搜索规则重放](unity-policy-replay.md)完成260张开发图，块大小、preset、选择原因和候选尝试次数均与原搜索一致；其中严格质量通过233张，大图放宽25张、最高PSNR回退2张。去掉非PSNR分支时仅207张块大小一致，这是实测质量的规则诊断，未运行Unity模型。绑定原采集缓存的正式审计进程3.646秒，首次来源绑定不足的记录保留。`[verified: unity-policy260-bound-v2.json；unity-policy260-analysis.json；对应job receipt；opinion: 验收范围]`

- [Unity原生监督与法线恢复](unity-patch-targets.md)新增完成：258图5160候选的RGBA通道SSE重建PSNR最大差3.74e-6dB；两张多级评价法线40候选补测与单独patch提取通过。原队列因mip0-only限制失败的记录保持，新候选队列重新核验已有578图并继续；质量分支建模和Unity生产验收仍未完成。`[verified: unity-patches-train256.json；unity-normal-multimip2.json；unity-patches-multimip2.json；unity-candidate-queue-multimip-v2.json；opinion: 验收范围]`

- Unity串行参考采集已核验train1088／validation2。256图候选补测全部完成，5120次编码新增3688组覆盖，原1432组指标与256个winner一致，进程609.70秒；[连续队列](unity-supplement.md#连续补测队列与训练清单)的258图实跑及最终源码复核通过，完整45批另行运行。原标签／基线保持，去maxpool CUDA对照已完成15轮，为74.6%／2.5459dB，低于标准stem；末轮EMA重估为78.6%／2.1127dB，资产组限权的后续对照已完成，为84.5%／1.3869dB（固定参数量、单seed）；完整Unity验收尚未完成。`[verified: unity-reference-series.json counts；unity-candidates-train256-audit.json；unity-candidate-queue-smoke.json；scratch-stem2-lr0003-result.json；normalization-scratch-stem2-lr0003.json；scratch-group512-summary.json；对应job receipts；opinion: 验收边界]`

- 新Unity两图参考采集通过，源文件与运行时规则核对通过，meta恢复0冲突。前两次启动失败及恢复记录保留在 [progress.json](progress.json)；成功记录见 [probe.json](probe.json)。已有64图归档另见 [data-readiness.json](data-readiness.json)。`[verified: 对应JSON记录]`
- [PSNR矩阵复核](psnr-matrix-audit.json)核对train10000／validation1000的receipt哈希和矩阵顺序，均与35 dB规则及回退一致。独立高斯噪声σ0.75 dB、5个seed的训练标签命中率平均90.116%；它是决策敏感性模拟。`[verified: psnr-matrix-audit.json results]`
- [64图目标探针](patch-data-smoke.json)通过，生成601个训练patch与155个验证patch，PSNR最大重建差异7.11e-15 dB。`[verified: patch-data-smoke.json]`
- [全量目标提取](patch-data-full.json)通过，10,000训练图产生120,276个patch，1,000验证图产生12,864个patch；44,000个候选的PSNR重建最大差异1.42e-14 dB，耗时614.55秒。原始SSE为int64，边缘只统计真实像素。`[verified: patch-data-full.json；GDCPatchCorpus._prepare_image]`
- [CUDA训练探针](patch-training-smoke.json)在RTX4070完成6次实际更新、0次AMP跳步，参数量11,178,564。该记录只有48训练图／16验证图、两轮各3步，用于执行检查，正式结果另见本页回归记录。`[verified: patch-training-smoke.json status、config、history；patch-v1/summary.json]`
- 独立patch编码20图80候选全部与整图区域逐像素一致。变换编码最大绝对PSNR变化为水平0.84、垂直1.02、旋转6.60 dB，首批训练关闭增强。`[verified: patch-equivalence20.json；opinion: 增强决定]`
- [五组分类对照](classification-controls/README.md)已完成，原配置验证66.3%，正则化CE最高68.5%，有序loss最高68.6%。保存预测、权重SHA、数据顺序及质量统计复核通过，仍未达到90%。`[verified: classification-controls/comparison.json]`
- [V1单调／EMA探针](patch-v1-smoke.json)完成6次CUDA更新、0次AMP跳步，batch128峰值显存约2.12GB；[权重重载核验](patch-v1-smoke-audit.json)通过，实际选中EMA权重与保存预测一致。正式scratch／pretrained回归已串行启动，见[回归入口](patch-v1/README.md)。`[verified: patch-v1-smoke.json；patch-v1-smoke-audit.json；patch-v1/summary.json]`

## 两项执行决定

抽样真实编码保留为独立成本／质量对照，不接入主模型的输入。主生产路径继续采用模型预测后一次最终编码。若以后采用探测编码，使用独立实验身份并报告实际额外编码成本。`[verified: 用户既有单次编码要求及V1待决定事项；opinion: 本轮执行决定]`

Unity训练采集保留原搜索提前停止、原标签与baseline计时。离线补测未覆盖的块大小×preset候选，完整身份为4×5配置，保存解码图、真实字节数及各自质量；补测成本单列。MS-SSIM、法线角度、黑像素、大图与RDO协议随记录保留。GDC四个medium/RGB35输出需要经过这一迁移，不能直接代替完整Unity判定。`[verified: V1“限制与待核实”；AGENTS自动选参规则；opinion: 本轮采集决定]`

## 实施差异与对照

- 当前执行探针使用四个独立log10(MSE+1e-10)输出、Huber delta0.1，尺度等价于1 dB的转折点。V1单调结构另作明确配置对照，因为训练数据有138张非单调图。模型未做PSNR20–50截断，归档保留零误差及精确SSE。`[verified: patch-training-smoke.json；psnr-matrix-audit.json；opinion: 首轮对照安排]`
- 当前探针去掉maxpool，按图等权抽patch，未启用增强或EMA。正式V1实验仍需覆盖标准stem、单调输出、资产组权重与EMA；这些实现或实验未完成时不标成已复现。`[verified: patch-training-smoke.json config；V1“模型”“超参数起点”]`
- patch源点对齐120，覆盖步长240，最后不足240的边缘在模型输入复制边界值，误差目标和整图聚合只用有效像素。patch样本相关性和整图分布仍需通过独立验证评价。`[verified: PatchErrorGrid.boxes；NativePatchDataset.__getitem__/aggregate；opinion: 泛化边界]`
- 缓存复核加入样本身份、SSE统计和配置指纹检查，PSNR回退补齐并列决胜。全量提取从空目录运行，原执行源码SHA对应的快照已归档，后续缓存核验修复另由回归用例覆盖。`[verified: patch-data-full.json archived_source；test_patch_targets.py]`

## 入口、记录与交付

入口为 [script/patch_regression.py](../../script/patch_regression.py) 的prepare、probe、train、suite和audit；分类入口为 [classification_control.py](../../script/classification_control.py) 与 [run_classification_controls.py](../../script/run_classification_controls.py)。新增数据、模型与训练class分别位于data、models和training目录。旧 [unity_accuracy90_scratch.toml](../../script/unity_accuracy90_scratch.toml) 是此前整图SGD草案，尚未运行，不用于启动V1回归。`[verified: 对应CLI子命令；配置文件]`

进展入口为 [progress.json](progress.json)，job记录保存在.local的jobs目录。每轮训练保存指标、实际更新数、AMP跳步、权重、预测和源码／数据身份，公开报告在阶段结果形成后同步仓库。V1计划与证据保留用户原始内容，执行差异在本页和implementation-notes中更新。`[verified: PatchTrainer.fit；ReproductionJob.run；用户持续记录及仓库同步要求]`

分类对照与首批两组正式patch回归已完成；最佳开发准确率88.8%、阈值附近RMSE0.9736dB，全量Unity参考／补充候选采集与90%独立验收尚未完成。目标保持active。`[verified: classification-controls/summary.json；patch-v1/summary.json；pretrained-result.json；get_goal active]`

## 正式实验配置与资源

分类五组串行执行，配置见 [分类配置](classification-controls/suite.json)，逐组结果见 [分类汇总](classification-controls/summary.json)。原配置、两档学习率的正则化CE、两档学习率的有序loss使用同一输入与seed，增强关闭，按验证NLL patience5早停。实际启动的队列源码另有归档。`[verified: classification-controls/suite.json；implementation-notes对应记录]`

首批回归采用 [V1回归配置](patch-v1/suite.json)：标准stem、单调输出、EMA0.999、batch128、每图每轮期望4个patch、AdamW/WD0.05、warmup1、最多30轮，按阈值附近RMSE patience5早停。随机初始化lr1e-3为主线，预训练lr3e-4作V1配方对照；不同学习率使结果不能单独归因于初始化。两者均保存原始权重与EMA指标，以及准确率最优和RMSE最优权重。`[verified: patch-v1/suite.json；PatchTrainer.fit]`

GPU实验串行，CPU静态检查可与训练同时发生。当前所有时长为本机开发成本，正式部署延迟需要独立计量。训练前检查空闲显存、RAM与磁盘；小样本确认batch128后再运行完整回归。`[opinion: 资源和计时安排]`

最初的[Unity DLL接口探针](unity-dll-probe.json)在一张归档sRGB Alpha贴图上，以10×10/exhaustive复现了原payload；输入需先垂直翻转以匹配Unity内存顺序。该探针仅验证一个已选候选。`[verified: unity-dll-probe.json scope、results]`

后续[Unity两图补测](unity-supplement.md)完成40组候选，新增24组原搜索未覆盖结果；原选中payload／解码一致，原16组已测质量在记录精度内一致。普通LDR实图与原生指标函数已跑通，真实法线／HDR、直接回调元数据及全量生产采集仍待完成。`[verified: unity-supplement2-bound.json；unity-quality-probe.json；补测报告限制]`

后续直接参数采集与随机初始化正式训练均取得结果：[回归汇总](patch-v1/scratch-result.json)记录14轮后按早停结束、最佳Top-1 76.0%、阈值附近RMSE 1.7681dB；[实际参数核验](unity-actual-options2-revalidated.json)记录两图16次回调和源码恢复，[参数绑定补测](unity-supplement2-actual.json)重放40候选通过。[64图采集](unity-actual-options64.json)另记录558次回调，包含普通颜色和法线用途，恢复无冲突。预训练结果见下文，目标仍未完成。`[verified: 对应JSON记录；patch-v1/summary.json；smoke1-receipt.json]`

[颜色扩展](unity-color8.json)完成8图160候选，新覆盖108组，原52组及winner一致。[法线审计](unity-normal20-policy.json)对真实4096² NormalMap的20个原ASTC重新解码、复测角度指标，通过原记录精度核验；新编码0次，原最高PSNR回退仍判为角度不达标。具体范围、浮点阈值修正和成本见[补测报告](unity-supplement.md)。`[verified: 对应JSON rows、encoded_candidates、quality_passing_candidates]`

预训练回归现已完成14轮，选中epoch9 raw，验证Top-1为88.8%、balanced accuracy85.81%、阈值附近RMSE0.9736dB，最佳权重重载通过。两组均未达到V1的90%／0.75dB，下一步固定容量先检验BN统计量，再按错误分布安排单项训练对照。`[verified: patch-v1/pretrained-result.json、pretrained-monotone-ema-audit.json；opinion: 下一步]`

[BN诊断](normalization.md)两组均完成：固定末轮EMA权重，训练集重估统计量后，随机初始化为76.7%／1.6467dB，预训练为89.2%／0.9512dB，0次优化器更新，test未打开。该结果按训练后处理单列；最高开发准确率89.2%，Unity90%独立验收仍未完成。`[verified: normalization-scratch.json；normalization-pretrained.json；opinion: 实验身份]`

新的[固定容量学习率对照](patch-fixed-capacity/README.md)已完成12轮，选中epoch7 raw，验证Top-1为80.7%、近阈值RMSE1.6040dB，最佳权重重载通过。相对原scratch仅lr1e-3→3e-4，总准确率提高4.7个百分点，但10×10召回下降4.69个百分点；训练墙钟2483.18秒。后续同容量比较输入stem及BN后处理，仍未达到V1／Unity验收。`[verified: patch-fixed-capacity/scratch-lr0003-result.json、scratch-lr0003-audit.json；opinion: 后续安排]`

[真实法线重编码](unity-normal-replay20.json)进一步完成同一4096²、mip0法线图的20候选：完整ASTC与解码RGBA逐字节一致，原角度不达标／最高PSNR回退身份不变。进程174.18秒，编码合计124.20秒，与CUDA训练并行；多mip／HDR仍未覆盖。`[verified: unity-normal-replay20.json rows.reencoding、quality_passing_candidates；.local/jobs/unity-normal-replay20/receipt.json]`

新增训练／验证分批采集支持，每批显式冻结1至256个路径和原source_split，归档保留划分；测试／校准划分及跨划分重复资产会被拒绝。原10000张搜索baseline入口和门槛保留，分批采集只提供生产输入／标签。[两张验证图采集](unity-validation2.json)通过，7次回调吻合，源码／meta恢复通过；[补测](unity-validation2-supplement.json)完成40候选，新增33组、原winner一致，归档保持validation。第一张源图512²经导入变为256²，使用实际参考像素生成监督。`[verified: benchmark.py prepare/verify_protocol；unity_reference.py collect；tests/test_unity_reference_batches.py；unity-validation2.json；unity-validation2-supplement.json；normalized-batch/manifest.json]`

[首批256张训练图](unity-train256-batch001.json)已完成，记录1432次实际编码回调，包含240张Default、16张NormalMap，源码与meta恢复通过；进程963.42秒。连同先前64张，共320张train、2张validation。已通过66张已有归档的[真实合并检查](unity-reference-series-smoke.json)，并启动45批全量[串行采集队列](unity-reference-series.md)，目标train10000／validation1000；当前为running，完整回归目标补测及最终Unity模型仍待完成。`[verified: unity-train256-batch001.json；.local对应jobs/unity-train256-batch001/receipt.json；unity-reference-series-smoke.json；unity-reference-series.json；opinion: 完成范围]`
