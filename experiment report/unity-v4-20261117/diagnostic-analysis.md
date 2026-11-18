# V4开发质量可达性与阈值诊断

开发集V3严格未通过125张，其中同块存在严格合格候选的有0张。`[verified: diagnostic-analysis.json failed_reachability]`

| V3未通过样本的可达情况 | 图片数 |
|---|---|
| 50%单图体积预算内存在合格候选 | 52。`[verified: diagnostic-analysis.json failed_reachability]` |
| 存在合格候选，均超出体积预算 | 39。`[verified: diagnostic-analysis.json failed_reachability]` |
| canonical20没有严格合格候选 | 34。`[verified: diagnostic-analysis.json failed_reachability]` |

预算参考为每张图当前V3输出的实际payload。全候选可达性使用开发集实测质量档案。`[verified: reachability-rows.json budget_candidates；V4计划第2节]`

| 指标 | 距实际门槛≤1的候选数 | 预测减实际均值 | RMSE | 假通过 | 假失败 |
|---|---|---|---|---|---|
| psnr | 1648 | 0.5624 | 1.4136 | 352 | 158。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.psnr.within_1]` |
| ms_ssim_db | 2337 | 0.2455 | 2.2713 | 344 | 297。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.ms_ssim_db.within_1]` |
| normal_mean_deg | 419 | 0.0090 | 0.2740 | 19 | 32。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.normal_mean_deg.within_1]` |
| normal_p95_deg | 166 | -0.0760 | 0.8203 | 24 | 30。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics.normal_p95_deg.within_1]` |

PSNR与MS-SSIM距离单位为dB，法线指标单位为度。各指标分别按其实际适用分支统计，假通过指预测合格而实测未合格。`[verified: diagnostic-analysis.json threshold_prediction_diagnostics各unit字段；本轮分类计算]`

已有32图实测和正在进行的1000图计时负责验证这些离线机会的实际质量、体积和时间代价。`[verified: smoke32-v2/result.json；progress.json]`
