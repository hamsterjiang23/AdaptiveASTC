# V5 实现笔记

## Deviations

- 小块标签按原图网格保存精确的 uint32 SSE，各存一份原生 RGBA 四通道误差与显示合成 RGB 误差和。训练读取时用有效像素数换算 MSE，再应用 log 变换。由此保留零误差、精确阈值比较和派生原生 RGB 并列评价。`[opinion: 存储选择；unity_tile_labels.py UnityTileLabels.CHANNELS]`
- 沿用 V4 的 29 张验证样本，另纳入 0615、0616、0617，使 V5 的 32 图审计同时覆盖已知渐变案例。复算时使用仓库内的三行历史输入，完整历史表的 SHA 另记。`[verified: audit_unity_tiles.py 默认样本选择；label-audit32.json indices、historical_fixture]`
- 128×128 原型固定 512 张训练图及全部 198 张同尺寸验证图。45 dB 对照只更改训练损失的高 PSNR 尾部，评价继续读取原始误差，28／30 dB 和 X 规则仅用于评价。`[verified: prototype128.json counts、variants；unity_dense_tile_trainer.py loss]`
- 校准改为网页逐组填写。回环地址服务复用已冻结的校准图，网页评分另存为兼容评分入口的 CSV，保留原模板和图片。`[verified: serve_unity_v5_review.py Review、main；unity_v5_review.html save]`

## Discovered edge cases

- 开发图 0901 为 100×100。现有 top-left patch 与 V5 底对齐小块的纵向起点相差 4 像素。V5 训练输入需先对整图顶部做对齐，再切 240×240 patch，同时保留有效像素 mask。`[verified: label-audit32.json unaligned_legacy_patch_grids]` `[opinion: V5 输入对齐方案]`
- 0616 的 `8×8 fastest` 平滑小块 PSNR 最低 34.22 dB，低于 28 dB 和 30 dB 的平滑小块数均为 0。`[verified: label-audit32.json known_cases.616]`
- `L_p95_primary` 保留历史候选 `8×8 fastest`、显示视图以及 16 像素窗口的排他右边界。步进分数缺失时，相关对照用双方均有分数的图片。`[verified: unity_gradient_step.py window_scores；unity_dense_screening.py compare_one；prototype128.json step_baseline]`

## Questions for review

- 主显示视图、坏块阈值和渐变筛图的有效性仍需在人工标注与留出复核中确定。`[opinion: 待验收条件]`

## 联合微调与确认准备

- V5 小块监督走底对齐 patch，V3 保留原顶对齐输入与原生质量监督。联训每轮分别遍历两种监督，保留 BatchNorm 运行缓冲区。生产回归使用原 V3 full20 起点与向后续搜、原生候选质量归档和已测逐图轨迹。`[verified: unity_dense_joint_trainer.py fit；joint-review-readiness.json native_parent_replay、joint_smoke]`
- 步进分数到坏块占比的单调映射只在开发校准组拟合，误差在同一支撑分数的留出组配对统计。正式人工复核根据校准 CSV 选定规则，留出 CSV 在通过校准 SHA 核验后才读取。评分和 SHA-256 使用同一份 CSV 字节，确认协议同时绑定评分入口及评分逻辑。`[verified: unity_dense_review_scoring.py step_baseline、select_rule；score_unity_dense_review.py main；freeze_unity_v5_confirmation.py freeze]`
- 首次采用历史的 2000/500 确认集规模，可用源身份 1379 个。调整为 1000/250 后保持原排除协议，首次结果保留。原生像素隔离和最终模型等绑定继续写入同一新确认协议。`[verified: confirmation-source-reservation-v1.json primary_images；confirmation-protocol-preparation.json]`
- 正式执行预检识别原主名单索引 313 的 GUI 和 458 的 Cube。获批后使用原备用索引 0、1 原位替换，保留原名单、稠密权重与 28 dB／10% 规则。当前执行在通过新旧原生像素对照后才打开模型评价。`[verified: confirmation-execution-preflight-v1.json approved_import_replacements、protocol；run_unity_v5_confirmation.py main]`
- 末批原生导入退出码为 0，归档阶段遇到单张 16 位 PSD 源 RGB 诊断失败。保留首次失败回执，为该诊断记空值，并使用原 Unity 导出重建归档，复核全量 PNG 和回调，重新导入次数为 0。`[verified: unity-v5-confirmation1000-v1-from00770-recovered-v1.json；unity-v5-confirmation1000-v1-series-recovered-v1.json]`
- 首轮像素隔离发现 6 张与开发集重叠。获批后按源候选的原冻结顺序选择 6 张替补，保留其余 994 张的原生回执。正式选参策略按每图真实采集批次关联，便于在合并名单上复核原生规则。`[verified: confirmation-pixel-isolation-v1.json；confirmation-pixel-revision-preflight-v2.json；evaluate_unity_v5_confirmation.py load_policy_batches]`
