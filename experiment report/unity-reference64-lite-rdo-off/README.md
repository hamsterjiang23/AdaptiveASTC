# Unity 导入参考像素采集

使用原搜索基线的固定 64 张训练资产，在相同 Editor／DLL 和 LITE、RDO-off 配置下开启原生磁盘导出，保存 mip0 参考图、选中 ASTC、解码 PNG 和候选报告。`[verified: summary.json capture_phase.provenance、sources_sha256、rows]`

| 检查 | 结果 |
|---|---|
| 完整导出 | 64/64，进程退出码 0 `[verified: summary.json images、capture_phase.process_exit_code]` |
| 与源图 RGB 像素完全一致 | 38/64 `[verified: summary.json source_rgb_equal]` |
| RGB 像素存在差异 | 26/64，逐图记录保留导入后的尺寸 `[verified: summary.json rows.source_rgb_equal、width、height]` |
| 与原基线选中配置一致 | 64/64 的 blockSize／preset 一致 `[verified: summary.json baseline_choice_differences]` |
| metadata 恢复 | 0 冲突 `[verified: summary.json capture_phase.metadata_restore_conflicts]` |
| 辅助导出任务墙钟 | 695.632 秒，包含启动、预热、磁盘导出与恢复 `[verified: summary.json capture_job.wall_seconds、scope]` |

第三方解码 PNG 按底行起始保存，接口的 `y_flip` 参数传入 false。统一质量计算先垂直翻转该 PNG，随后使用参考图的 RGB 尺寸计算完整图像 MSE PSNR。两图试跑和行方向回归测试覆盖了这个转换。`[verified: ASTCCompressor.cpp Astc3rdDecompress 定义与调试调用；normalized-probe/receipt.json；tests/test_unity_reference.py]`

原 10,000 张搜索基线的计时保存在其独立报告。当前导出记录用于核对输入像素和实际 payload，RGB 评价采用 35 dB 严格门槛，Unity 压缩继续使用 LITE 的导入 Alpha、用途和复合选参规则。`[verified: summary.json scope、limits；原基线 summary.json phases.full；候选报告的质量配置]`

初次 64 图导出在系统重启时中断，56 张已完成的输出和原始日志已归档，截断的原生日志记录保留在失败证据中。补跑使用独立空参数缓存，完整导出通过后恢复 metadata。`[verified: interrupted-smoke1-artifacts/receipt.json；summary.json capture_phase、capture_job]`

[完整检查与逐图结果](summary.json) 保存源 MD4、参考 RGB 哈希、输出 SHA-256、选中参数和执行记录。`[verified: summary.json rows、sources_sha256]`
