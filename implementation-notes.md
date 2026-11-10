# Implementation notes

## Reproduction implementation, 2026-11-10

### Deviations

- The distribution build was initially launched with the build-machine environment from `build_editor.bat`. That triggered cleanup of part of WindowsEditor. Original Unity.exe and the two source files were backed up, and native linking plus resource restoration are recorded under the baseline run directory. `[verified: editor build logs; engine-originals/; Unity-before-benchmark.exe]`
- The full build's Package Manager validation and the initial project probe failed because the tool environment omitted ALLUSERSPROFILE. A temporary diagnostic change exposed the stack and was restored in finally. The baseline launcher supplies the missing variable only to its child process. `[verified: upm-diagnostic/stack.txt; benchmark.py]`
- One full launch exited during startup with "Scripts have compiler errors" after producing the runner assembly. No CS diagnostic was present in that Editor log. A same-configuration restart entered measurement successfully; both attempts remain archived separately. `[verified: attempts/full-assembly-startup-failure/full-editor.log; current full-imports.jsonl]`
- pueue is unavailable on this Windows host. Long commands use managed exec sessions with explicit logs and exit-code checks. `[verified: Get-Command pueue,pueued returned no tools]`

### Discovered edge cases

- The first full-run technical failure occurred before import when Unity Mono could not create the 265-character metadata sidecar path. The existing backup path was 249 characters. Preflight identified 32 potentially affected paths. Flat SHA-256 backup names and targeted retry/assembly code replace this layout for subsequent runs. The original cohort remains in progress while this fix is prepared and unit-checked. `[verified: first failed full-imports.jsonl row; long-path-recovery-evidence.json; path-length preflight output; recovery.py]`
- Retry assembly preserves original import failures, original process exit codes and raw-file hashes, and reports passed_with_retries only after complete successful per-asset coverage. The flat index accepts identical warmup entries and restores its valid prefix after an interrupted JSON/UTF-8 append. `[verified: recovery.py assemble; benchmark.py restore_metadata; recovery regression checks]`
- Windows Unity canonicalizes one sample path from `_D.tga` to `_d.tga`. Receipt joining uses slash normalization and case-folding, and still rejects missing, duplicate or unexpected assets. Both 64-image native caches matched the frozen source hashes after this correction. `[verified: smoke1/smoke2 native logs and provenance; benchmark.py summarize/audit; casing regression test]`
- The Android target is temporarily forced to ASTC to exercise the search for all selected textures. Exact `.meta` backups are restored after process exit. Metadata sidecar hashes are captured immediately after the benchmark write, without authorizing later changes during import. Interrupt handling stops the owned Editor before recovery. `[verified: BenchmarkRunner.cs ImportOne; benchmark.py run/restore_metadata]`
- Prepared configurations are immutable and receipts bind to a protocol hash. The first two smoke receipts received an explicit post-run native-cache audit, covering source MD4, LITE policy and the measured Editor binary. `[verified: protocol-lock.json; smoke1/smoke2-receipt.json provenance_binding]`
- All 10,000 sources passed a pre-run MD4 check, reading 10,061,490,379 bytes in 24.29 seconds. Two additional Cubemap imports passed native search and exact metadata restoration. The first nine imports of the initial full launch were archived after stopping the owned Editor to add the metadata revisit guard. Restoration reported zero conflicts before the fresh full launch. `[verified: source-preflight.json; unity-search-baseline-cubemap-probe/probe-receipt.json; attempts/full-before-metadata-revisit-guard/full-receipt.json]`
- Warmup overlaps the first two measured images. Their importer settings at measurement entry can include the warmup override. The current runner names these fields pre_import_android_*, while original bytes remain in the metadata backups. `[verified: BenchmarkRunner.cs Run/ImportOne; smoke1 first two import records]`
- The supplied TexNN main paper omits the separately referenced architecture Appendix. The user will supply that later, and exact network implementation waits for it. `[verified: supplied PDF p.12; user reply “暂时没有等我补充”]`
- The native observer measures the original search, parameter-cache hits and mip payload reuse. Empty native logs reject a run even if import returns successfully. `[verified: ASTCBenchmark.h; benchmark.py summarize; test_reproduction_baseline.py]`
- Original source hashes are ccc8eea44b6bff44b8976389d7ecce96e9ce7f6831f149578f91fc54fb2dd209 and 442fc8fbbb57f78077ee3bd7f79e0ba6357cd8ce7733a53fb78206ba0eaeb9aa. Source navigation earlier in this document refers to that uninstrumented revision. `[verified: engine-originals/original_hashes.json]`
- The supplied TexNN PDF has 12 pages and SHA-256 3c4612b705faee35fda1739ee0fd19336cf3f2b99a8566609377db04e2e98d4e. Its separate Appendix Tables S1/S2 remain referenced artifacts. `[verified: reproductions/texnn/source.json; supplied PDF p.12]`

### Questions for review

- Current results and failures must be read from the latest baseline receipts before launching another phase. `[opinion]`

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

## 实际数据调查执行记录（2026-11-09）

### Deviations

- 按已接受计划交付报告、聚合统计、README入口和Obsidian副本。执行中补充确认了trunk目录中的同快照副本，作为来源关系证据。`[verified: notes/实际数据调查统计.json的snapshot_comparison/trunk_project]`

### Discovered edge cases

- 附件LITE配置与PSNR 35研究目标存在差异，回退路径及大图面积触发规则影响标签含义，preset和RDO也参与选择。`[verified: 实际数据调查报告“配置差异和字段语义”“本地源码中的标签生成机制”]`
- 64张MD4抽查与全量路径检查分开记录。1,480个重复哈希组的块大小不同，142条Packages路径需要保留包解析口径。`[verified: notes/实际数据调查统计.json的md4_sample、content_hash_groups、field_anomalies]`
- OpenSSL本机legacy provider不可用，内容核对改用系统certutil的MD4，smoke及64张抽查均通过。`[verified: OpenSSL provider报错；certutil smoke输出；md4_sample.matches=64]`

### Questions for review

- 快照生成时的Editor／编码DLL版本、Unity参考输入、法线实测角度及其他候选结果，按待补齐证据记录。`[verified: 实际数据调查报告“训练可用性与需要补齐的证据”]`

### Completion summary

- 范围变更为0，诊断补充为trunk同快照与包路径口径。`[verified: 已接受计划与本次交付清单]`
- 最可能重访的是源图到Unity压缩输入的对应关系。`[opinion]`
- 已记录配置／回退、重复标签／包路径、MD4工具三个检查边界。`[verified: 本节Discovered edge cases]`
- 后续先读数据调查报告，再按聚合统计中的来源哈希和源码行号复核。`[opinion]`
- 本次完成数据定位、存在性与抽样哈希检查，真实编码复现与模型训练状态记录为not_run。`[verified: notes/实际数据调查统计.json的verification]`
