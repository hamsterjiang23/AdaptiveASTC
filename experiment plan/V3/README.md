# V3 实验计划：原图输入、候选裁剪与真实耗时

实现、来源绑定和小样本闭环已完成，完整开发实验的实时状态见[执行记录](<../../experiment report/unity-v3-20261113/README.md>)与[阶段状态](<../../experiment report/unity-v3-20261113/progress.json>)。实验矩阵见[matrix.json](matrix.json)，V2来源哈希见[evidence.json](evidence.json)。`[verified: 对应文件及progress.json stages]`

以 V2 的 **ResNet-34＋预测起点向后续搜**为基础，重点验证真实耗时、移除 exhaustive 的影响，以及原图训练与预测是否可行。`[opinion]`

主要验收继续采用**系统块大小准确率≥90%，对照原20候选 Unity 搜索标签**；纯模型准确率、质量、体积和耗时分别报告。`[verified: 本轮“继承续搜系统”“原 Unity 标签”两项选择]`

原图分支的关键假设是：仅凭源文件和明确提供的导入配置，能够预测 Unity 导入后的压缩结果。该假设需要实验验证。`[opinion]`

## 1．继承基础与实验边界

| 项目 | V3 采用的基础 |
|---|---|
| 当前模型 | V2 最佳 ResNet-34 ImageNet＋整图头模型，validation1000 单次预测块大小准确率 **86.9%**。`[verified: imagenet-resnet34-head-sampled4-result.json selected_checkpoint_metrics.accuracy]` |
| 当前系统 | 从预测候选起点向后实际压缩、检查质量并续搜；验证准确率 **93.6%**，平均编码 **1.627 次**，严格质量通过率 **87.5%**，相对原标签质量回退 **0 张**。`[verified: forward-search-full1000-v1.json summary.forward.validation_metrics]` |
| 已有时间 | 当前续搜 **195.80 ms／图**，固定8×8／medium **21.34 ms／图**，均为预热后的整集耗时摊销；不等同于单图延迟。`[verified: forward-search-full1000-v1.json scope、summary]` |
| 数据 | 保留 train10000／validation1000；确认2000张的10图替换、补采和完整像素复审已完成，正式确认尚未运行。`[verified: confirmation-cohort-v3-result.json counts、replacements；forward-system-protocol-readiness-v4.json test_opened、formal_confirmation_executed]` |
| 优先级 | 准确率优先，先把耗时测清楚，不设“两次压缩”或固定毫秒上限；mask／MSAK 通道语义和专门误差规则暂缓。`[verified: 本次聊天截图7“准确率为优先”“那就先统计耗时”；截图6“目前不需要管这个”]` |

继续使用现有 LDR、Tex2D、RGBA8、mip0、RDO关闭的范围，保留颜色、Linear、法线的原有评价分支。法线用途仍由导入配置提供。`[verified: experiment plan/V2/README.md L29–35；unity_capture_input.py L57–90]` `[opinion: V3继承范围]`

## 2．实验顺序与输出

| 顺序 | 实验 | 固定做法与输出 |
|---|---|---|
| 真实耗时基线 | 比较原规则搜索、纯模型一次编码、V2续搜、固定8×8／medium | 在同一批1000张验证图、同机、同DLL下实际执行。原规则搜索使用相同参考像素和编码器逐候选运行，核对其选择与原标签一致；历史 Unity `search_ms` 单列。输出分段时间、编码次数、质量及字节数。`[opinion]` |
| exhaustive 裁剪 | 比较20候选与16候选 | 先冻结 V2 权重和预测，复用已有候选实测质量进行重放。16候选保留四种 Blocksize 和 fastest、fast、medium、thorough。分别统计原标签准确率、质量、payload、选择变化和预计查询次数，再进行真实计时验证。`[opinion]` |
| 原图直接预测 | 测试现有模型对输入变化的敏感性 | 冻结 V2 模型，比较 Unity参考图、原尺寸源图、按目标导入尺寸缩放的源图。单列尺寸变化、颜色／Alpha变化、法线等分组，区分输入变化造成的起点变化和后续续搜补救。`[opinion]` |
| 原图配对训练 | 验证训练能否适应源图输入 | 从相同 ImageNet 初始化训练两条路线：Unity参考图输入、尺寸对齐的源图输入。网络、监督目标、采样和训练配方一致，仅改变输入来源及由输入计算的属性。`[opinion]` |
| 系统组合评价 | 检查输入变化和候选裁剪能否同时使用 | 对冻结V2模型、重新训练的Unity输入模型、原图输入模型，分别评价20／16候选下的纯预测与续搜结果；所有正式候选组合都完成真实编码和统一计时。`[opinion]` |
| 选定与冻结 | 形成V3推荐方案 | 以原Unity标签的系统Top-1优先；准确率相同时比较真实耗时，再比较payload，仍相同则保留改动更少的方案。未优于V2时保留V2，并记录负结果。`[opinion]` |

**16候选的新规则标签只作辅助参照。** 同时报告它与原20候选标签的变化率，不把更换标签带来的准确率变化归因于模型改进，也不预设删除 exhaustive 必然提高准确率。`[verified: 本轮选择“原 Unity 标签”]` `[opinion: 对照解释]`

## 3．输入、训练与接口约定

- **原图输入接口**明确接收源文件或RGBA像素、源尺寸、目标导入尺寸、`srgb`、`normal`、`need_alpha`、`normal_metric_mips`。用途由调用方提供；像素统一转换为RGBA8。原图预测阶段的黑像素比例和Alpha恒定性只从原图输入计算。`[opinion]`
- **原图训练输入**采用固定版本的图像解码器，将源图转换为RGBA，再以BICUBIC缩放至明确提供的目标尺寸，使用与Unity参考图相同的240×240 patch坐标和边缘填充。该处理称为“尺寸对齐的原图输入”，不宣称复现了全部Unity导入处理。`[opinion]`
- **监督仍来自Unity。** 原图分支预测对应Unity patch误差和整图质量，保留现有候选标签；不得把这些标签解释成原图自身压缩前后的误差。原尺寸源图仅用于冻结模型诊断，不直接套用尺寸不同的patch监督。`[opinion]`
- **预测与实际门控分离。** 首次候选选择只能使用模型输入及其派生属性；起点确定后，真实编码和质量检查使用Unity参考像素及真实属性。报告两种来源的黑像素比例、Alpha属性和判定阈值差异，防止信息提前进入原图预测。`[opinion]`
- **两条配对训练路线**均继承V2的ResNet-34、均值池化、20候选输出。各执行30轮全模型训练，再执行30轮冻结骨干的整图头训练；沿用每批16图、每图4patch、学习率3e-4、weight decay 0.05、附加loss权重0.1、seed 20261112及各阶段原有学习率策略。阶段内选模沿用块大小Top-1优先、近阈值RMSE次之。`[verified: imagenet-resnet34-full30-config.json 对应训练字段；imagenet-resnet34-head-sampled4.json config]` `[opinion: 配对训练约定]`
- **候选裁剪保持模型兼容。** 本轮保留20候选输出，通过显式候选集合屏蔽4个 exhaustive；原始候选身份保持稳定。预测决策、续搜、回退、查询计数和输出审计共用该集合，不直接把数组下标改成16候选后继续沿用旧的分块运算。`[verified: system_variant_policy.py L92–118、L140–165 使用固定20候选与每块5档索引]` `[opinion: 实现要求]`
- **二进制继续复用。** `astcenc-avx2-shared.dll`负责真实压缩与解压，`unity_astc_quality.dll`负责质量计算；记录各自路径、SHA和计时。V3采用独立入口和实验身份，保留V2冻结源码与产物。`[opinion]`

原图路线只能说明模型输入是否可以脱离Unity参考图；训练监督、最终编码和质量门控仍依赖Unity协议，不能据此宣布整个流程已不需要Unity。`[opinion]`

## 4．计时、验证与验收

**统一计时。** 所有路线分别报告“所需文件读取到最终内存mip0 ASTC”和“输入像素已就绪后的计算”两种口径。原图路线计入源图解码、缩放及实际编码参考像素的准备成本；续搜计入每次编码、解码和质量检查。模型／DLL加载、Unity导入、标签准备、训练、写盘另列。`[opinion]`

在同一机器、相同线程设置下，固定候选与图片顺序，预热一次、正式重复三次，GPU计时同步。批处理报告整集耗时及摊销值；另以单图模式测量平均值、中位数和P95，不从批处理摊销值推导延迟分位数。`[opinion]`

**检查与晋级条件。**

- 先完成32张训练图、8张验证图的小样本闭环，覆盖颜色、Linear、法线、Alpha和尺寸变化；通过后才扩展到完整数据。`[opinion]`
- 20候选规则须重现原块大小、preset、选择原因和测量次数；16候选须证明预测、实际查询和回退均不会使用 exhaustive，并覆盖首候选通过、锁块、放宽、最高PSNR回退和并列值情况。`[opinion]`
- 原图预测入口测试中禁止读取Unity参考像素、候选质量和选参标签；训练数据必须按资产、划分、目标尺寸和patch坐标准确配对。源文件缺失或无法解码时保留失败记录，不能通过删图形成“完整验证集”结果。`[opinion]`
- 离线重放与真实编码的选择及查询轨迹必须一致，所选ASTC重新解码后复算质量；模型保存后重载验证预测。`[opinion]`
- 系统块大小Top-1≥90%是开发准入条件。另报告纯模型Top-1、完整配置匹配、严格质量通过率、质量回退数、payload、编码次数及实际耗时；这些辅助指标不新增硬门槛。原图路线必须说明续搜是否只是以更多编码弥补较差的预测起点。`[verified: 本轮验收选择；experiment plan/V2/README.md L19–21]` `[opinion: V3报告要求]`

## 5．交付与独立确认

计划落地为 `E:\ASTC_Compression\experiment plan\V3\README.md`，配套保存V2来源绑定、实验矩阵和执行状态；实验结果使用独立目录 `E:\ASTC_Compression\experiment report\unity-v3-20261113`。文档按纯文字Markdown维护。`[opinion]`

V3开发阶段结束时交付三项结论：**原图输入是否可用及其代价、删除exhaustive后的实际变化、推荐系统的准确率与真实耗时**。结论必须区分冻结模型诊断、重训练结果和真实系统结果。`[opinion]`

现有2000张确认集在开发与选模期间继续封存。最终只为一个选定系统准备新的完整合同，绑定模型、输入方式、候选集合、规则、DLL和计时范围，并检查共享封存记录；不得覆盖已有合同或通过更换输出目录重新打开同一确认集。正式确认仍在方案冻结并取得单独授权后执行一次，以原Unity标签的块大小Top-1≥90%验收，不用确认结果继续选模。`[verified: forward-system-protocol-readiness-v4.json execution_authorized=false、test_opened=false；unity_evaluation_seal.py L59–62、L78–104]` `[opinion: V3确认流程]`

