# 实验报告

- [TexNN 原生编码闭环项目适配](texnn/source-rgb64-patch64-v2/README.md)记录 64 源图的六网络训练、独立 validation 8 图的 48 次预测编码、质量损失、完整耗时及 96 次重新解码核验，原文训练规模与性能尚未复现。`[verified: 对应 validation8-patch128.json training、groups、audit、limits]`
- [脚本启动与SwanLab接入](script-swanlab-20261110/README.md)记录共享TOML、训练配置、指标上传、历史导入、离线试跑与云端核对。`[verified: 对应源码及verification.json]`
- [Class架构重构与兼容性检查](class-refactor-20261110/README.md)记录模型、数据、训练、校准、评估和报告的独立class，以及数值对照与CLI检查。`[verified: 对应源码类定义；class-refactor-20261110/verification.json]`
- [GDC分类复现与独立校准](gdc-lite-rgb-resnet18-seed20261109/protocol.md)使用现有LITE标签与源图，两组ResNet18各完成30轮及温度拟合。结果见[训练报告](gdc-lite-rgb-resnet18-seed20261109/training_report.md)、[数据报告](gdc-lite-rgb-resnet18-seed20261109/data_report.md)和[验证记录](gdc-lite-rgb-resnet18-seed20261109/verification.json)。`[verified: 对应运行报告及验证记录]`
- [实现记录](gdc-lite-rgb-resnet18-seed20261109/implementation-notes.md)记录计划调整与边界，[资源记录](gdc-lite-rgb-resnet18-seed20261109/task-costs.md)记录试跑和正式运行成本。`[verified: 对应记录文件]`
- [数据集划分比例复核](gdc-lite-rgb-resnet18-seed20261109/数据集划分比例复核.md)记录2026-11-10全量清单检查，类别占比接近，资源组成与单组集中度存在偏移。`[verified: split_proportion_audit.json的splits、class_conditional_effects]`

所有逐图清单、缓存、检查点和原始日志保存到本目录的`.local/`。聚合报告和代码纳入Git。`[verified: 用户确认的实验方案]`

## Python环境与入口

在仓库根目录使用uv安装锁定依赖、查看入口与运行检查，本轮锁定Windows x64与Python 3.12.13。`[verified: pyproject.toml tool.uv.environments、uv.lock、.python-version]`

```powershell
uv sync --frozen
uv run --frozen adaptive-astc --help
uv run --frozen pytest -q
uv run --frozen ruff check src script tests
uv run --frozen basedpyright
```

日常脚本入口统一位于根目录`script/`，共享`script/train_config.toml`，配置与SwanLab说明见[脚本接入报告](script-swanlab-20261110/README.md)。`[verified: 用户脚本目录要求；对应启动脚本和TOML]`

本次正式数据清单和模型保存在`.local/gdc-lite-rgb-resnet18-seed20261109/coverage-v2/`。独立数据复核目录为同级`coverage-v2-reproduce/`，软件试跑和资源探测分别在`.local/smoke-v2/`、`.local/resource-probe/`。`[verified: 本次运行目录及data_reproducibility.json]`

## 复核本次实验

数据准备依赖附件快照、外部源图和本机保存的试跑清单。下列排除清单属于私有运行输入，来源指纹记录在公开数据报告中。重复已有训练使用`--resume`，新实验使用独立`--run-dir`。`[verified: cli.py参数；data_summary.json；训练检查点恢复入口]`

```powershell
uv run --frozen adaptive-astc prepare --exclude-manifest "experiment report/.local/smoke/manifest.json" --exclude-manifest "experiment report/.local/resource-probe/manifest.json"
uv run --frozen adaptive-astc train --initialization pretrained
uv run --frozen adaptive-astc train --initialization scratch
uv run --frozen adaptive-astc calibrate --initialization pretrained
uv run --frozen adaptive-astc calibrate --initialization scratch
uv run --frozen adaptive-astc evaluate
```

两组完整训练后分别拟合温度，封存测试将检查数据、最佳检查点与温度指纹。测试推理缓存支持在相同封存状态下复用。`[verified: require_completed_training、calibrate、evaluate]`
