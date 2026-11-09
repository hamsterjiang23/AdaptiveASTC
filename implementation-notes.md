# Implementation notes

## Deviations

- 计划范围变更为0。资料按仓库主版本与Obsidian阅读副本组织，Git初始化状态为未运行。`[verified: 本轮文件操作；README“当前状态”]`

## Discovered edge cases

1. 官网简介提到强化学习，正文方法页展示有标签的块大小分类与ResNet。按正文记录方法，简介关系留待作者材料核实。`[verified: 官方Overview；10:00、11:28、12:28画面]`
2. 中英文字幕共同把PSNR方向写反，且部分阈值、块大小比较对象和体积数字存在冲突。校订稿逐项记录原文、画面及待核听项。`[verified: 完整中文校订稿“校订与待核对记录”]`
3. 原字幕183仅0.060秒，字幕91–92有切片交界处重复语句。40段校订稿覆盖328条，逐条对照保留原始措辞与时间。`[verified: source/subtitles.en.srt第91–92、183条；material-metadata.json覆盖表]`
4. 固定每分钟采样会漏掉17:57参考页和12:28结构页等内容，另补10张关键截图，固定19张采样保持独立计数。`[verified: frames目录；verification.json]`
5. 结果表Std (PSNR)数值的计算定义，以及例图RGBA8、128×128、38.4 KB之间的计量关系待核实。保留原表，后续实验需冻结口径。`[verified: 05:35、15:00、16:00、16:30画面；opinion: 复现前待确认项]`
6. 网站字幕存在至少2秒的间隔共30处，覆盖范围从00:02.583到18:12.440。间隔只记录为无字幕区间，独立音轨ASR状态为未运行。`[verified: material-metadata.json；本轮处理记录]`

## Questions for review

- 口述歧义、RL简介关系和原始实验定义已标入笔记，作为后续研究核对项。`[verified: 阅读笔记对应章节]`

## Completion summary

- 范围偏离数为0。`[verified: 本轮交付对照已接受计划]`
- 最可能重访的是少量原字幕语义冲突，可结合音轨进一步核听。`[opinion]`
- 发现并记录6类边界情况。`[verified: 上文编号1–6]`
- 下次先读README和演讲阅读笔记，再查看逐条字幕对照及时间戳画面。`[opinion]`
- 自动检查通过，包含视频哈希、完整包扫描、三处音视频解码、29张PNG结构、19张固定截图重提取、328条字幕覆盖与80个本地链接目标。`[verified: verification.json]`
