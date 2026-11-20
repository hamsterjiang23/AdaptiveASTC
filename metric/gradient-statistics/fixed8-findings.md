# 高 PSNR 的单个压缩版本能否筛出三张已知问题图

如果两个压缩档位都损失了同一段渐变，比较 A 与 B 时变化可以很小。因此单独测量了**原图相对固定 8×8 fastest 的绝对误差**。在有共同指标的 442 张高 PSNR 贴图里，要求三个信号中至少两个相对同尺寸层的其他素材目录偏高，白色渐隐弧、蓝色光晕与灰色圆环落在**同分的第 23 至 26 位**。这三个已知样本以资产 ID 打破并列后分别为 24、25、26。它们同属一个素材目录，三个样本命中不等于三类素材都已经独立验证。`[verified: fixed8-summary.json 的 protocol、known、metrics.two_tail；fixed8-absolute.csv 的 group、two_tail_tie_start/end]` `[opinion]`

[看三张已知图和三个新增候选的同坐标放大](fixed8-examples.png) · [560 张高 PSNR 图的完整队列与缺测](fixed8-absolute.csv) · [排序和分母记录](fixed8-summary.json)

| 已知图，固定 8×8 fastest | 原生 / 展示 RGB PSNR（dB） | 块边界额外跳变 P95 | 扣除错位网格后的接缝分 | FLIP P99 | 最强接缝位置 |
|---|---:|---:|---:|---:|---|
| 0615 白色渐隐弧 | 36.99 / 34.16 | 9.53 | 13.03 | 0.179 | (56, 92) `[verified: fixed8-summary.json 的 known[id=615]]` |
| 0616 蓝色光晕 | 36.88 / 36.88 | 8.24 | 11.16 | 0.242 | (84, 88) `[verified: fixed8-summary.json 的 known[id=616]]` |
| 0617 灰色圆环 | 36.45 / 34.64 | 9.54 | 10.44 | 0.212 | (112, 76) `[verified: fixed8-summary.json 的 known[id=617]]` |

**为什么三张都在“高 PSNR”里？** 这里按项目的 Unity 原生 PSNR ≥35 dB 入选。白弧和灰环在深灰背景合成后的展示 RGB PSNR 实为 34.16、34.64 dB。若将“高 PSNR”改为同时要求两种 PSNR 都过 35 dB，这三张中仅蓝色光晕会进入队列。`[verified: fixed8-summary.json 的 known.native_psnr、display_psnr]`

## 怎么排序

1. 从开发集 938 张颜色图中保留 560 张达到原生 PSNR 门槛的资产。额外跳变 P95 可用于 506 张，扣除错位网格的接缝分可用于 442 张，FLIP P99 可用于 560 张。公平比较使用三项都有值的 442 张，另 118 张在 CSV 保留空排名。`[verified: fixed8-summary.json 的 all_colors、high_psnr、raw_nonmissing、common_valid]`
2. 按原生图像面积分为 ≤128²、128² 至 512²、>512² 三层，三项齐全数分别为 101、272、69。计算某张图的每项分数时，只拿同层且不在同一直接素材目录的图作为参照。每个信号的上尾比例取（参照中分数大于或等于当前值的图数 + 1）/（参照数 + 1）。三张已知图各有 61 张、31 个其他目录的参照。`[verified: fixed8_absolute.py 的 scores、size_group；fixed8-summary.json 的 by_area、known.ref_n、known.ref_directories]`
3. 三项上尾比例从小到大排，**第二个**用作两项共同突出的复核优先级；也额外记录了只看最突出一项的队列。两项可以有相关性，这个优先级只用于安排看图顺序，**8.06% 不代表出错概率或多重检验校正后的 p 值**。`[verified: fixed8_absolute.py 的 scores；fixed8-summary.json 的 protocol、metrics]` `[opinion]`

| 同一批 442 张，审查前 45 张（前 10% 向上取整） | 在三个已知样本中命中 | 解释 |
|---|---:|---|
| 原生 PSNR 从低到高 | 0/3 | 三张已越过原生门槛，单独用 PSNR 难以优先看到。`[verified: fixed8-summary.json 的 metrics.native_psnr.budgets]` |
| 原始 FLIP P99 从高到低 | 2/3 | 命中蓝晕及灰环。`[verified: metrics.flip_p99.budgets]` |
| 原始扣错位接缝分从高到低 | 1/3 | 命中白弧。`[verified: metrics.phase_adjusted.budgets]` |
| 原始块边界额外跳变 P95 从高到低 | 3/3 | 简单的单指标也能找齐这三张。`[verified: metrics.grid_excess_p95.budgets]` |
| 分层后只看最突出的一个信号 | 2/3 | 前 45 个名额内命中蓝晕及灰环。`[verified: metrics.any_tail.budgets]` |
| 分层后至少两个信号共同突出 | 3/3 | 队列前三个不同目录新候选为 0003、0165、0563；这些素材没有新增人工好坏标签。`[verified: metrics.two_tail.budgets；fixed8-absolute.csv 的 rank_two_tail；fixed8-examples.png]` |

## 为什么还要保留这个队列

50 图配对样本里的 **0615**，A、B 相对原图的最强平台分分别为 **378、378**，原图自比是 **0**，所以只看两档的分差会得到 0。**0616** 在 thorough/exhaustive 中的接缝分仅 **3.62 → 3.23**，用户截图中实际显示的 fastest 为 **11.16**。**0617** 在这两档的等亮轮廓径向误差 P95 分别为 **1.331、1.304 px**，二者只差 **0.027 px**；两版仍各自相对原图发生了位移。这三个例子说明：判断某一档的交付风险，要保留它对原图的绝对分。判断改变编码配置带来什么变化，再看 A、B 之间的差值。`[verified: fixed8-summary.json 的 comparison50 与 known；原样本对照图 fixed8-examples.png]` `[opinion]`
