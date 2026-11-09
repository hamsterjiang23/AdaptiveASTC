# 资源与成本记录

| 任务 | 命令监控总秒数 | 进程树RSS观测峰值MiB | CUDA分配峰值MiB | 证据 |
|---|---|---|---|---|
| 64张完整软件试跑 | 104.33 | 2938.8 | 570.6 | `[verified: preflight.json]` |
| 128张训练资源探测 | 14.40 | 2721.5 | 910.3 | `[verified: preflight.json]` |
| 正式14000张准备 | 175.93 | 468.3 | 0.0 | `[verified: preflight.json]` |
| 独立目录重复准备 | 176.20 | 557.9 | 0.0 | `[verified: preflight.json]` |
| pretrained 30轮 | 749.79 | 3089.2 | 910.3 | `[verified: 私有logs/pretrained/receipt.json；pretrained_training.json]` |
| scratch 30轮 | 744.66 | 3080.0 | 910.3 | `[verified: 私有logs/scratch/receipt.json；scratch_training.json]` |
| pretrained_calibration | 14.33 | 1917.1 | — | `[verified: 私有logs/pretrained_calibration/receipt.json]` |
| scratch_calibration | 14.31 | 1944.2 | — | `[verified: 私有logs/scratch_calibration/receipt.json]` |
| evaluation | 24.53 | 2885.3 | — | `[verified: 私有logs/evaluation/receipt.json]` |

命令总耗时包含启动、数据加载、验证和保存。RSS为每2秒采样的进程树合计，包含共享页重复计数；CUDA为PyTorch统计。温度阶段总耗时包含校准集推理和拟合，测试推理分别为9.25秒和9.02秒。`[verified: monitor.py；metrics.json /arms/*/inference]`

资源探测在单独目录使用128张训练图和16张验证图，权重仅用于软件与成本检查。两组正式GPU训练顺序执行；独立数据复核在不同缓存树与预训练组前期重叠，源图只读。`[verified: preflight.json；资源探测及正式工作流日志]`

环境为RTX 4070 12GB、Python3.12.13、torch2.8.0+cu128、torchvision0.23.0+cu128。训练按主机内存和时长保守归为Moderate，正式数据准备归为Light。`[verified: verification.json installed_locked_versions及Python；preflight.json]`

首次安装的官方链路较慢，使用镜像传输后通过uv.lock中的SHA-256验证。原始下载与镜像重试耗时属于环境准备，表中训练时间对应已安装环境的正式命令。`[verified: implementation-notes.md；preflight.json /cuda_wheel]`
