# Unity ASTC 搜索基线

## 运行协议

固定 coverage-v2 的 10,000 张训练资产，LITE 质量阈值为 PSNR 30、MS-SSIM dB 21、法线平均角度 3.2°、P95 9°，关闭 RDO。黑像素策略、大图规则、候选顺序、提前停止与回退沿用原生代码。`[verified: .local/unity-search-baseline-lite-rdo-off/identity.json；原生 parameter_cache_detail.jsonl 的 tableConfig]`

每轮预热 Editor/DLL 后切换到独立空参数缓存。为让所有选定图片进入 ASTC 路径，临时将 Android 目标设置为 ASTC 8×8，再由原生搜索决定最终块大小和 preset。进程退出后按备份及预期哈希恢复 .meta。`[verified: BenchmarkRunner.cs ImportOne/Run；benchmark.py run/restore_metadata]`

search_ms 包含候选试压缩、解压、质量评价与最终选择。select_and_encode_ms 覆盖CompressTextureWithMultipleImages 的完整压缩过程，包含实际 payload 复用和 mip。import_wall_ms 单独测量同步 ImportAsset。Editor 启动、预热和退出计入进程墙钟。这些区间存在包含关系。`[verified: timing.patch；ASTCBenchmark.h；BenchmarkRunner.cs]`

Cubemap 与 2D 资产分别保留维度字段。原生选参取第一个 image 的 mip0，完整压缩计时包含其余面和 mip。`[verified: ImageOperations.cpp CompressTextureWithMultipleImages；BenchmarkRunner.cs ImportOne]`

## 实测结果

| 运行 | 状态 | 图片数 | 搜索合计 s | 选参及编码合计 s | 导入合计 s | 进程墙钟 s |
|---|---|---|---|---|---|---|
| probe | passed | 2 | 0.308 | 0.315 | 4.208 | 267.970 `[verified: probe-receipt.json]` |
| smoke1 | passed | 64 | 153.501 | 169.720 | 300.954 | 434.379 `[verified: smoke1-receipt.json]` |
| smoke2 | passed | 64 | 157.440 | 173.982 | 303.381 | 439.390 `[verified: smoke2-receipt.json]` |
| smoke3 | passed | 64 | 158.271 | 174.945 | 305.076 | 451.022 `[verified: smoke3-receipt.json]` |

10,000 张全量结果待运行完成，64 张分层子集用于检查配置与重复性。`[verified: 当前已生成的 phase receipt 集合]`

## 复跑与证据

运行入口为 `uv run --frozen python script/reproduce.py run --phase full`。已有缓存的运行标识会被拒绝复用。配置、manifest、Editor、DLL、原生缓存中的实际源图哈希均参与核验。详细聚合结果见 [summary.json](summary.json)。`[verified: script/reproduce.py；benchmark.py verify_protocol/audit/run]`

原始日志、逐图结果、配置锁、启动身份及 .meta 备份位于同名 `.local` 目录。smoke1/smoke2 的来源绑定由运行后核验补齐，其 `original_android_*` 字段表示每次导入前读到的状态，包含前两张预热图片留下的设置。后续 runner 使用 `pre_import_android_*` 命名。`[verified: phase receipts 的 provenance_binding；BenchmarkRunner.cs ImportOne]`

原始分类实验使用源图 RGB 输入，Unity 基线使用实际导入管线。后续速度比较需保持参考像素、尺寸、Alpha、颜色空间、mip 和最终编码范围一致。`[opinion]`

## 全量运行进度快照

在 2026-11-10T14:03:30.198555+00:00，全量已完成 5104/10,000 张，同期原生记录 5105 条，导入失败 0，已完成图片缺失原生记录 0，参数缓存命中 0。全量仍在运行。`[verified: summary.json running_full_snapshot；对应时点 full-imports.jsonl/full-native.jsonl]`
