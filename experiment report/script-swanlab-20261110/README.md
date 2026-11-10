# 脚本启动与SwanLab接入

公开启动入口集中在根目录`script/`，五个阶段共享`train_config.toml`。核心实现由TrainConfig、Trainer、SwanLabTracker与MetricsUploader等class维护，依赖通过uv锁定SwanLab 0.10.4。`[verified: script/五个启动文件；config.py、training/trainer.py、tracking/；uv.lock中的swanlab版本]`

## 启动入口与配置

| 文件 | 用途 |
|---|---|
| [prepare.py](../../script/prepare.py) | 读取共享配置的run/report目录，调用DataPreparer。`[verified: prepare.py的ExperimentCLI.main调用；cli.py的非train配置解析]` |
| [train.py](../../script/train.py) | 读取TOML并接受CLI覆盖，进入Trainer.from_config(...).fit()。`[verified: train.py；cli.py的train分支]` |
| [calibrate.py](../../script/calibrate.py) | 对指定initialization拟合独立校准温度并上传指标。`[verified: calibrate.py；cli.py的calibrate分支]` |
| [evaluate.py](../../script/evaluate.py) | 封存测试、生成报告，上传聚合指标与三张图。`[verified: evaluate.py；cli.py的evaluate分支]` |
| [upload_metrics.py](../../script/upload_metrics.py) | 校验来源身份后上传既有训练／校准／测试记录。`[verified: upload_metrics.py；tracking/upload.py的MetricsUploader.upload]` |
| [train_config.toml](../../script/train_config.toml) | 集中维护training与swanlab两个配置段。`[verified: 对应TOML内容]` |

TOML中的相对路径以配置文件所在目录为基准，CLI路径按调用时工作目录解释，显式参数覆盖TOML。根目录的常规流程见[README](../../README.md#脚本启动与swanlab)。软件试跑使用`--smoke`生成的64张清单，正式GDC校准／测试入口保留30轮完整训练门禁，有效batch对应的完整步数按实际配置计算。`[verified: config.py的TrainConfig.load；cli.py的参数覆盖；utils/checkpoints.py的require_completed；verification.json的software_scope]`

TrainConfig开放原有启动参数与学习率、momentum、weight decay、有效batch、scheduler周期和seed。每次训练保存有效配置快照，检查点记录optimization_config；resume会核对数据指纹、初始化及优化参数，训练轮数、workers和micro-batch可按支持范围调整。`[verified: config.py的TrainConfig、optimization_signature；training/trainer.py的config和state；utils/checkpoints.py的validate_resume]`

## SwanLab记录内容

| 范围 | 指标与产物 |
|---|---|
| 训练 | 每轮loss、accuracy、样本数、优化步数与训练秒数。`[verified: Trainer.train_epoch的返回字段；SwanLabTracker.log_epoch]` |
| 验证 | Accuracy、macro F1、balanced accuracy、NLL、Brier、15-bin ECE及逐类Precision／Recall／F1／support。`[verified: ClassificationMetrics.compute；SwanLabTracker.scalars递归展开]` |
| 优化与资源 | learning_rate、micro_batch、epoch_seconds、peak_vram_mib、rss_mib。`[verified: Trainer.fit的record；SwanLabTracker.log_epoch]` |
| 校准 | 温度、初始／拟合NLL、优化迭代数、梯度与完整结果JSON。`[verified: cli.py的calibrate分支；TemperatureCalibrator.fit]` |
| 测试 | raw／calibrated完整标量指标、逐类结果、多数类基线与完整JSON。`[verified: cli.py的evaluate分支；MetricsUploader.upload]` |
| 图表 | 训练曲线、可靠性图、混淆矩阵三张PNG。`[verified: SwanLabTracker.log_report]` |
| 来源 | 配置、数据指纹，历史导入另保存源文件SHA-256、historical_import与scope。`[verified: ExperimentCLI.train的metadata；MetricsUploader.upload的metadata]` |

新训练新增train accuracy，历史记录按已有字段上传。逐轮指标使用实际epoch编号作为step。校准与评估可单独形成阶段run，历史上传将同一模型的训练、校准与测试聚合到一个run。`[verified: Tracker.log_epoch、CLI各阶段with块、MetricsUploader.upload]`

online上传默认使用现有登录，SDK以非交互设置启动，并设置on_online_error=raise。offline记录在运行目录的swanlog中，disabled直接跳过SDK初始化。run ID与状态写入tracking目录，训练resume核对并复用已有身份。SDK接口已核对官方文档和已安装版本的签名。`[verified: SwanLabTracker.__enter__、__exit__；本次SDK签名检查]` [init官方文档](https://docs.swanlab.cn/api/py-init.html)、[log官方文档](https://docs.swanlab.cn/api/py-log.html)

## 本次实际云端上传

两组既有30轮实验以历史导入方式上传到HAMSTER/AdaptiveASTC，配置中historical_import=true、scope=replay_of_recorded_results，原始来源SHA随记录保留。云端run均显示FINISHED，每组90个标量键和5个媒体键。`[verified: 本次云端info、series查询及verification.json的cloud_verification]`

| 模型 | 云端入口 | 云端与本地核对 |
|---|---|---|
| pretrained | [g2jst3lu](https://swanlab.cn/@HAMSTER/AdaptiveASTC/runs/g2jst3lu) | Accuracy 0.675，raw NLL 0.8016288771，calibrated NLL 0.7751764955。`[verified: cloud-g2jst3lu-summary.json与原实验metrics.json]` |
| scratch | [9upi1o1n](https://swanlab.cn/@HAMSTER/AdaptiveASTC/runs/9upi1o1n) | Accuracy 0.6235，raw NLL 0.9367290952，calibrated NLL 0.9197797728。`[verified: cloud-9upi1o1n-summary.json与原实验metrics.json]` |

Accuracy回读与本地值完全相同，所核对NLL的API回读最大绝对差为1.11×10⁻¹⁶，验收绝对容差为10⁻¹²。`[verified: 本次云端summary与本地metrics.json逐值比较输出；verification.json的cloud_verification]`

这些云端曲线对应已归档的GDC复现实验，数据代表性和生产质量边界见[原实验报告](../gdc-lite-rgb-resnet18-seed20261109/training_report.md)与[比例复核](../gdc-lite-rgb-resnet18-seed20261109/数据集划分比例复核.md)。`[verified: 上传配置的historical_import、source_artifact_sha256；对应历史报告]`

另用32张训练、8张验证数据执行真实online训练及resume，云端[s4fwa28g](https://swanlab.cn/@HAMSTER/AdaptiveASTC/runs/s4fwa28g)复用了同一run ID并显示FINISHED，train accuracy、loss、验证NLL和micro-batch的最新step均为2，配置标记dataset_smoke=true。`[verified: online-smoke.json；cloud-s4fwa28g-info.json、summary.json]`

## 验证与边界处理

- 64张离线软件试跑覆盖准备、两组训练、scratch恢复、两组校准、测试、缓存复用、图表与历史上传。`[verified: verification.json的各阶段命令、offline_end_to_end]`
- 修改learning_rate后恢复被拒绝，既有last.pt哈希保持一致。`[verified: verification.json的changed_resume_rejected；独立validate.py的检查点SHA断言]`
- 两轮默认训练与接入前源码逐项对照，模型、optimizer、scheduler、scaler、Python／NumPy／Torch／CUDA RNG以及loss和验证指标相同，使用真实offline SDK记录。`[verified: verification.json的default_optimization_parity]`
- 审查发现误启动可能覆盖旧SwanLab身份，以及脚本默认目录分歧。已提前执行resume校验并统一共享TOML，新增对应回归测试。`[verified: 本次review_experiment的C1、C2与CLEAN复查；tests/test_launch_tracking.py]`
- SDK offline模式的url属性会抛错，适配器仅在online读取该属性。Windows诊断命令使用PYTHONIOENCODING=utf-8。`[verified: SDK实测异常及修复后probe；本次UTF-8 ping成功输出]`

完整检查结果见[verification.json](verification.json)，实现选择见[implementation-notes.md](implementation-notes.md)。逐命令日志、云端API原始响应和新旧对照脚本归档在`.local/script-swanlab-20261110/`。`[verified: 本次检查与工件路径]`
