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

- 实验协议、数据、训练、校准、成本及验证报告统一保存在`experiment report/`，逐图清单、缓存、原始日志、预测和检查点保存在该目录的`.local/`并Git忽略。`[verified: 用户确认的GDC复现计划及报告目录要求]`
- Python环境和依赖统一使用uv，提交`pyproject.toml`、`uv.lock`与`.python-version`；安装使用`uv sync --frozen`，实验和检查使用`uv run`。`[verified: 用户要求“仓库里使用uv进行python依赖管理”；pyproject.toml]`
- 实施前检查已有文件、工具和入口，采用完成任务所需的最小修改，保留用户已有工作。Git状态在实际操作前重新查询。`[opinion]`
- 先运行小样本压缩、解压、质量测量和字节统计，再扩大到完整数据集、训练或批处理。`[verified: 用户提供的全局规则“Smoke test first”；README.md“后续研究方向”]`
- 实验协议记录编码器版本、preset、候选块集合、颜色空间、通道用途、Alpha、mip、尺寸取整、容器与硬件。`[opinion]`
- 质量目标、标签生成规则、训练目标和部署质量复检分别定义。记录无可行候选、编码失败、质量违规及回退处理。`[opinion]`
- 对照优先覆盖当前生产使用的固定8×8，补充固定6×6、固定12×12和同质量目标下的搜索选参，学习方法与搜索方法使用一致的编码和测量口径。`[verified: README.md“当前生产基线与优化空间”]` `[opinion]`
- 分别报告数据准备、训练、预测和最终编码耗时，以及体积、质量分布和失败率。跨资产或跨项目划分时检查近重复数据泄漏。`[opinion]`
- 实验状态以本次运行日志和产物为依据。`verification.json` 中的历史资料检查与新增实验验证分别记录。`[opinion]`

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
