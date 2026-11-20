# PSNR 接近时，怎样筛出渐变上的 ASTC 方块

**如果专查 PSNR 已达标的漏网图，建议先按「块边界额外跳变 P95」排，再用本次提出的「渐变区块边界接缝分」定位横线或竖线。** 在你发的白色渐隐弧上，两次真实 8×8 压缩的 Unity PSNR 只差 **0.31 dB**，新接缝分从 **7.91 升到 13.03**。在另一张项目贴图上，两版 PSNR 都高于 38 dB，新分数从 **0.64 升到 8.92**。两种指标都需要原图和解码图。`[verified: same-asset-pairs.csv 的 0615 fast/fastest、0228 exhaustive/medium；phase-summary.json 的 subsets/native_psnr_ge35]` `[opinion]`

[打开离线图片对照，可滚轮同步放大](review.html) · [打开 PSNR ≥35 dB 的 P95 初筛队列](high-psnr-by-boundary-p95.csv) · [按新接缝分排序](review-queue.csv) · [查看 1,960 对真实压缩](same-asset-pairs.csv)

![白色渐隐弧在两个真实8×8候选下的整图和同一坐标局部](0615-same-asset.png)

## 分数具体在抓什么

在一张白雾或光晕上，原图通常是逐像素变亮、变暗。压缩后，如果恰好在 8×8 的块边界上突然跳了一下，而且相邻几行都在同一处跳，人眼会看到一截横线或竖线。本实验提出的分数越高，表示这类**沿真实块边界持续出现的额外跳变**越突出。输入是原图、实际解码图和块尺寸，使用原生像素坐标。只有未压缩的原图时，可以先用渐变面积和最大连续渐变区筛素材。`[verified: seam_metric.py 的 gradient_mask、evaluate；phase_screen.py 的 phase_peaks、phase_score]` `[opinion]` [原图渐变检测的计算方式](../README.md)

1. **圈出渐变。** 透明贴图先在线性光下合成到固定深灰底，不需要 Alpha 的图直接取 RGB。转到 CIELAB，在原图 7×7 和 15×15 窗口拟合颜色平面，保留变化连续且有足够色差的位置，后续所有候选都用这张原图的掩膜。`[verified: seam_metric.py 的 lab、gradient_mask；run_screen.py 的 inputs；项目 prepare.py 的 table、picture]`
2. **找连续的接缝。** 计算相邻像素颜色跳变相对原图增加了多少，再扣掉两侧紧邻位置的平均新增跳变。沿同一块边取连续 4 个像素，用四个值中的最小值代表这一段，取全图最强的一段及其起点。这样，一个孤立亮点无法单独把分数推高。`[verified: seam_metric.py 的 evaluate；phase_screen.py 的 phase_peaks、check]`
3. **扣掉普通位置也会出现的跳变。** 把网格按原生坐标分别错开 1 至 7 个像素，每次用相同办法找到最强的一段。**最终分数 = max(0，真实网格最强接缝 − 七个错位网格最强接缝的中位数)**。例如白弧 8×8 fastest，真实网格是 **15.71**，错位中位数 **2.68**，最终 **13.03**。任何一个相位缺乏有效像素时记为空值。`[verified: phase_screen.py 的 phase_peaks、phase_score；equal-psnr-controls.json 的资产 615 / astc]`

**P95 初筛**复用第 2 步得到的单个边界像素的额外跳变，在全部有效真实块边界上取第 95 百分位。它衡量一张图里较坏的一批边界有多突兀。新接缝分额外考察这些跳变能否连成线，以及在真实网格上是否更明显。前者适合按整张图排复核顺序，后者能指到一截具体接缝。`[verified: seam_metric.py 的 evaluate；phase_screen.py 的 phase_peaks；phase-summary.json 的 subsets/native_psnr_ge35]` `[opinion]`

## 实验一 · 同一张图，两个真实压缩版本

从开发验证集取全部 **196 张 128×128 颜色图**。固定块尺寸 8×8，每图五个编码搜索档位，两两配对得到 **980 个候选、1,960 对**。把“PSNR 接近”定义为两个候选分别相对于同一原图计算时，**Unity 原生 PSNR 和实际展示 RGB PSNR 的差都 ≤0.5 dB**。同时报告更严的 0.1 dB 筛法。原图自比会得到数学上的无穷大或实现规定的满分，因此真实配对比较的是两份候选。`[verified: same-asset-summary.json 的 0.1、0.5；same-asset-pairs.csv 的 psnr_a/b、display_psnr_a/b]`

| 同图两个真实候选 | Unity PSNR（dB） | 展示 RGB PSNR（dB） | 新接缝分 | 高分候选中发生了什么 |
|---|---:|---:|---:|---|
| **0615 白色渐隐弧**，fast → fastest | 37.30 → 36.99 | 34.40 → 34.16 | **7.91 → 13.03** | 同一位置 (56,92) 的竖向接缝强度由 10.09 升至 15.71。`[verified: same-asset-pairs.csv 的 615 fastest/fast]` |
| **0228 角色贴图的紫色渐变**，exhaustive → medium | 39.20 → 38.73 | 39.20 → 38.73 | **0.64 → 8.92** | 在 (120,56)，水平接缝强度从 0 升至 9.69。这是两版原生 PSNR 均 ≥35 dB 的合格配对里分差最大的一对。`[verified: same-asset-summary.json 的 0.5/unique_asset_top_five_native_both_35]` |
| **0586 环形特效**，medium → thorough | 29.40 → 29.72 | 30.01 → 30.35 | **4.09 → 12.65** | 两个 PSNR 都提高，(117,64) 的水平接缝仍从 5.63 升至 13.18。这是双 PSNR 差 ≤0.5 dB 下所有有效配对的最大分差。`[verified: same-asset-summary.json 的 0.5/unique_asset_top_five]` |
| **0602 环形特效**，fastest → fast | 43.270 → 43.291 | 36.656 → 36.660 | **10.07 → 11.58** | 在双 PSNR 差 ≤0.1 dB、两版原生 PSNR 均 ≥35 dB 的子集中，测到的最大分差为 1.51。`[verified: same-asset-summary.json 的 0.1/unique_asset_top_five_native_both_35]` |

![0228 紫色渐变两个候选，各列下方为同一坐标的六倍放大](0228-same-asset.png)

双 PSNR 差 ≤0.5 dB 的有 **471 对**，其中两端都能算出新分的有 **258 对、123 张图**。这 258 对的绝对分差中位数为 **0.43**，P95 为 **4.21**，分差 ≥5 的有 **8 对、6 张图**。收紧至 0.1 dB 后有 **46 对**符合 PSNR 条件，其中 **19 对**能算新分，最大分差 **2.42**。已知蓝色光晕和灰色圆环在 0.5 dB 配对里最大的分差也只有约 **0.39、1.27**。可见的大跳是配对分布里的少数样本。`[verified: same-asset-summary.json 的 0.1、0.5 及 examples_known；same-asset-pairs.csv 的 delta_phase_adjusted]`

## 实验二 · 使两张失真图的 PSNR 精确相同

对你发的三张图，各取真实的 **8×8 fastest**。把“解码像素减原图像素”的 RGB 误差向量在相似亮度、同属渐变区或同属非渐变区的像素之间随机交换，只接受交换后仍在 8 位合法范围内的配对。每图用 **32 个固定种子**得到人工对照。逐通道核对了整图和原图渐变区内的误差平方和，**96 个对照全部与各自的真实 ASTC 相等**。因此每行的真实图与随机图展示 RGB PSNR 完全相同。`[verified: equal-sse-checks.json 的 control、seeds、sse_checks、assets；equal-psnr-controls.json 的 assets]`

| 原图 → 真实 8×8 | 相同的展示 RGB PSNR | 原图自比的新分 | 真实 ASTC 的新分 | 32 次打散的新分，中位数［最小，最大］ |
|---|---:|---:|---:|---:|
| 0615 白色渐隐弧 | 34.15998 dB | 0 | **13.03** | **0.00**［0，2.89］ `[verified: equal-psnr-controls.json 的 615]` |
| 0616 蓝色光晕 | 36.88420 dB | 0 | **11.16** | **0.00**［0，2.29］ `[verified: equal-psnr-controls.json 的 616]` |
| 0617 灰色圆环 | 34.64322 dB | 0 | **10.44** | **0.06**［0，2.72］ `[verified: equal-psnr-controls.json 的 617]` |

三张真实压缩图都高于各自全部 32 个随机对照。作为对照指标，普通“渐变区梯度误差 P95”在三张图上都给**打散后的版本更高的误差分**。这个对照说明，新分能区分误差是否排成 ASTC 方块边；随机噪点是否更能被玩家接受，还需要美术或玩家评价。`[verified: equal-psnr-controls.json 的 distribution；equal-sse-checks.json 的 gradient_change_p95]` `[opinion]` [看三张原图、真实压缩和相同 PSNR 的随机对照](equal-psnr-controls.png)

## 实验三 · 能否真的把三张问题图筛到前面

在 **1,000 张开发验证图**中，取 **938 张适用的颜色贴图**，原生分辨率、固定 8×8 fastest。**712 张**八个网格相位都有足够的渐变像素，**226 张**缺测。下表中每种指标都对同一批可计算图像排序。三个名次按“白弧、蓝色光晕、灰色圆环”的顺序；复核数量按百分比向上取整。三张来自同一个 Ring 目录，是提出指标时已经看到的示例。`[verified: fixed8-validation.csv 的 615–617 资产路径；phase-summary.json 的 subsets、rank_method]`

| 筛查范围 | 新分排名 | 新分前 10% / 前 15% 命中 | 原连续接缝前 15% | FLIP P99 前 15% | 按低 PSNR 前 15% |
|---|---|---:|---:|---:|---:|
| 全尺寸，共 712 张可比 | **66 / 92 / 100** | **1/3 · 3/3** | 2/3 | 0/3 | 0/3 `[verified: phase-summary.json 的 subsets/all]` |
| 全尺寸，Unity PSNR ≥35 dB，共 442 张可比 | **34 / 50 / 53** | **1/3 · 3/3** | 2/3 | 3/3 | 0/3 `[verified: phase-summary.json 的 subsets/native_psnr_ge35]` |
| 与样例同为 128×128，共 133 张可比 | **9 / 12 / 13** | **3/3 · 3/3** | 3/3 | 0/3 | 0/3 `[verified: phase-summary.json 的 subsets/128x128]` |

如果只看 **PSNR ≥35 dB** 的资产，560 张中有 442 张可按新分排序，另 118 张保留空值。复核前 **67 张**时，新分和 FLIP P99 都包含三张已知问题图；预算只有 **45 张**时，新分包含 1 张，FLIP P99 包含 2 张。新分的用处是解释**方块在哪儿**，FLIP P99 可同时提示其他视觉差异。不能用这三张的命中数估计生产精确率、漏报率或自动选块阈值。`[verified: phase-summary.json 的 subsets/native_psnr_ge35；fixed8-validation.csv 的 seam_x、seam_y]` `[opinion]`

在上述**同一批 442 张、同样看前 45 张**的条件下，**块边界额外跳变 P95 找到 3/3**，白弧、蓝色光晕、灰色圆环依次排 **28、42、27**。单独使用 P95 时覆盖面更大，560 张高 PSNR 图中有 **506 张能算、54 张缺测**；这时三张排 **37、53、36**，看前 **53 张**才全部命中。因此面向“PSNR 已过线但渐变可能压坏”的工作流，优先交付了按 P95 排列、保留空值的初筛表。`[verified: phase-summary.json 的 subsets/native_psnr_ge35.metrics.grid_excess_p95；high-psnr-by-boundary-p95.csv 的 0615–0617]` `[opinion]`

## 怎么用这次结果

- **查真实素材。** [442 张复核队列](review-queue.csv) 只含原生 PSNR ≥35 且新分有效的贴图，按接缝分降序，带资产路径、分数、FLIP P99 和定位坐标。[图片对照](review.html)内嵌了 4 组真实同图配对、3 组严格同 PSNR 对照，以及按队列顺序抽取的 3 张待判新图。新图限制长边 ≤512 且目录不重复，便于先看不同素材。`[verified: review-queue.csv、review.html 的样本选择器]`
- **解释空值和低分。** 空值表示原图缺少足够可测的渐变区。低分表示真实块边界没有比错位网格突出很多。块内色带、斜向轮廓变化、均匀模糊仍可能可见。透明特效在游戏里的底色和混合方式可能与本实验的深灰合成不同；复核时用实际渲染条件更合适。`[verified: phase_screen.py 的 phase_score；run_screen.py 的 inputs]` `[opinion]`
- **区分高分与不合格。** 这里取全图最强接缝，大尺寸图有更多位置可供取最大值。表里同时列出同尺寸排名。若要定自动回退到较小块的门槛，值得从其他素材目录的高分、低分、空值都抽取少量盲评，记录哪些确实影响观感。`[verified: phase_screen.py 的 phase_peaks；phase-summary.json 的 subsets]` `[opinion]`

全量输入和指标见 [938 张逐图结果](phase-validation.csv)、[逐图定位与传统指标](fixed8-validation.csv)、[配对统计](same-asset-summary.json) 和 [96 个严格同 PSNR 对照](equal-psnr-controls.json)。从项目根目录可运行 `uv run --no-sync python metric/gradient-screen/run_screen.py` 与 `uv run --no-sync python metric/gradient-screen/phase_screen.py` 复算全量排序，两者都支持 `--smoke`。此处复用开发验证集已归档的真实编码与解码像素，统计仅涉及开发数据。`[verified: run_screen.py 的 MEDIA、inputs、main；phase_screen.py 的 main]`
