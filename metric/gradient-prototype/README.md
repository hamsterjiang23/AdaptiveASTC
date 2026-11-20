# 高 PSNR 下的渐变失真原型

**保留 Unity 原生 PSNR 作为主标准。辅助检查推荐沿渐变方向量台阶，并用软权重网格分扩大可测范围。** 三张已知图的这两项分数都超过了各自全部 32 个等原生 PSNR 对照。旧平台分仍能帮忙定位短而孤立的台阶。 `[verified: evidence/summary.json 的 matched_controls；本报告“适用边界”]` `[opinion]`

[逐图与逐种子 CSV](evidence/scores.csv) · [覆盖率、排名和对照统计](evidence/summary.json) · [原图渐变区域对比](evidence/source-masks.png)

## 计算方法

| 信号 | 计算方式 | 输出含义 |
|---|---|---|
| 原图渐变区域 | 在 7×7 和 11×11 窗内拟合二阶曲面，检查解释方差、拟合幅度及结构张量相干性。对比原有一阶掩膜，另测四维 \((\alpha L^*, \alpha a^*, \alpha b^*, 100\alpha)\) 输入。 | 仅从原图标出候选渐变区域，记录面积与最大连通区。四维表征是工程权重。 `[verified: source_support.py 的 _fit_energies、_source_orientation、source_support；run.py 的 source_field、area_summary]` `[opinion]` |
| 方向性台阶 P95 | 沿原图局部颜色变化最大的方向采样。以双线性插值取得 5 个单位间隔，要求原图沿同一方向平滑变化。用相邻间隔压平程度乘以中间新增的色差跳变，再取加权 P95。 | 值越大，支持区域里的明显台阶越严重。另记录 P99、峰值、坐标和有效剖面数。 `[verified: distortion.py 的 normal_steps]` |
| 软权重网格分 | 比较真实块网格与错开 1–7 像素的网格。每个相位按原图渐变权重取额外色差跳变的 P95，再用真实相位减去错位相位中位数并截到非负。 | 值越大，额外跳变越集中在 ASTC 网格上。支撑不足时留空，同时记录有效相位数、有效样本量及权重。 `[verified: distortion.py 的 grid_phase]` |
| 切向误差 | 取原图梯度的垂直方向，测解码减原图的残差沿该方向的变化。另试验先以 2 像素高斯尺度平滑有符号残差，再求导。 | 用于诊断沿轮廓的额外波动。平滑口径在三个已知案例上探索，适用性需用新图再检验。 `[verified: distortion.py 的 tangential_error、measure_distortion]` `[opinion]` |

多通道梯度方向借鉴 Di Zenzo 的张量定义。这里使用 8 位展示 RGB 转 CIELAB 计算失真分。对透明素材先在线性光下分别合成深灰和浅灰背景，然后回到 sRGB；两种背景的分数单独记录。 `[verified: Di Zenzo 原文 p.116–118；run.py 的 linear_light、composite、measure_asset]` [Di Zenzo 原始论文](https://people.csail.mit.edu/tieu/notebook/imageproc/dizenzo86.pdf)

## 五个案例

固定 8×8 fastest。透明图表中取深灰底，不透明图取 RGB。重排对照按原图亮度和 Alpha 分箱，合法地交换完整 RGBA 残差向量。逐种子核对四通道误差平方和，并用 Unity 原生 DLL 复算 **160 个重排候选**。原生 PSNR 与各自真实压缩完全相同。透明图重新合成后的展示 RGB PSNR 会有变化，范围见 JSON。 `[verified: run.py 的 measure_asset、groups_for_shuffle；evidence/summary.json 的 matched_controls]`

| 贴图 | 原生 PSNR | 旧掩膜 → 二阶掩膜 | 方向性台阶，真实 / 32 个对照最高 | 网格分，真实 / 32 个对照最高 |
|---|---:|---:|---:|---:|
| 0615 白色渐隐弧 | 36.99 dB | 15.63% → 20.96% | **1.42 / 0.73** | **5.26 / 2.10** `[verified: scores.csv 的 615/dark/fastest；summary.json 的 615/dark]` |
| 0616 蓝色光晕 | 36.88 dB | 31.84% → 42.61% | **0.522 / 0.005** | **7.27 / 0.79** `[verified: scores.csv 的 616/rgb/fastest；summary.json 的 616/rgb]` |
| 0617 灰色圆环 | 36.45 dB | 19.76% → 33.72% | **2.25 / 0.45** | **8.27 / 0.82** `[verified: scores.csv 的 617/dark/fastest；summary.json 的 617/dark]` |
| 0544 金色细线 | 36.40 dB | 0 → **9 个像素** | 空 | 空 `[verified: scores.csv 的 544/dark/fastest；summary.json 的 544/dark]` |
| 0698 环境贴图 | 40.90 dB | 11.50% → 14.51% | **0.88 / 0.38** | **4.00 / 0.42** `[verified: scores.csv 的 698/dark/fastest；summary.json 的 698/dark]` |

蓝色光晕 0616 的展示 RGB PSNR 在全部对照中也是 **36.8842 dB**。实测真实台阶分 **0.522**，同 PSNR 打散最高 **0.005**。另一个真实项目贴花 0467 的原生 PSNR 只相差 **0.0035 dB**，两张图的网格分分别为 **7.27 和 2.00**，方向性台阶分只差 **0.039**。这组近分真实对照说明两项指标各有响应。 `[verified: summary.json 的 616/rgb；scores.csv 的 467/rgb/fastest 与 616/rgb/fastest]`

## 适用边界

- 在固定 8×8 fastest、128×128、原生 PSNR ≥35 dB 的 **110 张开发图**上，新网格分由旧扣错位接缝分的 **82/110** 扩至 **109/110** 可测，也高于旧块边界 P95 的 **99/110**。新网格分排序时三张已知图排第 **2、6、16**。在两代网格分和方向性台阶等都可测的同一批 **82 张**里，旧扣错位接缝分排第 **2、4、5**，新网格分排第 **2、6、13**。新分提升的是覆盖率，这批已知图靠旧分排得更集中。 `[verified: summary.json 的 coverage、rank_among_valid_rows；本轮 scores.csv 共用可测集重排]`
- 未平滑的切向分在三张截图的主展示方式下均低于各自全部 32 个重排对照，对像素级随机起伏敏感。平滑后，在三个主展示方式中均超过 32 个对照，但白弧浅灰底仍有 **3/32** 个对照不低于真实分。 `[verified: summary.json 的 615/dark、615/light、616/rgb、617/dark]`
- 0544 改用二阶仍只有深灰底 9 像素、浅灰底 0 像素，当前网格分与正常方向上的台阶分都缺测。0698 的 thorough 与 exhaustive 原生 PSNR 为 **42.4167 / 42.5236 dB**，旧平台分为 **385 / 60**，新方向性台阶 P95 都是 **0.2124**。这两张说明细线和极小的局部异常仍需要保留旧平台定位。 `[verified: scores.csv 的 544 与 698 两档；../gradient-screen-50/individual-scores.csv L102–103、L114–115]` `[opinion]`
- 三张截图来自同一素材目录。这轮使用开发集和人工构造的机制对照，没有新增质量标签。使用已有原生 PSNR 判定，按辅助指标安排复核。 `[verified: ../gradient-screen/fixed8-validation.csv L66、L105、L165；run.py 的 load_jobs、shuffled_decode；evidence/summary.json 的 cohort_rows、matched_controls]` `[opinion]`

## 复跑

```powershell
uv run --no-sync python metric/gradient-prototype/run.py --output metric/gradient-prototype/evidence-repeat --seeds 32 --cohort128 --workers 4
```

依赖原生开发集归档、既有 8×8 清单和 Unity 质量 DLL。小样本用 `--seeds 1`，省略 `--cohort128`。CSV 空值表示当前条件无法评分。 `[verified: run.py 的 MANIFEST、NATIVE_BUILD、load_jobs、main；distortion.py 的 normal_steps、grid_phase]`
