# Implementation notes

## Formal GDC training and Unity pixel capture, 2026-11-11

### Deviations

- Formal 14k collection passed in5,263.53s. OS reboot at15:11 interrupted assembly and the first64 reference export. After metadata recovery with0 conflicts, 56 exports and the truncated native log were retained. The isolated64 retry passed with38 source-equal RGB inputs and26 changed inputs, and all64 choices matched the baseline. `[verified: collection.json; OS LastBootUpTime; partial archive receipt; reference summary.json]`
- Assembly found15 all-zero RGB224 copies with valid frozen source caches. They were archived and repaired. Successful assembly retry took1,666.14s, failed retry325.60s, known preparation components total7,255.27s. Original startup and partial assembly duration remain unknown. `[verified: classifier-cache-recovery.json; preparation-process.json; assembly job receipts]`
- Formal ResNet18 completed10000images x30epochs on RTX4070/CUDA12.8/FP16 in689.862s, with4709 applied optimizer updates and1AMP skip. Best validation checkpoint is epoch2. Independent test2000 passed final encode/decode and report audit, with1540 strict RGB35 passes and23% violations. Paired fixed8 passed1505, payload ratio0.987747 and pipeline time ratio0.973311. `[verified: training_complete.json; wall-clock.json; history.json; test2000/pretrained-test.json]`

### Discovered edge cases

- Cache copies now use writable temporary files, content SHA checks, fsync and atomic replacement. Source read-only attributes remain usable. Job records distinguish live children from terminal outcomes when observation is interrupted. `[verified: dataset.py copy_classifier_cache; jobs.py; cache/lifecycle regression tests]`
- Native debug PNGs require a Y flip relative to Unity's reference export. The normalized capture keeps raw images and cropped RGB output. Complete import coverage, restored metadata and mirrored source hashes are required for a passed archive. `[verified: Astc3rdDecompress y_flip=false; common/unity_reference.py; actual2-image probe and cache regressions]`

### Questions for review

- Final test2000, source64 and matched Unity-reference64 comparisons are complete. Captured-reference common RGB35 passes are Unity27, Nah2022 64, Nah2023 62, GDC46 and fixed8 46 out of64. The source-trained GDC model produces11,881,536 bytes versus fixed8's8,735,312 on these imported inputs. Native goals and timing scopes stay explicit. `[verified: test2000/pretrained-test.json; reproduction-shared64/comparison.json; reproduction-unity-reference64/comparison.json]`

## GDC fixed controls and shared-cohort comparison, 2026-11-11

### Deviations

- Formal collection continues unchanged. GDC reports now audit fixed6/8/10/12 candidate quality and payload on the same evaluation inputs; offline parallel encode times stay separate from the paired fixed8 deployment control. Smoke16 counts are 16/15/11/5 strict35 passes. `[verified: smoke/test16/pretrained-test.json offline_fixed_footprints; gdc2023/reporting.py]`
- Collection-only timing omitted manifest validation and cache assembly. An external OS process observer now records the current Python process from its original StartTime to ExitTime, and report metadata binds that full preparation cost to the exact dataset. Optional incomplete records retain unknown cost. The process API probe returned its requested exit7 and a positive measured span. `[verified: formal preparation-process.json; process-observer probe output; costs.py; test_gdc_reporting.py]`
- Shared Unity/Nah64 belongs to train, so its formal GDC comparison is a resubstitution diagnostic. Independent test2000 remains the generalization result. Unity imported pixels/mips/native quality policy and each publication target stay explicit; common source-RGB measurement is not equal-objective timing. `[verified: common/cohort.py; common/comparison.py; gdc2023/README.md]`

### Discovered edge cases

- Checking only 64 valid train members would accept a replaced smoke config. The cohort loader now verifies config SHA against protocol-lock and lock SHA against the baseline receipt; evaluation/report bind and verify cohort identity. A replacement by another64 regression is rejected. `[verified: common/cohort.py unity64; test_gdc_evaluation.py test_unity64_rejects_replacement_with_other_training_members]`
- Historical Nah per-image audit hashes are not bound by its original summary. The shared comparison therefore freshly decodes selected ASTCs using the frozen binary and checks exact PNG hashes, then recomputes RGB quality. GDC public rows must match the raw batch's index/receipt SHA list and current per-image files. `[verified: common/comparison.py nah/write]`

### Questions for review

- The shared64 preflight covers both existing Nah runs and frozen inputs. Formal GDC model/final-encoding integration and its comparison output remain pending; prepared code is not a measured comparison result. `[verified: .local/reproduction-shared64-preflight.json; current formal collection state]`

## TexNN expanded measurements and GDC smoke loop, 2026-11-11

### Deviations

- Expanded TexNN to 1,024 source patches: 186,141 / 75,758 / 48,456 nonconstant blocks. Six networks consumed 1,865.59 seconds of measured training. Independent validation8 top3×10 lost 1.07/1.63/2.36 dB at pipeline ratios 0.678/0.702/0.796. These are project reconstruction results; paper-scale performance remains unverified. `[verified: expanded data.json; validation8-patch128.json training/groups/audit]`
- GDC smoke used 32 training, 8 validation, 8 calibration and 16 test images with ten training epochs. The real predicted encode/decode chain passed, with strict PSNR >35 on 5/16. The formal 14k collection is now running; formal 10k×30 training, 2k evaluation and common-input comparisons remain pending. `[verified: smoke pretrained-test.json; formal collection log]`

### Discovered edge cases

- GDC cached/assembled receipts now require all four candidates, thirteen artifacts, real ASTC dimensions/bytes, reconstructed PSNR and recomputed selection. Resume rejects a different frozen recipe, and Nah rejects unsupported full input rather than silently running 64. `[verified: dataset.py validate_receipt; script/reproduce.py; eleven label/CLI regression tests]`
- GDC evaluation rejects stale completed-training records, binds training/model/cost hashes and preflights sources before sealing. Shared probability and compression seals retain temperature identity. Unknown prior training durations remain unknown; foreign collection and cost metadata are rejected. `[verified: evaluation.py; training.py; reporting.py; utils/evaluation_seal.py; metadata regression tests]`
- The two-image AMP probe's first step had empty optimizer state and scale 32768, while its epoch was counted as completed. Real optimizer post-hooks now distinguish applied updates from skips; scheduler/best selection requires an update, and a run with no valid best cannot publish completion. The separate 32-image smoke applied ten updates. Historical artifacts remain unchanged. `[verified: probe last.pt; training/trainer.py; test_amp_step_accounting.py; smoke history.json]` [PyTorch 2.8 AMP](https://docs.pytorch.org/docs/2.8/notes/amp_examples.html#typical-mixed-precision-training).

### Questions for review

- Formal GDC labels use 6.793 billion source pixels across 14k images. Preflight measured about 41.8 GiB available RAM, 983 GiB free disk and low host load; four single-encoding-thread workers were chosen. Encoding latency, data generation cost, training cost and Unity import wall time retain separate scopes. `[verified: full manifest/resource preflight; formal command; method protocols]`

## GDC measured-label source preparation, 2026-11-11

### Deviations

- Prepared a new source-RGB35/astcenc3.3-medium label path using the existing four-square classes and ResNet trainer. Complete talk candidate set, codec preset/version and fallback are unavailable; four-square scope and best-PSNR infeasible fallback are explicit project reconstructions. Existing historical LITE labels and checkpoints remain separate. `[verified: gdc2023/dataset.py collect protocol; GDCLabelSelection.choose; gdc2023/README.md]`

### Discovered edge cases

- Strict `>` excludes a candidate exactly at 35 dB. Minimum actual payload can tie on small images, so ties prefer larger footprint area. An infeasible result remains a recorded quality violation. Separate tests exercise those cases, lossless inputs and invalid metrics. `[verified: tests/test_gdc_labels.py]`
- Source splits and RGB224 cache hashes are reused, while all new candidates carry original source MD4, artifact SHA-256 and native build identity. Assembly verifies candidate artifacts, receipt/source identities, cache containment and cross-split hash/group isolation before creating a new training fingerprint. `[verified: gdc2023/dataset.py _collect_one/assemble]`

### Questions for review

- Only source preparation and unit/static checks have run at this checkpoint. GDC native experiments and training remain pending behind the active TexNN work. `[verified: this stage's command history]`

## TexNN learned-encoder project adaptation, 2026-11-11

### Deviations

- Kept all six Appendix widths, but reconstructed class identities, ReLU/Gaussian scale, Adam, endpoint padding and early stopping. The first measured adaptation uses 64 source-image crops and independent validation 8-image crops, rather than claiming the paper's 2050-image or million-block training results. `[verified: texnn/corpus.py prepare; training.py train; public validation8-patch128.json training/protocol/limits]`
- P-NN and DEM-NN use a two-pass native file interface. All preprocessing, features, neural inference, file exchange, CLI starts, predicted encoding and fallback encoding are counted in the model pipeline. Model loading, data preparation, training and verification are reported separately. Ideal weights for all grids remain computed by the backend, leaving an explicit acceleration limit. `[verified: inference.py predict; evaluation.py evaluate; native/solver.inc]`

### Discovered edge cases

- Corrected teacher-dependent endpoint features before training. The previous observer used the selected dual-plane metadata; v2 fits endpoints from pixels and partition alone, shared with inference. Old v1 evidence remains archived and is rejected as training input. Native oracle tests check identical features when all unknown DEM fields are removed. `[verified: native/labels.cpp texnn_ideal_endpoints; corpus.py rows; test_texnn_runtime.py]`
- Physical packing may change delta endpoint families, so canonical labels use base endpoint packing families and repeat-last padding. Native feasibility checks guard partition, dual-plane, endpoint classes and bit budgets. Oracle configurations reproduce reference pixels for 4/6/8, and empty candidates exercise original-search fallback. `[verified: runtime.py from_teacher; native/prediction.cpp and solver.inc; test_texnn_runtime.py]`
- Frozen prepared data rejects another split seed. Validation uses the training corpus's frozen source manifest, whose hashes are bound through collection and prepared fingerprints. Raw and masked classification accuracies are distinguished because Appendix output widths include unused local class IDs. `[verified: corpus.py prepare; inference.py __init__; evaluation.py run; training.py epoch]`
- Each native rebuild archives the prior binaries and receipt. Resume archives previous trained checkpoints and preserves RNG/optimizer/data identity, including interrupted runs without a completion receipt. The first two-epoch pipeline-smoke P-NN was resumed once before checkpoint archival was added; that older smoke evaluation retains hashes but its original P-NN file was replaced. The independent 64-image report uses unchanged completed models. `[verified: reference.py _archive_previous_build; training.py train; pipeline-smoke-v2 raw evaluations; public validation8-patch128.json training]`

### Questions for review

- The eight validation crops show a speed/quality tradeoff, with top3×10 losing about 1.82/2.70/2.46 dB at 4/6/8. These are project-adapted, single-run results and provide no equal-quality production speedup or direct comparison with Unity/Nah. Larger training and original paper-scale results remain unverified. `[verified: public validation8-patch128.json groups and limits]`

## Evaluation recovery and immutable measurements, 2026-11-11

- The first formal test2000 process stopped after218 complete image receipts when Windows refused replacement of progress.json. Its failed process receipt retains600.132646s and exit1. The retry uses the same sealed checkpoint and validates source identity, frozen candidate hashes, actual ASTC headers, reconstructed RGB quality and timing totals before reusing a completed image. Prior valid progress hashes additionally anchor cached receipts. `[verified: jobs/evaluate-test2000 receipt.json and stderr.log; gdc2023/recovery.py; evaluation.py]`
- JSON writes use a unique temporary file, flush/fsync and bounded replacement retries. Invalid partial image folders are archived under the evaluation's own attempts directory. Interrupted process durations remain unknown, while known process costs and failed attempts stay in the public cost ledger. `[verified: utils/artifacts.py; gdc2023/recovery.py and costs.py; test_artifact_atomic_write.py and test_gdc_recovery.py]`
- Native reference comparison now has a dedicated report schema and CLI entry. Its64-image comparison is prepared for completion after the held-out evaluation, with per-method targets, presets and timing scopes retained. `[verified: common/reference_comparison.py; script/compare_reproductions.py --unity-reference; gdc2023/reference_reporting.py]`

## TexNN source and reference integration, 2026-11-11

### Deviations

- The user supplied the 13-page Appendix, resolving the network-width dependency. Its p.1 Tables 1/2 are the main paper's S1/S2. Layer sequences are used verbatim, while input endpoint padding, ReLU, Gaussian scale 0.01 and hidden-layer dropout placement are recorded local reconstruction choices. `[verified: archived appendix.pdf p.1; source.json; architectures.json; models.py]`
- The historical encoder snapshot is the last upstream main commit before the paper's cited access date, ddadf547770ddbe8261cfd854b2a5f21b3a9074c. The exact author-used revision is unspecified. Clean original source is retained, and generated hook sources plus binary hashes are recorded separately. `[verified: upstream git log; reference.py; build-receipt.json]`

### Discovered edge cases

- Modern MSVC required _USE_MATH_DEFINES for historical M_PI references. Its modern cmath declarations conflict with the legacy fmin/fmax functions, so the observer checks finite floats through cfloat bounds. Initial build logs are retained. `[verified: build-initial-math-defines.log; build-labels-cmath.log; CMakeLists.txt; native/labels.cpp]`
- Native PNG loading uses y_flip=1, so RGB label coordinates are bottom-left and partial blocks repeat border texels. Pixel pairing is checked in addition to each physical ASTC block and the original-codec byte comparison. `[verified: upstream astc_stb_tga.cpp L31/L76; data.py verify_labels; 34-block pixel probe and six actual-project collection receipts]`

### Questions for review

- DEM joint-label enumeration and predicted configurations must preserve partition-dependent endpoint modes and dual-plane metadata. Current probes establish teacher export and dimensions, with training and learned-encoder validation still to execute. `[opinion]`

## Reproduction implementation, 2026-11-10

### Deviations

- The distribution build was initially launched with the build-machine environment from `build_editor.bat`. That triggered cleanup of part of WindowsEditor. Original Unity.exe and the two source files were backed up, and native linking plus resource restoration are recorded under the baseline run directory. `[verified: editor build logs; engine-originals/; Unity-before-benchmark.exe]`
- The full build's Package Manager validation and the initial project probe failed because the tool environment omitted ALLUSERSPROFILE. A temporary diagnostic change exposed the stack and was restored in finally. The baseline launcher supplies the missing variable only to its child process. `[verified: upm-diagnostic/stack.txt; benchmark.py]`
- One full launch exited during startup with "Scripts have compiler errors" after producing the runner assembly. No CS diagnostic was present in that Editor log. A same-configuration restart entered measurement successfully; both attempts remain archived separately. `[verified: attempts/full-assembly-startup-failure/full-editor.log; current full-imports.jsonl]`
- pueue is unavailable on this Windows host. Long commands use managed exec sessions with explicit logs and exit-code checks. `[verified: Get-Command pueue,pueued returned no tools]`

### Discovered edge cases

- The full Unity baseline finished with all 10,000 source hashes and native selected block/preset pairs verified. The 32 technical failures passed a separate short-path retry. Native cache compaction moves earlier rows into a JSON snapshot, so audit replays that snapshot followed by JSONL updates under the same policy. `[verified: full-receipt.json; full-assembly.json; benchmark.py read_parameter_cache/audit]`
- Nah native PNG loaders expose four components for RGB input. Reference RGBA PSNR and project RGB PSNR therefore require distinct target counts. The 2023 author code also samples blocks with a time-seeded RNG and divides by one tenth of full-image pixels, including the zero-error return of 999 dB. The final-file audit recomputes both full-image metrics without altering author code or original timing receipts. `[verified: upstream astcenccli_image_load_store.cpp load_image_with_stb; astcenc_entry.cpp L833–879; astcenccli_error_metrics.cpp L250–265 and L333–392; common/reporting.py]`
- Nah 2022 class analysis currently reuses the published Game target 37.3873 dB. Its missing class-specific initial footprint is reconstructed as 6×6 from the 2023 author example. Its fastest search includes CLI starts, decode and Python quality checks, followed by thorough final encoding. Both Nah adaptations use source RGB8, original resolution, no mip and one encoding thread, with CLI-default decode threads. `[verified: common/nah_experiment.py protocol/_measure; common/encoder.py encode/decode; nah2022_psnr_search/source.json]`
- The Nah 2022 64-image run shared the host with pytest/static checks and an offline quality audit. Its 546.329-second search/final-encoding total and 295.809-second fixed-8 control are validation-run wall clocks. Both methods also use a different input/quality/mip protocol from the Unity import baseline, so performance comparisons require that scope to be retained. `[verified: exec sessions 92587, 15732 and 18013; source-rgb64-game receipt.json; method protocols]`
- New measurements hash all input/selected/fixed8 PNG and ASTC artifacts. The report independently re-decodes both actual ASTCs with the measured binary and requires exact saved-PNG hashes, covering earlier receipts without artifact hashes. Original receipts and search timings remain unchanged. The early 2022 game-probe protocol retained a generic 2023-randomness description even though the 2022 path executes full-image PSNR probes. The 64-image 2022 protocol correctly stores null for that field. `[verified: common/nah_experiment.py _measure/run; common/reporting.py write; game-probe and source-rgb64-game protocol.json]`
- The first full-run technical failure occurred before import when Unity Mono could not create the 265-character metadata sidecar path. The existing backup path was 249 characters. Preflight identified 32 potentially affected paths. Flat SHA-256 backup names and targeted retry/assembly code replace this layout. All 32 affected imports later passed native retry with zero metadata recovery conflicts. `[verified: first failed full-imports.jsonl row; long-path-recovery-evidence.json; path-length preflight output; repair-receipt.json; recovery.py]`
- Retry assembly preserves original import failures, original process exit codes and raw-file hashes, and reports passed_with_retries only after complete successful per-asset coverage. The flat index accepts identical warmup entries and restores its valid prefix after an interrupted JSON/UTF-8 append. `[verified: recovery.py assemble; benchmark.py restore_metadata; recovery regression checks]`
- Four of the interrupted metadata writes include legacy importer migration, with version-4 to version-11 serialization, obsolete-setting conversion and empty-field additions. Exact original/current byte hashes and complete diffs are bound to the protocol and Editor identity. The native conversion code was read before accepting these pairs for recovery. `[verified: reviewed-metadata-overrides.json; TextureImporter.cpp L769–920、L953–970; TextureImporterTypes.cpp L66–110]`
- Windows Unity canonicalizes one sample path from `_D.tga` to `_d.tga`. Receipt joining uses slash normalization and case-folding, and still rejects missing, duplicate or unexpected assets. Both 64-image native caches matched the frozen source hashes after this correction. `[verified: smoke1/smoke2 native logs and provenance; benchmark.py summarize/audit; casing regression test]`
- The Android target is temporarily forced to ASTC to exercise the search for all selected textures. Exact `.meta` backups are restored after process exit. Metadata sidecar hashes are captured immediately after the benchmark write, without authorizing later changes during import. Interrupt handling stops the owned Editor before recovery. `[verified: BenchmarkRunner.cs ImportOne; benchmark.py run/restore_metadata]`
- Prepared configurations are immutable and receipts bind to a protocol hash. The first two smoke receipts received an explicit post-run native-cache audit, covering source MD4, LITE policy and the measured Editor binary. `[verified: protocol-lock.json; smoke1/smoke2-receipt.json provenance_binding]`
- All 10,000 sources passed a pre-run MD4 check, reading 10,061,490,379 bytes in 24.29 seconds. Two additional Cubemap imports passed native search and exact metadata restoration. The first nine imports of the initial full launch were archived after stopping the owned Editor to add the metadata revisit guard. Restoration reported zero conflicts before the fresh full launch. `[verified: source-preflight.json; unity-search-baseline-cubemap-probe/probe-receipt.json; attempts/full-before-metadata-revisit-guard/full-receipt.json]`
- Warmup overlaps the first two measured images. Their importer settings at measurement entry can include the warmup override. The current runner names these fields pre_import_android_*, while original bytes remain in the metadata backups. `[verified: BenchmarkRunner.cs Run/ImportOne; smoke1 first two import records]`
- The initially supplied TexNN main paper references a separate architecture Appendix. The user subsequently supplied it, and the current integration is recorded above. `[verified: main PDF p.12; archived materials/appendix.pdf]`
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
