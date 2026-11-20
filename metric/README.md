# ASTC 贴图质量指标手册

[用多指标统计筛查 PSNR 接近的渐变失真](gradient-statistics/README.md) · [查看统计复核名单](gradient-statistics/review.html)。用不同素材目录建立参考分布，报告异常集中在哪项指标、原图的连续渐变占多大面积，以及三张原始样例在固定 8×8 队列中的位置。`[verified: gradient-statistics/statistical-screen.json、gradient-candidates.csv、fixed8-summary.json]`

[50 张图的全部指标实测对照](gradient-screen-50/README.md) · [离线图片和指标浏览器](gradient-screen-50/review.html)。含每张原图、两个 PSNR 接近的真实 8×8 解码版本、各项分数及差值，以及同一坐标的局部放大。`[verified: gradient-screen-50/comparisons.json 的 samples、metrics；review.html]`

[实测：PSNR 几乎相同时，哪种指标能筛出渐变方块？](gradient-screen/README.md) 这组实验比较同一张图的真实 8×8 候选、96 个严格同 PSNR 对照，并给出开发验证集上的复核队列及可放大的配图。`[verified: gradient-screen/same-asset-summary.json、equal-psnr-controls.json、phase-summary.json]`

**筛选原图中的平滑渐变，用“渐变面积占比”和“最大连续渐变区”。筛选压缩后变成方块的贴图，用“连续接缝强度”。筛选渐变中的其他视觉损伤，用“渐变区 FLIP P95”和“沿渐变方向的平台与跳变”。** 前两项只需要原图。后面几项需要该候选的解码图，可以返回分数，部分还能指出缺陷坐标。用这些信号安排人工复核，验收阈值由游戏实际显示条件和美术判断确定。`[verified: probe.py 的 gradient_mask、evaluate；general/results.json 的 masked_fp95；special/measurements.json 的 platform]` `[opinion]`

## 先看同一张图

样本 **0615** 是白色渐隐弧，原尺寸 128×128。下图固定编码搜索档位为 **fastest**，从左到右是原图、4×4、8×8、12×12。用户截图里的是第三列。透明部分统一在线性光下合成到深灰底（sRGB 码值 64），再转回 sRGB。展示图按最近邻放大，表中所有分数按原生像素计算。`[verified: matches0.json 的 ref/ranked；prepare.py 的 table、picture；general/results.json 的 615；handbook_assets.py 的 sheet]`

![同一张白色渐隐弧在原图和三种 ASTC 块尺寸下的对照](examples/0615-comparison.png)

可单独打开四张 128×128 的原尺寸图核对像素。 `[verified: examples/0615 原尺寸 PNG]` [原图](examples/0615-ref-dark.png) · [4×4](examples/0615-4x4-fastest-dark.png) · [8×8](examples/0615-fastest-dark.png) · [12×12](examples/0615-12x12-fastest-dark.png)

这张图有一个肉眼也能核对的例子。在原图坐标 **x=56，y=88 至 96**，原图九个像素的亮度依次是 **82、90、99、108、118、125、131、136、139**。8×8 解码后变为 **88、88、88、88、88、88、88、88、145**。原本由暗到亮的弧面出现了八像素长的平台，最后一步从 3 级跳变增至 57 级。下面各个指标都可以用这类可见变化来理解。`[verified: special/measurements.json，0615 / fastest / platform]`

**读数约定。** 对需要两张图的指标，“压缩前”是原图与自身比较，“压缩后”是同一原图与解码图比较。对单图指标，则独立计算两张图。↑/↓ 表示保真度通常随分数升高/降低而改善；“越高越优先复核”用于失真或风险排序。分位数 P95、P99 是第 95、99 百分位。表中示例刻意选择变化明显的档位，属于个例。`[verified: general/measure_example.py、probe.py、screen.py 的输入与统计；opinion: 示例选取]`

## 1. 整图、局部误差和感知质量

下表每行都用上图的 **0615**。Unity 原生指标使用合成前的原始 RGBA 和原生质量分支。其余指标使用眼睛实际看到的深灰底展示图。数字按行舍入。`[verified: general/measure_example.py；general/results.json，615/self、4、8、12]`

| 指标 | 怎么算、用于什么 | 压缩前 | 4×4 | 8×8 | 12×12 |
|---|---|---:|---:|---:|---:|
| **Unity 原生 PSNR ↑** | 对原生 RGB 求各通道均方误差；需要且非常量的 Alpha 也可参与。项目实现对误差大于 10⁻¹⁰ 的参与通道取平均，再计算 10 log₁₀(255²/MSE)；全无损返回 100。用于重放历史 Unity 判据。 | 100.00 | 51.66 | 36.99 | 31.78 dB `[verified: ASTCCompressor.cpp 的 CalculatePSNR；general/results.json 的 psnr]` |
| **展示 RGB PSNR ↑** | 对合成后所有像素的 R、G、B 三个通道等权算 MSE，再转 dB。用于检查实际底色下的整体像素误差。 | ∞ | 44.81 | 34.16 | 28.70 dB `[verified: prepare.py 的 local_scores；general/results.json 的 view_psnr_db]` |
| **最差局部 PSNR ↑** | 把展示图分成不重叠的 32×32 窗口，各自算 RGB PSNR，取最低值并保留左上角坐标。用于定位局部最差区域。 | ∞ | 39.29 | 28.90 | 24.09 dB，位置 (32,64) `[verified: general/results.json 的 worst_patch_psnr_db、worst_x、worst_y]` |
| **低 PSNR 面积占比 ↓** | 找出局部 PSNR 低于阈值的窗口，累计有效像素数，除以整图有效像素数。此处三个值依次对应 **28 / 30 / 32 dB**。用于区分一小处误差与大面积损伤。 | 0 / 0 / 0% | 0 / 0 / 0% | 0 / 12.5 / 25% | 37.5 / 43.75 / 50% `[verified: prepare.py 的 counts、area_under；general/results.json 的 area_under_28/30/32]` |
| **普通 SSIM ↑** | 将展示图转亮度，在 11×11 高斯窗内比较亮度均值、方差和协方差，只平均完整窗口。用于衡量局部结构保真度。 | 1.0000 | 0.9922 | 0.9621 | 0.9158 `[verified: struct/measure.py 的 luma、wang_ssim；general/results.json 的 ssim]` |
| **Unity 原生 MS-SSIM dB ↑** | 在原生亮度图及逐级缩小的图上比较对比度、结构，最后一级计入亮度，按尺度权重相乘得到 MS，再取 −10 log₁₀(max(1−MS, 10⁻⁶))。用于原生颜色质量判据。此图自比实测 56.23 dB，转换的数值上限为 60 dB。 | 56.23 | 33.43 | 20.20 | 15.43 dB `[verified: ASTCCompressor.cpp 的 CalculateMSSSIMDb_Luma、SafeMsSsimToDb；general/results.json 的 ms]` |
| **SSIMULACRA2 ↑** | 在感知颜色空间的多个尺度提取结构、模糊和额外边缘误差，按学习到的权重汇总。用于给压缩候选一个感知保真分，最高 100，低分也可以为负。 | 100.0 | 88.8 | 66.9 | 38.0 `[verified: 作者 README 的 How it works、Usage；general/results.json 的 ss2]` |
| **LPIPS-Alex ↓** | 将原图和解码图送入同一预训练网络。在选定层归一化通道特征，比较特征差的平方，按学习权重和空间位置汇总。用于比较感知上的整体差异。 | 0 | 0.0083 | 0.1150 | 0.3158 `[verified: LPIPS 作者项目的 paper、官方 Alex 实现；general/results.json 的 lpips]` |
| **FLIP 均值 ↓** | 在指定观看条件下比较可感知的颜色与特征变化，生成逐像素误差图，再取全图均值。本例使用 LDR-FLIP、67 像素/视角度。用于衡量整图平均可见误差。 | 0 | 0.0082 | 0.0252 | 0.0519 `[verified: NVIDIA FLIP README；general/results.json 的 flip；flip/validation.py 的 ppd]` |
| **FLIP P95 / P99 ↓** | 在同一张 FLIP 误差图上取两个高分位，观察较坏位置的误差。比全图均值更突出局部问题；分数本身不包含坏区的形状。 | 0 / 0 | 0.0402 / 0.0629 | 0.1113 / 0.1787 | 0.2179 / 0.3316 `[verified: general/results.json 的 fp95、fp99]` |
| **渐变区 FLIP P95 ↓（项目汇总方式）** | 先在原图上固定渐变掩膜，只取掩膜内的 FLIP 像素值算 P95。用于检查特效弧面、雾化或光晕，避开无关背景。本例选中 2,561 / 16,384 像素。 | 0 | 0.0545 | 0.1369 | **0.2732** `[verified: general/measure_example.py 的 mask；general/results.json 的 masked_fp95、mask_pixels]` |

这组数字里，**8×8 的 28 dB 坏区面积是 0%，但已经有八像素长的台阶**。收紧到 32 dB 又会圈出 25% 的面积。要判断这些错误有没有排成一条人眼很容易看到的线，需要保留错误的位置和形状。`[verified: general/results.json 的 615/8；special/measurements.json 的 0615/fastest/platform]` `[opinion]`

算法来源与项目口径见 [SSIM 原论文](https://ece.uwaterloo.ca/~z70wang/publications/ssim.pdf)、[SSIMULACRA2 官方实现](https://github.com/cloudinary/ssimulacra2#how-it-works)、[LPIPS 作者项目](https://richzhang.github.io/PerceptualSimilarity/) 和 [NVIDIA FLIP](https://github.com/NVlabs/flip)。`[verified: 各链接的论文方法或官方 README]`

## 2. 项目自定义指标：判渐变、抓方块、查透明度

原图的渐变掩膜在 CIELAB 的三个通道上计算。分别在 7×7 和 15×15 窗口内拟合颜色平面，要求斜坡解释至少 85% 的局部颜色变化，且拟合的跨窗口变化量至少约 2 个 Lab 单位，再合并两个尺度。以下数字使用这一版参数。它们是用来筛样本的工程设定。`[verified: probe.py 的 lab、gradient_mask；opinion: 参数用途]`

| 指标 | 怎么算、分数含义 | 变化明显的实测例 |
|---|---|---|
| **渐变面积占比** | 渐变候选像素数 / 全图像素数。仅有原图也能算；值越高，越值得检查渐变。若要看压缩怎样改变了图像，可在解码图上独立重算一次。 | 灰色圆环 **0617**，原图 **19.76%**，8×8 后 **4.14%**，12×12 后 **2.50%**。原先能拟合为平滑渐变的许多位置，在解码图上已不再满足条件。`[verified: local-examples.json 的 gradient/617、detector_area_on_display_pct]` |
| **最大连续渐变区** | 将掩膜中的像素按上下左右相邻分组，取最大组的像素数。用来区分一整片平滑渐变和许多零散的小碎片。跨分辨率筛图时可再除以整图面积。 | 同一圆环独立重算，最大连通区从原图的 **2,120 像素**缩至 8×8 后的 **106 像素**。原图所有渐变区共 **3,237 像素**。后面的渐变误差都在完整原图掩膜内统计。`[verified: local-examples.json 的 gradient/617；probe.py 的 label、support；general/results.json 的 617/self/mask_pixels]` |
| **渐变区梯度误差 P95 ↓** | 对掩膜内相邻像素，算解码与原图的 **Lab 颜色变化向量之差**，取其长度，再在水平、竖直的有效像素对中取 P95。能抓到渐变变平、变陡或变色，包括块内部。 | 0615 原图自比 **0**，4×4 **2.17**，8×8 **6.30**，12×12 **9.38**。单位是相邻像素颜色变化的 Lab 向量差。`[verified: local-examples.json 的 gradient/615、gradient_change_p95]` |
| **块边界额外跳变 P95 ↓** | 在真实 ASTC 网格上算跨边界的颜色跳变，扣除原图已有的跳变，再扣除两侧紧邻块内位置的平均新增跳变，负数取零。在有效边界像素对中取 P95。用于定位网格比附近更突兀的情况。 | 蓝色光晕 **0616**，自比 **0**，4×4 **3.09**，8×8 **8.24**，12×12 **16.64**。`[verified: local-examples.json 的 gradient/616、grid_excess_p95；probe.py 的 surplus]` |
| **连续接缝强度 ↓** | 沿同一块边取连续 **4 个原生像素**，用四个“额外跳变”中最小的一个给该段打分，再取全图最高分和坐标。这样单个亮点不会独自触发。无有效连续段时记为空。 | 0615 自比 **0**，4×4 **2.14**，8×8 **15.71**，8×8 最强位置 **(56,92)**。按此分数从高到低排，三张截图在 138 张有可计算结果的贴图中分列 **7、12、20**。`[verified: local-examples.json 的 gradient/615；screen-summary.json 的 rank_continuous_seam]` |
| **沿渐变方向的平台长度与末端跳变 ↓** | 原型扫描水平和竖直亮度剖面，要求原图每步同向变化 1–12 级；在解码图同位置寻找 2–12 像素的等值平台。段分数为“平台长度减 1 × 新增同向末跳”，取最大值。能给出可逐像素复查的位置，不依赖 ASTC 网格对齐。 | 开头的 0615 剖面从 **1 像素等值段 → 8 像素平台**，末跳 **3 → 57**，分数 **0 → (8−1)×(57−3)=378**。这个初版只扫描亮度与两个轴向。`[verified: special/measurements.json 的 0615/fastest/platform；special/metrics.py 的平台检查]` |
| **圆环等亮轮廓位移 P95 ↓** | 用在圆心已知的圆环。以图心发出 360 条射线，在三个亮度水平 90、110、140 处分别找最外侧下降交点。比较原图、解码图交点的半径，把绝对位移取 P95。可直接回答圆弧偏了几个像素。 | 0617 的 1,080 个匹配交点，自比 **0 px**，8×8 **1.85 px**，12×12 **2.87 px**。不同形状需要另定义可对应的轮廓，且要报告缺失交点。`[verified: special/measurements.json 的 0617/ring_displacement；opinion: 应用条件]` |
| **透明度劣化贡献** | 固定同一背景，分别合成“原 RGB＋解码 Alpha”和“解码 RGB＋原 Alpha”，与原合成图算展示 RGB MSE。两次反事实评分用来定位通道原因，不能直接相加为完整误差。 | 0615 深灰底，原图自比 **0**。8×8 只换 Alpha 得 **24.79**，只换 RGB 得 **0.12**，两者都换得 **24.95**，单位均为 8 位 RGB 码值平方。白弧的主要问题来自透明度渐变。`[verified: alpha-ablation.json 的 615.actual_view_mse、decoded_alpha_only_mse、decoded_RGB_only_mse]` |

![三张用户样本的原图、渐变掩膜、8×8 解码及局部误差位置](examples/gradient-locations.png)

绿色由原图决定，右侧亮色表示同一原图区域的梯度误差，青圈标出分数最高的接缝。热图亮度逐行归一化，适合看位置。196 张同尺寸颜色贴图中，有 58 张未形成足够长的可测接缝，因此空值应单列。三张已知问题图同属一个 Ring 素材目录；以上排序可供筛查，仍需在其他素材族上核对漏报和误报。`[verified: probe.py 的 visuals；screen-summary.json 的 assets、valid_rank_denominators、asset；opinion: 排序用途]`

## 3. 文献中的专项指标

### PSNR-B 和 GMSD

| 指标 | 怎么算、作用 | 原图 → 压缩后 |
|---|---|---|
| **PSNR-B ↑** | 计算解码图的跨块与块内相邻亮度平方差均值，分别记作 DB、DI。项目按真实块宽 b 计算 BEF = max(0, DB−DI) × log₂(b)/log₂(min(W,H))，再取 10 log₁₀(255²/(MSE+BEF))。用于给整图 PSNR 增加块边界惩罚。比较前后须使用同一块网格，Unity 倒序存储的行也要映射回显示坐标。 | 0617、固定 12×12 网格，**38.26 → 25.79 dB**。原图自比时 MSE 为 0，原图在该网格上的 BEF 为 9.72，故基线是有限值。`[verified: special/measurements.json 的 0617/12x12-fastest/same_block_reference_psnrb、psnrb；Yim 与 Bovik §V 式 19–26]` [原论文](https://utw10503.utweb.utexas.edu/publications/2011/cy_tip_jan11.pdf) |
| **GMSD ↓** | 对亮度图做 2×2 均值与二倍下采样，再用 Prewitt 算每个位置的梯度幅值 g。每点相似度为 (2gR·gD+170)/(gR²+gD²+170)，最终取整张相似度图的样本标准差。用于测梯度结构失真程度在空间上的波动。 | 同一圆环 12×12，**0 → 0.13839**。这里用的是 8 位亮度量纲，常数 170 与此量纲配套。`[verified: special/measurements.json 的 0617/12x12-fastest/gmsd；Xue 等论文与作者 GMSD.m]` [原论文](https://arxiv.org/abs/1308.3052) · [作者实现](https://www4.comp.polyu.edu.hk/~cslzhang/IQA/GMSD/GMSD.htm) |

### Wang 全参考色带分数

**作用与算法。** 在 8 位亮度图中寻找同灰度、四邻连通且面积大于全图 0.2% 的区域。考察相邻区域之间较弱但连贯的边界，使用 11×11 邻域，按论文的对比度与边缘一致性条件过滤，再回原图同位置去掉原有的相似轮廓。将保留的边缘像素数乘以两区域的灰度差，对所有边求和，除以图像对角线长度；分数越高，新增色带越强。它适于寻找弯曲或位于 ASTC 块内的色带。`[verified: Wang 等 §3–4，尤其 Fig. 4 后的参考匹配与 Q 定义；opinion: ASTC 用途]` [原论文](https://storage.googleapis.com/gweb-research2023-media/pubtools/5794.pdf)

**可逐项核算的压缩例。** 将一张 512×256、带轻微交错抖动的 8 位灰色坡，仅保留每个像素的高 6 位并实际按 6 位打包，再解码回 8 位。原图最大等值连通区只有 **2 像素**，解码图出现 **8 条**各宽 64 像素的纯色带。只计图内交界，7 条边各长 256，跨边落差都是 4，一致性为 1，原图没有对应的大区域边界。该特例按论文公式得到 **0 → 7×256×4/√(512²+256²) = 12.52**。这是六位量化的受控实例，数值来自公式与像素枚举。`[verified: local-examples.json 的 wang；handbook_assets.py 的 wang_example；Wang §4]` [量化前](examples/wang-ref.png) · [量化后](examples/wang-decoded.png)

### Netflix CAMBI

CAMBI 在多个空间尺度上估算低纹理区域的**亮度色带可见性**，得到单图分；越高表示可见色带越严重。全参考模式另算 max(0, 解码图分−原图分)，可扣除原图已有的整体色带。官方实现会拒绝宽和高都小于 216 的输入，所以本项改用原生 512×512 的渐变素材 **0529**。`[verified: Netflix 文档 Background、Options；cambi.c 的 CAMBI_MIN_WIDTH_HEIGHT 与尺寸判断；cambi-0529.json 的 id]` [官方说明](https://github.com/Netflix/vmaf/blob/master/resource/doc/cambi.md) · [源码](https://github.com/Netflix/vmaf/blob/master/libvmaf/src/feature/cambi.c#L479-L484)

0529 是同一 Ring 素材目录中参与筛查的 38 张 256×256 或 512×512 贴图里，12×12 fastest 新增色带分最高的一张。各版本使用相同的 BT.709 亮度转换和原生尺寸。单图分从原图的 **4.4991** 升至 12×12 的 **7.6530**。全参考新增分在原图自比时是 **0**，4×4 为 **0.5289**，12×12 为 **3.1539**。`[verified: literature/cambi-0529.json、cambi-results.json 的 cambi_full_reference；run_cambi.py 的 frame、measure]`

![用于 CAMBI 的 0529 原图和 ASTC 解码图](examples/0529-comparison.png)

### BBAND 无参考色带分

BBAND 可单独给原图或解码图打分。作者的单帧实现从亮度图的 Sobel 梯度中选出弱边，剔除邻近明显纹理的像素，再细化和连接边缘。每个边缘像素按局部亮度、纹理掩蔽、边长与梯度强度加权，对较显眼的像素汇总，并乘空间活动度权重。越高表示该图里疑似可见的色带越重。它也可能对原图本来的分层给高分。`[verified: Google BBAD_I.m 的 Step1–4；Tu 等 §II]` [论文](https://arxiv.org/abs/2002.11891) · [作者单帧实现](https://github.com/google/bband-adaband/blob/a896f7336387e1e004dbbb7bc7c3028db1769c54/src/BBAD_I.m)

0615 深灰底，**原图 0.5524 → 4×4 为 0.5457 → 8×8 为 1.0021 → 12×12 为 1.1161**。反例是 0617：原图为 **2.4012**，12×12 后降至 **1.7850**，但圆环外缘确有方块。BBAND 响应的是它识别出的亮度色带，其分数与 ASTC 新增接缝分数可以朝不同方向变化。本地用 Octave 运行作者的单帧热图算法，最终空间活动度采用与官方 MATLAB 基准一致的边界处理；两个作者基准的最终分均复现到 1.3×10⁻¹² 以内。`[verified: bband-scores-parity.json 的 rows/direct_map_pooling、official_golden_final_pooling；0617 的接缝图]`

### Denes 亮度与彩色色带可见性模型

该模型用来回答“在这种亮度、渐变斜率和观看尺度下，量化产生的色带有多容易看见”。将量化后的台阶误差分解成空间频率分量，按人眼对各频率及亮度、色度通道的敏感度加权，再换算为**模型预测的检出概率**。适用于可描述端点和斜率的受控色坡。`[verified: Denes 等 Abstract、式 (2)–(7)、(11)]` [原论文](https://www.cl.cam.ac.uk/~rkm38/pdfs/denes2019banding_model.pdf)

**同一灰色渐变的受控算例。** 中心亮度 10 cd/m²，斜率 1/32 cd/m²/像素，观看尺度每度 60 像素。按无彩色特例取 16 个谐波，理想连续坡的预测检出概率 **0%**，量化阶距为 0.25 cd/m² 时 **0.0951%**，阶距为 4 cd/m² 时 **55.85%**。这些是给定条件的模型值。实际 ASTC 光晕的屏幕亮度和显示大小需要另行指定。`[verified: denes-example.json；denes_example.py 的 probability；opinion: 项目应用条件]` [连续坡预览](examples/denes-ref.png) · [粗量化预览](examples/denes-quantized.png)

### PIM 学习型感知距离

PIM 用相邻视频帧无监督学习表征。评价时输入原图和失真图。官方 PIM-5 对两张图的表征分布估计两个方向的 KL 散度并求和，距离越大表示模型认为差异越大；单混合分量的 PIM-1 则直接计算表征均值之间的均方差，再在尺度间平均。适合比较压缩方法的感知差异。`[verified: Bhardwaj 等式 (3)、§3.1；官方 models.py L125–142]` [论文](https://arxiv.org/abs/2006.06752) · [作者计算代码](https://github.com/google-research/perceptual-quality/blob/478157a5457c3b335e55de8fb2a4b779fe385143/perceptual_quality/pim/models.py#L125-L142)

**可核对的压缩例来自论文。** ImageNet-C 的 JPEG 压缩由强度 1 增至 5，图 6 中 PIM 对应的等效高斯噪声标准差约从 **0.05 升至 0.08**，无扰动原图的等效噪声为 0。作者先对数据集的 PIM 距离取平均，再映射到同一指标对高斯噪声强度的响应。该图给的是**数据集等效噪声**。本次访问 PIM-1、PIM-5 官方权重均返回 HTTP 403，0615 等单张 ASTC 贴图暂缺可核实的原始 PIM 分数。`[verified: pim-evidence.json；论文附录 A.3、Fig. 6 的 JPEG compression 面板]` [论文图 6](https://arxiv.org/pdf/2006.06752#page=15) · [官方模型入口](https://github.com/google-research/perceptual-quality)

若想复核**原始距离**的量纲，可取一个单尺度 PIM-1 教学例。假设两张图的表征均值从同为 (0,0) 变成 (0,0) 与 (2,2)，则均方距离从 **0 → (2²+2²)/2 = 4**。这个 4 仅用于演示计算。作者另在图 8 展示了真实 JPEG 压缩的图像效果，图中未给出单张图的原始 PIM 分数。`[verified: models.py 的单混合分量分支；论文 Fig. 8]` [论文图 8](https://arxiv.org/pdf/2006.06752#page=17)

## 4. 项目里另用到的评价量

| 评价量 | 怎么算、作用 | 例子 |
|---|---|---|
| **法线角误差的均值 / P95 ↓** | 法线贴图的 RGB 解包为 2×RGB/255−1 的向量，归一化，点积夹到 [−1,1]，取反余弦并换算为度。均值衡量整体方向偏差，P95 反映较差区域。示例只评 mip0。 | 法线图 **0265**，原图自比 **0.009° / 0.028°**，12×12 fastest **13.19° / 38.44°**。自比的微小正数是原生浮点实现的实际输出。`[verified: general/normal265.json 的 self、12x12fastest；ASTCCompressor.cpp 的法线角度计算]` |
| **ASTC 有效载荷字节、单次编码耗时** | mip0 载荷字节 = 16 × ceil(W/b) × ceil(H/b)，不含 16 字节文件头；耗时用归档中的实际编码计时。这两项回答“省多少空间、花多少时间”。 | 0615 的未压缩 RGBA8 像素为 **65,536 B**；4×4 / 8×8 / 12×12 载荷为 **16,384 / 4,096 / 1,936 B**。该图相应最快档的记录为 **4.70 / 6.41 / 9.87 ms**。4×4 来自单独补测，单图计时不能外推普遍速度。`[verified: data.js 的 615/fastest/dark、blocks.js 的同配置；package-qa.json 的 media；opinion: 计时解释]` |
| **Pearson r、Spearman ρ** | 前者把两个指标的协方差除以各自标准差，比较数值线性关系；后者先对样本排序，再对秩算 Pearson，比较排序一致性。每个相关系数需要一组样本，两张单图不能产生可解释的“压缩前后相关性”。 | 在固定 8×8 fastest 的 **575 张无需 Alpha 的 sRGB 图**上，FLIP 均值与 Unity PSNR 的 Pearson **−0.5841**、Spearman **−0.7648**。两者分数优劣方向相反。指标间相关性不能替代美术的接受度标注。`[verified: work/analysis.json 的 corr 对应行；assemble.py 的 correlate；opinion: 美术验收解释]` |

## 实际使用

- **只有原图。** 按渐变面积占比排，再用最大连续渐变区筛掉许多零散的小区域。可以找出光晕、渐隐弧或较大片平滑坡面的候选图。`[verified: probe.py 的 gradient_mask、largest_component_px]` `[opinion]`
- **已有原图和压缩图。** 横竖方块优先看连续接缝强度和位置；平滑坡分层优先看平台与末跳、渐变区 FLIP；圆环轮廓形状另看径向位移。透明特效先按实际底色合成看，再用交叉合成定位损伤来自 RGB 还是 Alpha。`[verified: special/measurements.json 的 platform、ring_displacement；alpha-ablation.json 的 615、617]` `[opinion]`
- **要定生产门槛。** 同时抽看高分、低分和空值，并留出其他素材族进行盲评。本文的三张问题图来自同一目录；4×4、8×8、12×12 之间的这些跳变可用来确认指标含义，不能作为人眼通用的分界线。`[verified: screen-summary.json 的 examples.asset；opinion: 验证方法]`

**复核材料。** 随文的 [示例数值与来源记录](examples/measurements.json) 按指标保留未舍入结果和证据类型；在本工作区还可打开 [0615 的原尺寸交互复核页](../outputs/01a1eca4-b759-74d2-82d5-2d27a4db8e18/open/0615-fastest.html)，或查看 [196 张同尺寸贴图的逐图排序 CSV](../tmp/gradient-diagnostics-20261119/screen-128.csv)。`[verified: examples/measurements.json、0615-fastest.html、screen-128.csv]`
