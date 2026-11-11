# Unity候选补测与原生指标核验

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

## 后续实际编码参数采集

[两图实际参数记录](unity-actual-options2.json)来自重新启动的Editor，共16次原搜索回调。两图实际`need_alpha=true`、profile0即LDR sRGB、normal pack关闭，输入通道为RGBA32。对回调指针内存做SHA-256，与归档PNG按Unity行序还原后的字节完全一致。整次启动／采集268.67秒，包含脚本编译、预热、PNG导出及哈希开销，不能替代原搜索baseline计时。`[verified: unity-actual-options2.json rows；jobs/unity-options2/receipt.json；astccustom.cs AstcEncProfile]`

入口临时给原managed回调添加记录调用，原编码调用保留。原文件和改后文件先写入独立恢复目录并落盘，回调记录失败继续原编码、由采集审计拒绝缺失数据；正常结束和异常路径均执行受保护恢复，发现第三方独立修改时拒绝覆盖。实测原始与恢复源码SHA均为`64dfbd63ce9baf390299ff70881b38fb6505bacab8d1ff42e0a8507447ef7265`，meta恢复0冲突。`[verified: metadata.py ManagedCaptureHook、UnityOptionCapture.run；unity-actual-options2.json managed_source_restoration；原probe-receipt.json]`

审查后补齐了候选身份核验：合法footprint、私有format枚举、preset质量值、原表已测候选覆盖及原winner成员关系。对同一归档记录重新核验通过，结果另存[严格核验记录](unity-actual-options2-revalidated.json)，原结果与运行时源码快照保留。此复核没有重新运行Editor或编码。`[verified: unity-actual-options2-revalidated.json scope、candidate_keys；tests/test_unity_metadata.py]`

[实际参数绑定补测](unity-supplement2-actual.json)再次完成40组候选，原16组指标吻合、新增覆盖24组，两图原选中payload和RGBA解码逐字节一致。补测墙钟0.92785秒，当前与CUDA训练并行。配置显式绑定实际参数记录及原始回调日志SHA，Alpha/profile不符、原日志改变或来源采集不同会拒绝运行；此前基于重放推定的结果继续保留历史身份。`[verified: unity-supplement2-actual.json metadata_binding、rows、wall_seconds；supplement.py verify_actual_options]`

固定[64张训练图采集](unity-actual-options64.json)通过，共558次回调，覆盖63 Default和1 NormalMap、63 sRGB和1 Linear；needAlpha为true／false的图数分别31／33。源码恢复哈希一致，meta恢复0冲突；进程637.63秒，其中输入SHA计算合计74.20秒，该数值不含全部日志与导出成本。`[verified: unity-actual-options64.json rows；jobs/unity-options64/receipt.json；smoke1-receipt.json]`

NormalMap样本为4096²，实际normal-pack=false，不能将pack标志直接当作法线用途。采集完成只证明参数与参考像素覆盖；离线补测目前仍只接收LDR Default颜色图，真实法线／HDR补测与全量生产数据仍未验收。`[verified: unity-actual-options64.json NormalMap row；supplement.py collect_image；opinion: 完成边界]`

## 颜色覆盖扩展与真实法线审计

[八图补测](unity-color8.json)绑定64图实际回调记录，覆盖1×1、5×2、4×1、8×9、512²、1024×607、2048²和1024²；全部160候选完成编码／解码／质量测量，原52组指标在两位小数容差内一致，新增108组。8张图原winner的payload与解码像素均一致，包括first-valid、size-first-strict和size-first-relaxed标签分支。进程52.79秒，收集循环52.43秒，与CUDA训练并行，成本不替换原搜索baseline。`[verified: unity-color8.json rows、wall_seconds；jobs/unity-color8/receipt.json]`

[法线20候选审计](unity-normal20-policy.json)使用64图中的4096² NormalMap，导入mipmaps=false、实际Linear profile1、needAlpha=false、normal-pack=false。复用原搜索留下的20个ASTC，逐个重新解码后与原候选PNG逐像素核对，再用原样提取的原生函数计算PSNR、法线平均角度与p95角度，均在原报告两位小数精度内一致。实际新编码次数为0；该结果验证真实法线mip0的解码与质量评价，未覆盖法线重新编码或多mip。`[verified: unity-normal20-policy.json input_options、rows、encoded_candidates、native_mip_evidence]`

20组均未达到平均角度≤3.2°且p95≤9°的要求。原选中6×6/exhaustive的PSNR为31.32078dB、平均角度2.93632°、p95为11.59958°，因此属于最高PSNR回退。即使PSNR超过30dB、平均角度合格，也不能把这个结果标为法线质量达标。`[verified: unity-normal20-policy.json quality_passing_candidates、original_selection、rows[19].metrics]`

审查修正两处边界：原报告状态可能带`Valid [BEST]`；角度门槛必须采用真实tableConfig并还原float32，避免Python双精度3.2错误拒绝原生float32(3.2)的等值候选。原先的[首次审计](unity-normal20.json)保留，修正后的审计使用新目录重跑，通过20组比较，进程21.40秒、循环15.93秒。原tableConfig、源SHA及运行代码SHA随结果归档。`[verified: tests/test_unity_normal_audit.py；unity-normal20-policy.json native_policy_binding、source_files_sha256、wall_seconds；jobs/unity-normal20-policy/receipt.json]`

```powershell
uv run --frozen python script/unity_supplement.py audit-normal --config <新的法线审计配置.json>
```

对应配置为[颜色八图](unity-color8-config.json)与[法线审计](unity-normal20-policy-config.json)。全量train／validation导入参考与完整候选仍待收集，HDR及多mip法线未验证。资源与读写依赖见[实验成本表](../../references/task-costs.md)。`[verified: 对应配置；opinion: 后续范围]`

```powershell
uv run --frozen python script/capture_unity_options.py run --config <新的采集配置.json>
uv run --frozen python script/capture_unity_options.py audit --config <采集配置.json> --report <新的审计记录.json>
uv run --frozen python script/capture_unity_options.py restore --journal <managed-hook目录>
```

采集配置包含project、editor、manifest、run_id、phase和report。原phase支持probe／smoke1／smoke2／smoke3；显式分批增加`phase=batch`、`source_split=train/validation`和1至256个`capture_paths`。每批路径须属于冻结划分且不可跨划分重复，参考manifest保留原划分，test／calibration不进入开发采集。独立restore要求项目关闭，只恢复原字节或本次补丁可识别的文件状态。`[verified: metadata.py UnityOptionCapture.run；benchmark.py prepare；unity_reference.py collect；capture_unity_options.py main]`

## 真实法线重新编码

先按[选中候选配置](unity-normal-replay-winner-config.json)重编码6×6/exhaustive，完整ASTC及RGBA解码逐字节一致；再按[全部候选配置](unity-normal-replay20-config.json)完成20次重编码，20组均一致。输入和实际needAlpha=false／Linear profile1／normal-pack=false、原DLL、原生指标及源码身份均由既有采集链绑定，结果见[完整重编码记录](unity-normal-replay20.json)。本轮只覆盖这一张4096²、mip0法线图。`[verified: unity-normal-replay-winner.json rows.reencoding；unity-normal-replay20.json input_options、rows.reencoding、native_mip_evidence]`

20组纯编码合计124.1963秒、重编码后的解码0.4525秒，审计循环170.1485秒、全进程174.1805秒；循环还包含原候选归档、原解码／指标核验和输出写盘。这些成本与CUDA训练重叠，不能替换独立搜索baseline或作为部署加速结果。新ASTC与上行起点RGBA PNG保存在独立reencoded目录，原搜索产物保持原身份。`[verified: unity-normal-replay20.json rows.reencoding、wall_seconds；.local/jobs/unity-normal-replay20/receipt.json；normal_audit.py replay_candidate；opinion: 计时边界]`

`audit-normal`配置的`reencode`可取none／winner／all，缺省none；记录尝试数、成功数与当前候选，失败时保留新产物和失败记录。重编码仍要求实际normal-pack=false，HDR和多mip不会被这次通过结果覆盖。`[verified: normal_audit.py run/replay_candidate]`

## 分批采集的异常恢复

正常结束与可捕获异常仍自动恢复meta和managed源码。若采集进程被强制终止，先确认该工程Editor已退出，再用以下入口分别恢复meta与源码；`recover --phase batch`会核对冻结批次身份、路径／划分和协议哈希，拒绝改变过的配置。它只开放恢复，不能绕过原baseline入口启动batch。`[verified: benchmark.py run/restore_metadata；metadata.py run；script/reproduce.py recover分支；test_unity_reference_batches.py CLI恢复与拒绝用例]`

```powershell
uv run --frozen python script/reproduce.py recover --phase batch --run-id <批次run_id> --project <原工程路径> --editor <原Editor路径> --manifest <原manifest路径>
uv run --frozen python script/capture_unity_options.py restore --journal <该批次的managed-hook目录>
```

## 验证划分的真实采集闭环

[两张validation图](unity-validation2.json)使用[固定配置](unity-validation2-config.json)完成7次原搜索回调，实际输入哈希吻合；归档manifest只包含validation，源码恢复SHA一致、meta恢复0冲突，进程370.06秒。第一张源RGB512²导入后为256²，第二张仍为512²，两图实际needAlpha分别false／true。`[verified: unity-validation2.json rows、managed_source_restoration；.local/unity-validation2-20261111/references/normalized-batch/manifest.json；batch-receipt.json；jobs/unity-validation2/receipt.json]`

随后按实际参数[补测40候选](unity-validation2-supplement.json)，新增33组，原搜索已测7组指标与两个选中payload／解码一致；收集循环3.8977秒，与CUDA训练并行。该小样本验证了validation身份在导出和候选补测中的传递，不代表完整验证集或最终测试验收。下一批训练参考路径已冻结在[256图配置](unity-train256-batch001-config.json)，排除已采集actual64中的路径。`[verified: unity-validation2-supplement.json rows、wall_seconds；unity-train256-batch001-config.json capture_paths；opinion: 完成边界]`

## 颜色与提前停止法线的统一补测

新增`script/complete_unity_candidates.py`及`UnityCandidateCompletion`，继承既有颜色补测流程，增加原搜索提前停止后的法线候选补齐。读取已完成采集的归档参考图和选中ASTC，不依赖活动工程中的调试候选目录，也不打开Editor。原搜索label／提前停止／基线产物保持，补测单列计时。运行中的参考采集所依赖的原supplement／metadata／collection实现未修改。`[verified: candidate_completion.py、complete_unity_candidates.py；git diff及已冻结collection SHA；opinion: 运行边界]`

法线范围明确为实际回调Profile1、normal-pack=false、RGBA8、Linear、Tex2D、mipmaps=false的mip0图；needAlpha按实际值。补测配置绑定导入日志SHA及扩展源码SHA；原搜索已测候选复核PSNR与mean／p95角度，选中候选完整ASTC与解码像素一致，ASTC header的footprint须与原label一致。多mip、HDR和normal-pack=true仍拒绝执行，不能用本次结果覆盖这些分支。`[verified: candidate_completion.py verify_normal_imports、verify_actual_options、collect_image；test_unity_candidate_completion.py；opinion: 验证范围]`

| 真实三图探针 | 全部候选 | 原已测／新测 | 结果 |
|---|---|---|---|
| 256²法线图 | 20 | 3／17 | 原PSNR、角度及winner完整ASTC／解码一致。`[verified: unity-candidates-train256-smoke-v2.json rows[0]]` |
| Linear颜色图 | 20 | 3／17 | 原指标及winner payload／解码一致。`[verified: unity-candidates-train256-smoke-v2.json rows[1]]` |
| 带Alpha颜色图 | 20 | 9／11 | 原指标及winner payload／解码一致。`[verified: unity-candidates-train256-smoke-v2.json rows[2]]` |

[最终探针配置](unity-candidates-train256-smoke-v2-config.json)与[结果](unity-candidates-train256-smoke-v2.json)保留60次真实编码，45个候选此前未测；进程11.89秒，与参考采集和CUDA训练重叠。此前不额外复核normal header的[先期探针](unity-candidates-train256-smoke.json)及其源码快照保留，正式运行绑定的是最终探针的扩展源码。`[verified: 两份smoke报告；.local对应jobs/unity-candidates-train256-smoke-v2/receipt.json、source快照；opinion: 成本边界]`

[256图正式配置](unity-candidates-train256-config.json)已通过实际参数和导入范围检查，包含240张Default、16张NormalMap，共5120候选，正式进程已启动。每张图完成后写.local的`unity-candidates-train256/receipt.json`，完整成功才发布汇总；当前状态随[progress.json](progress.json)记录。已有原候选也重新编码以核验一致性，因此“新增覆盖数”与“实际编码次数”分别计量。`[verified: unity-candidates-train256-config.json items；preflight.json；job receipt；UnitySupplementalCapture.run；opinion: 状态与成本口径]`

```powershell
uv run --frozen python script/complete_unity_candidates.py --config "experiment report/unity-accuracy90-20261111/unity-candidates-train256-config.json"
```

上面的身份已启动，保留运行产物，不重复执行或覆盖；下一批使用新的配置／输出身份。四项扩展测试及既有原生指标测试分别核验重复／缺失角度行、导入SHA变化、多mip拒绝、源码身份与错误ASTC header拒绝。真实探针验证的是已列三图，不等于全部256图通过。`[verified: test_unity_candidate_completion.py；test_unity_supplement.py；实际smoke-v2；opinion: 运行约束]`
