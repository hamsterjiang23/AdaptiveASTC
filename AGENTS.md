# AGENTS.md

## 适用范围与研究定位

- 本文件适用于 `E:\ASTC_Compression` 全目录，执行任务时同时遵循用户提供的全局规则。`[opinion]`
- 当前研究主题为ASTC纹理压缩块大小自动选择，关注质量、真实字节数与处理成本的权衡。`[verified: README.md“当前状态”“已核实的方法与待核实问题”]`
- 以固定8×8为当前生产基线，研究机器学习预测参数后执行一次最终压缩。PSNR 35 dB按项目经验判据记录，法线与MSAK贴图的标准和Unity导入后训练数据的获取方式按待明确事项处理。`[verified: README.md“项目需求与优化目标”]`
- 开始任务先读 [README.md](README.md)，按任务需要读取对应资料和检查记录。研究题目、算法路线与新增实验范围以用户确认的内容为准。`[opinion]`

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
