# Unity ASTC 搜索基线

## 运行协议

固定 coverage-v2 的 10,000 张训练资产，LITE 质量阈值为 PSNR 30、MS-SSIM dB 21、法线平均角度 3.2°、P95 9°，关闭 RDO。黑像素策略、大图规则、候选顺序、提前停止与回退沿用原生代码。`[verified: .local/unity-search-baseline-lite-rdo-off/identity.json；原生 parameter_cache_detail.jsonl 的 tableConfig]`

每轮预热 Editor/DLL 后切换到独立空参数缓存。为让所有选定图片进入 ASTC 路径，临时将 Android 目标设置为 ASTC 8×8，再由原生搜索决定最终块大小和 preset。进程退出后按备份及预期哈希恢复 .meta。`[verified: BenchmarkRunner.cs ImportOne/Run；benchmark.py run/restore_metadata]`

search_ms 包含候选试压缩、解压、质量评价与最终选择。select_and_encode_ms 覆盖CompressTextureWithMultipleImages 的完整压缩过程，包含实际 payload 复用和 mip。import_wall_ms 单独测量同步 ImportAsset。总墙钟包含 Editor 启动、预热、退出及恢复核验。这些区间存在包含关系。`[verified: timing.patch；ASTCBenchmark.h；BenchmarkRunner.cs]`

Cubemap 与 2D 资产分别保留维度字段。原生选参取第一个 image 的 mip0，完整压缩计时包含其余面和 mip。`[verified: ImageOperations.cpp CompressTextureWithMultipleImages；BenchmarkRunner.cs ImportOne]`

## 实测结果

| 运行 | 状态 | 图片数 | 搜索合计 s | 选参及编码合计 s | 导入合计 s | 总墙钟 s |
|---|---|---|---|---|---|---|
| probe | passed | 2 | 0.308 | 0.315 | 4.208 | 267.970 `[verified: probe-receipt.json]` |
| smoke1 | passed | 64 | 153.501 | 169.720 | 300.954 | 434.379 `[verified: smoke1-receipt.json]` |
| smoke2 | passed | 64 | 157.440 | 173.982 | 303.381 | 439.390 `[verified: smoke2-receipt.json]` |
| smoke3 | passed | 64 | 158.271 | 174.945 | 305.076 | 451.022 `[verified: smoke3-receipt.json]` |
| full | passed_with_retries | 10000 | 4060.469 | 4163.310 | 23828.660 | 24416.512 `[verified: full-receipt.json]` |

## 全量分布

| 计时区间 | 平均 ms | 中位数 ms | P95 ms | 最大 ms |
|---|---|---|---|---|
| search_ms | 406.047 | 259.521 | 1262.068 | 122755.406 `[verified: full-receipt.json timings]` |
| select_and_encode_ms | 416.331 | 266.829 | 1286.168 | 137514.633 `[verified: full-receipt.json timings]` |
| import_wall_ms | 2382.866 | 2223.666 | 3272.804 | 140622.488 `[verified: full-receipt.json timings]` |

共尝试 77,706 个候选，平均每张 7.7706 个。候选压缩结果的实际复用已包含在本基线中。模型路径比较计入预处理、推理和最终编码。`[verified: full-receipt.json timings；ASTCBenchmark.h；用户确认的计时协议]`

## 补测与验收

首批 10,000 张中有 32 张发生备份路径技术失败，随后在独立空缓存中补测成功。合并结果逐图保留成功测量，初次失败、原始退出码和完整原始记录保存在归档中。本次状态为 `passed_with_retries`。`[verified: full-receipt.json recovery/process_exit_codes；full-assembly.json]`

完整覆盖、原生搜索执行、源图 MD4、LITE/RDO-off 策略及参数选择均通过核验，metadata 恢复冲突为 0。引擎参数缓存按 JSON 快照和 JSONL 增量共同读取，原始文件及合并文件由 SHA-256 绑定。`[verified: full-receipt.json provenance/metadata_restore_conflicts；full-assembly.json]`

## 复跑与证据

运行入口为 `uv run --frozen python script/reproduce.py run --phase full`。已有缓存的运行标识会被拒绝复用。配置、manifest、Editor、DLL、原生缓存中的实际源图哈希均参与核验。详细聚合结果见 [summary.json](summary.json)。`[verified: script/reproduce.py；benchmark.py verify_protocol/audit/run]`

原始日志、逐图结果、配置锁、启动身份及 .meta 备份位于同名 `.local` 目录。smoke1/smoke2 的来源绑定由运行后核验补齐，其 `original_android_*` 字段表示每次导入前读到的状态，包含前两张预热图片留下的设置。后续 runner 使用 `pre_import_android_*` 命名。`[verified: phase receipts 的 provenance_binding；BenchmarkRunner.cs ImportOne]`

原始分类实验使用源图 RGB 输入，Unity 基线使用实际导入管线。后续速度比较需保持参考像素、尺寸、Alpha、颜色空间、mip 和最终编码范围一致。`[opinion]`
