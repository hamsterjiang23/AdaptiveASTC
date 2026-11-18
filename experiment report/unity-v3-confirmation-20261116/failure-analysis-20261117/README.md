# V3独立确认未达标样本统计

统计对象为已冻结的2000张独立确认图，质量结果与原标签来自原始执行产物。本文进行已有结果的描述性统计。`[verified: ../result.json measurements[0]绑定的rows.json及trace]`

## 指标口径

| 口径 | 图片数 |
|---|---|
| 严格质量未通过 | 228／2000，11.40%。`[verified: summary.json strict_quality_failures]` |
| Blocksize＋Quality不匹配 | 267／2000，13.35%。`[verified: summary.json config_mismatches]` |
| Blocksize不匹配 | 47／2000，2.35%。`[verified: summary.json block_mismatches]` |

本次267张配置不匹配图全部严格质量合格，与228张严格质量未通过图没有交集。`[verified: summary.json quality_pass_among_config_mismatches]`

## 按导入属性分组

| 类型 | 总图数 | 严格未通过 | 组内失败率 | 配置不匹配 |
|---|---|---|---|---|
| sRGB大图 | 1310 | 189 | 14.43% | 123。`[verified: summary.json types.sRGB大图]` |
| sRGB小图 | 661 | 38 | 5.75% | 140。`[verified: summary.json types.sRGB小图]` |
| Linear | 16 | 0 | 0.00% | 3。`[verified: summary.json types.Linear]` |
| 法线 | 13 | 1 | 7.69% | 1。`[verified: summary.json types.法线]` |

类型使用sRGB、normal及大图分支属性。路径和导入标记随逐图CSV提供。`[verified: analyze.py kind构造；逐图CSV type]`

## 哪些质量指标未通过

| 未通过指标组合 | 张数 |
|---|---|
| MS-SSIM | 190。`[verified: summary.json quality_failure_metrics]` |
| PSNR | 31。`[verified: summary.json quality_failure_metrics]` |
| PSNR+MS-SSIM | 6。`[verified: summary.json quality_failure_metrics]` |
| 法线平均角度+法线P95角度 | 1。`[verified: summary.json quality_failure_metrics]` |

PSNR使用每图有效阈值，MS-SSIM及法线角度使用该图绑定的规则。逐图重新执行strict_quality，并核对原记录布尔结果一致。`[verified: analyze.py policy.strict_quality与failed检查]`

## 搜索分支

- size_first_relaxed有186张。`[verified: summary.json final_failure_reasons]`
- highest_psnr_fallback有42张。`[verified: summary.json final_failure_reasons]`

228张均属于原Unity标签已经严格未通过的样本，当前相对严格质量回退0张。该统计描述分支与结果，具体图像内容的致因需结合像素和候选质量进一步分析。`[verified: quality-failures-228.csv original_strict_pass；../result.json summary]` `[opinion: 归因边界]`

## 尺寸与逐图耗时

先对每张图三次files/single时长取中位数，再在组内计算平均、中位数、P95。时间包含输入、预测、实际编码、解码及门控。`[verified: analyze.py latency；../result.json timings.scope_details]`
尺寸按最大边分组，大图策略分支按面积判定，两个口径分别保留。`[verified: analyze.py size_group；v3_policy.py search的size_first判定]`

| 最大边分组 | 总图数 | 严格未通过 | 失败率 | 平均ms | 中位ms | P95 ms |
|---|---|---|---|---|---|---|
| 最大边1024–2047 | 809 | 92 | 11.37% | 654.37 | 292.48 | 3053.07。`[verified: summary.json sizes.最大边1024–2047]` |
| 最大边512–1023 | 312 | 62 | 19.87% | 275.46 | 139.20 | 776.31。`[verified: summary.json sizes.最大边512–1023]` |
| 最大边2048–4095 | 252 | 36 | 14.29% | 2360.05 | 1164.74 | 7438.66。`[verified: summary.json sizes.最大边2048–4095]` |
| 最大边<512 | 625 | 38 | 6.08% | 66.92 | 45.63 | 200.20。`[verified: summary.json sizes.最大边<512]` |
| 最大边≥4096 | 2 | 0 | 0.00% | 2477.65 | 2477.65 | 3267.68。`[verified: summary.json sizes.最大边≥4096]` |

| 失败数最多的分辨率 | 总图数 | 严格未通过 | 失败率 |
|---|---|---|---|
| 1024×1024 | 717 | 54 | 7.53%。`[verified: summary.json resolutions]` |
| 512×512 | 213 | 47 | 22.07%。`[verified: summary.json resolutions]` |
| 2048×2048 | 225 | 36 | 16.00%。`[verified: summary.json resolutions]` |
| 1780×1000 | 53 | 30 | 56.60%。`[verified: summary.json resolutions]` |
| 16×16 | 14 | 7 | 50.00%。`[verified: summary.json resolutions]` |
| 32×32 | 41 | 5 | 12.20%。`[verified: summary.json resolutions]` |
| 64×64 | 38 | 5 | 13.16%。`[verified: summary.json resolutions]` |
| 880×344 | 15 | 5 | 33.33%。`[verified: summary.json resolutions]` |
| 1000×500 | 6 | 4 | 66.67%。`[verified: summary.json resolutions]` |
| 128×128 | 124 | 3 | 2.42%。`[verified: summary.json resolutions]` |
| 1640×1020 | 16 | 3 | 18.75%。`[verified: summary.json resolutions]` |
| 1024×704 | 6 | 2 | 33.33%。`[verified: summary.json resolutions]` |

## 完整配置不匹配

267张中，220张块大小相同、Quality不同，47张块大小不同。其中267张仍严格质量合格。267张的原标签候选都位于预测起点之前，当前后缀搜索已经跳过该候选。`[verified: summary.json；config-mismatches-267.csv original_before_start]`

以上结果用于描述冻结系统的表现，后续模型或规则调整应在开发集验证。`[opinion]`

## 逐图明细

- [严格质量未通过228张](quality-failures-228.csv)
- [完整配置不匹配267张](config-mismatches-267.csv)
- [完整2000张及质量、延迟字段](all-images-2000.csv)
