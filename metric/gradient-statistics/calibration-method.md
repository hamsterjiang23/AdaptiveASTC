# 同 PSNR 配对的经验尾部筛查

每张资产用同一张原图作为参照，计算真实压缩候选 B 与 A 的指标差。统计问题是「在同样 PSNR 接近的条件下，这个变化放进其他开发资产里有多少见？」数值表示开发参考分布里的相对少见程度。是否肉眼不可接受仍需查看图片。`[verified: calibrate.py 的 inputs、apply_scales、outputs]` `[opinion]`

## 先分目录，再看分数

50 张待筛图来自 48 个目录。额外参考样本有 368 对，都满足 Unity PSNR 差和展示 PSNR 差的绝对值同时 ≤0.5 dB，且排除了这 48 个目录。为了避免同目录重复计数，用固定哈希从剩余每个目录各取一对，再用目录哈希排序交替分为 **139 个标尺目录**和 **138 个校准目录**。选样与分组均未使用待筛指标。最终的校准数据都是同一开发验证集中的额外目录。`[verified: reference-selection.json 的 protocol；reference-partition.csv；calibrate.py 的 split_reference]`

## 把不同单位的变化放在一套规则里

预先选择五类用途，共 15 项。组内的指标可以高度相关；重复增加相似指标也会改变极值分布，所以用完全相同的 15 项处理校准图和待筛图。`[verified: calibrate.py 的 FAMILIES、apply_scales、outputs]`

| 家族 | 纳入的指标 |
|---|---|
| 块边界方格 | 边界额外跳变 P95、最强连续接缝、错位网格扣除后的接缝分。`[verified: FAMILIES/block_seam]` |
| 平台或末端台阶 | 平台分、最强平台长度。`[verified: FAMILIES/flat_steps]` |
| 亮度色带 | Wang 全参考近似、CAMBI 全参考。128² 的 CAMBI 留空。`[verified: FAMILIES/banding；reference-banding.csv]` |
| 集中的局部失真 | 渐变区 FLIP P95、最差 32² 窗口 PSNR、窗口 PSNR 低于 28 dB 的面积占比。`[verified: FAMILIES/local_error]` |
| 整体感知和结构 | SSIM、SSIMULACRA2、LPIPS、FLIP P99、GMSD。`[verified: FAMILIES/overall]` |

1. 对每项计算原单位下的 `d = B−A`。用标尺数据 `|d|` 的第 90 百分位作尺度，再计算目标 `|d|/尺度`。首先尝试“同尺寸、同绝对 PSNR 层”标尺，要求至少 20 个有效值；不足时优先退回同 PSNR 层，再退回全部标尺。若 P90 为 0 且仍有正数，用正数中位数并标明；整层恒零则继续扩层。每个分母及样本数见 [标尺明细](fit-scales.csv)。`[verified: calibrate.py 的 fit_scales；fit-scales.csv]`
2. 每类取可用标准化值的最大值，整张图再取所有类别的最大值。整图分取绝对变化，保留触发指标的原始正负方向。整图挑选不会把 A 变差与 B 变差的数值相加。平台长度只标 A 或 B 哪个更长。无值的指标不参加最大值，也不计作“零失真”。`[verified: calibrate.py 的 apply_scales、direction；metric-tail.csv]`
3. 把同一套分数应用到另一半校准资产。两候选原生 PSNR 都 ≥35 dB 的图与 108 个高 PSNR 校准资产比较，其余图与 30 个相应资产比较。含同分的经验尾比为 **(1＋校准图中分数不低于这张的张数)/(1＋校准图张数)**。整图最大值的尾比记作 `p_any`；它已经纳入“15 个指标中挑一个最突出的”这步观察。单项和家族的尾比各自单列，保留有效参考数。`[verified: calibrate.py 的 tail、outputs；statistical-screen.json 的 calibration_strata]`

为呈现缺测和尺寸构成的影响，输出还列出“同 PSNR 层且同尺寸”及“同 PSNR 层且 15 项的可算/缺测模式完全相同”的校准数和经验尾比。它们沿用已经冻结的标尺。严格 PSNR 窗口的敏感性分析只保留两套 PSNR 都相差 ≤0.1 dB 的目标和校准资产。样本数为零时留空，样本很少时尾比的步长会很大。`[verified: statistical-screen.csv 的 n_cal_same_size、n_cal_same_metric_pattern、n_cal_within_0p1；calibrate.py 的 outputs]`

## 怎样解释这一轮的名单

**按单张图同时筛 15 项后的 5% 经验尾部，50 张里有 4 张；再要求控制横跨 50 张图的多重比较时，Holm 0.05 没有一张通过。** 最极端的 0698 单图尾比为 1/109，跨 50 张后为 0.4587。高 PSNR 层有 108 张校准，最小可取尾比为 1/109；低层的最小步长为 1/31。参照样本的分辨率限制了多重比较结论的强度，实际输出更适合排人工复核顺序。个别组内稀有变化也可能在整图筛选中落到阈值之外。`[verified: statistical-screen.csv 的 p_any、p_any_holm50；calibrate.py 的 holm]` `[opinion]`

对于熟悉的白弧 0615，连续接缝和相位修正接缝都指向 B 变差，该家族尾比约 **0.038**；整图尾比是 **0.083**。蓝色光晕 0616 与灰环 0617 两个所选档位间的整图尾比分别为 **0.743、0.394**。这回答了「两个压缩版本之间有没有显得异常的变化」；两版都相对于原图受损的情形，需要另看固定 8×8 时相对于原图的绝对损伤。`[verified: statistical-screen.csv 的 615–617；family-tail.csv 的 615/block_seam]` [固定 8×8 的绝对损伤评估](fixed8-findings.md)

本次采用经验参考分布。正式的误报概率解释还需要新样本与参考目录近似可交换，尤其是尺寸、资产用途、预设及可测性相近。已知的三张图来自同一素材目录，并且白弧两档的 A、B 排序方向与常规选样相反；绝对值筛查对调换 A/B 不变，报告的变差方向按实际 A/B 标注。本实验没有据此估算美术误报率或准确率。`[verified: reference-selection.json；selection.json 的 protocol/known；calibrate.py 的 apply_scales、direction]` `[opinion]`
