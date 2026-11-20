# V5 实验计划——逐8×8小块的稠密误差预测头

计划创建于2026-11-19，创建时状态为**计划草案已建立，实验待实施**。实验矩阵见[matrix.json](matrix.json)，历史输入及来源SHA-256见evidence.json，计划创建阶段检查见verification.json。`[opinion]`

完整 11,000 图标签、五轮冻结训练、三轮联合微调和开发集数值评价已完成。联合模型第二轮通过开发集回归门槛。71 组人工校准、64 组留出复核和新独立确认协议冻结已完成。获批替换 6 张重叠图后，1,000 张 Unity 输入已归档并通过跨开发集像素隔离审计。1,000 张正式机器评价和独立可见台阶盲评均已完成。结论见[V5 实验报告](<../../experiment report/V5/README.md>)，复算与开发结果见[V5 执行记录](<../../experiment report/unity-v5-20261119/README.md>)，正式人工指标见[独立盲评回执](<../../experiment report/unity-v5-20261119/confirmation-human-v1.json>)。`[verified: full-development-result.json joint_epochs；human-review-result.json；confirmation-complete-capture-v2.json；confirmation-pixel-isolation-v2.json；confirmation-evaluation-v1.json images；confirmation-human-v1.json status、human_ratings]`

## 1．继承基础、已知现象与实验目标

### 当前基础

| 项目 | V5采用的基础 |
|---|---|
| 模型 | V3选定的Unity输入ResNet-34质量回归模型，检查点SHA-256为`783c69281d127362882a6a84935d928857f33745bb90e282cfb4b648062ada85`，V5前两阶段冻结编码器。`[verified: ../V4/README.md 第1节“当前基础”模型行]` `[opinion: V5冻结范围]` |
| 数据 | 沿用train10000／validation1000开发语料，V5的标签生成、原型训练与选型只使用这两个划分，确认集保持封存、不生成标签。`[verified: ../V4/README.md 第1节“当前基础”数据行；AGENTS.md“确认集保持封存”]` |
| 候选 | 12×12、10×10、8×8、6×6，每块依次为fastest至exhaustive，canonical20顺序固定。`[verified: ../V4/README.md 第1节“当前基础”候选行]` |
| 开发基线 | 原V3在validation1000上块大小匹配93.6%、完整配置匹配80.4%、严格质量通过87.5%、平均编码1.627次。V4推荐的兼容方案保持同样三项匹配／通过率。`[verified: ../V4/README.md 第1节“开发基线”行；V4摘要中的推荐结果]` |
| 现有监督粒度 | 现有patch监督是每个240patch的RGBA通道SSE，不含8×8小块误差，V5需重新生成小块标签。`[verified: AGENTS.md“原生patch监督”条目：RGBA各通道SSE按240patch保存]` |

### 已观察现象

- 压缩前后肉眼可见的质量变差大多出现在有连续或明确色彩梯度的图上，例如0615白色渐隐弧、0616蓝色辉光、0617灰色环形光晕，8×8下表现为台阶。`[verified: 用户本轮原始请求]`
- 逐小块PSNR可用“有X%的小块PSNR低于Y dB”描述。在三张已知图上显示视图Y=28 dB时，坏块占全部小块的5.9%／3.1%／9.4%，占内容小块的12.1%／4.9%／14.4%。`[opinion: 数值来自压缩前会话的tile-psnr运行结果，label_audit阶段按固定网格重算复核]`
- 560张原生PSNR≥35的图已按归档像素复算。平滑小块占内容小块的7.3829%，Y=28时平滑小块的坏块率为0.06024%，其他内容小块为1.82787%。35,112个坏块中92个处于平滑区，占0.26202%。`[verified: ../../experiment report/unity-v5-20261119/progress.json historical_gradient_pool；gradient-pool-exact560-v1.json counts、fractions]`
- X与Y无法由三张已知图确定。0616的平滑小块PSNR最小值为34.2 dB，任何Y都无法在平滑小块口径下抓到它，而0617的平滑小块最小值为24.6 dB。`[opinion: 同上，来自压缩前会话的运行结果，待复核]`

### 研究问题与目标

1. 冻结编码器后，仅训练稠密8×8头，能否预测每个小块、每个候选的误差，并让图级坏块占比与真实占比一致。`[opinion]`
2. 稠密头的图级坏块占比与步进指标、固定规则重放、真实小块PSNR口径相比，在筛出已知问题图与人工标注问题图上是否有额外价值。`[opinion]`
3. 联合微调是否在不降低V3块大小匹配及严格质量通过率的前提下提升小块预测精度。`[opinion]`
4. 目标是预测小块误差，坏块阈值X、Y只在评价阶段施加，使其可在不重训的情况下调整。`[verified: 用户选择方案B（稠密8×8头）；压缩前会话中约定“预测MSE而非是否低于28 dB”]`

## 2．小块定义、标签与独立评价边界

### 小块网格与对齐

- 小块边长8，网格按显示方向锚定在最底一行，顶部和右侧的不足8像素的边缘小块只统计真实像素。`[verified: tmp/gradient-metric-brainstorm-20261119/fullset/tile_psnr.py L32–38 _blocks：顶部／右侧补齐，网格锚定底行；L41–45 tile_psnr：count按真实像素计]`
- 候选解码PNG与原生解码PNG存在上下翻转关系，标签生成须先统一方向，再划分小块。`[verified: reproductions/unity_search_baseline/candidate_archive.py L137–142：原生PNG经[::-1]后与归档解码图比较]`
- 训练输入的240×240 patch在右侧和底侧用edge填充并带有效区域mask，小块网格与patch网格的对齐需在标签审计阶段逐图核对。`[verified: src/adaptive_astc/data/unity_patch_dataset.py L183–188：右下方向edge填充至patch_size]` `[opinion: 对齐核对要求]`

### 观看视图与小块分类

| 项目 | 定义 | 状态 |
|---|---|---|
| 主视图 | 显示视图：Alpha在线性光下叠加到灰64后的RGB。`[verified: 用户前序会话摘要“Display composite”约定；tile_psnr.py 头部注释 primary display view]` | 暂定 |
| 备选视图 | 原生RGB、原生RGBA。`[verified: tile_psnr.py L29 VIEWS]` | 对照 |
| 内容小块 | 显示参考图小块内最大值减最小值≥2。`[verified: tile_psnr.py L53–54]` | 暂定 |
| 平滑小块 | 梯度掩膜覆盖率≥50%。`[verified: tile_psnr.py L55–57]` | 暂定 |

视图的最终选择放到标签审计阶段，依据是各视图下三张已知图与人工标注图的区分度，而不是单一数值。`[opinion]`

### 坏块规则X、Y的确定方法

规则表述为“有X%的小块PSNR低于Y dB”，X、Y都只在评价阶段施加，训练目标是小块MSE。`[verified: 用户本轮提问“有X%的小块PSNR在Y以下”；matrix.json bad_tile_rule.threshold_applied_at]`

| 参数 | 候选 | 选择依据 |
|---|---|---|
| Y | 28、30 dB，暂定30 dB | 原生标签整图PSNR目标中869／1000为30 dB，Y=30与多数资产的整图门槛一致。`[verified: 压缩前会话中对manifest目标的统计；matrix.json bad_tile_rule.y_db_candidates]` `[opinion: 暂定理由]` |
| X | 3%、5%、10% | 由人工复核预算反推，或用带人工标签的校准集确定、再用留出集复核，不用三张已知图定值。`[opinion]` |
| 分母 | 全部小块、内容小块 | 两种分母并列报告，分别说明。`[opinion]` |

小块PSNR与8位RMSE的换算为：28 dB约10.15、30 dB约8.06、34 dB约5.09。`[opinion: 由255/10^(Y/20)计算]`

### 标签生成与封存边界

- 标签目标为每个小块、每个候选的对数MSE，分显示合成RGB与原生RGBA两路。既有RGBA通道MSE不能直接合成显示视图MSE，因此显示视图需要单独生成，或在预测头中增加显示MSE通道。`[verified: matrix.json labels.channels；压缩前会话对稠密头的限制说明]` `[opinion: 合成关系判断]`
- 存储估计：74609个patch × 900小块 × 20候选 × fp16，单通道约2.7 GB，四通道约10.7 GB，实施前须按实际patch数和压缩方式重估，并决定是否改为按需生成。`[opinion: 算术估计]`
- 全 20 候选训练标签只来自 train10000／validation1000 的归档解码图。独立确认在另行授权及像素隔离通过后使用冻结模型推理，并按冻结协议执行实测与盲评。`[verified: full-label-verification.json counts；confirmation-pixel-isolation-v2.json full_scoped_pixel_isolation_passed；confirmation-evaluation-v1.json seal、training_updates；confirmation-human-v1.json human_ratings]`
- 阈值X、Y只在评价阶段施加。人工标注的top-20并排对照用于确定X，不进入训练目标。`[opinion]`

## 3．模型与实验行为

### 稠密头结构

在冻结的V3 ResNet-34编码器之上增加8×8稠密头。240×240输入经layer2得到30×30特征，经layer4得到8×8特征，后者上采样到30×30后与前者拼接，经1×1卷积输出每小块×20候选的对数MSE。`[opinion: 结构设计，压缩前会话与用户确认的方案B]`

- 仅用layer2不够：layer2一个单元只覆盖有限的感受野，8×8小块误差受周围块量化和编码模式影响，需要layer4的上下文。`[opinion]`
- 元数据调制须在空间上广播，而不是只作用于图级向量。`[verified: src/adaptive_astc/models/unity_quality.py 中 metadata_conditioner 为 Linear(8, 2*feature_dim)，当前为图级调制]` `[opinion: 修改要求]`
- 有效区域mask按同一网格池化到30×30，边缘小块按真实像素数加权。`[opinion]`
- 输出候选维度20，与canonical20顺序一致。`[verified: ../V4/matrix.json candidate_set]`

### 实验阶段

| 阶段 | 内容 | 完成条件 |
|---|---|---|
| 标签审计与对齐 | 复核tile-psnr.py的网格、翻转与视图定义；在32张开发图上重算并与压缩前会话结果对照。`[opinion]` | 32图重算通过，三张已知图数值可复现。`[opinion]` |
| 小块标签生成 | 对develop集全部patch生成小块×候选标签，先做存储与按需生成决策。`[opinion]` | 完整读取通过，存储路径与SHA归档。`[opinion]` |
| 冻结编码器原型 | 冻结V3编码器，仅在128²图上训练稠密头。`[opinion]` | 原型训练完成并重载通过。`[opinion]` |
| 稠密头评价 | 与步进指标、固定规则重放、oracle小块PSNR对照，并跑top-20人工复核。`[opinion]` | 图级坏块占比误差与top-20召回报告齐备。`[opinion]` |
| 联合微调 | 解冻后微调，检查是否降低V3块大小匹配及严格质量通过率。`[opinion]` | 完整训练完成，回归检查通过或保留负结果。`[opinion]` |
| 新独立确认协议 | 另行预留资产，绑定冻结模型、规则与参数；确认集不开封。`[opinion]` | 协议文件与隔离审计齐备，执行状态明确写为未授权。`[opinion]` |

### 对照矩阵

| 对照 | 内容 |
|---|---|
| V3基线 | 原V3 ResNet-34质量回归，只输出整图／patch候选质量。`[verified: ../V4/README.md 第1节]` |
| 稠密头（冻结编码器） | 新增8×8稠密头，编码器冻结。`[opinion]` |
| 稠密头（联合微调） | 解冻后联合训练，观察回归。`[opinion]` |
| 步进指标 | `L_p95_primary`等步进指标排序，作为无训练基线。`[verified: 压缩前会话摘要“Step metrics”]` |
| 固定规则重放 | 20候选原规则重放，作为oracle上限对照。`[verified: ../V4/README.md 第3节“真实编码对照”]` |
| 小块PSNR oracle | 真实小块PSNR，作为筛图上限。`[opinion]` |

## 4．评价指标、闭环验证与选型

### 评价指标

| 层级 | 指标 |
|---|---|
| 块级 | 每小块对数MSE的RMSE；Y附近的小块PSNR误差，Y取28与30两类。`[opinion]` |
| 图级 | 预测坏块占比与真实坏块占比的误差、与真实占比的Spearman、top-20召回。`[opinion]` |
| 分视图 | 显示视图为主，原生RGB与原生RGBA并列报告。`[opinion]` |
| 分分母 | 全部小块与内容小块并列报告。`[opinion]` |

图级评价以聚合的坏块占比为主指标，不用单块命中率，因为单块预测正确但图级占比偏差无意义的组合同样会出现。`[opinion]`

### 与现有基线的比较

- 步进指标`L_p95_primary`在361张原生PSNR≥35图上对615／616／617的排名为2／43／6，稠密头需报告同一排名与top-20重叠。`[opinion: 该排名来自压缩前会话运行结果，标签审计阶段复核]`
- 小块PSNR口径与步进口径的Spearman为0.20、与原生PSNR为−0.50，top-20重叠为2，两者并不等价，比较时分别说明抓到的图像类型。`[opinion: 同上，待复核]`
- oracle小块PSNR给出“若已知真实小块误差，能筛到多少”的上限，稠密头报告与上限的差距。`[opinion]`

### 人工标注与X的确定

在top-20并排对照表中并列显示小块PSNR排序、平滑小块排序、步进指标排序，由人工标注哪些图确实可见质量损失。标注结果用于确定X，并用留出部分复核，不用标注集直接定值。`[opinion]`

### 闭环与边界检查

先固定32张开发图（覆盖颜色、Linear、法线、Alpha、大图放宽、最高PSNR回退、尺寸变化）完成标签重算与原型训练闭环，再扩展。边界检查包括：顶部／右侧边缘小块、8×8整除的尺寸、非整除尺寸、全透明小块、零误差小块（对数MSE取负无穷时的处理）、候选缓存复用、翻转方向错误、patch与小块网格错位。`[verified: ../V4/README.md 第4节“小样本闭环与边界检查”确定32图选择方式]` `[opinion: V5边界清单]`

### 选型标准

稠密头进入推荐须同时满足：标签审计通过；图级坏块占比误差在验证集上优于步进指标基线；联合微调阶段相对V3的块大小匹配率与严格质量通过率不下降，否则保留冻结编码器版本并记录回归。`[opinion]`

## 5．交付、执行状态与完成条件

本次计划交付为本目录README、matrix.json、evidence.json及verification.json。后续结果目录预定为`E:\ASTC_Compression\experiment report\unity-v5-20261119`，原始产物目录预定为其同级`.local\unity-v5-20261119`。`[verified: ../V4/README.md 第5节同类目录约定]` `[opinion: V5目录命名]`

| 阶段 | 产物及完成条件 |
|---|---|
| 标签审计与对齐 | 32图重算报告、视图选择理由、网格与翻转核对记录。`[opinion]` |
| 小块标签生成 | 完整标签、存储决策、SHA归档、失败记录。`[opinion]` |
| 冻结编码器原型 | 原型训练日志、重载通过记录、初步块级误差。`[opinion]` |
| 稠密头评价 | 块级与图级指标、三基线对照、top-20并排人工标注表、X的确定记录。`[opinion]` |
| 联合微调 | 完整训练、回归检查、负结果保留。`[opinion]` |
| 新独立确认协议 | 新资产预留、冻结条件、隔离审计；执行状态明确为未授权。`[opinion]` |

计划完成须回答四项问题：稠密头能否预测小块误差并让图级占比一致；它对筛出问题图相对步进指标、固定规则与oracle有何增量；联合微调是否带来回归；X、Y在人工标注下应取何值。结论区分开发集同集选择与后续独立确认。`[opinion]`

当前阶段状态由matrix.json记录，计划创建阶段的检查范围由verification.json记录。`[opinion]`
