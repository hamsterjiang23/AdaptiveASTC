# AGENTS.md

## 适用范围与研究定位

- 本文件适用于 `E:\ASTC_Compression` 全目录，执行任务时同时遵循用户提供的全局规则。`[opinion]`
- 当前研究主题为ASTC纹理压缩块大小自动选择，关注质量、真实字节数与处理成本的权衡。`[verified: README.md“当前状态”“已核实的方法与待核实问题”]`
- 以固定8×8为当前生产基线，研究机器学习预测参数后执行一次最终压缩。PSNR 35 dB按项目经验判据记录，法线与MSAK贴图的标准和Unity导入后训练数据的获取方式按待明确事项处理。`[verified: README.md“项目需求与优化目标”]`
- 优先研究原始块大小分类上的calibration，分类校准路线经实验仍达不到项目目标时，再研究质量预测回归的calibration。分别评价概率校准、标签正确率和最终压缩质量违规率。`[verified: README.md“研究顺序与分类校准”]`
- 开始任务先读 [README.md](README.md)，按任务需要读取对应资料和检查记录。研究题目、算法路线与新增实验范围以用户确认的内容为准。`[opinion]`

## 文献发展路线与研究定位

- 完整问题链见[README的发展路线](README.md#文献发展路线与问题演进)，每项工作按“已有问题 → 方法改进 → 剩余限制”阅读和维护。`[verified: README.md“文献发展路线与问题演进”]` `[opinion]`
- **编码加速路线**。昂贵配置搜索 → FasTC／SegTC的结构近似和Web ASTC的启发式 → TexNN的块内部配置预测；Pruned ASTC另以配置裁剪和下游重训练换取低延迟。记录格式、质量损失和任务用途。`[verified: README.md“编码器加速，从昂贵搜索到近似与学习”]` `[opinion]`
- **自动选参路线**。固定参数与人工设置 → 2022年目标PSNR搜索 → 2023年astcenc内部集成。GDC 2023另展示离线试压缩标签与ResNet整图选参，本项目优先研究该分类路线的calibration。VBTC作为图内可变分配的系统分支记录。`[verified: README.md“自动选参，从统一配置到质量约束与学习式决策”“研究顺序与分类校准”]`
- **质量评价路线**。贴图误差 → 多视点渲染比较 → diffuse／normal掩蔽的主观实验、任务专用可见性指标与FLIP误差图。分别记录纹理指标、渲染指标、观看条件和人类接受标准。`[verified: README.md“质量评价，从贴图误差到渲染可见性”]` `[opinion]`
- **表示与部署路线**。NTC联合材质通道与mip，后续分别研究BC特征／NBC的表示、DBC的任务损失、cooperative vectors的硬件加速、hypernetwork的逐材质优化成本及共享解码器的执行分歧。NTBC加载重建、高斯、JPEG和TexF分支分别保留其存储、采样与运行时条件。`[verified: README.md“神经纹理，从联合表示到硬件、训练与解码效率”“其他表示与系统分支”]`
- 直接继承关系以作者明确表述为依据，跨论文的问题链标为综述归纳。Multi-output ASTC归入解码电路，ASTC Encoding Survey作为技术地图；本项目的新颖性与质量／字节收益以进一步文献核实和独立实验评价。`[verified: README.md对应路线及“AdaptiveASTC在这些路线中的位置”]` `[opinion]`

## 目录与资料维护

- `README.md` 汇总项目定位、进展、资料入口、相关研究和综述完整书目。新增研究资料时优先补入已有分类。`[verified: README.md“从这里阅读”“学术综述与相关研究”]` `[opinion]`
- `materials/gdc2023-astc-parameter-selection/source/` 保存视频、原始双语字幕和元数据。按原件维护，校订内容写入 `transcripts/` 并保留字幕条目及时间戳映射。`[verified: README.md“资料目录”]` `[opinion]`
- `materials/gdc2023-astc-parameter-selection/frames/` 保存定时截图和关键页截图。新增截图使用能识别视频时间点的文件名。`[verified: README.md“资料目录”“视频与处理口径”]` `[opinion]`
- `notes/` 保存阅读笔记，`implementation-notes.md` 记录取舍与边界问题，`verification.json` 保存已执行检查的结果。`[verified: README.md“从这里阅读”]`
- Obsidian副本位置由README记录，跨目录同步按用户本次授权范围执行。`[verified: README.md“资料目录”末段]` `[opinion]`

## 文献与证据要求

- 技术结论优先引用论文原文、作者项目页、官方规范与对应代码。引用定位到章节、页码、表格、视频时间戳或代码行。`[opinion]`
- 每项事实、推断和建议使用行内标记。实际读取的证据使用 `[verified: 可定位来源]`，推断、研究设想和建议使用 `[opinion]`。`[verified: 用户提供的全局规则“Output Style — Epistemic Markers”]`
- 分别标明原文结果、综述转述、本地复现结果和研究提议。摘要阅读、全文阅读、书目转录与原文访问失败分别记录核实深度。`[opinion]`
- 综述完整书目保留原编号和书目信息。新增独立论文放入相应导读分类，并附稳定论文链接、DOI或arXiv编号。`[opinion]`
- 演讲正文当前整理为有标签的块大小分类流程。官网简介中的强化学习表述与正文机制的关系，继续按待核实问题记录。`[verified: README.md“需要保留的证据边界”]`
- 分开描述整张纹理的块大小选择、块内部编码配置预测、存储侧压缩和运行时解码，分别说明格式、硬件与过滤要求。`[opinion]`

## 实现与实验

- 当前执行顺序为Unity搜索baseline、Nah 2023、Nah 2022、TexNN、GDC，再研究新模型与校准。新增方法代码集中在`reproductions/`，启动入口仍放`script/`。先完成10,000张训练图的真实搜索计时报告，再启动正式文献实验。缺作者代码时允许论文重实现，原文设置、补全假设和实际完成状态分别记录。`[verified: 用户2026-11-10实施请求及复现标准选择]`
- 正式文献实验通过`BaselineGate`检查10,000张覆盖、原生搜索记录、源图哈希核验、退出码与metadata恢复。Unity基线按实际进入ASTC的目标格式测量，临时Android覆盖与恢复、参数缓存隔离和计时区间见[复现入口](reproductions/README.md)。`[verified: reproductions/common/upstream.py BaselineGate；reproductions/unity_search_baseline/benchmark.py]`
- 技术失败补测使用独立空缓存，保留初次失败记录与退出码，合并结果使用`passed_with_retries`并校验来源SHA-256。初次批次、补测批次、逐图计时与整轮墙钟分别记录。`[verified: reproductions/unity_search_baseline/recovery.py；reproductions/common/upstream.py BaselineGate]`
- TexNN已取得用户提供的主文，精确网络结构等待用户补充单独的Appendix Tables S1/S2。主文归档、SHA-256与当前状态保留在`reproductions/texnn/`。`[verified: reproductions/texnn/source.json；用户回复“暂时没有等我补充”]`
- 实验协议、数据、训练、校准、成本及验证报告统一保存在`experiment report/`，逐图清单、缓存、原始日志、预测和检查点保存在该目录的`.local/`并Git忽略。`[verified: 用户确认的GDC复现计划及报告目录要求]`
- Python环境和依赖统一使用uv，提交`pyproject.toml`、`uv.lock`与`.python-version`；安装使用`uv sync --frozen`，实验和检查使用`uv run`。`[verified: 用户要求“仓库里使用uv进行python依赖管理”；pyproject.toml]`
- 实施前检查已有文件、工具和入口，采用完成任务所需的最小修改，保留用户已有工作。Git状态在实际操作前重新查询。`[opinion]`
- 先运行小样本压缩、解压、质量测量和字节统计，再扩大到完整数据集、训练或批处理。`[verified: 用户提供的全局规则“Smoke test first”；README.md“后续研究方向”]`
- 实验协议记录编码器版本、preset、候选块集合、颜色空间、通道用途、Alpha、mip、尺寸取整、容器与硬件。`[opinion]`
- 质量目标、标签生成规则、训练目标和部署质量复检分别定义。记录无可行候选、编码失败、质量违规及回退处理。`[opinion]`
- 对照优先覆盖当前生产使用的固定8×8，补充固定6×6、固定12×12和同质量目标下的搜索选参，学习方法与搜索方法使用一致的编码和测量口径。`[verified: README.md“当前生产基线与优化空间”]` `[opinion]`
- 分别报告数据准备、训练、预测和最终编码耗时，以及体积、质量分布和失败率。跨资产或跨项目划分时检查近重复数据泄漏。`[opinion]`
- 实验状态以本次运行日志和产物为依据。`verification.json` 中的历史资料检查与新增实验验证分别记录。`[opinion]`

## Unity训练数据采集与源码定位

- 训练数据导出任务先读[README源码导航](README.md#unity训练数据导出与源码导航)，再核对本机引擎文件哈希、函数和行号。README保存完整位置表、调用链、字段与采集条件。`[verified: 用户要求“全部整理到readme和agent里面”；README对应小节]` `[opinion]`
- 输入取自`ImageOperations.cpp`的`CompressTextureWithMultipleImages`取得的第一个image／mip0，经`PrepareOriginalImageData`转换／绑定为RGBA32。参考图采集从`SetupTestEnvironment → ExportImageToPNG`读取，源图与参考像素的等价性按样本实测。`[verified: ImageOperations.cpp L2947–2964；ASTCCompressor.cpp L2675–2694、L1999–2010]` `[opinion]`
- 主链为`FindOptimalASTCFormat → FindOptimalParameters → TestAllParameterCombinations → SelectBestParameter → SaveBestParametersToCache → SaveCacheEntryToFile`，分别定位到`ASTCCompressor.cpp`的L3738、L3435、L2958、L3364、L1935、L1836。`[verified: ASTCCompressor.cpp L3767、L3499–3522、L1975]`
- 采集前核对ASTC目标格式、自动选参开关、第三方编码／解码接口和磁盘调试开关。缓存命中在图片导出前返回，采集方式需显式记录缓存复用、重新测量、cache-hit及导出结果。`[verified: ImageOperations.cpp L2958–2968；ASTCCompressor.cpp L428–478、L2963–2970、L3437–3462]` `[opinion]`
- 维护资产路径、源MD4、参考图及其哈希、导入配置、尺寸、颜色空间、用途、Alpha、mip、Editor／DLL版本与tableConfig的对应关系。调试目录的纹理名和进程内计数用于定位产物，批量数据集通过清单建立稳定样本身份。`[verified: ASTCCompressor.cpp L2001–2009、L1964–1973、L3466–3499]` `[opinion]`
- 记录实际候选覆盖、编码／解码失败、earlyExit、valid与回退原因。常规搜索提前停止，大图允许MS-SSIM失败时采用PSNR通过候选，全部不合格时按最高PSNR回退。标签称为“当前策略选中配置”，最优性与质量达标分别评价。`[verified: ASTCCompressor.cpp L3121–3125、L3157–3158、L3262–3269、L3337、L3348–3419]` `[opinion]`
- 字段采用源码口径，PSNR仅平均误差非零的参与通道且排除恒定Alpha，msSsimDb为亮度MS-SSIM的dB转换，fileSize为本次参考尺寸payload，timestamp为写缓存时刻，rdo为最终采用精炼payload。法线角度、候选表与RDO尝试状态单独保存。`[verified: ASTCCompressor.cpp L2238–2304、L2456–2478、L3067–3072、L1964–1973、L657–666]` `[opinion]`
- 核对实际缓存目录、tableConfig、JSONL新增记录和快照合并，保留历史LITE与主包协议差异。锁或写入失败、源文件缺失及哈希失败需要纳入采集完整性检查。`[verified: ASTCCompressor.cpp L1178–1205、L1372–1397、L1836–1899、L1937–1939、L3506–3523；README对应小节]` `[opinion]`
- 源码静态定位、图片导出实测、候选压缩质量和训练效果分别报告。先验收小样本，再按用户授权范围扩展批量采集。`[verified: 用户“Smoke test first”要求]` `[opinion]`

### 术语口径

- 术语解释沿用[README完整术语表](README.md#压缩参数与图像术语)，分别记录压缩参数、亮度范围、颜色编码及贴图用途。`[verified: 用户要求“这些所有的术语的解释也放到agents和readme里面”；README对应小节]` `[opinion]`
- blockSize／block footprint为每个ASTC块覆盖的texel宽高，texel为纹理像素，块输出固定128 bit／16字节。4×4、8×8、12×12分别为8、2、约0.89 bpp，payload为原始块数据，mip链、容器与打包大小分别计量。`[verified: Arm《ASTC Format Overview》“Block compression”；ASTCCompressor.cpp L3067–3072；ImageOperations.cpp L2975–2985]` `[opinion]`
- preset统一称编码预设／编码档位，原交流“present速度”按preset解释。fastest至exhaustive控制编码搜索投入与时间／质量取舍，同图同尺寸同blockSize的payload容量相同，编码耗时和最终质量分别测量。`[verified: ASTCCompressor.cpp L620–625、L3067–3108；Arm astc-encoder README “Experimenting”]` `[opinion]`
- LDR为Low Dynamic Range，低动态范围，常见8位颜色分量0～255归一化到0～1。整数除以255只描述归一化，光强解释还取决于颜色编码。`[verified: Unity 2019.4《High dynamic range》“How HDR works”；《Color space》“Linear and gamma color space”]`
- HDR为High Dynamic Range，高动态范围，在线性光照表示中可保留超过1的值，常见浮点表示与EXR／HDR输入。亮度范围、数值精度、实际存储格式分别记录。`[verified: Unity 2019.4《High dynamic range》L159–180；Arm astc-encoder README “Encoder feature support”]` `[opinion]`
- sRGB是常用颜色空间标准，本项目重点区分其非线性颜色编码与Linear数值解释。线性渲染流程可使用sRGB颜色纹理，并在采样时转换，项目渲染色彩空间与逐纹理sRGB属性分别核对。`[verified: Unity《Color space》L170–182；《Gamma Textures with linear rendering》L160–180；ASTCCompressor.cpp L3466–3472]` `[opinion]`
- Linear对颜色表示线性光强，对遮罩／查找表等数据图保留存储值的数学含义并绕过sRGB转换。Normal Map是贴图用途，按线性数据采样，通道值用于还原方向，质量按法线角度分支评价。`[verified: Unity《Working with linear Textures》L174–183；ASTCCompressor.cpp L2552–2559、L3198–3204]`
- LDR／HDR与sRGB／Linear按两个维度记录，可组合为Linear LDR、sRGB LDR和HDR模式。isHDR来自输入格式，useSRGB来自stored color space，isNormalMap来自usage；blockSize和preset来自候选配置。`[verified: Arm astc-encoder README “Compressing an image”L259–264；ASTCCompressor.cpp L3746–3747、L3466–3475、L620–625]`
- PSNR衡量像素误差，SSIM比较局部亮度／对比度／结构，MS-SSIM跨尺度组合，本地msSsimDb为亮度MS-SSIM的dB值。RDO为率失真优化，质量测量、编码优化及打包后收益分别描述，保留本地通道、单位、分支与DLL核实深度。`[verified: ASTCCompressor.cpp L2181–2304、L2456–2541、L2754–2956；Wang等MS-SSIM论文§2–3；Arm ASTC RDO讨论“Approaches”]` `[opinion]`

### 自动选参偏好与标签判定规则

- 修改选参、采集、分类标签或质量评价前，读取[README完整判定规则](README.md#自动选参的偏好与判定规则)，按当前源码复核，区分C++默认值、运行时有效配置和历史快照协议。`[verified: 用户要求“偏好规则…全部写入到readme和agent里面”；ASTCCompressor.cpp L627–643、L1178–1205、L3590–3665]` `[opinion]`
- 候选顺序固定为12×12、10×10、8×8、6×6，每组依次fastest、fast、medium、thorough、exhaustive，共20组。顺序是标签协议的一部分，当前循环顺序执行，扫描阶段RDO关闭。`[verified: ASTCCompressor.cpp L618–625、L2979–2981、L3026–3028、L3088–3108]`
- 按贴图类型判断质量，法线默认meanWavg≤2.5°且p95Wavg≤7°，LDR sRGB默认PSNR≥有效门槛且msSsimDb≥24，其他分支按PSNR门槛。法线角度为从mip0构造的最多四级法线图中各级统计量的像素数加权。`[verified: ASTCCompressor.cpp L627–631、L2622–2673、L3198–3225]`
- 纯黑RGB像素比例≤40%时采用基础PSNR默认35，>40%且≤80%时默认40，>80%时默认42 dB，强档优先。数值随运行配置核对，LITE与主包协议分别保留。`[verified: ASTCCompressor.cpp L628、L634–637、L3166–3175、L3704–3709；README配置调查入口]` `[opinion]`
- 常规分支接受顺序中的首个合格候选后break。源码中的比较次序为payload更少、同字节下PSNR更低、字节与PSNR相同时qualityValue更低，解读时保留首个有效结果立即退出的控制流。`[verified: ASTCCompressor.cpp L3293–3337]`
- 大图size-first触发条件为LDR sRGB颜色图且width×height≥默认512²。首个PSNR通过候选锁定块大小，同块依preset继续尝试，PSNR与MS-SSIM都通过时立即接受。该组始终MS-SSIM失败时，采用最后一个PSNR通过候选并将valid置true。`[verified: ASTCCompressor.cpp L2988–2990、L3241–3284、L3348–3359]`
- size-first锁组后的切组判断发生在候选测量及allResults追加之后，报告中的下一块候选按实际执行记录解释。保留候选覆盖、失败跳过与提前停止状态。`[verified: ASTCCompressor.cpp L3121–3125、L3157–3158、L3238–3256]` `[opinion]`
- 无有效bestResult但有已测结果时，统一按最高PSNR回退，包括法线分支，PSNR并列保留先出现者并返回成功。已测结果为空且bestResult无效时返回失败，success、valid、逐项阈值通过和fallback原因分别记录。`[verified: ASTCCompressor.cpp L3371–3380、L3390–3422]` `[opinion]`
- RDO精炼要求全局开启、正余量、接口可用、有效选中参数和payload，且winnerPSNR≥保存的有效PSNR门槛+默认1 dB余量。沿用块大小与preset重编码，复测质量且payload≤原结果才采用，保留精炼前后指标、attempted、status和最终rdo。`[verified: ASTCCompressor.cpp L643、L2754–2833、L2878–2953、L657–666]` `[opinion]`
- 规则变化同步README与本节，记录候选、阈值、黑像素、大图、回退和RDO协议及源码／DLL版本，复核旧标签与缓存。已有标签称为当前策略选中配置，候选最优性、严格质量通过和实际训练效果分别评价。`[verified: ASTCCompressor.cpp L1178–1205、L1372–1446、L3437–3462；用户本次文档要求]` `[opinion]`

#### 关键判定源码摘录

以下保留质量判断、常规接受和大图回退的实际语句，完整候选表、黑像素分级、锁组、通用回退与RDO代码见[README完整源码片段](README.md#自动选参的偏好与判定规则)。片段只省略纯注释、空行和公共左缩进。`[verified: ASTCCompressor.cpp下列行范围；README对应小节]`


质量判定分支对应源码L3195–3226。`[verified: ASTCCompressor.cpp L3195–3226]`

```cpp
bool isValid = false;
float distance = psnr - effectivePSNRThreshold;
if (isNormalMap)
{
    NormalAngularResult ang = CalculateNormalAngularErrorMip0To3(originalDataPtr, decompressedRGBA32.data(), origWidth, origHeight, mipCount);
    angleMeanWavg = ang.meanWavgDeg;
    angleP95Wavg = ang.p95WavgDeg;
    isValid = (angleMeanWavg <= kTargetNormalAngleMeanWavgDeg) && (angleP95Wavg <= kTargetNormalAngleP95WavgDeg);
}
else if (!isHDR && useSRGB)
{
    if (psnr >= effectivePSNRThreshold)
    {
        msSsimDb = CalculateMSSSIMDb_Luma(originalDataPtr, decompressedRGBA32.data(), origWidth, origHeight);
        isValid = (msSsimDb >= kTargetMSSSIMDb);
    }
    else
    {
        msSsimDb = 0.0f;
        isValid = false;
    }
}
else
{
    isValid = (psnr >= effectivePSNRThreshold);
}
```

常规保存候选并提前停止对应源码L3324–3338。`[verified: ASTCCompressor.cpp L3324–3338]`

```cpp
if (isBetter)
{
    sharedResult.bestDistanceToTarget = distance;
    sharedResult.bestResult = result;
    sharedResult.bestCompressedData = std::move(compressedData);
    sharedResult.bestTextureFormat = textureFormat;
    sharedResult.bestWidth = width;
    sharedResult.bestHeight = height;
    sharedResult.hasCompressedData = true;
    sharedResult.earlyExit = true;
    break;  // Exit the for loop immediately: we can stop testing other parameters since they will have larger file sizes or same size with higher quality
}
```

size-first回退采用对应源码L3349–3359。`[verified: ASTCCompressor.cpp L3349–3359]`

```cpp
if (useSizeFirstOnLargeTexture && !selectedBySizeFirst && lockedBlockSizeValue >= 0 && hasSizeFirstFallback)
{
    sharedResult.bestResult = sizeFirstFallbackResult;
    sharedResult.bestDistanceToTarget = sizeFirstFallbackResult.psnr - sizeFirstEffectivePSNRThreshold;
    sharedResult.bestCompressedData = std::move(sizeFirstFallbackCompressedData);
    sharedResult.bestTextureFormat = sizeFirstFallbackTextureFormat;
    sharedResult.bestWidth = sizeFirstFallbackWidth;
    sharedResult.bestHeight = sizeFirstFallbackHeight;
    sharedResult.hasCompressedData = true;
    sharedResult.earlyExit = false;
}
```

## 代码组织与Class规范

- 核心实现使用独立class，按[README的目录职责](README.md#目录职责)分包。`models/`维护模型，`data/`维护数据准备、Dataset和DataModule，`training/`维护Trainer，`calibration/`、`evaluation/`、`reporting/`分别维护校准、推理评估和报告。`[verified: 用户要求“MODEL，DATA，TRAIN这些按照规范需要全部分开”“全部以class的形式分开”及本次规范入文档要求]`
- 新功能优先归入已有目录和class，文件围绕一种主要职责组织，紧密相关的类可同文件维护。有状态组件通过实例持有配置、依赖及运行状态，纯计算方法可使用`staticmethod`。`[opinion]`
- 类名使用`PascalCase`，模块和方法使用`snake_case`，新增接口复用现有表示和调用方式，所有Python函数遵循下节的类型注解要求。`[opinion]`
- 依赖按配置与工具 → 数据／模型／推理与指标 → 训练／校准／评估 → CLI组织。数据准备和CLI帮助路径保持CPU依赖，Torch Dataset与DataModule从`data.dataset`按需导入。`[opinion]`
- 新业务逻辑放入对应class，CLI构造组件并调用公开方法。包入口负责导出和薄兼容，既有函数入口委托给class实现。`[opinion]`
- 结构调整时核对CLI、检查点键与严格加载、初始化随机数顺序、resume状态、数据清单指纹及测试封存。先运行小样本回归，再扩大运行范围，报告写入`experiment report/`。`[opinion]`
- 修改架构时同步[README规范](README.md#代码组织与class规范)和本节，具体实现与兼容性记录见[重构报告](<experiment report/class-refactor-20261110/README.md>)。`[opinion]`
- 可维护的启动脚本统一放在根目录`script/`，调用src中的class，阶段之间共享同一TOML的实验目录。历史运行脚本与原始日志按实验工件归档在`experiment report/.local/`。`[verified: 用户要求“用脚本启动的脚本全部放到script里面”；opinion: 入口与历史工件的维护边界]`
- 训练配置使用`TrainConfig`，SwanLab设置使用`SwanLabConfig`，命令行显式值覆盖TOML。添加配置项时同步参数校验、有效配置快照和resume兼容性检查。`[opinion]`
- 实验跟踪逻辑放入`tracking/`的class，上传已有可计算指标与聚合图表。创建跟踪run前检查训练目录与resume条件，保存run ID，失败时正确结束跟踪；历史导入保留来源指纹与historical_import标记。接入和验证记录见[脚本与SwanLab报告](<experiment report/script-swanlab-20261110/README.md>)。`[opinion]`

## 工具与代码风格

- 文本检索优先 `rg`，Python依赖与执行优先 `uv`、`uv run`，采用用户全局规则中的工具偏好。`[verified: 用户提供的全局规则“Available CLI Tools”]`
- 所有Python函数参数和返回值都写类型注解，无返回值显式使用 `-> None`，优先现代类型语法。`[verified: 用户提供的全局规则“Python Preferences”]`
- Python格式与静态检查优先 `ruff`、`basedpyright`，长任务使用无缓冲输出。依赖、检查命令和运行入口以实际代码为准。`[verified: 用户提供的全局规则“Python Preferences”]` `[opinion]`
- 遇到连续3–5次无收敛的排查，汇总已观察的输出与剩余未知项，再调整方法。`[verified: 用户提供的全局规则“Bound investigation”]`

## 修改后验证与交付

- Markdown修改后检查本地链接、内部锚点、书目编号及新增内容的来源定位。外部URL格式检查与网络可访问性检查分别报告。`[opinion]`
- 修改原始资料或处理流程时，按影响范围复查哈希、字幕覆盖、截图时间点和元数据一致性。修改代码时先运行对应的小规模入口与相关检查。`[opinion]`
- 检查结果中记录实际命令、输入范围和结果，沿用已有验证记录时注明历史来源。`[opinion]`
- 最终回复列出交付文件、需要用户核对的选择与限制，并以 `Verification:` 汇报实际执行的检查和结果。`[verified: 用户提供的全局规则“Verification after changes”]`
