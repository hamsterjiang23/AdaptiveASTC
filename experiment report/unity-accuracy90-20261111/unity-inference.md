# Unity 原生模型的独立输入与 CUDA 推理计时

已完成两张验证图／13patch的CUDA计时，一次预热、三次正式测量，新预测与原生smoke8权重的已保存预测完全一致。两图合计预处理＋推理＋决策中位数27.50ms；等待3932.86秒与活动2.39秒分开记录。只验证小样本推理，完整Unity模型效果及最终编码另行评价。`[verified: unity-inference-smoke2-v1.json measurements、median_preprocess_inference_decision_seconds、active_seconds；v1-completed-runtime-verification.json stages；opinion: 解释范围]`

## 输入契约与核验

[UnityInferenceTexture／UnityInferenceInput](../../src/adaptive_astc/data/unity_inference.py)接收参考PNG、sRGB、法线用途、Alpha需求和法线评价mip数。尺寸、恒定Alpha与黑像素比例直接从参考像素计算；240网格、边缘复制填充、有效像素mask和八项元数据顺序保持训练契约。该组件不接受候选误差文件、质量标签或原搜索选择。`[verified: data/unity_inference.py UnityInferenceTexture、UnityInferenceInput；test_unity_inference.py]`

[实际输入核验](unity-inference-input-audit.json)比较两张验证图的全部13个patch，RGBA张量、有效mask、metadata和patch索引均以零容差检查，几何、图索引与像素权重数组一致。测试还覆盖边缘不足240、透明度、法线输入和元数据非法组合。这个结果只证明输入一致，不能代替CUDA预测重放或完整训练验收。`[verified: unity-inference-input-audit.json exact_input_parity、input_keys；test_unity_inference.py；opinion: 验收边界]`

## 执行与计时

入口为[benchmark_unity_inference.py](../../script/benchmark_unity_inference.py)，[冻结配置](unity-inference-smoke2-v1-config.json)使用已完成的`unity-native-smoke8-v1`权重，保留原验证batch16和zero阈值0.5。任务依赖`scratch-group512-metadata`成功退出，随后才初始化CUDA；等待期间及执行结束分别核验配置和19份执行源码，等待成本单独记录。已有输出不能覆盖。`[verified: inference_benchmark.py run、execution_sources；unity-inference-smoke2-v1-config.json；opinion: 执行要求]`

已执行一次预热、三次正式测量，每轮重新读取PNG、准备元数据与patch输入、推理、聚合和决策。13patch的预测与同一checkpoint已保存结果零差异，zero mask和决策一致。模型加载0.1744秒、活动2.3926秒、依赖等待3932.8576秒，推理区间两图合计中位数27.5035ms；等待不能计作推理延迟。`[verified: unity-inference-smoke2-v1.json measurements、model_load_seconds、active_seconds、dependency_wait_seconds；opinion: 计时解释]`

[UnityQualityInference](../../src/adaptive_astc/evaluation/unity_inference.py)分别计量patch输入组装、patch前向与传输、整图head与传输、MSE聚合，CUDA阶段显式同步。外层另记录PNG／元数据准备、策略决策和整个“预处理＋推理＋决策”区间。模型加载、来源核验、训练Dataset输入对照与CUDA等待不算入该区间；核验阶段会读取监督数据，实际推理组件不读取监督。`[verified: evaluation/unity_inference.py run；inference_benchmark.py run]`

本入口不执行最终编码；此前[保存预测的最终编码检查](unity-final-encoding.md)保留独立身份。后续已完成[同次预测与编码的小样本计时](unity-deployment.md)，两图预测路径中位数48.81ms、fixed8为38.34ms。独立运行的推理和旧编码时长不能相加声称完整部署加速；完整模型、法线／其他实际输入范围与独立测试验收仍待完成。`[verified: inference_benchmark.py encoding_calls；unity-deployment-smoke2-v1.json summary；opinion: 后续验收要求]`

## 检查与运行边界

51项CPU检查包括本次新增16项、原生质量与训练接口回归。新增生命周期检查覆盖空依赖拒绝、等待顺序、上游失败不进入输入／CUDA、等待期间源码变化拒绝。代码审查通过；开始等待后冻结19份源码，当前主训练的12份绑定源码和完整数据管线的14份绑定源码保持。`[verified: 本轮pytest；test_unity_inference.py；本轮独立代码审查；unity-inference-smoke2-v1-config.json sources_sha256；opinion: 活动任务要求]`

启动前资源与读写位置记录在`experiment report/.local/unity-accuracy90-20261111/jobs/unity-inference-smoke2-v1/launch-preflight.json`。原训练成功退出后仍需至少4GiB空闲RAM、初始化时至少2GiB空闲显存；只写独立测量目录，0次训练更新，不打开test。小样本活动阶段预计不足一分钟，实际等待和运行成本以最终报告为准。`[verified: inference_benchmark.py run；对应launch-preflight.json；opinion: 运行估计]`
