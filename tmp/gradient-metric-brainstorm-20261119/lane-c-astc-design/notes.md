# Lane C：从 ASTC 表示机制出发设计渐变损伤指标

日期 2026-11-19。全部脚本与结果都在本目录，仓库其他位置只读。`[verified: 本目录文件列表]`

## 0. 结论先行

1. **这三张图在 8×8 fastest 下损坏，主因是“密权重网格＋极少权重级数”的块模式，与块尺寸本身无关。** 渐变块里多数采用 7×7（49 个）权重、只有 3 级的模式。0615 有 24/39 块是 3 级，0616 有 64/75，0617 有 28/52。同一张图换成 medium 后，权重级数中位数升到 10 级，网格降到约 20 个权重；exhaustive 升到 16–20 级，网格约 12–16 个权重。`[verified: mechanism.json counts / median_*]`
2. **按规范，一个线性坡在块内可以精确表示，前提是权重级数足够。** 双线性 infill 用 4:4 定点坐标在网格权重间插值（§23.18）。所以 2×3、3×3 这类小网格配 ≥10 级权重，就足够表示单调坡和轻度曲率。如果把 49 个权重压到 3 级（每个 trit 约 1.6 bit，约 79 bit，接近 96 bit 上限），7×7 网格的节点间距只有约 1.17 texel，infill 来不及抹平，块内就变成约 3 个平台，相邻块之间再出现跳变。这正是“平台＋跳变”。`[verified: Khronos DF 1.3 §23.18、§23.24；astc_modes.py ise_bits；推断：平台形成过程]`
3. **0615 的问题块另有一个透明度机制。** 原生块（行 4、列 7，对应显示坐标 x=56..63、y=88..95）采用 7×6 网格、4 级权重、CEM 4（LDR 亮度＋Alpha 单平面），端点 96 级。原图 Alpha 在 x=56 这一列为 9→53，解码后 8 个像素都是 13；整块解码 Alpha 只有 1–13，原图为 0–53。块内 RGB 是 Alpha≈0 处不可见的 239–254 噪声，每通道标准差 12.4，与 Alpha 的 12.6 相当。CEM 4 让亮度和 Alpha 共用一组权重；亮度复制到 R、G、B 三个通道，如果三者等权，误差就按 3 份计入。因此共享权重去拟合不可见的亮度噪声、牺牲 Alpha 坡度，是与观测一致的解释。`[verified: mechanism.json 0615_block_x56_y88；Khronos Table 149 CEM 4；推断：通道权重未从 DLL 核实]`
4. **这个透明度竞争因子不能单独做通用风险预测。** 在 6 张透明图共 786 个块上，竞争因子 1−corr² 与块误差的 Spearman ρ 为 −0.023，乘积版 A1 为 0.214。可见 Alpha 坡幅本身的 ρ 为 0.862。`[verified: a1-block-check.json]`
5. **0617 的问题不只出在搜索档位。** 它的 CEM 10 / 12 需要 6 / 8 个端点值，端点只剩中位数 40 级，部分块只有 16–24 级。改用 medium 后，低级数块占比仍有 64%，B2 也只从 12.1 降到 9.6。端点精度和 Alpha 是另一条独立的成因。`[verified: mechanism.json 617 counts；mode-choice.json 617；prototype-results.csv 617 medium]`
6. **fastest 的低级数选择基本是默认行为，并不由内容触发。** 在 16 张图的 701 个渐变块中，85% 的块权重 ≤4 级。按坡幅四分位从低到高，占比依次为 100%、98.9%、89.2%、52.8%；坡越大的块反而越常换到更高级数。可预测损伤的量是“块内可见坡幅 ÷ (实际级数−1)”，噪声多少不能预测这一选择。`[verified: mode-choice.json pooled]`

## 1. 来源与定位

| 来源 | 定位 | 用到的事实 |
|---|---|---|
| Khronos Data Format 1.3 | https://registry.khronos.org/DataFormat/specs/1.3/dataformat.1.3.html §23.18 Weight Infill | Ds=⌊(1024+⌊B/2⌋)/(B−1)⌋；gs=(cs·(W−1)+32)>>6；js=gs>>4，fs=gs&15；2D 双线性插值 |
| 同上 | §23.24 Illegal Encodings | 权重总数不得超过 64；权重 ISE 位数须在 24–96 bit 之间；网格不得大于块 |
| 同上 | §23.13 末段 | 端点量化范围取能放入剩余 bit 的最大值，迭代算法见原文 |
| 同上 | Table 149–152 | CEM 4 为 LDR 亮度＋Alpha direct，6 为 RGB base+scale，10 为 RGB base+scale plus two A，12 为 RGBA direct；多分区 CEM 的位布局 |
| 同上 | §23.20 | 双平面模式下由一个分量使用第二组权重 |
| astcenc main | downloads/astcenc_block_sizes.cpp L36–L140 | decode_block_mode_2d，已移植到 astc_modes.py |
| astcenc main | downloads/astcenc_preset_configs.h preset_configs_low | 64 texel 及以上的块：fastest 为 block_mode_limit 40、candidate_limit 2、partition_count_limit 2；medium 为 77 / 3 / 3 |
| astcenc main | downloads/astcenc_entry.cpp L495–L510 | texels≥64 → preset_configs_low |
| 引擎 | E:/hamster_unity/.../ASTCCompressor.cpp L412–L415 | 编码调用第三方 DLL（`Astc3rdCompressOptimize`），其 astcenc 版本与通道权重**未核实** |
| 本地 | tmp/multimetric-review-20261118/population/fixed8_manifest.json | 原生参考 PNG、解码 PNG 与 .astc 的路径 |

网格相位：原生 PNG 与展示图同向（0615/0617 合成后最大差 0.50 码值，0616 为 0）。.astc 第 j 行块对应显示行 [H−(j+1)b, H−jb)。void-extent 常色块按这一映射全部匹配，分别为 71/71、88/88、93/93。`[verified: 本次命令输出；mechanism.json orientation_void_matches]`

## 2. 指标定义与原型数值

公共设定：渐变掩膜沿用 probe.py 的 Lab 平面拟合（7/15 窗、R²≥0.85、跨度≥2）。块按真实原生网格划分，掩膜占块面积 ≥50% 的块计为渐变块。L* 由展示图计算，深灰底取 sRGB 64。JND 暂定 3 L*，是未校准的工程单位。`[verified: common.py、prototypes.py]`

- **B1 块内色阶塌缩率**：渐变块中，若 L* 拟合坡幅 ≥4，且 1−N_dec/N_ref ≥0.5（N 为取整 L* 的不同值个数；N_ref<4 时记 0），就计为塌缩块。取塌缩块占渐变块的比例；没有渐变块时为空。
- **B2 块内坡度丢失**：对每个块的参考 L* 和解码 L* 各拟合一个平面，保留率 k=(s_dec·s_ref)/|s_ref|²，丢失量 F=max(0,1−k)×参考坡幅。报告 P90，以及 F≥JND 的块占比。
- **B3 台阶集中度（不依赖网格）**：沿行和列取 16 px 窗、步长 4。要求整窗都在掩膜内，参考 L* 单调（|Σd|≥0.8·TV），且 TV≥4。集中度 c=max|d|/Σ|d|，段分为 (c_dec−c_ref)+×TV_ref，取 P95。
- **B4 轴向集中漂移**：在掩膜内用 Sobel 算梯度，按幅值加权，统计方向角模 90° 后落在 0°±11.25° 内的能量占比，取解码减参考。
- **A1 透明度竞争（只看原图）**：对 Alpha 跨度 ≥8 的块，在存储 RGBA 上做 PCA，取 Alpha 与第一主轴得分的相关系数平方 corr²；可见 Alpha 坡幅 vis 为块均色在 α_min 和 α_max 时合成到深灰底的 L* 差。块分 =(1−corr²)·vis。
- **A2 预期块内台阶（只看原图）**：渐变块的 L* 平面坡幅 A_b，按 q_eff=3 估算台阶 A_b/2；统计台阶 ≥JND 的块。
- **E1 码流预测台阶（编码器侧）**：A_b/(该块实际权重级数−1)，权重级数从 .astc 块模式读出；void-extent 块记 256 级。报告 P90 和台阶 ≥JND 的块占比。

prototype-results.csv（8×8 fastest，除另注外）：

| id | 组 | 连续接缝 | B1 | B2 P90 | B2 面积 | B3 P95 | B4 | A1 max | A2 台阶块 | E1 P90 |
|---|---|---|---|---|---|---|---|---|---|---|
| 615 | 正例 | 15.7 | 0.462 | 5.30 | 0.385 | 11.4 | 0.095 | 59.4 | 39/39 | 21.5 |
| 616 | 正例 | 12.9 | 0.122 | 2.15 | 0.041 | 5.67 | 0.037 | – | 64/75 | 10.6 |
| 617 | 正例 | 10.7 | 0.481 | 12.1 | 0.442 | 9.93 | 0.100 | 16.7 | 41/52 | 33.1 |
| 630 | 对照（Ring，接缝低） | 1.65 | 0.308 | 6.02 | 0.769 | 6.97 | 0.063 | 36.2 | 13/13 | 23.7 |
| 602 | 对照（Ring，接缝高） | 12.6 | 0.275 | 4.11 | 0.176 | 6.95 | 0.094 | 30.0 | 100/131 | 16.1 |
| 790 | 对照（场景灯光） | 24.6 | 0.099 | 1.36 | 0 | 4.37 | −0.087 | – | 108/133 | 10.8 |
| 207 | 对照（角色 jpg） | 1.77 | 0.014 | 1.60 | 0 | 3.55 | 0.079 | – | 43/73 | 6.9 |
| 580 / 608 / 384 | 对照 | ≤1.8 | 0 | ≤1.6 | 0 | ≤2.8 | ≤0.041 | – | 37 / 15 / 11 | 8.1 / 7.7 / 12.9 |
| 363 | 对照（透明） | 0.89 | 0 | 1.39 | 0 | 1.98 | 0.005 | 7.5 | 13/13 | 25.2 |
| 867 / 449 / 350 | 对照 | ≤13.6 | ≤0.036 | ≤0.92 | 0 | ≤0.90 | – | ≤2.5 | ≤13 | ≤4.7 |
| 16 / 62 | 对照（无渐变块） | 空 | 空 | 空 | 空 | 空 | – | – | 0 | 空 |

上表各行数值见 prototype-results.csv 与 bitstream-step.json。`[verified]`

块尺寸与档位的单调性（0615）：B3 在 4×4、6×6、8×8、12×12 下依次为 1.73、6.03、11.4、25.4；B2 面积依次为 0.133、0.147、0.385、0.706。8×8 medium 的 B3 为 7.0，exhaustive 为 5.6。0616 的 B3 依次为 1.02、2.70、5.67、8.24，medium 为 1.84，exhaustive 为 0.40。E1 P90 在 0615 上从 fastest 的 21.5 降到 medium 的 8.75、6×6 fastest 的 7.44；0616 为 10.6、3.21、5.74。`[verified: prototype-results.csv；bitstream-step.json]`

**解读。** 在 16 张图中，B1 与 B3 都把正例排在第 1、2、5 位；排在 616 前面的是 630 和 602，均来自 Ring 素材族，目前没有人工标签，属于误报还是漏报未知。B4 把 616 排到第 9 位，判别力弱。现有连续接缝分在这批图里的排名为 2、4、6，但对照中有一部分本来就是按接缝分挑选的，这个比较有偏。`[verified: 上表；推断：判别力]`

## 3. 探针命令

```
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python mechanism.py     # 块模式统计、网格相位、0615 问题块
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python prototypes.py    # B1–B4、A1、A2 → prototype-results.csv
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python mode_choice.py   # fastest 低级数选择与块特征 → mode-choice.json
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python a1_block_check.py # A1 块级消融 → a1-block-check.json
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python bitstream_step.py # E1 → bitstream-step.json
```

## 4. 限制

- 只有 3 张正例，且来自同一 Ring 目录。所有阈值（JND 3 L*、≥50% 掩膜、B1 的 0.5）都是在看过这三张图之后定的，存在循环风险。
- 第三方 DLL 的 astcenc 版本、通道权重和 Alpha 加权标志都未核实；preset 表取自 astcenc 当前 main 分支。
- B 系列只用 L*。0616 的损伤可能在色度上：CEM 6 base+scale 的颜色线必须经过黑点，这一点未测，是下一步要试的变体（改用 ΔE 或 a*b*）。
- 4×4 没有原生 .astc（只有展示 PNG），所以 E1 / mode 统计不覆盖 4×4。
- 原定检索 Khronos 规范之外的文献，但本 lane 时间预算内没有展开，相关文献交给 Lane A。
