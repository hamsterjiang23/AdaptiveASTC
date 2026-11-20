# 用多项指标筛查 PSNR 接近、渐变却被压坏的贴图

**最值得先看的是新样本 0698。** 两个真实 8×8 候选的 Unity PSNR 只差 **0.107 dB**，展示 RGB PSNR 只差 **0.147 dB**。平台分却从 **385 降到 60**。按其他素材目录的正常波动校准，这对候选的联合尾比是 **0.92%**。它的原图也确实有大片连续渐变，最大连通区占全图 **6.63%**，大于 102 张同尺寸参考图中 **90.2%** 的对应区域。`[verified: statistical-screen.csv 与 gradient-candidates.csv 的 0698；上轮 0698-profile.json]` `[opinion]`

[打开统计复核页，筛选、排序后点击图片编号](review.html) · [50 张逐图结果，附原图渐变面积](gradient-candidates.csv) · [看 0698 同一位置的原图和两个版本](../gradient-screen-50/0698-platform.png)

## 怎么定义“明显”

1. **先限制 PSNR。** 每张原图配两个不同的真实 8×8 解码版本 A、B。A 与 B 都用这张原图计算 PSNR，要求 Unity 原生和展示 RGB 两种 PSNR 的 A/B 差都 ≤0.5 dB，另报双差 ≤0.1 dB 的结果。原图自比有无穷大或实现规定的满分，所以使用两个压缩候选可以检验 PSNR 几乎不动时其他分数能否区分质量变化。`[verified: reference_selection.py 的 choices；calibrate.py 的 inputs、Asset.strict]`
2. **用其他资产给变化量定标。** 除了原有 50 张复核图，又实测了同一开发验证集中 368 张、277 个不同素材目录的配对，排除了复核样本所在的 48 个目录。每个参考目录取一个代表，139 个目录用于估计每项指标的通常变化幅度，余下 138 个目录用于校准筛选结果。原有 45 个字段里预先选了能在较多图上计算、可解释的 15 项，覆盖块边界、渐变台阶、亮度色带、局部误差、整体结构。选用每项自身的尺度，面积百分点、Lab 色差、PSNR dB 各自比较。`[verified: reference-checks.json、reference-partition.csv、calibration-method.md 的五类指标、fit-scales.csv]`
3. **给“挑出最突出的一项”定标。** 每张图都按同样规则计算 15 项里的最大标准化变化，再与校准图的最大变化比。这里的“联合尾比”是（至少同样极端的校准图数＋1）/（相同 PSNR 层的校准图数＋1），越小越值得看。两版原生 PSNR 都 ≥35 dB 的层有 108 张校准图，其余层有 30 张。每个异常另保留原分数与 B−A 的方向，可看是 A 的平台更重，还是 B 的块边更重。不同类别、不同方向的变化不会相互抵消。`[verified: calibrate.py 的 fit_scales、apply_scales、tail、outputs]`
4. **辨别你想要的素材。** 在优先候选中再看原图最大连续渐变区占全图的比例，并与同尺寸、不同目录的参考图比较。该值只来自原图。这样可区分大片光晕上的渐变退化与一根细线的变化；这一步用于整理候选，沿用上轮的渐变掩膜，无需添加一个通用面积阈值。`[verified: gradient_candidates.py 的 main；gradient-candidates.csv 的 original_largest_gradient_component_pct]` `[opinion]`

图中横轴是两种 PSNR 绝对差中的较大值，虚线为 0.1 dB，纵轴是每项指标在同一对候选上的绝对差。灰点是参考目录代表，蓝点是待复核面板，缺测值省略。三幅图的纵轴使用各自单位。`[verified: plot_changes.py 的 main；reference.csv、reference-banding.csv]`

![近似相同 PSNR 下，渐变平台、块接缝和色带三类指标的变化](metric-changes.png)

## 50 张里优先出现了什么

单图联合尾比 ≤5% 的有 **4 张**，≤10% 的有 **11 张**。按“原图本来是否有大片连续渐变”核对，4 张里 **0698** 的最大连续渐变区为 **6.63%**，其余三张均不超过 **0.10%**。因此，对于寻找类似白弧、蓝色光晕的素材，单靠某个指标进入统计尾部仍会捞到一些细线和普通贴图。`[verified: statistical-screen.json 的 per_image_alpha_05、per_image_alpha_10；gradient-candidates.csv]` `[opinion]`

| 样本 | 两版 PSNR 差，Unity / 展示 | 触发项和方向 | 单图联合尾比 | 原图最大连续渐变区 |
|---|---:|---|---:|---:|
| [0698 蓝色渐变环境贴图](../gradient-screen-50/review.html#0698/a/platform) | 0.107 / 0.147 dB | 平台分 **385 → 60**。A 更重。同一位置的同亮平台从 8 像素缩到 4 像素。 | 0.92% | 6.630% `[verified: statistical-screen.csv、gradient-candidates.csv 的 0698；0698-profile.json]` |
| [0544 金色线条特效](../gradient-screen-50/review.html#0544/b/platform) | 0.278 / 0.344 dB | 平台分 **50 → 184**，B 更重。原图以细线为主，当前掩膜没有检测出满足条件的连续渐变区。 | 2.75% | 0% `[verified: 0544/ref-dark.png；individual-scores.csv、gradient-candidates.csv 的 0544]` |
| [0755 彩色图块](../gradient-screen-50/review.html#0755) | 0.498 / 0.498 dB | Wang 全参考近似色带分 **10.44 → 5.49**，A 更重。两版原生 PSNR 均低于 35 dB。只看同尺寸校准时仅有 4 张，尾比变为 20%。 | 3.23% | 0.037% `[verified: statistical-screen.csv、gradient-candidates.csv 的 0755]` |
| [0132 角色武器贴图](../gradient-screen-50/review.html#0132) | 0.474 / 0.474 dB | Wang **5.60 → 2.73**，CAMBI **1.83 → 1.45**，两项指向 A 的亮度色带更重。边界额外跳变 P95 **2.26 → 4.82**，局部块边则是 B 更重。 | 4.59% | 0.090% `[verified: family-tail.csv 的 132；individual-scores.csv、gradient-candidates.csv 的 0132]` |

保持 277 个目录代表不变，只改变标尺组和校准组的划分，重复 30 次，0698 和 0755 各 **30/30** 次进入单图 5% 名单，0132 为 **14/30**，0544 为 **8/30**。0755 对重分组稳定，但对是否限同尺寸敏感。30 次重分组使用同一份资产，表示名单的稳定性。`[verified: split-sensitivity.csv；statistical-screen.csv 的 n_cal_same_size、p_any_same_size]`

**技术上的显著性边界。** 对每张图同时看 15 项的机会已通过最大值校准。另对“从 50 张里再挑图”做 Holm 校正后，**没有一张通过 0.05**，最小校正值为 **0.459**。这也受样本量限制：最大的校准层只有 108 张，即使目标比分层内所有校准图都极端，平滑尾比也只能降到 1/109；对 50 张做 Holm 校正的第一道 0.001 门槛在本设计中无法达到。本表用于决定先审哪几张；数值不能解释成人眼认为某图不合格的概率。面板里有 16/50 张透明图、9/50 张特效目录图，138 张校准图中对应为 11 张和 5 张，特效域的人眼误报率尚未测量。`[verified: statistical-screen.json 的 holm_50_alpha_05；reference-population.json 的 target50、calibration]` `[opinion]`

## 三张原有图片怎样找回来

如果生产里只有**原图和一份解码图**，可以先保留项目原生 PSNR ≥35 dB 的素材；对每张原图与解码图测 **块边界额外跳变 P95、接缝分、FLIP P99**。按相近尺寸且其他目录的分布给三项分别排位，使用三项中第二突出的那项安排复核，意味着至少要有两种信号。938 张颜色图里有 560 张过原生 PSNR 门槛，442 张三项都有效。白弧、蓝光晕、灰圆环在 442 张中**并列第 23–26 名**；审前 45 张找到 **3/3**。同预算下，单用边界额外跳变 P95 也找到 **3/3**，按低 PSNR 排找到 **0/3**。三张都是先前已知的同目录样本。`[verified: fixed8-summary.json 的 common_valid、known、metrics；fixed8-absolute.csv]`

| 原有图片 | 统计上可筛的现象 | 本次该怎么读 |
|---|---|---|
| **0615 白色渐隐弧** | 透明度渐变出现平台和沿块边的断层 | 配对接缝组尾比 **3.81%**，综合 15 项后是 **8.26%**。A、B 的平台分都为 **378**，原图自比为 **0**。只看平台分差会漏掉已经存在的台阶。`[verified: family-tail.csv 的 615/block_seam；comparisons.json 的 615]` |
| **0616 蓝色光晕** | 发光渐变边缘或光核旁的方块、局部感知损伤 | 固定 fastest 的原生和展示 PSNR 都是 **36.88 dB**，接缝分 **11.16**。选作配对的 thorough/exhaustive 两档之间综合尾比 **74.3%**，说明这两档间的变化很常见。`[verified: fixed8-summary.json 的 616；statistical-screen.csv 的 616]` |
| **0617 灰色圆环** | 曲线附近的网格接缝、光环厚度或轮廓偏移 | 固定 fastest 的接缝分为 **10.44**。配对两档综合尾比 **39.4%**。原图圆心已知时，还能查轮廓位移；这两个版本各自对原图的 P95 位移为 **1.33、1.30 px**。其他轮廓需先定义可对应的位置。`[verified: fixed8-summary.json 的 617；comparisons.json 的 617；statistical-screen.csv 的 617]` `[opinion]` |

三张固定 fastest 的**原生 / 展示** PSNR 分别为 **36.99 / 34.16、36.88 / 36.88、36.45 / 34.64 dB**。如果业务改成两种 PSNR 都必须 ≥35 dB，三张中只有蓝色光晕入选。以上方法可筛“具有这些失真特征”的图，图案的美术类别和生产合格线仍需查看实图。`[verified: fixed8-summary.json 的 known；fixed8-findings.md]` `[opinion]` [看三张已知图与三个新候选的同坐标对照](fixed8-examples.png) · [560 张高 PSNR 复核队列](fixed8-absolute.csv)

## 如果“PSNR 没变化”要求更严

在原 50 对里，双差都 **≤0.1 dB** 的只有 **3 对**。在同样严格的校准子集中每图只有 **13 个参考**，平滑尾比最小只能到 1/14。这 3 对的联合尾比为 **0.429、0.571、1.000**，没有测出强异常。`[verified: statistical-screen.json 的 strict_0p1]`

另外枚举了原 697 张颜色图的全部 **6,970 对**真实档位组合，单独检查严格近零时的平台分。排除实际展示像素相同的输出后，双差都 **≤0.1 dB** 的有 **156 对 / 136 张**，平台绝对分差中位数 **0**、最大 **48**；双差都 **≤0.01 dB** 的有 **16 对 / 15 张**，中位数 **0**、最大 **16**。例如 **0331** 的 Unity PSNR 约 **47.318 → 47.322 dB**，平台分 **60 → 76**。两种已记录的 PSNR 都完全相等且像素确实不同的组合为 **0 对**。这个枚举是描述性检查，未与主分析合并计算尾比。`[verified: near-equal-summary.json 的 0.1、0.01、0；near-equal-pairs.csv 的 331]` [严格近零的全部配对](near-equal-pairs.csv)

**方法依据与明细。** 平滑尾比使用留出参考样本进行排序；形式上的错误率控制依赖待测和校准数据可交换等条件。本项目面板有刻意保留的已知问题图和素材构成差异，使用“经验尾比”描述开发集筛查结果。所有计算口径、空值、参考数和方向可逐项查验。`[verified: Bates 等，The Annals of Statistics 2023；calibration-method.md；reference-population.json]` [Bates 等原论文](https://doi.org/10.1214/22-AOS2244) · [统计方法](calibration-method.md) · [逐图分组](family-tail.csv) · [全部 750 条指标差](metric-tail.csv) · [30 次重分组稳定性](split-sensitivity.csv)
