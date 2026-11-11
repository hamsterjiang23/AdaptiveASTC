# Unity 原生 patch 监督与法线评价恢复

Unity 原生 RGBA 监督提取已在 train256／validation2 上完成，保留 20 组块大小与 preset 的逐通道误差、整图质量及同次原搜索标签。生成 1664／13 个原尺寸 patch，5160 个候选的整图 PSNR 重建最大差异为 0.000003742 dB。这里验收的是监督数据链路，生产模型训练和独立测试 90% 仍未完成。`[verified: unity-patches-train256.json counts、patch_counts、candidate_count、max_psnr_reconstruction_error_db；opinion: 验收边界]`

## 法线多级评价恢复

第一版全量补测在 `unity-v1-train-002-20261111` 的两张 mipmaps=true 法线图上被 mip0-only 检查拒绝。此前已完成 train576／validation2；失败报告、逐批产物和 1233.83 秒完整进程记录保持原身份，后续采用 `unity-candidate-queue-multimip-v2` 继续，重新审计后复用完成的批次。该耗时包含已完成工作，不能全部视为无效重试成本。`[verified: unity-candidate-queue-full.json error、counts；unity-candidate-queue-multimip-v2-config.json prior_queue、reuse；opinion: 成本解释]`

引擎对 mip0 参考图和候选解码图逐级生成法线向量图，最多评价 mip0–3，并按各级像素数加权。补测仍只编码 mip0，角度评价层数从哈希绑定的 Tex2D 导入 mipmaps 设置和实际尺寸推导；每个原候选的角度与 PSNR 必须继续复现原报告的两位小数值。这不是对完整最终 mip 压缩链的复现。`[verified: ASTCCompressor.cpp L2623–2673、L3504–3508；candidate_completion.py normal_metric_mips、verify_normal_imports、collect_image；opinion: 推导与范围]`

两张 512² 图的全 20 候选补测通过：40 组编码，原搜索 17 组指标复现，新增 23 组覆盖，两张原选中完整 ASTC 文件和解码像素均一致。收集循环 6.67 秒、整进程 6.99 秒。输入仍限 Linear RGBA8、Profile1、normal-pack=false、Tex2D；HDR 未覆盖。`[verified: unity-normal-multimip2.json rows、wall_seconds；对应 jobs/unity-normal-multimip2/receipt.json；candidate_completion.py verify_actual_options]`

## 监督数据口径

| 内容 | 实现与验收 |
|---|---|
| 输入和网格 | 原生 RGBA；240 像素非重叠 patch，原点对齐 120；边缘仅统计有效像素。`[verified: patch_targets.py UnityChannelErrors；unity-patches-train256-config.json patch_size]` |
| 数值目标 | 每个 patch 保存 `[20候选, 4通道]` 的 int64 SSE；先聚合整图各通道 MSE，再执行引擎的非零误差通道选择。`[verified: patch_targets.py squared_errors、psnr、prepare_image]` |
| Alpha | 按实际 needAlpha 决定是否参与，整图参考 Alpha 恒定时排除；不能逐 patch 独立判定恒定 Alpha 后平均 PSNR。`[verified: ASTCCompressor.cpp L2239–2297；patch_targets.py psnr；opinion: 聚合限制]` |
| 无损通道 | 零误差通道不进入平均；所有参与通道无损时取引擎的 100 dB。`[verified: ASTCCompressor.cpp L2242–2297；test_unity_patch_targets.py test_native_psnr_excludes_lossless_channels_and_constant_alpha]` |
| MS-SSIM／法线角度 | 保存原生整图指标和评价 mip_count；当前没有把它们拆成可平均的 patch 标签。相应模型目标与聚合方式仍待实现。`[verified: patch_targets.py image_quality、scope；opinion: 模型待办]` |
| 原标签与身份 | 保留原选中块大小、preset、回退原因、源划分、实际编码参数和导入元数据；候选补测不替换原策略标签。`[verified: patch_targets.py prepare_image identity、measured_image]` |
| 归档与恢复 | 绑定候选清单、公开报告、原始批次记录、单图记录、候选列表及解码 PNG 的 SHA；恢复时复核目标文件、几何和整图 PSNR。`[verified: patch_targets.py prepare、measured_image、prepare_image；test_unity_patch_targets.py 缓存与元数据反例]` |

## 已运行的提取

| 数据 | 候选／patch | 核验和成本 |
|---|---|---|
| 5 train＋2 validation | 140 候选；19＋13 patch | 最大 PSNR 差 0.000001905 dB，循环 1.01 秒。`[verified: unity-patches-smoke.json]` |
| 256 train＋2 validation | 5160 候选；1664＋13 patch，含 16 张法线 | 最大 PSNR 差 0.000003742 dB，循环 51.53 秒／进程 57.00 秒。与原参考采集、候选补测和 CUDA 训练重叠，属于数据准备成本。`[verified: unity-patches-train256.json；对应 jobs/unity-patches-train256/receipt.json；opinion: 成本范围]` |
| 2 多级评价法线＋2 validation | 80 候选；18＋13 patch | 最大 PSNR 差 0.000001884 dB，循环 0.92 秒；保留两张法线的 mip_count=4 和原生整图角度。此处 validation2 与上一行重复，不能相加计为新验证样本。`[verified: unity-patches-multimip2.json；对应 corpus.json image_quality、metadata；opinion: 计数范围]` |

复跑入口为 `uv run --frozen python script/unity_patch_targets.py --config "experiment report/unity-accuracy90-20261111/unity-patches-train256-config.json"`。本机大文件留在 `.local/`，公开配置与报告保留对应路径和 SHA；需有冻结候选归档才能复跑。`[verified: script/unity_patch_targets.py；unity-patches-train256-config.json；opinion: 依赖说明]`

这批数据只覆盖已完成的开发子集。全量候选继续跟随原参考采集；Unity 质量分支建模、完整生产数据训练、端到端时间与独立测试尚待完成。实时入口为[候选队列](unity-candidate-queue-multimip-v2.json)、[原参考队列](unity-reference-series.json)及[执行进展](progress.json)。`[verified: 对应队列 counts、expected_counts；opinion: 待办范围]`
