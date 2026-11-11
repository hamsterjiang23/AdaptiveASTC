# Unity 原生预测与最终编码的同次运行计时

已完成两图、一次预热及三次配对重复，共16次真实编码。两图合计参考PNG到内存mip0 ASTC的中位数为预测路径48.81ms、fixed8路径38.34ms；质量通过率分别1／2与2／2，payload分别59168与81920字节。使用原生smoke8权重，此小样本没有速度或等质量收益结论，也不代表完整Unity验收。`[verified: unity-deployment-smoke2-v1.json summary、measurements；opinion: 解释边界]`

入口为[benchmark_unity_deployment.py](../../script/benchmark_unity_deployment.py)，配置见[冻结配置](unity-deployment-smoke2-v1-config.json)。沿用完成的原生smoke8权重与两张开发验证图，不训练、不打开test；不替代完整Unity模型和独立测试Top-1≥90%的验收。`[verified: deployment_benchmark.py run；unity-deployment-smoke2-v1-config.json；opinion: 验收边界]`

## 计时路径

[UnityDeploymentTrial](../../reproductions/unity_search_baseline/deployment.py)仅接收参考PNG、导入属性、原策略、编码后端和已加载的预测器。每次重新准备原尺寸输入，以CUDA前向预测20候选质量，按原规则选取一个块大小／preset，再对每图调用一次原生编码。另一条fixed8路径读取同一参考图，以固定8×8／medium编码一次，不运行模型。两条路径均返回内存中的mip0 ASTC容器。`[verified: deployment.py __init__、run、encode；unity-final-encoding-smoke2-v2-config.json fixed8_preset]`

连续计时包含参考图读取、输入准备、推理与传输、MSE聚合、策略决策、编码及容器组装。模型／DLL加载在预热前单列；解码、质量计算、归档候选比较、哈希和写盘发生在两条计时路径结束后。报告另保存分段耗时，不以旧推理和旧编码记录相加代替本次总耗时。范围是参考PNG到内存ASTC，不包含Unity导入、完整mip链或磁盘落盘。`[verified: deployment.py run timings.scope；deployment_benchmark.py run、audit；opinion: 成本解释范围]`

已执行一次预热和三次正式配对测量，交替两条路径的顺序；每轮每路径编码两图，共16次，其中正式测量每路径6次。活动阶段3.3420秒、依赖等待3032.8438秒，原始测量全部保留，中位数未择最短值。使用预热模型／DLL和文件系统，Unity采集等CPU活动可能并行，不作为独占生产性能。`[verified: unity-deployment-smoke2-v1.json measurements、summary、active_seconds、dependency_wait_seconds；opinion: 干扰与计时范围]`

## 核验与状态

新预测必须与同一checkpoint已保存预测在浮点绝对误差1e-5内一致，zero mask和完整决策完全一致。每次真实编码的容器字节、解码方向与像素、payload及全部适用的原生指标都与候选归档核对。质量结果保留失败，不以成功编码代替达标；当前编码接口检查中，保存预测选参的payload为59168字节、质量通过1／2，fixed8为81920字节、通过2／2。后续同次CUDA推理＋编码结果保持这些质量和payload数值；仍仅为原生smoke8权重的两图检查。`[verified: deployment_benchmark.py audit；unity-deployment-encode4.json arms；unity-deployment-smoke2-v1.json summary；opinion: 指标边界]`

14项新增CPU检查覆盖动态预测改变真实编码选项、每图一次编码、原生ABI参数及Y翻转、profile／Alpha、空payload失败、黑像素比例精度、非法输入及依赖／源码变动拒绝。独立代码审查通过。任务冻结22份源码，等待结束后与运行结束时都复核，已有输出拒绝覆盖；原19份推理源码、12份主训练源码和14份数据管线源码保持不变。`[verified: test_unity_deployment.py；本轮独立代码审查；unity-deployment-smoke2-v1-config.json sources_sha256；opinion: 活动任务要求]`

原始ASTC、预测、选择和运行记录保存于`experiment report/.local/unity-accuracy90-20261111/unity-deployment-smoke2-v1/`及对应jobs目录；公开状态见[计时报告](unity-deployment-smoke2-v1.json)、[编码接口核验](unity-deployment-encode4.json)和[进度记录](progress.json)。启动前记录RAM可用约19.78GiB，正式进入CUDA前另要求4GiB空闲RAM和2GiB空闲显存；活动阶段预计不足一分钟，等待与执行成本分开记录。`[verified: 对应launch-preflight.json free_ram_bytes；deployment_benchmark.py run；opinion: 活动成本估计]`
