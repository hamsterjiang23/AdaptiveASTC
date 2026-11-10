# nah2022_psnr_search 原生复现测量

固定提交 `954af82d2832aa2707d936c5aa5522c76ecd4426`，编码器 SHA-256 为 `9fc8bc5b971d3b4a4587518525e978ee20f79a65a452a83595b610e8595e1a2a`。本次为 2 张项目源图 RGB8 适配，原始分辨率、Linear LDR、无 mip，编码线程数为 1，初始块 [6, 6]，目标 37.3873 dB，最终 preset 为 thorough。`[verified: summary.json protocol]`

| 项目 | 结果 |
|---|---|
| 编码及解码完成 | 2/2，失败 0 `[verified: summary.json succeeded/failed]` |
| 搜索及最终编码 | 1.262 s，逐图中位数 0.631159 s `[verified: receipt.json；images.jsonl]` |
| 参考像素准备 | 0.010 s `[verified: summary.json preprocess_seconds]` |
| 固定 8×8 编码 | 0.035 s `[verified: summary.json fixed8_encode_seconds]` |
| 实验总墙钟 | 1.398 s，含两种结果的解码与质量检查 `[verified: summary.json wall_seconds；common/nah_experiment.py run]` |
| 选择结果 payload | 208 B `[verified: summary.json selected_payload_bytes]` |
| 固定 8×8 payload | 208 B，选择结果相对变化 +0.00% `[verified: summary.json payload fields]` |
| 全图 RGBA 达标 | 2/2 `[verified: summary.json quality_audit]` |
| 全图 RGB 达标 | 2/2 `[verified: summary.json quality_audit]` |
| 固定 8×8 RGBA／RGB 达标 | 2／2，分母 2 `[verified: summary.json quality_audit]` |

## 评价口径与补全设置

参考编码器 PNG 加载器扩展为 4 通道，原生目标评价使用 RGBA。本次另保存全图 RGB 指标，两个口径的达标率分开统计。原始 Alpha 在源图 RGB8 适配中去除，编码器读取时为不透明 Alpha。`[verified: astcenccli_image_load_store.cpp load_image_with_stb；astcenccli_error_metrics.cpp compute_error_metrics/componentmasks；common/nah_experiment.py _measure]`

本次类别记录为 game，目标 37.3873 dB。初始块为 [6, 6]，其来源记录为 `reconstructed 6x6 default from the Nah 2023 author example`。论文类别目标保存在 source.json，目标覆盖以本次 protocol 的数值为准。搜索使用 fastest 和完整 RGBA 质量测量，最终重新编码为 thorough。逐候选 CLI 启动、解码及质量计算包含在本实现的搜索计时中。`[verified: source.json class_target_psnr；common/nah_experiment.py；summary.json protocol；Nah 2022 Table 1；2023 upstream README L1–9]`

本次使用项目图片及明确补全的协议，原文发表数据集和结果另行保留。Unity 基线使用实际导入像素及项目插件，本次采用源图 RGB8 和参考编码器。解码验证使用 CLI 默认设置。可比控制为同方法、同输入、同 preset 的固定 8×8。`[verified: summary.json protocol；Unity 基线 identity.json；common/encoder.py encode/decode 启动参数]`

逐图测量、候选日志、ASTC、解码图片与质量复查保存在同方法同运行名的 `.local/reproduction-runs/` 目录。公共 summary 通过 SHA-256 绑定原始记录与协议。报告使用同一固定二进制重新解码，核对 PNG SHA-256 后重算质量，原始 receipt 和计时保持其测量值。`[verified: summary.json quality_audit；common/reporting.py write]`
