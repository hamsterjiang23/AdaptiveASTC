# Lane B 笔记：纹理压缩领域与游戏工业对“平滑渐变被块压缩破坏”的做法

日期 2026-11-19。只读访问仓库；本目录是唯一写入位置。下载的第三方源码/PDF 放在 `src_dl/`、`dl_griffin/`、`dl_arm/`（仅作文本读取）。

## 0. 结论先行

1. 工业界做法几乎都在**编码器内部**：给平滑区（低方差/低活动度）或块边纹素更高误差权重，让编码器自己少犯错。它们是代价函数，不是检测器。本次把四种工业加权直接当“整图检测分”用在 196 张 128² 图上，三张已知样例名次 102–118/196，与原生 PSNR（111–118）几乎相同（见 §6）。**按均值汇总的平滑加权 MSE 抓不到这类图；接缝的线状结构才是关键**，这与 metric/ 中“误差沿块网格排成线”的结论一致。
2. 真正能补 metric/ 缺口的工业经验有三类：
   - **观看语境 / 用途分层**：Griffin & Olano 证明 3D 贴图的压缩误差会被几何与多贴图组合掩蔽，且掩蔽强度随贴图类别变化；Arm 指南建议 UI 用 4×4/5×5；Unreal 的 UI 压缩设置历史上就是不压缩 RGBA8。FX/UI 这类屏幕对齐、无掩蔽的贴图应单独分层、单独定阈值。
   - **混合方式感知的 Alpha 误差**：编码器默认 Alpha 权重 1，`-a` 只按 Alpha 缩小 RGB 权重；但 over 混合下 Alpha 误差在屏幕上被放大 |C−Bg| 倍。推导给出“对所有背景的误差上界只需黑、白两张合成”。
   - **平滑块的工业定义与默认参数**（bc7enc_rdo/ERT、UASTC RDO：σ_max<18 视为平滑、最多 10× 权重；ultrasmooth：4×4 σ<2.9、区域≥64 块、120×）可以作为接缝分的门控/加权，以及浅渐变（天空、雾）的补充检测器。
3. astcenc 2.x–3.3 曾有专门的去块选项 `-b`，源码注释写明用于“reduce block artifacts when compressing gradients”，法线默认 1.8；3.4（2022-02）移除。它可用作“编码器 A/B 差分”探针，但本次未实测。

## 1. 纹理压缩感知质量研究

### Griffin & Olano, I3D 2014 “Objective Image Quality Assessment of Texture Compression”
- 全文 PDF：https://userpages.cs.umbc.edu/olano/papers/texiqa.pdf（WebFetch 超 10 MB 限制，改用 curl 下载到 `dl_griffin/texiqa.pdf`，`pdftotext -layout` 提取为 `texiqa.txt`）。
- 方法：在场景中均匀采样大量视点，用未压缩与压缩贴图分别渲染，比较最终渲染图（texiqa.txt §3 “Approach”，约 L84–L88）。
- 指标：RMS 颜色误差、CIELAB ΔE94、CIELAB L* 上的 SSIM；“weighting the metric at each pixel by the alpha value”只统计被渲染的像素（texiqa.txt 约 L155–L168，§4.1 后段）。
- 格式：BC5/BC4/BC3 由 NVTT（quality normal）；ASTC 4×4/8×8/12×12 由 ARM Mali ASTC Evaluation Codec（texiqa.txt §4.2，约 L149–L183）。
- 结论（§4.3，texiqa.txt 约 L409–L433）：出现掩蔽；“perceptual sensitivity to compression artifacts and masking effects varies based on the class of texture”；Gloss 从 4×4 到 12×12 几乎不降质；“Figure 11 implies SSIM values as low as 0.9 still result in good image quality”；“Current GPU compression algorithms are too conservative”。
- TVCG 2015 扩展版（DOI 10.1109/TVCG.2015.2429576）只读到 PubMed/NIST 摘要：masking 显著且随贴图类型变化、硬件压缩过于保守。全文未获取（非开放获取）。
- **对本项目的含义（推断）**：Griffin 的结论针对贴在 3D 模型上、与法线/光泽组合的贴图。本项目三张问题图是 FX 光环/光晕，屏幕对齐显示、常用加法或 Alpha 混合，没有几何与贴图组合掩蔽，正好是这篇论文结论的反面。用途/语境应当进入标注协议和阈值分层。

### Arm《Adaptive Scalable Texture Compression Developer Guide》Version 4.3（Document ID 102162_0430_00_en）
- 下载：https://documentation-service.arm.com/static/6410854656ea36189d4e9659（WebFetch 域名被拒，curl 成功，`dl_arm/arm.txt`）。
- “Choosing a suitable bitrate”（PDF 第 21–22 页，arm.txt L787–L817）原文：
  - “split all your texture assets into quality categories based on their distance to the viewer or general visibility and importance … high, medium, and low”
  - “For the majority of color textures using a block size between 6x6 (3.56bpp) and 8x8 (2bpp) gives an acceptable quality”
  - “For 2D user interface elements, where image quality can be more important, a smaller block size such as 4x4 or 5x5 might be more appropriate.”
  - 法线建议 `-thorough` 与 6×6。
- HDR 段（arm.txt L857–L860）：低码率“are prone to block artifacts in regions with fast luminance changes”。
- 指南没有直接说“渐变需要小块”；这一条是检索代理的推断，不能当作 Arm 原文引用。

### ASTC 格式文档（本地 astcenc 4.5 源码树）
- `reproductions/nah2023_adaptive_astcenc/upstream/Docs/FormatOverview.md` L292–L306：大块无法每纹素存一个权重，权重网格可低于纹素分辨率，解码时“interpolated … using a bilinear interpolation”；权重数和量化级别按块选择。
- 推断：线性坡（平面）可被 2×2 权重网格的双线性插值精确表示；8×8 块上**带曲率**的渐变（环形衰减）且**颜色/Alpha 跨度大**时，需要更多权重点和更多量化级，128 bit 预算不够，就会出现“平台 + 跳变”。0615 的 82…139 → 8×88 + 145 符合这一模式。

### ETC2 planar 模式（Ström & Pettersson, Graphics Hardware 2007）
- 只通过检索摘要获知（未打开全文）：ETC2 用 ETC1 的无效位组合新增 T/H/planar 模式；planar 模式存 C0、CH、CV 三色在 4×4 内线性插值，专门针对“colors change smoothly”的块；ETC1/S3TC 平滑过渡易发生 blocky。论文 PDF：https://www.jacobstrom.com/publications/StromPetterssonGH07.pdf ；GH07 幻灯片：https://www.graphicshardware.org/previous/www_2007/presentations/strom-etc2-gh07.pdf 。核实深度：检索摘要级，章节号未核对。

## 2. 编码器内部做法

### Arm astcenc：去块权重、活动度权重、Alpha 权重
本地有三个版本源码：
- 原始 ARM Evaluation Codec（1.x 时代）：`reproductions/texnn/upstream/Source/`
- astcenc 3.3.0：`reproductions/nah2022_psnr_search/upstream/`（CMakeLists.txt L27）
- astcenc 4.5.0：`reproductions/nah2023_adaptive_astcenc/upstream/`（CMakeLists.txt L27）

**`-b` 块边去块权重**
- 帮助文本（texnn astc_toplevel.cpp 约 L978–L982）：“Increase error weight for texels at compression-block edges and corners … Higher values should reduce block-artifacts, at the cost of worsening other artifacts.”
- 实现（3.3 `astcenc_compress_symbolic.cpp` L931–L968；旧版 astc_compress_symbolic.cpp L833–L854）：块内纹素 (x,y)，xdif=(x−(B−1)/2)/B，ydif 同理，wdif=0.36，dist=√(xdif²+ydif²+wdif²)，权重 = dist^b。注释 L933–L936：“assigning a higher error weight to blocks the closer they are the edge … can help reduce block artifacts when compressing gradients.”
- 应用：3.3 compress_symbolic L1117 `error_weight = error_weight * ctx.deblock_weights[idx]`。
- 法线默认：3.3 `astcenc_entry.cpp` L664–L667：“Normals are prone to blocking artifacts on smooth curves so force compressor to try harder here … config.b_deblock_weight = 1.8f; config.tune_db_limit *= 1.03f;”。旧版 `-normal_percep` 预设也设 1.8（astc_toplevel.cpp L1641）。
- 移除：4.5 源码树 `Docs/ChangeLog-3x.md` L131–L134（“## 3.4”，Status February 2022）：`-v`/`-va` 与 `-b` “are no longer supported”；`-a` 不再作为误差加权工具，仅用于 sprite-sheet RDO；`-mask`、对 mask/normal 的 `-perceptual` 变为 no-op（L135–L142）。

**`-v`/`-va` 活动度（局部均值/方差）权重**
- 帮助文本（texnn astc_toplevel.cpp L925–L955）：weight = 1 / (baseweight + avgscale·average² + stdevscale·stdev²)，邻域半径 radius，mixing 控制 RGB 通道合并。
- 实现（旧版 astc_compress_symbolic.cpp L895–L934；3.3 compress_symbolic L1055–L1100）。
- 预设：3.3 `astcenc_entry.cpp` L669–L676（normal+perceptual：radius 3，stdev 50）；L678–L685（mask：radius 3，mix 0.03，stdev 25）。旧版 `-mask` 同（astc_toplevel.cpp L1650–L1659）。
- 含义：低方差（平滑）区权重高，高方差（纹理）区权重低，即活动度掩蔽。

**`-perceptual`（颜色）**：3.1 起按亮度贡献加权通道（ChangeLog-3x.md L214–L217；3.3 entry.cpp L695–L700 “l = r * 0.3 + g * 0.59 + b * 0.11”）。不涉及空间平滑度。

**`-a` Alpha 权重**：4.5 `astcenc_entry.cpp` L924–L933：“Scale RGB error contribution by the maximum alpha in the block … can buy up to 0.5 dB PSNR.” RGB 权重乘块内最大 Alpha，Alpha 通道权重仍为 cw_a_weight。旧版 `-a <radius>` 用邻域平均 Alpha 的平方缩放 RGB 权重（astc_compress_symbolic.cpp L950–L960）。
- 推断：编码器只考虑“透明处 RGB 不重要”，没有考虑“Alpha 误差在屏幕上乘以 |C−Bg|”。0615 的损伤恰好主要来自 Alpha（alpha-ablation.json：只换 Alpha 24.79，只换 RGB 0.12）。

**astcenc 4.5 Encoding.md 没有渐变/天空的块大小建议**（`rg -i "gradient|sky|smooth|banding"` 无命中）。

### bc7enc_rdo / ERT（Rich Geldreich）与 Basis Universal UASTC RDO
源码（curl 到 `src_dl/`，master 分支，2026-11-19 获取）：
- `ert.cpp` L93–L111 `compute_block_max_std_dev`：块内各通道 8-bit 码值标准差取最大。
- `ert.cpp` L342–L346：yl = clamp(σ_max / m_max_smooth_block_std_dev, 0, 1)²；smooth_block_mse_scale = lerp(m_smooth_block_max_mse_scale, 1, yl)。L360：代价 t = mse·scale + bits·λ。
- `ert.h` L19：“distortion is scaled MS error multiplied against the smooth block MSE weighting factor”；默认 L46–L47：σ 阈值 18、最大倍数 10。
- `rdo_bc_encoder.cpp` L722–L729：未手设时自动取 lerp(15, 50, min(1, λ/4))。
- **ultrasmooth 区域**（`rdo_bc_encoder.cpp` L31–L175）：4×4 RGB 块 σ_max/2.9 → yl²；块平均亮度 <13 或 ≥222 视为非平滑；一次 3×3 膨胀非平滑区；32 轮“3×3 邻域中 ≥5 个非平滑则置为非平滑”；剩余平滑连通区 <64 块丢弃；保留块 MSE ×120。
- README L7：“modified to favor MSE on very smooth blocks”；L137：“Use -zb1.0 to disable smooth block error scaling completely … can result in noticeable artifacts on smooth/flat blocks at higher lambdas.”
- 作者博客 https://richg42.blogspot.com/2021/02/how-to-use-bc7encrdo.html：“RDO compression using MSE as the internal error metric is difficult on smooth or flat regions.”；“-zb30-100 works well.”；“tune smooth block handling so lambdas at or near 1 it looks OK on textures with smooth gradients, skies, etc.”
- KTX-Software libktx `ktxBasisParams`（https://github.khronos.org/KTX-Software/libktx/structktxBasisParams.html）：`uastcRDOMaxSmoothBlockErrorScale` 范围 [1,300]、默认 10，“Larger values suppress more artifacts (and allocate more bits) on smooth blocks”；`uastcRDOMaxSmoothBlockStdDev` 默认 18。

### Oodle Texture（Charles Bloom）
- https://cbloomrants.blogspot.com/2020/06/oodle-texture-slashes-game-sizes.html（“How does Oodle Texture do it?”）：“a very simple approximation that treats errors as more significant when they occur in smooth or flat areas”；“errors that occur in areas that were already noisy or detailed will not be as noticeable, so they get a lower D score”；“without a perceptual distortion measure the RDO can produce ugly visible blocking artifacts even when RMSE is quite low”。没有公开公式与权重数值。
- https://cbloomrants.blogspot.com/2021/02/rate-allocation-in-oodle-texture.html：同 λ=40 下 RMSE 与感知 D 的码率图对比；RMSE 版在平滑区把码率降到近 0，“That's a mistake perceptually and causes bad blocking artifacts”；感知版“the bit rate of the smooth regions come up to avoid blocking artifacts”。
- https://www.radgametools.com/oodletexture.htm 仅由检索摘要获知“perceptual rate allocation … gives more bits to blocks where errors would be highly visible”，未打开核对。

### NVTT、Compressonator、ISPC texcomp
- 本次时间内未找到它们针对平滑区的专门机制；未核实，列入 unreachable/未覆盖。DirectXTex texconv 有 `-aw`（BC7 GPU 压缩器 Alpha 权重）与 `-pmalpha`（检索摘要，未打开核对）。

## 3. 引擎与美术流程
- Unreal：UI 贴图常用 `UserInterface2D (RGBA)`，即不压缩 RGBA8；UE 5.7 改名为 `Uncompressed (RGBA8)`，Epic 员工回复推荐 BC7（Epic 论坛 https://forums.unrealengine.com/t/missing-compression-setting-userinterface2d/2692223 ，检索摘要级，未逐帖核对）。Paper2D 可把精灵默认设为 UserInterface2D（UE 文档，检索摘要级）。
- Arm 指南：UI 4×4/5×5；按可见度/重要性分高中低三类，每类试几张后批量（§1）。
- Unity 文档中未在本次时间内找到“渐变/特效需小块”的明文；Arm 指南有 Unity 导入设置段（arm.txt L1065–L1083），未细读。
- 移动 GPU 厂商（Qualcomm、Apple、Imagination）关于渐变需小块的指导：本次未检索到可定位原文，列入 unreachable。

## 4. 透明特效：混合方式与误差放大（推导，属推断）
记线性光下源色 C、Alpha α、背景 B，预乘色 P=αC，解码后 P'、α'，ΔP=P'−P，Δα=α'−α。
- Alpha 混合（预乘 over）：out = P + (1−α)B → Δout = ΔP − Δα·B。
- 非预乘 over：out = αC + (1−α)B → Δout = Δ(αC) − Δα·B，与上式同形。
- Δout 对 B 线性，|Δout| 在 B∈[0,1] 上的最大值必在 B=0 或 B=1 取到：**黑底与白底两次合成即可给出所有背景的误差上界**。现有 dark（码值 64）/light 视图是该区间内的两个点，不是上界。
- 加法混合（SrcAlpha, One）：out = B + αC → Δout = Δ(αC)，与背景无关（饱和截断除外），等于“黑底合成”误差。
- 白色渐隐弧（0615）：C≈1，主要误差来自 Δα；在黑底 Δout≈Δα，在白底 Δout≈Δα·(C−1)≈0。深灰 64 底时 B_lin≈0.05，Δout≈0.95Δα，与 alpha-ablation.json 中“只换 Alpha 主导”一致。
- 编码器侧对照：astcenc `-a` 只按 α 缩小 RGB 权重（§2），Alpha 权重不随 |C−B| 增大。

## 5. 探针

### 5.1 工业加权当整图检测分（`industry_probe.py`）
命令：`uv run --no-sync python tmp/gradient-metric-brainstorm-20261119/lane-b-texture-practice/industry_probe.py`
- 输入：`tmp/gradient-diagnostics-20261119/screen-128.csv` 的 196 张 128² 图；原生 RGBA 参考与 8×8 fastest 解码路径来自 `tmp/multimetric-review-20261118/blocks/source/candidates.jsonl` 的 reference_path、decoded_path（同 `metric/gradient-screen-50/select_samples.py` L18、L95–L106 的取法）。128 能被 8 整除，上下翻转不改变网格相位；脚本按 MSE 自动判断翻转，结果 0 张需要翻转。
- 需 Alpha 且非恒定的图用 RGBA 四通道，否则 RGB。
- 输出：`industry-probe.csv`、`industry-probe-summary.json`。

三张已知图名次（越小越可疑；分母 196，blend 两项分母 106 张 Alpha 图）：

| 指标 | 0615 | 0616 | 0617 |
|---|---:|---:|---:|
| 原生 PSNR（同 196 张） | 118 | 114 | 111 |
| ERT 平滑加权 MSE（8×8 块、σ阈 18、10×，均值汇总） | 105 | 114 | 102 |
| ERT 平滑块误差占比 | 55 | 77 | 74 |
| astcenc -b 1.8 加权 PSNR | 115 | 114 | 108 |
| astcenc -v 活动度加权 PSNR（r=3，stdev 50） | 105 | 112 | 109 |
| 黑/白底上界 RMSE（Alpha 图） | 78/106 | — | 75/106 |
| 黑/白底上界 × ERT 平滑权重 | 83/106 | — | 72/106 |
| 对照：连续接缝分（screen-128.csv，138 张可算） | 7 | 12 | 20 |

ultrasmooth 区域块数（原图）：0615=0，0616=0，0617=199；196 张中 59 张 >0（最多 832 块：0789）。

### 5.2 块级最大池化（`block_pool_probe.py`）
命令：在本目录 `uv run --no-sync python block_pool_probe.py`。8×8 块，ERT 权重 × 块 MSE，只取 2≤σ_max<18 的“平滑但非平坦”块，取全图最大值或前 4 块均值。输出 `block-pool-probe.csv`。

| 指标 | 0615 | 0616 | 0617 |
|---|---:|---:|---:|
| 最大块 | 22 | 104 | 73 |
| 前 4 块均值 | 14 | 96 | 69 |

前 4 块均值的前 10 名：583、584、593、456、790、464、523、476、477、365。

### 5.3 解读（推断）
- 平滑度加权只改变误差的空间权重，汇总后仍主要反映误差能量。三张已知图的误差能量不突出，名次接近 PSNR。
- 块级最大池化对 0615（局部 8 像素平台）有效，对 0616/0617 无效；后两者的损伤是许多中等误差沿网格排成长线，正是连续接缝分的设计对象。
- 因此工业平滑权重更适合当**接缝分的门控或加权**，例如只在 σ_max<18 的相邻块之间计接缝段，或按两侧块 ERT 权重加权，不宜单独使用。本次未实测该组合。
- 没有人工标注，以上名次只说明与三张已知图的一致程度，不代表精确率或漏报率。

## 6. 无法访问或未核实
- Arm documentation-service：WebFetch 域名安全检查失败，curl 成功。
- Griffin & Olano TVCG 2015 全文：非开放获取，只读到 PubMed/NIST 摘要。
- Griffin I3D 2014 PDF 超 WebFetch 10 MB 上限，改用 curl。
- ETC2 原论文、GH07 幻灯片：未打开全文，只用检索摘要。
- RAD Oodle Texture 产品页、DirectXTex options.md、2004 年 Game Developer 杂志关于预乘 Alpha 的说法：仅检索摘要。
- NVTT、Compressonator、ISPC texcomp 的平滑区处理：未找到可定位来源。
- Qualcomm/Apple/Imagination 关于渐变需要小块的指导：未找到可定位原文。
- Unity 手册关于特效/渐变贴图压缩的建议：未找到明文。
- astcenc `-b`/`-v` 的实际编码 A/B 探针：时间限制未运行。本地可用旧版 `reproductions/texnn/upstream/Binary/Win32/astcenc.exe`（支持 `-b`、`-v`），3.3 源码需自行编译。
