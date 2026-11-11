# Unity 原生模型的独立输入与 CUDA 推理计时

已完成只读参考像素和导入属性的输入组件、分阶段推理入口及51项CPU检查。两张真实验证图的全部13个patch与原训练Dataset逐张量完全一致，输入检查耗时0.878秒。CUDA计时任务已启动等待原尺寸元数据训练成功退出，当前还没有新增推理耗时或模型效果结果。`[verified: unity-inference-input-audit.json；本轮pytest 51 passed；unity-inference-smoke2-v1.json status=waiting_training；opinion: 完成边界]`

## 输入契约与核验

[UnityInferenceTexture／UnityInferenceInput](../../src/adaptive_astc/data/unity_inference.py)接收参考PNG、sRGB、法线用途、Alpha需求和法线评价mip数。尺寸、恒定Alpha与黑像素比例直接从参考像素计算；240网格、边缘复制填充、有效像素mask和八项元数据顺序保持训练契约。该组件不接受候选误差文件、质量标签或原搜索选择。`[verified: data/unity_inference.py UnityInferenceTexture、UnityInferenceInput；test_unity_inference.py]`

[实际输入核验](unity-inference-input-audit.json)比较两张验证图的全部13个patch，RGBA张量、有效mask、metadata和patch索引均以零容差检查，几何、图索引与像素权重数组一致。测试还覆盖边缘不足240、透明度、法线输入和元数据非法组合。这个结果只证明输入一致，不能代替CUDA预测重放或完整训练验收。`[verified: unity-inference-input-audit.json exact_input_parity、input_keys；test_unity_inference.py；opinion: 验收边界]`

## 执行与计时

入口为[benchmark_unity_inference.py](../../script/benchmark_unity_inference.py)，[冻结配置](unity-inference-smoke2-v1-config.json)使用已完成的`unity-native-smoke8-v1`权重，保留原验证batch16和zero阈值0.5。任务依赖`scratch-group512-metadata`成功退出，随后才初始化CUDA；等待期间及执行结束分别核验配置和19份执行源码，等待成本单独记录。已有输出不能覆盖。`[verified: inference_benchmark.py run、execution_sources；unity-inference-smoke2-v1-config.json；opinion: 执行要求]`

计划执行一次预热、三次正式测量，每次重新准备参考PNG和元数据，批量生成输入并推理，再在MSE域聚合、按原规则作决策。每轮都将新预测与同一checkpoint已保存结果比较，浮点绝对误差≤1e-5，zero mask和最终决策必须完全一致。预热与正式测量分开保存，当前尚无实际CUDA计时值。`[verified: inference_benchmark.py run；unity-inference-smoke2-v1-config.json warmups、repetitions；opinion: 计划测量范围]`

[UnityQualityInference](../../src/adaptive_astc/evaluation/unity_inference.py)分别计量patch输入组装、patch前向与传输、整图head与传输、MSE聚合，CUDA阶段显式同步。外层另记录PNG／元数据准备、策略决策和整个“预处理＋推理＋决策”区间。模型加载、来源核验、训练Dataset输入对照与CUDA等待不算入该区间；核验阶段会读取监督数据，实际推理组件不读取监督。`[verified: evaluation/unity_inference.py run；inference_benchmark.py run]`

本入口不执行最终编码；此前[保存预测的最终编码检查](unity-final-encoding.md)保留独立身份。两次运行的计时不能简单相加声称完整部署加速，后续仍需同一次执行中的预测和编码，以及完整模型、法线／其他实际输入范围和独立测试验收。`[verified: inference_benchmark.py encoding_calls、deployment_end_to_end_seconds；opinion: 后续验收要求]`

## 检查与运行边界

51项CPU检查包括本次新增16项、原生质量与训练接口回归。新增生命周期检查覆盖空依赖拒绝、等待顺序、上游失败不进入输入／CUDA、等待期间源码变化拒绝。代码审查通过；开始等待后冻结19份源码，当前主训练的12份绑定源码和完整数据管线的14份绑定源码保持。`[verified: 本轮pytest；test_unity_inference.py；本轮独立代码审查；unity-inference-smoke2-v1-config.json sources_sha256；opinion: 活动任务要求]`

启动前资源与读写位置记录在`experiment report/.local/unity-accuracy90-20261111/jobs/unity-inference-smoke2-v1/launch-preflight.json`。原训练成功退出后仍需至少4GiB空闲RAM、初始化时至少2GiB空闲显存；只写独立测量目录，0次训练更新，不打开test。小样本活动阶段预计不足一分钟，实际等待和运行成本以最终报告为准。`[verified: inference_benchmark.py run；对应launch-preflight.json；opinion: 运行估计]`
