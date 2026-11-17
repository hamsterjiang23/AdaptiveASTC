# V3 开发实验结果

推荐系统使用**Unity输入配对训练权重**，输入为`unity`，候选集合为`full20`，1000张开发验证图的块大小准确率为 **93.6%**，文件到mip0 ASTC的批量中位耗时为 **195.60 ms／图**。`[verified: summary.json recommendation]`

选定系统的Blocksize＋Quality完整配置匹配率为80.4%，严格质量通过率为87.5%，相对原标签的严格质量回退为0张。1000图的mip0 ASTC payload为32,067,120字节，固定8×8／medium为59,761,616字节，比例为53.66%。`[verified: summary.json recommendation.metrics full_choice_accuracy、actual_strict_quality_pass_rate、quality_regression_images、payload_bytes、fixed8_medium_payload_bytes、payload_ratio_to_fixed8]`

计时期间观察到并发Blender CPU负载。各轮原始计时及逐图延迟均已保存，运行时负载观测见resource-observations.jsonl。`[verified: resource-observations.jsonl；benchmark报告各轮measurements]`

## 真实耗时基线

以下四组使用同批1000张验证图和同一编码器DLL，预测路径使用冻结V2权重。耗时为文件到内存mip0 ASTC的三次批量测量中位数摊销。`[verified: benchmark-v2-full1000-v1-config.json cases、repetitions；benchmark-v2-full1000-v1.json results]`

| 路线 | 原Unity标签块大小匹配率 | 严格质量通过 | 平均编码次数 | 批量摊销ms／图 |
|---|---|---|---|---|
| 原20候选规则搜索，同DLL实际重放 | 100.0% | 87.4% | 7.061 | 445.02 `[verified: benchmark-v2-full1000-v1.json results.original-full20]` |
| 固定8×8／medium | 14.3% | 81.1% | 1.000 | 23.70 `[verified: benchmark-v2-full1000-v1.json results.fixed8-full20]` |
| ResNet-34纯预测后一次编码 | 86.9% | 68.2% | 1.000 | 128.38 `[verified: benchmark-v2-full1000-v1.json results.pure-unity-full20]` |
| ResNet-34预测起点后续搜 | 93.6% | 87.5% | 1.627 | 200.84 `[verified: benchmark-v2-full1000-v1.json results.forward-unity-full20]` |

## 系统组合

| 系统 | 原Unity标签Top-1 | 严格质量通过 | 平均编码次数 | 批量摊销ms／图 |
|---|---|---|---|---|
| V2冻结权重／forward-unity-full20 | 93.6% | 87.5% | 1.627 | 200.84 `[verified: benchmark-v2-full1000-v1.json results.forward-unity-full20]` |
| V2冻结权重／forward-source_native-full20 | 92.8% | 87.6% | 2.382 | 239.33 `[verified: benchmark-v2-full1000-v1.json results.forward-source_native-full20]` |
| V2冻结权重／forward-source_aligned-full20 | 87.3% | 87.8% | 1.577 | 197.14 `[verified: benchmark-v2-full1000-v1.json results.forward-source_aligned-full20]` |
| V2冻结权重／forward-unity-no_exhaustive16 | 86.7% | 86.4% | 1.562 | 105.13 `[verified: benchmark-v2-full1000-v1.json results.forward-unity-no_exhaustive16]` |
| V2冻结权重／forward-source_native-no_exhaustive16 | 86.9% | 86.6% | 2.185 | 139.24 `[verified: benchmark-v2-full1000-v1.json results.forward-source_native-no_exhaustive16]` |
| V2冻结权重／forward-source_aligned-no_exhaustive16 | 81.2% | 86.7% | 1.547 | 116.23 `[verified: benchmark-v2-full1000-v1.json results.forward-source_aligned-no_exhaustive16]` |
| Unity输入配对训练权重／forward-unity-full20 | 93.6% | 87.5% | 1.627 | 195.60 `[verified: benchmark-trained-unity-full1000-v1.json results.forward-unity-full20]` |
| Unity输入配对训练权重／forward-unity-no_exhaustive16 | 86.7% | 86.4% | 1.562 | 105.33 `[verified: benchmark-trained-unity-full1000-v1.json results.forward-unity-no_exhaustive16]` |
| 原图输入配对训练权重／forward-source_aligned-full20 | 92.1% | 88.0% | 1.838 | 208.32 `[verified: benchmark-trained-source_aligned-full1000-v1.json results.forward-source_aligned-full20]` |
| 原图输入配对训练权重／forward-source_aligned-no_exhaustive16 | 85.3% | 86.9% | 1.693 | 121.26 `[verified: benchmark-trained-source_aligned-full1000-v1.json results.forward-source_aligned-no_exhaustive16]` |

冻结V2权重使用原尺寸源图时，续搜准确率为92.8%，平均编码2.382次。尺寸对齐原图经过配对训练后，续搜准确率为92.1%，平均编码1.838次，批量摊销耗时为208.32ms／图。`[verified: summary.json systems 对应原图输入条目]`

冻结V2权重删除exhaustive后，续搜准确率为86.7%，批量摊销耗时为105.13ms／图，相对原标签有14张严格质量回退。16候选规则标签与原20候选的块大小变化率为6.2%。`[verified: summary.json systems 对应冻结V2的16候选条目；candidate-ablation.json results.no_exhaustive16.oracle]`

## 原图训练与预测

| 模型／输入 | 纯预测Top-1 | 近阈值PSNR RMSE dB | 黑像素比例变化图数 |
|---|---|---|---|
| imagenet-resnet34-head-sampled4／unity | 86.9% | 1.6135 | 0 `[verified: input-diagnostics.json controls[0]]` |
| imagenet-resnet34-head-sampled4／source_native | 76.9% | 3.1323 | 326 `[verified: input-diagnostics.json controls[1]]` |
| imagenet-resnet34-head-sampled4／source_aligned | 81.9% | 2.0300 | 347 `[verified: input-diagnostics.json controls[2]]` |
| train-unity-head-full-v1／unity | 86.9% | 1.6135 | 0 `[verified: input-diagnostics.json controls[3]]` |
| train-source_aligned-head-full-v1／source_aligned | 81.7% | 2.4997 | 347 `[verified: input-diagnostics.json controls[4]]` |

原图路线的纯预测、后续编码次数和完整耗时分别由本表与系统表提供。训练与模型输入准备的成本见对应训练报告，最终系统按原Unity标签准确率优先的既定规则选择。`[verified: input-diagnostics.json；summary.json systems、recommendation]`

原图路线的训练监督、最终编码和实际质量门控使用Unity参考像素及真实导入属性，调用方提供目标尺寸、sRGB、法线用途、Alpha需求和法线评价mip范围。`[verified: unity_v3_input.py SourceTextureSpec；v3_deployment.py UnityV3DeploymentTrial.run、V3NativeQueries.measure；unity_v3_dataset.py UnityV3PatchDataset]`

源尺寸变化、对齐后RGB变化、Alpha变化、法线和Linear等分组的纯预测效果，见input-diagnostics.json的groups；对应真实续搜、质量与编码次数，见summary.json的input_change_groups。`[verified: input-diagnostics.json controls[*].groups；summary.json controls[*].input_change_groups]`

## 配对训练成本

| 输入 | 全模型30轮进程秒 | 整图头30轮进程秒 |
|---|---|---|
| unity | 2227.99 | 412.73 `[verified: summary.json training_costs.unity]` |
| source_aligned | 2767.52 | 617.31 `[verified: summary.json training_costs.source_aligned]` |

Unity输入配对训练与冻结V2的1000图完整质量预测存档的SHA相同，两个模型条目的计时分别来自对应的实测过程。`[verified: summary.json unity_input_retraining_reproduction]`

源图核验覆盖10000张训练图和1000张验证图，失败0张，源尺寸与Unity目标尺寸不同的数量为3167／368。`[verified: source-input-audit.json counts、failures]`

冻结V2模型删除exhaustive后，纯预测Top-1为84.9%，续搜Top-1为86.7%，对应20候选为86.9%／93.6%。`[verified: candidate-ablation.json results]`

完整时间分段、逐图延迟序列及P95见各benchmark报告的measurements。模型和DLL加载成本见input-diagnostics.json的model_setup_seconds和binary_setup_seconds，所选输出审计及ASTC／PNG写盘成本见selected-output-audit.json。这些成本在最终诊断进程独立测量。`[verified: benchmark报告 results.*.measurements；input-diagnostics.json；selected-output-audit.json]`

## 计时口径与单图延迟

`files`从所需文件读取、解码及输入准备开始计时，原图路线包含源图缩放和Unity编码参考像素的准备。`pixels_ready`从已就绪的RGBA像素开始计时。文件口径的批量预测覆盖完整1000图，像素就绪口径按每组8图独立测量后汇总。`[verified: v3_benchmark.py UnityV3Benchmark.measure；v3_deployment.py UnityV3DeploymentTrial.run；benchmark报告 timings.scope_details、chunk_images]`

各路线预热一次、正式测量三次，单图模式逐图执行新的预测和编码。所选Unity输入／20候选续搜系统的逐图实测延迟如下。`[verified: benchmark-trained-unity-full1000-v1-config.json warmups、repetitions、measurement_modes；v3_deployment.py _single_image_trials]`

| 起点与重复 | 平均ms | 中位ms | P95 ms |
|---|---|---|---|
| 文件输入，第1次 | 228.48 | 91.46 | 608.67 `[verified: summary.json recommendation.single_image_latency_ms.files[0]]` |
| 文件输入，第2次 | 229.12 | 93.40 | 610.91 `[verified: summary.json recommendation.single_image_latency_ms.files[1]]` |
| 文件输入，第3次 | 230.49 | 95.04 | 612.54 `[verified: summary.json recommendation.single_image_latency_ms.files[2]]` |
| 像素就绪，第1次 | 224.26 | 90.72 | 600.95 `[verified: summary.json recommendation.single_image_latency_ms.pixels_ready[0]]` |
| 像素就绪，第2次 | 223.40 | 88.70 | 596.14 `[verified: summary.json recommendation.single_image_latency_ms.pixels_ready[1]]` |
| 像素就绪，第3次 | 225.34 | 89.73 | 608.04 `[verified: summary.json recommendation.single_image_latency_ms.pixels_ready[2]]` |

## 历史Unity采集时间

以下数值来自原始采集记录，保留原记录的计时范围。本轮真实编码计时见上文系统表。`[verified: summary.json historical_unity_capture_timings]`

| 原记录字段 | 平均ms／图 | 中位ms／图 | P95 ms／图 |
|---|---|---|---|
| search_ms | 1068.42 | 514.70 | 4219.77 `[verified: summary.json historical_unity_capture_timings.search_ms]` |
| format_ms | 1075.95 | 520.37 | 4224.38 `[verified: summary.json historical_unity_capture_timings.format_ms]` |
| select_and_encode_ms | 1078.72 | 522.37 | 4224.40 `[verified: summary.json historical_unity_capture_timings.select_and_encode_ms]` |

最终开发合同已保存，2000张独立确认集仍等待正式执行授权。`[verified: confirmation-contract.json confirmation_execution_authorized、test_opened]`

## 执行入口

```powershell
uv run --no-sync python script/execute_unity_v3.py --status
```

计划与矩阵见[V3计划](<../../experiment plan/V3/README.md>)，回归检查见[verification.json](verification.json)，阶段记录见[progress.json](progress.json)。`[verified: 对应文件]`
