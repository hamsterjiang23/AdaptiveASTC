# 完整 Unity 数据到正式 CUDA 训练的衔接

当前使用[Sprite恢复后的训练full-v2](unity-sprite-recovery.md)，配方不变，新32图CUDA预检已通过，等待完整数据。原full-v1因上游失败退出；下文v1状态为历史记录，当前见[full-v2报告](unity-native-training-full-v2.json)。`[verified: full-v1/full-v2报告；unity-sprite-recovery-readiness.json training_recipe_changed；opinion: 历史边界]`

已完成32训练图／2验证图的CUDA预检：两轮4次实际更新、0次AMP跳步、最佳权重重载通过，完整进程83.45秒。当前等待完整10000／1000数据四阶段核验，正式训练尚未启动；后续GPU任务继续纳入串行调度，独立测试90%仍待验收。`[verified: native-training-full-v1/smoke.json training_updates、checkpoint_audit；unity-native-training-full-v1.json status、stages；opinion: 验收与调度边界]`

入口为[queue_unity_training.py](../../script/queue_unity_training.py)，调度实现为[UnityTrainingQueue](../../reproductions/unity_search_baseline/training_queue.py)。[冻结配置](unity-native-training-full-v1-config.json)和[32图预检配置](unity-native-smoke32-v1-config.json)明确两个阶段，使用已存在的UnityQualityTrainer执行；没有修改正在运行的训练、推理、编码或数据准备源码。活动期间23份绑定源码保持不变。`[verified: unity-native-training-full-v1-config.json sources_sha256；training_queue.py train；opinion: 活动版本要求]`

## 执行条件与训练设置

1. 等尺寸元数据训练、独立推理和同次预测编码三个已绑定进程成功退出，核对PID身份、配置及源码。CUDA训练前另测空闲RAM≥12GiB、显存≥6GiB及GPU利用率≤20%，条件不足继续等待；等待期间不初始化CUDA。`[verified: training_queue.py wait、resources；unity-native-training-full-v1-config.json cuda_dependencies]`
2. 在已冻结的2370图部分语料中，用32张训练图／2张验证图做两轮CUDA检查。训练图含29张sRGB、2张法线，其中1张采用多级法线评价、1张图需要Alpha；分类按输入属性记录，不以预检准确率选正式模型。image batch16、每图4patch，即64patch／更新，预期两轮共4次更新。`[verified: unity-native-training-readiness.json preflight；unity-native-smoke32-v1-config.json；opinion: 预检解释边界]`
3. 预检的训练进程、实际更新和选中权重重载全部通过后，等待完整数据管线成功退出。准备、合并、Dataset读取、原规则接口四项必须全部通过，并各自核对SHA；coverage必须complete，清单实际行数必须train10000／validation1000，精确目标必须重建原块大小和preset。部分语料、失败阶段和变更产物均不能启动正式训练。`[verified: training_queue.py complete_corpus、train；UnityQualityTrainer.validate_coverage]`
4. 此时绑定完整corpus的新SHA、生成独立正式配置并启动训练。正式与预检保持相同batch、采样、优化器参数、worker及损失设置；只改变语料、训练范围、轮数和早停设置。两个阶段都保留原始日志、子进程退出码和失败结果，不覆盖重试。`[verified: training_queue.py __init__、train、run；opinion: 对照与记录范围]`

正式起点沿用已验证的原生随机初始化ResNet-18适配，11,377,660参数，RGBA＋mask和导入属性输入、20候选通道误差与整图质量头。AdamW lr0.0003、weight decay0.05、1轮warmup后余弦、最多30轮、近阈值RMSE早停patience5；零通道／MS-SSIM／法线附加loss各0.1、zero概率门槛0.5、workers2，验证batch16。没有新增预训练、EMA、资产组限权或深度扩容；这是首个完整Unity原生训练起点，不是GDC最优模型的等价迁移。`[verified: unity-native-training-full-v1-config.json recipe；unity-native-smoke8-v1.json config；opinion: 原生起点定位]`

## 验收边界与记录

选模仍只使用validation。正式训练结束要求配置、语料、选中checkpoint／预测／决策及重载证据一致，但队列的`passed`只表示完整开发训练通过，`goal_complete`保持false。独立测试仍需在模型和规则冻结后执行；当前入口不访问test或calibration，已有source-RGB test2000观察结果不参与新的选模。最终Unity独立测试Top-1≥90%、质量、字节与完整成本仍是未完成验收。`[verified: training_queue.py train、run；V1“目标与开发数据”；opinion: 最终验收边界]`

队列主报告见[运行状态](unity-native-training-full-v1.json)，前置核对见[配置就绪记录](unity-native-training-readiness.json)。子阶段报告计划写入`native-training-full-v1/`，权重和原始日志写入`.local/unity-accuracy90-20261111/unity-native-training-full-v1/`。等待、每个训练进程完整耗时及训练器内部阶段分别记录。预检预计30–120秒，正式最多30轮预计1–4小时，均为外推预算，实际按退出记录统计。`[verified: training_queue.py train、run；unity-native-training-readiness.json preflight；opinion: 成本估计]`

后续GPU实验必须纳入这条串行调度后再启动，避免在该任务等数据时另起训练、与自动开始的正式训练重叠。现有Unity参考采集／候选补测继续按原计划运行。`[opinion: 调度要求]`
