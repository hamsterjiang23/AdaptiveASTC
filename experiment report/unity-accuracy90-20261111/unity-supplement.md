# Unity候选补测：两图执行核验

两张已归档训练图各完成20组候选编码、解码与质量测量。原搜索测过10／6组，本次分别补齐10／14组；原选中候选的payload和RGBA解码像素逐字节一致，原搜索16组指标在原记录两位小数的精度内一致。`[verified: unity-supplement2-bound.json rows]`

## 实现与数据口径

- 从当前`ASTCCompressor.cpp`的L2182–2675原样提取PSNR、MS-SSIM、法线角度函数及其辅助函数，以MSVC `/fp:precise`编译独立评价DLL。抽取源码只保存在.local，公开实现仅包含提取器、薄封装和CMake配置，来源SHA／函数区间／生成源码SHA见[指标核验](unity-quality-probe.json)的metric_build。`[verified: quality.py；native/quality_wrapper.cpp；unity-quality-probe.json metric_build]`
- 编码和解码直接调用归档采集使用的`astcenc-avx2-shared.dll`，运行前沿原采集协议锁核对identity与原DLL的SHA。候选顺序为12／10／8／6，各自fastest／fast／medium／thorough／exhaustive，对应quality0／10／60／98／100；RDO与normal pack关闭。`[verified: supplement.py UnityASTCBackend；unity-supplement2-bound-config.json]`
- 输入保留RGBA，并从导出PNG的上行起点翻转到Unity内存顺序；保存的候选PNG再转回通常的上行起点。MS-SSIM降采样遇到奇数尺寸时也依赖此顺序，所以质量评价直接使用原内存顺序。`[verified: supplement.py collect_image；ASTCCompressor.cpp Downsample2x2；opinion: 方向一致性的意义]`
- Unity PSNR计入非恒定Alpha，且只平均误差非零的参与通道。第一个样本的RGB PSNR约34.55dB，而Unity原生PSNR为30.03074dB，原报告保存30.03dB。GDC的RGB均方误差不能直接替代Unity指标。`[verified: quality.py提取的CalculatePSNR；unity-quality-probe.json rows[0]；归档参考receipt首行]`
- 补测重新编码全部20组，其中原搜索覆盖的组用于重放核验。编码、解码、质量测量和整个补测墙钟单独记录，原搜索标签及原baseline文件不变。当前CPU测量与CUDA训练同时发生，不用于宣称部署加速。`[verified: unity-supplement2-bound.json config.scope、rows.cost；原始记录读取路径；opinion: 性能边界]`

## 核验结果

| 样本 | 原搜索候选 | 本次完整候选 | 新覆盖候选 | 原选中payload／解码 | 原指标对比 |
|---|---|---|---|---|---|
| icon_point01，14×14 | 10 | 20 | 10 | 一致 | 10组在0.00501dB内一致。`[verified: unity-supplement2-bound.json rows[0]]` |
| New13，24×24 | 6 | 20 | 14 | 一致 | 6组在0.00501dB内一致。`[verified: unity-supplement2-bound.json rows[1]]` |

原搜索低于PSNR阈值时不会计算MS-SSIM，因此原表中的0不能作为真实SSIM标签。补测对全部sRGB候选计算该值；仅对原表中实际计算过的MS-SSIM做一致性检查。`[verified: ASTCCompressor.cpp L3206–3218；supplement.py collect_image]`

原生函数与采集绑定另通过6项测试：原DLL身份链拒绝篡改、提取边界、候选表重复拒绝、边缘ASTC块字节数、PSNR参与通道／Alpha语义、恒等图MS-SSIM与解析法线角度。后两项实际调用本轮编译DLL，未跳过。`[verified: tests/test_unity_supplement.py；pytest输出6passed]`

## 保留的失败与限制

- 第一次CMake配置失败，因为传入生成源码的Windows反斜杠被当成转义符；改为正斜杠后使用新目录重建。原build-0.log保留在.local/unity-quality-native，成功版本在unity-quality-native-retry1。`[verified: 两个build-0.log；quality.py build命令]`
- 第一次指标对比采用1e-4dB容差，而原缓存仅保留两位小数。该失败比较已归档，当前结论明确为原记录精度内一致，未声称未舍入值完全一致。`[verified: unity-quality-probe.json prior_comparison、comparison]`
- 复核后将payload复制移出解码计时，并补齐原采集协议锁→identity／phase→原DLL及完整路径顺序的自动核验。新身份`unity-supplement2-bound`重跑40候选通过；此前两次试跑及其计时保留，旧源码另有归档。`[verified: unity-supplement2-bound.json capture_binding、source_files_sha256；implementation-notes对应记录]`
- 当前实图验证仅覆盖普通LDR Default颜色图。Alpha需求与非HDR属性是经原payload和指标重放核验的推定设置，正式采集仍需直接记录实际编码回调参数。法线分支只通过数学样本，真实法线、HDR、其他纹理类型和完整20候选生产覆盖均未验收。`[verified: unity-supplement2-bound.json config.items.metadata_source；supplement.py类型限制；tests/test_unity_supplement.py]`
- Unity训练还需RGBA输入及逐通道误差目标；其全图参与通道数、Alpha恒定判断、MS-SSIM与法线p95不能简单用局部PSNR的平均替代。应保留原始RGBA和完整候选解码结果，再按对应原生规则构造监督。`[verified: ASTCCompressor.cpp CalculatePSNR、CalculateMSSSIMDb_Luma、CalculateNormalAngularErrorMip0To3；opinion: 迁移设计]`

## 复跑入口

使用[配置](unity-supplement2-bound-config.json)中的冻结路径和SHA，改用新的输出／报告目录后运行；完整逐候选记录、RGBA解码PNG和ASTC保存在.local，公开[结果](unity-supplement2-bound.json)绑定其SHA。`[verified: supplement.py run；对应配置与结果]`

```powershell
uv run --frozen python script/unity_supplement.py build-metrics --engine-source <ASTCCompressor.cpp> --output <新的本地构建目录>
uv run --frozen python script/unity_supplement.py collect --config <新的补测配置.json>
```
