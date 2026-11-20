# 50 张真实贴图：PSNR 接近时，哪些指标还能看出变化？

**最值得补看的是平台分。** 接缝分找的是沿 ASTC 网格连成线的突变，平台分找的是原先逐渐变亮或变暗的一段，被压成了几格同色、末尾又突然跳一级。新增样本 0698 上，两版 Unity PSNR 为 **42.42、42.52 dB**，接缝分为 **2.83、3.09**，但平台分从 **385 降到 60**。同坐标像素能解释为什么两项指标给了不同信号。`[verified: individual-scores.csv 的 0698；evidence/0698-profile.json 的 three_luma_profiles]` `[opinion]`

[打开 50 张离线图片对照](review.html) · [原图及 A、B 全部实测值 CSV](individual-scores.csv) · [逐图 B−A 差值 CSV](paired-changes.csv) · [各项指标的变化分布 CSV](metric-summary.csv) · [指标相关性 CSV](correlations.csv)

页面可按选中指标的绝对差或有符号差排序。鼠标滚轮在三列同步放大，可以选 A 或 B 的最强接缝、最强平台或最差 32×32 窗口，直接比较原图同一位置。图片已内嵌，单个 HTML 可以离线传阅。`[verified: review.html 的样本列表、定位控件和内嵌图像]`

## 先看一张：白弧的接缝和环境贴图的台阶是两种现象

![0698 原图与同一坐标的两种真实压缩结果、放大像素](0698-platform.png)

**0698 环境贴图。** 在同一条竖线上，原图九个亮度值是 **130、132、134、135、136、138、139、143、151**。A 版变成 **连续八个 134，然后 197**。B 版变成 **128、128、128、128、132、141、149、159、197**。所以这处平台从八像素缩到四像素，末端跳变从 **63 降到 38**，原图最后一步是 **8**。B 在这处恢复了部分过渡。报告的 **385、60** 是两个版本各自的全图最强平台分，B 的最高分另在一处。`[verified: evidence/0698-profile.json；evidence/special.json 的 698/a、698/b]` [打开 A 定位，三列同坐标查看](review.html#0698/a/platform)

**0615 白色渐隐弧。** A、B 的平台分同为 **378**，接缝分却从 **7.91 升至 13.03**。LPIPS 从 **0.10778 升到 0.11505**，普通 SSIM 从 **0.96313 降到 0.96213**，均显示整体保真度略降；FLIP P99 从 **0.18703 降到 0.17869**，SSIMULACRA2 从 **66.24 升到 66.87**，两者对这一对给出相反方向。看清这截竖向方块边时，局部坐标比整图分更容易解释。`[verified: individual-scores.csv 的 0615/fast、0615/fastest；comparisons.json 的 615.points]` `[opinion]` [打开白弧的接缝位置](review.html#0615/b/seam)

## 50 张怎样选

取开发验证集中原生 **128²、256²、512²** 的全部 697 张适用颜色图，固定 8×8，对五档编码搜索预设两两配对。以同一原图为参考，要求两候选的 **Unity PSNR 差和展示 RGB PSNR 差都 ≤0.5 dB**，并核实展示 RGB 像素确实不同。6,970 对里共有 **1,622 对、666 张资产**满足条件。`[verified: selection.json 的 counts、protocol]`

保留用户给的 3 张，另外 47 张按固定种子抽取，选样只用 PSNR、尺寸、资产组和候选身份。最终 **10 张 128²、20 张 256²、20 张 512²**，共 **48 个资产组**；25 对的两个 Unity PSNR 都 ≥35 dB，另外 25 对至少一个低于 35 dB。16 张需 Alpha 的图在线性光下合成深灰底再做展示图评价，其余 34 张直接评 RGB。三个原始样本的档位沿用前次配对；其余图优先取预设档位序号相距较大的合格组合。A/B 是档位身份，二者的好坏顺序需要看测量或图像。`[verified: selection.json 的 samples、protocol、counts；evidence/general.json 的 checks]`

每图给出原图、解码 A、解码 B 三列。双图指标始终以同一原图为参考，原图列是自比；CAMBI 单图、BBAND 及各版本渐变面积等单图量分别在三幅图上计算。**B−A** 表示同一指标在两种候选之间的有符号变化，面积差的单位为百分点。50 对中的双 PSNR 差均 ≤0.1 dB 的仅 **3 对**，本报告的总体数字采用 0.5 dB 范围。`[verified: comparisons.json 的 metrics、samples；paired-changes.csv 的 unity_psnr_db、view_psnr_db]`

## 除了接缝分，实际该对比什么

| 肉眼想检查什么 | 建议看的指标 | 这批图中的例子 |
|---|---|---|
| 渐变从光滑变成一段段平台 | **平台分、平台长度、末端亮度跳变** | 0698 的全图最强平台分 **385 → 60**，同一位置有可核对的 9 个像素。`[verified: evidence/0698-profile.json；individual-scores.csv 的 0698]` |
| 坏区是否变大、是否集中在渐变里 | **低局部 PSNR 面积、最差窗口、渐变区 FLIP P95** | 0954 的展示 PSNR 仅 **30.35 → 30.69 dB**，低于 28 dB 的面积从 **37.5% 缩至 25%**，渐变区 FLIP P95 从 **0.3131 降至 0.2732**。`[verified: individual-scores.csv 的 0954]` |
| 平滑过渡是否多出亮度色带 | **CAMBI 全参考、BBAND、Wang 色带分** | 0132 两个原生 PSNR 都超过 36 dB，CAMBI 新增色带分 **1.833 → 1.446**，Wang 参考匹配近似 **5.602 → 2.732**。两种算法能提供同向的色带线索。`[verified: individual-scores.csv 的 0132；banding.py 的 wang、cambi]` |
| 整体轮廓、结构或纹理保真度 | **SSIM、MS-SSIM、SSIMULACRA2、LPIPS、GMSD、FLIP** | 0875 的 SSIMULACRA2 **10.73 → 21.34**，是这 50 对里该分数变化最大的一张。两版 Unity PSNR 都很低，仅 **18.36、18.74 dB**，该例属于整体质量较差的组。`[verified: metric-summary.csv 的 ssimulacra2；individual-scores.csv 的 0875]` |
| 横竖方块边、透明度退化或圆环变形 | **块边界额外跳变 P95、PSNR-B、Alpha/RGB 交叉合成误差、圆环径向位移** | 0520 的边界 P95 从 **0 → 7.12**，但原图只有 **5 对有效边界像素**。0615 有 **527 对**。数值相同的情况下，前者要优先核对采样位置。径向位移仅对圆心已核实的 0617 计算。`[verified: evidence/mask-support.json 的 520、615；individual-scores.csv 的 0520、0617]` `[opinion]` |

## 各指标在 50 对中变化多少

下面给的是每图 **|B−A|** 的中位数和第 90 百分位。它们回答“同一项指标通常动多少、较大时动多少”。不同指标的单位和标度不同，不能直接用跨行数值大小判定谁更灵敏。所有 **45 项**的数值条件、方向、有效对数、最大变化及对应样本都在汇总表，含无实测值的 4 项。`[verified: metric-summary.csv 的 eligible_pairs、median_abs_delta、p90_abs_delta、max_abs_delta、max_id]` `[opinion]` [打开完整指标汇总](metric-summary.csv)

| 指标 | 有效对数 | 中位变化 | P90 变化 | 最大变化（样本） |
|---|---:|---:|---:|---|
| Unity PSNR，dB | 50 | 0.300 | 0.454 | 0.498（0755）`[verified: metric-summary.csv 的 unity_psnr_db]` |
| 最差局部 PSNR，dB | 50 | 0.213 | 0.588 | 1.385（0377）`[verified: worst_patch_psnr_db 行]` |
| SSIM | 50 | 0.00129 | 0.00337 | 0.01885（0875）`[verified: ssim 行]` |
| SSIMULACRA2 | 50 | 0.854 | 1.971 | 10.605（0875）`[verified: ssimulacra2 行]` |
| LPIPS-Alex | 50 | 0.00123 | 0.00302 | 0.00727（0615）`[verified: lpips_alex 行]` |
| FLIP P99 | 50 | 0.00462 | 0.01333 | 0.05525（0875）`[verified: flip_p99 行]` |
| 渐变区 FLIP P95 | 47 | 0.00383 | 0.01110 | 0.03990（0954）`[verified: masked_flip_p95 行]` |
| GMSD | 50 | 0.00113 | 0.00330 | 0.01763（0875）`[verified: gmsd 行]` |
| PSNR-B，dB | 50 | 0.261 | 0.556 | 1.355（0108）`[verified: psnrb_db 行]` |
| 平台分 | 50 | 12 | 92.2 | 325（0698）`[verified: platform_score 行]` |
| 块边界额外跳变 P95，Lab | 45 | 0.287 | 1.173 | 7.119（0520，5 对有效边界像素）`[verified: grid_excess_p95 行；evidence/mask-support.json 的 520]` |
| 扣除错位网格的接缝分，Lab | 39 | 0.392 | 3.781 | 6.151（0261）`[verified: phase_adjusted 行]` |
| CAMBI 全参考 | 40 | 0.0386 | 0.1331 | 0.3868（0132）`[verified: cambi_fr 行]` |
| BBAND | 44 | 0.0219 | 0.1280 | 0.5562（0617）`[verified: bband 行]` |
| Wang 色带分，参考匹配近似 | 50 | 0.00345 | 0.6983 | 4.9442（0755）`[verified: wang_fr 行]` |

## 哪些指标和 PSNR 一起变化

每张图只贡献一次 **B−A**，分别计算 Pearson 和 Spearman。以 Unity PSNR 的变化为参照，SSIM 的 Spearman 为 **+0.673**（50 对），LPIPS 为 **−0.482**（50 对），新接缝分为 **−0.202**（39 对），平台分为 **−0.091**（50 对），CAMBI 全参考为 **+0.022**（40 对）。SSIM 高分更好，LPIPS、接缝及色带分低分更好。这里已把 PSNR 的变化限制在 0.5 dB 以内，数值反映这个子集内的共同变化。此轮没有对 50 对做独立视觉盲评，不能据此判断哪个指标最准。`[verified: correlations.csv 的 anchor=unity_psnr_db；selection.json 的 protocol]` `[opinion]`

## 缺测和实现口径

- **CAMBI、BBAND、渐变区分数。** CAMBI 用 libvmaf 全参考模式实跑 40 张 256²/512² 的原图和候选，10 张 128² 低于该实现的尺寸条件。BBAND 用作者单帧实现及与 MATLAB 基准核对的边界处理，在 150 个视图上运行，136 个有有效数值，44 对的 A、B 都有效。缺少原图渐变像素、真实块边界或完整八相位支持时，对应渐变指标留空。可查看逐图有效像素数。`[verified: evidence/banding.json、evidence/special-checks.json、evidence/mask-support.json]` [区域和边界像素数](evidence/mask-support.json)
- **Wang 色带分。** 项目按原论文的大均匀连通区、弱边界对比、11×11 邻域、边缘一致性和对角线归一化计算。实现按较亮侧像素及相邻区域计数，参考匹配用 11×11 范围内是否存在一致性差小于 0.2 的边界；这是项目对论文细节的近似。受控八条色带例复现 **0 → 12.52**，全部原图自比的全参考分为 0。此处没有作者自然图逐图黄金值。`[verified: banding.py 的 edge_pixels、wang、smoke；evidence/banding.json]` [Wang 等原论文 §3–4](https://storage.googleapis.com/gweb-research2023-media/pubtools/5794.pdf)
- **PIM、Denes 和法线角度。** PIM-1/PIM-5 的官方下载地址本轮均返回 HTTP 403，未填替代数值。Denes 的检出概率依赖实际显示亮度、观看尺度和色坡参数，本批没有这些标定。50 张样本均为颜色展示图，法线平均和 P95 角误差不适用。这 4 行在 CSV 和页面保留空值和说明。`[verified: 本轮 PIM-1/PIM-5 HTTP 返回 403；comparisons.json 的 metrics；selection.json 的 protocol]` [PIM 作者模型入口](https://github.com/google-research/perceptual-quality) · [Denes 等的显示条件模型](https://www.cl.cam.ac.uk/~rkm38/pdfs/denes2019banding_model.pdf)
- **字节与时间。** 两版使用相同的尺寸、8×8 足迹及 mip0，所以 50 对的 ASTC 载荷差都为 0。归档的编码与解码毫秒数单列，供判断搜索档位成本。每份 ASTC 和解码 PNG 都留有哈希。`[verified: storage-timing.csv 的 astc_payload_bytes、encode_ms、decode_ms、astc_sha256、decoded_native_png_sha256]` [原始编码记录](storage-timing.csv)

**复核。** 100 个真实候选各有 12 项复算指标与归档逐项一致，最大绝对差 0。专项检查核对了 150 张视图的文件身份及原图自比。可从随文证据重建整表：在项目根目录运行 `uv run --no-sync python metric/gradient-screen-50/assemble.py`。`[verified: evidence/general.json 的 checks；evidence/special-checks.json；assemble.py 的 main]`
