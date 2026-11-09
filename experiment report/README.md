# 实验报告

- [GDC分类复现与独立校准](gdc-lite-rgb-resnet18-seed20261109/protocol.md)使用现有LITE标签与源图，两组ResNet18各完成30轮及温度拟合。结果见[训练报告](gdc-lite-rgb-resnet18-seed20261109/training_report.md)、[数据报告](gdc-lite-rgb-resnet18-seed20261109/data_report.md)和[验证记录](gdc-lite-rgb-resnet18-seed20261109/verification.json)。`[verified: 对应运行报告及验证记录]`
- [实现记录](gdc-lite-rgb-resnet18-seed20261109/implementation-notes.md)记录计划调整与边界，[资源记录](gdc-lite-rgb-resnet18-seed20261109/task-costs.md)记录试跑和正式运行成本。`[verified: 对应记录文件]`

所有逐图清单、缓存、检查点和原始日志保存到本目录的`.local/`。聚合报告和代码纳入Git。`[verified: 用户确认的实验方案]`

## Python环境与入口

在仓库根目录使用uv安装锁定依赖、查看入口与运行检查，本轮锁定Windows x64与Python 3.12.13。`[verified: pyproject.toml tool.uv.environments、uv.lock、.python-version]`

```powershell
uv sync --frozen
uv run --frozen adaptive-astc --help
uv run --frozen pytest -q
uv run --frozen ruff check src tests
uv run --frozen basedpyright
```

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
