# Unity 90%目标执行记录

当前方案以用户提供的 [V1：原分辨率 patch 误差回归](<../../experiment plan/V1/README.md>) 为准，诊断依据见 [V1 evidence.json](<../../experiment plan/V1/evidence.json>)。用户清除旧goal后，已按V1重新创建active goal。原来的树模型优先实验和24组SGD搜索不再作为当前执行顺序。`[verified: 用户本轮V1与重建goal要求；create_goal返回active]`

## 验收与执行顺序

主验收保持Unity导入后参考像素与同次原始搜索标签，独立测试块大小Top-1≥90%。GDC源RGB train10000／validation1000用于开发，test2000保持已观察身份，不参与新选模。训练全部使用CUDA，随机初始化为主线，预训练为独立对照。`[verified: 用户既有数据口径确认、CUDA和初始化要求；V1“目标与开发数据”]`

| 顺序 | 当前工作 | 判据 |
|---|---|---|
| patch目标与编码核验 | 从四候选解码图提取真实像素SSE，核对整图PSNR，检查独立patch编码及变换敏感性 | V1 E1的三项分别记录，数据提取通过不能替代独立编码检查。`[verified: V1“实验步骤”E1]` |
| 正则化分类对照 | 固定ResNet-18/RGB224，比较label smoothing、weight decay、学习率、早停和有序loss | 记录验证Top-1、NLL与逐类结果，增强先通过编码核验。`[verified: V1 E2]` |
| 原生patch回归 | 固定ResNet-18容量，scratch与pretrained对照，MSE域整图聚合，验证集选择余量 | 验证Top-1≥90%且阈值附近RMSE≤0.75 dB后进入Unity复核。`[verified: V1 E3]` |
| 按错误分布改进 | 元数据、资产组权重、stem、图级loss逐项比较，仍不足再增大网络 | 每次报告独立增益与成本，最终在Unity数据上验收。`[verified: V1 E4及“限制与待核实”]` |

## 已完成与当前状态

- 新Unity两图参考采集通过，源文件与运行时规则核对通过，meta恢复0冲突。前两次启动失败及恢复记录保留在 [progress.json](progress.json)；成功记录见 [probe.json](probe.json)。已有64图归档另见 [data-readiness.json](data-readiness.json)。`[verified: 对应JSON记录]`
- [PSNR矩阵复核](psnr-matrix-audit.json)核对train10000／validation1000的receipt哈希和矩阵顺序，均与35 dB规则及回退一致。独立高斯噪声σ0.75 dB、5个seed的训练标签命中率平均90.116%；它是决策敏感性模拟。`[verified: psnr-matrix-audit.json results]`
- [64图目标探针](patch-data-smoke.json)通过，生成601个训练patch与155个验证patch，PSNR最大重建差异7.11e-15 dB。`[verified: patch-data-smoke.json]`
- [全量目标提取](patch-data-full.json)通过，10,000训练图产生120,276个patch，1,000验证图产生12,864个patch；44,000个候选的PSNR重建最大差异1.42e-14 dB，耗时614.55秒。原始SSE为int64，边缘只统计真实像素。`[verified: patch-data-full.json；GDCPatchCorpus._prepare_image]`
- [CUDA训练探针](patch-training-smoke.json)在RTX4070完成6次实际更新、0次AMP跳步，参数量11,178,564。该记录只有48训练图／16验证图、两轮各3步，用于执行检查。正式模型训练尚待完成。`[verified: patch-training-smoke.json status、config、history]`
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

分类对照已完成；正式patch回归正在运行，全量Unity参考／补充候选采集与90%独立验收尚未完成。目标保持active。`[verified: classification-controls/summary.json；patch-v1/summary.json；progress.json；get_goal active]`

## 正式实验配置与资源

分类五组串行执行，配置见 [分类配置](classification-controls/suite.json)，逐组结果见 [分类汇总](classification-controls/summary.json)。原配置、两档学习率的正则化CE、两档学习率的有序loss使用同一输入与seed，增强关闭，按验证NLL patience5早停。实际启动的队列源码另有归档。`[verified: classification-controls/suite.json；implementation-notes对应记录]`

首批回归采用 [V1回归配置](patch-v1/suite.json)：标准stem、单调输出、EMA0.999、batch128、每图每轮期望4个patch、AdamW/WD0.05、warmup1、最多30轮，按阈值附近RMSE patience5早停。随机初始化lr1e-3为主线，预训练lr3e-4作V1配方对照；不同学习率使结果不能单独归因于初始化。两者均保存原始权重与EMA指标，以及准确率最优和RMSE最优权重。`[verified: patch-v1/suite.json；PatchTrainer.fit]`

GPU实验串行，CPU静态检查可与训练同时发生。当前所有时长为本机开发成本，正式部署延迟需要独立计量。训练前检查空闲显存、RAM与磁盘；小样本确认batch128后再运行完整回归。`[opinion: 资源和计时安排]`

[Unity DLL接口探针](unity-dll-probe.json)在一张归档sRGB Alpha贴图上，以10×10/exhaustive复现了原payload；输入需先垂直翻转以匹配Unity内存顺序。完整20候选补测与原生质量指标复现尚未完成。`[verified: unity-dll-probe.json scope、results]`
