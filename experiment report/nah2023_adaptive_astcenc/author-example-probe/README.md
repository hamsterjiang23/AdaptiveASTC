# nah2023_adaptive_astcenc 原生复现测量

固定提交 `4a3a3a61b2f961efe63e00c913876576315872fb`，编码器 SHA-256 为 `eeff85f4871e6e51d5d1cfa386aa54aba66df9e2ad0d7df9ceaf4fa3e041f92c`。本次为 2 张项目源图 RGB8 适配，原始分辨率、Linear LDR、无 mip，编码线程数为 1，初始块 [6, 6]，目标 40.0 dB，最终 preset 为 medium。`[verified: summary.json protocol]`

| 项目 | 结果 |
|---|---|
| 编码及解码完成 | 2/2，失败 0 `[verified: summary.json succeeded/failed]` |
| 搜索及最终编码 | 1.418 s，逐图中位数 0.708816 s `[verified: receipt.json；images.jsonl]` |
| 参考像素准备 | 0.018 s `[verified: summary.json preprocess_seconds]` |
| 固定 8×8 编码 | 0.027 s `[verified: summary.json fixed8_encode_seconds]` |
| 实验总墙钟 | 1.559 s，含两种结果的解码与质量检查 `[verified: summary.json wall_seconds；common/nah_experiment.py run]` |
| 选择结果 payload | 128 B `[verified: summary.json selected_payload_bytes]` |
| 固定 8×8 payload | 208 B，选择结果相对变化 -38.46% `[verified: summary.json payload fields]` |
| 全图 RGBA 达标 | 0/2 `[verified: summary.json quality_audit]` |
| 全图 RGB 达标 | 0/2 `[verified: summary.json quality_audit]` |
| 固定 8×8 RGBA／RGB 达标 | 2／2，分母 2 `[verified: summary.json quality_audit]` |

## 评价口径与补全设置

参考编码器 PNG 加载器扩展为 4 通道，原生目标评价使用 RGBA。本次另保存全图 RGB 指标，两个口径的达标率分开统计。原始 Alpha 在源图 RGB8 适配中去除，编码器读取时为不透明 Alpha。`[verified: astcenccli_image_load_store.cpp load_image_with_stb；astcenccli_error_metrics.cpp compute_error_metrics/componentmasks；common/nah_experiment.py _measure]`

作者版本保留基于当前时间的随机块抽样，搜索中约跳过 90% 的块，误差分母使用全图像素数的十分之一。零误差返回 999 dB。本报告的达标率通过最终完整 ASTC 文件解码后重新计算。`[verified: upstream astcenc_entry.cpp L833–836、L862–879；astcenccli_error_metrics.cpp L250–265、L333–392；quality-audit.jsonl]`

本次使用项目图片及明确补全的协议，原文发表数据集和结果另行保留。Unity 基线使用实际导入像素及项目插件，本次采用源图 RGB8 和参考编码器。解码验证使用 CLI 默认设置。可比控制为同方法、同输入、同 preset 的固定 8×8。`[verified: summary.json protocol；Unity 基线 identity.json；common/encoder.py encode/decode 启动参数]`

逐图测量、候选日志、ASTC、解码图片与质量复查保存在同方法同运行名的 `.local/reproduction-runs/` 目录。公共 summary 通过 SHA-256 绑定原始记录与协议。报告使用同一固定二进制重新解码，核对 PNG SHA-256 后重算质量，原始 receipt 和计时保持其测量值。`[verified: summary.json quality_audit；common/reporting.py write]`
