# 独立确认集 2000 张串行采集

完整采集入口已实现并启动等待任务，沿用冻结主名单：先等待 `unity-confirmation-capture-smoke2-v2` 两图原生预检成功，复用这两张的参考图与原搜索标签，再分 8 批采集剩余 1998 张。当前状态为 `waiting_smoke`，确认集已采集数为0；CPU检查和真实配置只读核验通过，实际原生采集仍受前置任务约束，模型独立测试尚未打开。`[verified: unity-confirmation-series2000-v1.json status、captured_images、test_opened；unity-confirmation-series-readiness.json plan；confirmation_series.py ranges/run]`

启动后[核验记录](unity-confirmation-series-verification.json)确认六个活动任务的进程／命令身份，以及原数据、训练和两图采集的14／23／15份源码绑定仍一致；本任务新增17份源码绑定，未修改原活动执行代码。`[verified: unity-confirmation-series-verification.json jobs、unchanged_active_source_bindings、source_files_sha256]`

## 固定名单与执行条件

- 配置为 [unity-confirmation-series2000-v1-config.json](unity-confirmation-series2000-v1-config.json)，主名单来自[预留记录](unity-confirmation-cohort.md)，2000 张顺序保持，500 张备用不参与此自动流程。预留清单 SHA-256 为 `42bed07c6bc668f86a0734f1afda7578fd67293b19635435d941a273c5d7b238`。`[verified: unity-confirmation-series-readiness.json reservation_manifest_sha256、plan；confirmation_series.py __init__/publish]`
- 绑定两图预检配置、启动命令、任务回执和 17 份执行源码；预检仍等待开发参考采集、候选补测、完整数据与首轮原生训练成功。全量采集只在两图任务成功退出并通过原生证据复查后开始。`[verified: unity-confirmation-series2000-v1-config.json sources_sha256、smoke_config、smoke_job；unity-confirmation-capture-smoke2-v2-config.json dependencies；confirmation_series.py audit_batch/run]`
- 剩余批次起点为 2、258、514、770、1026、1282、1538、1794；前七批各 256 张，末批 206 张。首两张与所有后续批次合起来必须和冻结主名单逐项一致。`[verified: unity-confirmation-series-readiness.json plan.remaining_batches；confirmation_series.py publish]`
- 每批沿用原采集入口的项目锁、Editor 关闭检查、空参数缓存、原搜索提前停止、导入设置与 managed hook 恢复；最低空闲 RAM 20 GiB、磁盘 40 GiB。等待任务不启动额外 Editor，也不占用训练 GPU。`[verified: unity-confirmation-capture-smoke2-v2-config.json minimum_free_ram_gib/minimum_free_disk_gib；confirmation_capture.py run；confirmation_series.py run]`

## 原生证据与产物

每批完成后重新核验完整参考归档、回调参数、原搜索记录、源身份、逐图顺序、配置哈希和恢复回执。合并产物保留 `confirmation` 划分、RGBA 原生参考路径与哈希、实际 Alpha/profile/用途、原搜索选择、导入信息和逐批来源；不会改写成 train 或 validation。`[verified: confirmation_series.py audit_batch/publish]`

原始完整清单位于 `experiment report/.local/unity-confirmation-series2000-v1/manifest.json`，只有运行后才生成；逐批配置和公开状态写入 `unity-confirmation-series2000-v1-batches/`。一批失败时保留此前已审计的 partial 清单与失败现场，停止后续采集，禁止跳过样本或按质量／模型错误换样。重新执行必须使用新身份，已有输出不可覆盖。`[verified: confirmation_series.py run/batch_config/publish]`

串行采集墙钟包含等待时间，`dependency_wait_seconds` 单列；`editor_process_seconds` 汇总全部原生批次，包括复用的两图预检。逐批 `capture_wall_seconds` 和原任务回执保留，不能把本次控制器墙钟当作纯搜索基线或模型推理时间。`[verified: confirmation_series.py audit_batch/run；opinion: 成本解释]`

完成这份采集仍不等于 Unity 90% 验收通过。后续需完成与开发集的原生像素重复审计、模型及规则冻结、独立预测、真实最终编码和质量／字节／完整成本测量；当前无新准确率结果。`[opinion: 后续验收边界]`

## 复跑入口与验证

只读检查配置：`[verified: script/collect_unity_confirmation_series.py main]`

```powershell
uv run python script/collect_unity_confirmation_series.py --config "experiment report/unity-accuracy90-20261111/unity-confirmation-series2000-v1-config.json" --validate-only
```

首次启动使用 `script/run_reproduction_job.py` 包装该入口，任务配置与 stdout/stderr/receipt 归档在 `.local/unity-accuracy90-20261111/jobs/unity-confirmation-series2000-v1/`。已启动任务以同目录回执核对，禁止重复运行同一身份。`[verified: unity-confirmation-series-readiness.json job、job_config_sha256；reproductions/common/jobs.py run]`

检查覆盖：新串行入口与原确认集入口共 50 项 CPU 测试通过，格式、Ruff 与 basedpyright 通过；合成测试只证明顺序、门控、失败与证据约束，不替代真实 Unity 采集。真实配置只读核验通过，并确认 V1 原始证据 SHA-256 仍为 `d9f17eb3d083002c9f7e6379448f21610e6572309df7c67a10a98ecd82cf25b5`。`[verified: pytest tests/test_unity_confirmation_series.py tests/test_unity_confirmation_capture.py 输出50 passed；ruff/basedpyright 输出；unity-confirmation-series-readiness.json]`
