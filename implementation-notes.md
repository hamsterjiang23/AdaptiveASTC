# Implementation notes

## 2026-11-12 valid-pixel-proportional sampling control

- Train-only diagnosis found3467/120276nonmonotone patches. Exact-target isotonic projection changed0/10000image labels and only0.05934dB near-threshold image RMSE; this is not a trained result or accuracy upper bound. Independent PAV comparison matched1003examples within2.22e-16. `[verified: patch-monotonicity.json; baseline_code_review probe; opinion: scope]`
- The next fixed-capacity control changes only within-image patch probabilities, preserving capped image/group mass. Expected draws with less than one-quarter valid area fall38.82to20.67percent, while total image mass remains7982. Default sampling sequence stays unchanged; unsupported bag combination fails.26tests and independent review pass. `[verified: patch-pixel-sampling-analysis.json; test_patch_sampling.py; test_patch_training_bags.py]`
- Two-epoch48train/16validation CUDA smoke completed4actual updates and best-checkpoint replay in21.54seconds. The formal10000/1000trial uses groupcap512 and the same11178564parameters; outcome remains pending. Completed bag-control sources were archived before modification. `[verified: scratch-group512-pixels-smoke-summary.json; jobs/scratch-group512-pixels-smoke/receipt.json; scratch-group512-pixels-suite.json; pre-pixel-sampling-source/sources.json; opinion: outcome boundary]`

## 2026-11-12 native CUDA training and completed bag controls

- Added a CUDA-only native trainer with per-image patch bags, full-image quality targets, original-policy validation and frozen best-checkpoint replay. Formal admission requires the complete10000/1000 corpus; the8train/2validation smoke completed2epochs/4updates with0AMP skips and matching reloaded predictions. Total process23.81seconds, prototype11377660parameters; no production accuracy claim. `[verified: unity_quality_trainer.py; unity-native-smoke8-v1-result.json; opinion: scope]`
- Review found three evidence issues before launch: checkpoint artifacts were not bound to selection-time hashes, final validation reused loaded inputs, and interrupted epochs could undercount updates. Save-time hashes plus pre/post replay checks, fresh frozen validation and selected-training input verification, and immediate update accounting now cover those cases.35targeted tests and independent recheck passed. `[verified: test_unity_quality_training.py; unity-native-training-verification.json; baseline_code_review C1-C3 closure]`
- GDC bag4 controls completed10/7epochs, accuracy71.2/71.7percent and same-selected-checkpoint nearRMSE3.5647/2.0188dB. Added aggregate loss improved0.5percentage points within paired sampling, but both trails remain below independent sampling80.7percent. Retain the negative result and separate sampling from loss attribution. `[verified: scratch-bag4-comparison.json; opinion: comparison boundary]`

## 2026-11-12 frozen native patch batches

- Added an independent frozen-snapshot batch preparation path. It revalidates original reference/choice and all20candidate artifacts, then creates immutable per-batch patch corpora with Dataset checks. A64train/2validation smoke passed; the11published-batch snapshot covers2368train/2validation and is being prepared separately. No new encoding or GPU training is involved. `[verified: patch_batches.py; unity-patch-batches-smoke-v2.json; unity-patch-batches2370-config.json]`
- The first smoke preserved completed64image targets but failed because the native log used lowercase_d.tga while the source path used_D.tga. Dataset now compares canonical Windows asset paths while retaining external corpus hashes; different assets still fail. Review also caught selected-plan/full-source coverage conflation, now fixed with explicit plan/full counts.42targeted tests and independent recheck pass. `[verified: unity-patch-batches-smoke.json; unity_patch_dataset.py; patch_batches.py coverage; pytest and review outputs]`
- First smoke process63.53seconds; repaired smoke12.81seconds includes target reuse. The expanded run retains these costs and immutable corpus identity; unified training manifest assembly and full native model evaluation remain pending. `[verified: corresponding jobs/receipt.json; unity-patch-batches-smoke-v2-config.json prior_attempt; opinion: scope]`

## 2026-11-12 native Unity Dataset validation

- Added a separately frozen RGBA Dataset with valid-pixel masks,20x4channel SSE/log-MSE and zero-error targets,8input-only attributes, and retained whole-image quality supervision. Real258train/2validation images pass pixel/padding and native PSNR reconstruction checks. No Unity model updates or test access occurred. `[verified: unity_patch_dataset.py; unity-dataset260-v2.json unique_images, training_updates, test_opened]`
- Review C1 reproduced a duplicate identity bug: unchanged whole-image SSE could hide changed patch distributions. The final identity also binds target_sha256 and patch_size. The regression accepts each corpus independently and rejects the conflicting merge;19tests and the final260image audit pass. Earlier audit versions remain as historical receipts. `[verified: dataset_audit.py; test_unity_patch_dataset.py; unity-dataset260-v2.json; review C1 followup]`
- Final audit loop9.52seconds/process13.22seconds;1708checks include13repeated validation patches. These are data validation costs under concurrent workloads, not deployment latency. Native non-PSNR model objectives and full production training remain pending. `[verified: unity-dataset260-v2.json; jobs/unity-dataset260-v2/receipt.json; opinion: cost and completion scope]`

## 2026-11-12 same-image patch bag preparation

- Added independent sampler/loss components while leaving live group512 trainer/model/data sources unchanged. Bag4 draws preserve marginal image weights but this seed covers6336distinct training images from10000bags/40000patch draws;7276bags repeat an index. Paired loss0/loss1 configurations isolate the added loss, with a separate historical independent-patch comparison for sampling. CUDA integration and execution remain pending. `[verified: patch_bags.py; bag-sampling-analysis.json; scratch-bag4-suite.json; opinion: comparison boundary]`
- Pixel-weighted log-MSE aggregation matches existing inference epsilon/clipping and exact sampled targets within1.26e-6log units. It supervises sampled bags, not complete images. Fourteen component checks and existing nine sampling checks pass; independent review found no issues. `[verified: patch_loss.py; test_patch_bags.py; bag-sampling-analysis.json; pytest and review outputs]`
- Frozen validation predictions show single-patch images remain difficult: scratch246images/51errors, pretrained246/27. This diagnosis does not fit new parameters or access test; aggregation is one experiment rather than an asserted cause of all errors. `[verified: patch-coverage-diagnosis.json; opinion: interpretation]`

## 2026-11-12 original Unity policy replay

- Added a pure rule decoder for the complete20candidate RDO-off LDR grid. It preserves nativefloat32 gates, normal versus color branches, black thresholds, large-image locking, the already-measured next-block candidate and highest-PSNR fallback. All260development choices match the original block, preset, reason and attempted count. `[verified: policy.py select; unity-policy260-bound-v2.json matching_fields, mismatches]`
- The first audit trusted a caller-supplied cache hash; review reproduced acceptance of a substituted near-identical policy. The bound-v2 audit derives the exact cache from frozen capture identity/phase, repeats the complete original LITE audit and retains the earlier result as limited history. The foreign-cache regression is rejected before report publication. `[verified: policy_audit.py verify_policy_origin; test_unity_policy_audit.py; bound-v2 config prior_audit]`
- Exact measured-PSNR-only decisions match207/260footprints and110/260complete choices. This selected-development rule ablation is not a model accuracy ceiling. Unity migration retains MS-SSIM/angular supervision and original policy branches; learned whole-image aggregation remains pending. `[verified: unity-policy260-analysis.json; opinion: migration boundary]`

## 2026-11-12 native candidate corpus follower

- Completed256images/5120encodes:3688new targets,1432original measurements and256winners match; process609.70seconds. Independent archive audit checks everyASTC/PNGhash, header, byte count and selected decode orientation. `[verified: unity-candidates-train256-audit.json; jobs/unity-candidates-train256/receipt.json]`
- Added frozen45batch follower plus archive verifier. Real258image smoke passed in46.20seconds; final implementation replay passed in43.16seconds. New18tests cover missing/duplicate/reordered targets, corruption/orientation, changed labels, publication races, relative config paths, initial wait, preserved retry attempts and project locking. Full Unity training and90%acceptance remain pending. `[verified: unity-candidate-queue-smoke.json; jobs/*queue-smoke*/receipt.json; test_unity_candidate_archive.py; test_unity_candidate_queue.py; opinion: completion boundary]`


## V1 partial-search normal candidate completion, 2026-11-11

- Added a subclass/independent CLI to complete archived color and mip0 normal grids. The original supplement, metadata and collection modules remain unchanged while the live reference series imports them. Normal targets require observed Profile1, normal-pack=false, captured mipmaps=false/Linear/Tex2D, and frozen import-log/source hashes. No live project candidate directory or Editor mutation is used. `[verified: candidate_completion.py; complete_unity_candidates.py; original module hashes]`
- Three real images passed60encodes and45new measurements, including a normal whose original search stopped after3candidates. Original PSNR/angular metrics match at report precision; normal winner complete ASTC/header and decoded RGBA match. The final smoke process took11.89seconds. The earlier14.06second smoke and source snapshot remain archived; full256binds final SHA56546d463a7c013c53c86e1731b68ec156fb89f3c359900b3dc2193432f63c04. `[verified: unity-candidates-train256-smoke-v2.json; jobs/*smoke*/receipt.json; full config]`
- Four extension regression tests cover malformed/duplicated metric tables, actual import hash/mip restrictions, source binding and inconsistent winner footprint. Read-only review found no bugs in the extension; the full-header guard was added afterwards and tested. Full256/5120candidate completion started after the final smoke and26.97GiB RAM preflight. Costs overlap Editor reference collection and CUDA training and are not deployment measurements. `[verified: pytest/test_unity_candidate_completion.py; readonly review; full job preflight; opinion: cost scope]`

## V1 completed LR control and serial reference corpus, 2026-11-11

- Scratch LR0.0003 completed12epochs and best-checkpoint audit: selectedepoch7raw80.7%, balanced74.50%, nearRMSE1.6040dB,11178564parameters. The single formal change from original scratch is learning_rate; accuracy gains4.7points but10x10recall loses4.69points. Training2483.18seconds; process2516.98seconds including reload. Historical reports and checkpoint remain immutable. `[verified: patch-fixed-capacity/scratch-lr0003-result.json; scratch-lr0003-audit.json; jobs/scratch-lr0003/receipt.json]`
- Separate frozenepoch12EMA BN reestimation reaches80.9%/1.3716dB, balanced76.97%, quality87.9%, payload95148832bytes, with zero optimizer updates and unchanged learned parameters. All four variants remain reported; process419.26seconds. Next fixed-parameter stem control changes remove_maxpool only against LR0.0003, CUDA smoke first. `[verified: normalization-scratch-lr0003.json; jobs/normalization-scratch-lr0003/receipt.json; scratch-stem2-lr0003-suite.json; opinion: next experiment]`
- Training256 capture passed1432callbacks, including16NormalMaps, with source/meta restored, process963.42seconds. Three completed captures now cover320train/2validation. The new serial collector freezes45batches covering10000train/1000validation; actual64+2archive merge passed before the full queue launched. Candidate completion remains separate from reference/label coverage. `[verified: unity-train256-batch001.json; unity-reference-series-plan.json; unity-reference-series-smoke.json; unity-reference-series.json; opinion: corpus scope]`
- Read-only review found and resolved subset/full-coverage conflation, missing reference-receipt anchor comparisons, nonfinite resource limits and a repo-local lock that could not protect shared Unity projects. The collector now checks original MD4/selection, requires finite positive budgets, and holds an OS byte lock in the shared project's Library.16tests passed, including real Windows lock exclusion and retained failure invocations. The running implementation is frozen at SHA134b9d99b5a6eedf5b16e781e0f0999f032f84943302acf7b538d492f0477dc2. `[verified: collection.py; test_unity_reference_series.py; readonly review C1-C4 recheck; unity-reference-series.json implementation_sha256]`

## V1 normal re-encoding and split-aware collection, 2026-11-11

- The existing 4096-square mip0 NormalMap passed a winner-only encode probe, then all 20 actual candidate encodes. Complete ASTC containers and decoded RGBA bytes match the original search; its failed angular quality and highest-PSNR fallback remain unchanged. Encoding totals124.1963seconds, the audit loop170.1485seconds, and the process174.1805seconds, overlapping CUDA training. Original candidates and previous zero-encode audits retain their identities. `[verified: unity-normal-replay-winner.json; unity-normal-replay20.json; jobs/unity-normal-replay20/receipt.json]`
- `audit-normal` adds optional none/winner/all re-encoding, separate attempt/completion counts, and retained failure artifacts. Re-encoded PNGs are top-left aligned; native metric evaluation remains bottom-first. Actual Linear profile1, normal-pack=false and needAlpha are bound to the observed callback and frozen DLL. No HDR or multiple-mip result is implied. `[verified: normal_audit.py replay_candidate/run; readonly review; opinion: scope]`
- Reference batches freeze an explicit train/validation split and1..256unique paths. Membership and cross-split path checks precede preparation; manifests retain the source split and test/calibration are rejected. The original10000training-image baseline and full-run smoke gates are unchanged. CPU tests cover split/order binding, tampering, membership, excluded splits, and cached normalized-image validation. The actual validation2 capture passed7callbacks with source/meta restoration in370.06process seconds; separate40candidate encoding added33measurements and matched both original winners. One512-square source becomes256-square after Unity import. `[verified: benchmark.py; unity_reference.py; test_unity_reference_batches.py; test_unity_reference.py; unity-validation2.json; unity-validation2-supplement.json; jobs/unity-validation2/receipt.json; normalized-batch/manifest.json]`
- Review found that the old recovery CLI omitted batch, leaving no standard metadata recovery after a hard process interruption. `reproduce.py recover --phase batch` now binds the saved split/path identity and verifies its frozen protocol before restoration; other actions still reject batch. Synthetic on-disk metadata recovery and altered-config rejection passed. Managed source restoration remains a separate guarded command. `[verified: script/reproduce.py recover; test_unity_reference_batches.py; readonly review C1]`

## V1 wider color replay and actual normal audit, 2026-11-11

- Pretrained patch regression completed14epochs and passed strict best-weight reload: selectedepoch9raw, accuracy88.8%, balanced85.81%, near-thresholdRMSE0.9736dB, wall2966.68seconds.8x8/10x10 recalls are81.77%/75.78%;11,178,564parameters unchanged. Neither scratch nor pretrained meets the joint V1 development gate. These are recipe-level comparisons on GDC validation, not Unity acceptance or isolated input attribution. `[verified: patch-v1/pretrained-result.json; pretrained-monotone-ema-audit.json; opinion: evidence boundary]`
- Eight color references spanning1x1 through2048-square and odd edges passed160candidate encodes/decodes. The52original metric records and8selected payloads match;108candidate measurements are new. Whole process52.79seconds overlaps CUDA training and does not replace the Unity search baseline. `[verified: unity-color8.json; jobs/unity-color8/receipt.json]`
- The4096-square NormalMap has mipmaps=false, Linear profile1 and normal-pack=false. Its20existing ASTC files were archived and freshly decoded, then measured with unchanged native normal functions. All decoded pixels match and rounded metrics agree;0candidates pass the angular gates. The original6x6/exhaustive winner is a highest-PSNR fallback, withmean2.93632andp9511.59958degrees. No new normal encoding or multiple-mip validation is claimed. `[verified: unity-normal20-policy.json rows, input_options, encoded_candidates]`
- Review fixed report status with a trailingBEST marker and thefloat32(3.2) threshold boundary. Thresholds now come from native tableConfig, agree with capture configuration and report display, and are compared as nativefloat32. The original audit stays archived; a separate20candidate re-audit passed in21.40process seconds. `[verified: normal_audit.py native_thresholds/native_status_valid; test_unity_normal_audit.py; unity-normal20-policy.json; jobs/unity-normal20-policy/receipt.json]`
- A separate frozen-checkpoint BN diagnosis is prepared to test normalization statistics before another expensive training run. It uses only training inputs to recompute statistics, keeps learned parameters fixed, and evaluates only development validation. CUDA execution and results will be recorded separately from implementation checks. `[verified: evaluation/patch_normalization.py; opinion: diagnostic purpose]`
- The scratch diagnosis completed with128train batches/16384patches covering8066images. Last-epoch raw changes62.4%→70.5%; the same EMA parameters change48.3%→76.7%, nearRMSE5.5114→1.6467dB. This isolates the effect of BN statistics for the frozen weights, not all differences between training recipes. Compared with the original selectedepoch9raw76.0%, the postprocessed last-EMA gains0.7points. Process400.03seconds; pretrained diagnosis runs next. No test access or optimizer updates. `[verified: normalization-scratch.json; jobs/normalization-scratch/receipt.json; opinion: inference boundary]`
- Frozen best-prediction strata show67of112pretrained errors among203images within0.5dB of a candidate threshold;604images at least1dB away reach96.36%.6x6near-threshold residual bias is+0.563dB/RMSE1.539dB. Padding strata have unequal class composition and do not establish padding as the root cause. No test or forward pass was used; the analysis binds prediction, audit, history and corpus hashes. `[verified: patch-v1/error-strata.json; opinion: diagnostic boundary]`
- Pretrained BN diagnosis also completed: raw86.1%→86.3%, sameEMA81.3%→89.2% withnearRMSE0.9512dB. Its0.4point gain over the original best raw accompanies lower zero-margin quality pass87.3% versus88.3%; all variants and costs remain reported. Process429.82seconds,0optimizer updates, unchanged parameters and no test access. The joint V1 gate and Unity acceptance remain unmet. `[verified: normalization-pretrained.json; jobs/normalization-pretrained/receipt.json; patch-v1/pretrained-result.json]`

## V1 actual callback metadata and completed scratch regression, 2026-11-11

- Scratch native-patch regression stopped after14epochs with the best raw checkpoint at epoch9: validation accuracy76.0%, balanced accuracy69.54%, near-threshold RMSE1.7681dB. Strict checkpoint reload and saved prediction audit passed. This is9.7percentage points above the original RGB224 control and7.4above the best classification recipe on the same validation1000; it changes several parts of the method and is not component attribution. Pretrained regression continues separately. `[verified: patch-v1/scratch-result.json; scratch-monotone-ema-audit.json; opinion: attribution boundary]`
- EMA0.999 did not help this scratch recipe: its maximum validation accuracy was48.3%. The live recipe is not changed; diagnosis of averaging/normalization and error strata remains separate. The decision margin0.5dB gives76.2% accuracy and84.4% measured candidate quality pass rate; no Unity production acceptance is claimed. `[verified: scratch-result.json curves and margins; opinion: diagnostic boundary]`
- Actual callback collection injects a temporary logger into the existing managed encoder handler, preserving the original encoding call. It records needAlpha/profile/normal-pack and SHA256 over the input memory. Source backup and replacement are fsynced/atomic, restoration rejects independent edits, and failure receipts retain the error and restoration outcome. `[verified: metadata.py; native/capture_options.cs.txt]`
- A fresh two-image Editor run recorded16callbacks and exact archived RGBA hashes. Its source restored byte-for-byte, and metadata restoration had0conflicts. A stricter follow-up audit validates actual format names/values, the original winner and measured candidate coverage. Earlier audit/source snapshots remain local, and the follow-up receipt is separate. `[verified: unity-actual-options2.json; unity-actual-options2-revalidated.json; jobs/unity-options2]`
- Full40candidate replay bound to those actual options passed, retaining16native metric comparisons and24new candidate measurements. Callback capture cost268.67seconds includes Editor compilation/startup, export and hashing; the0.92785second supplemental process overlaps CUDA training. Neither replaces the original baseline timing. `[verified: unity-supplement2-actual.json; jobs/unity-options2/receipt.json; opinion: timing boundary]`
- Review caught candidate substitutions that could pass a count-only audit and a mixed-cohort gate that rejected selected color images because unselected normal images existed. Candidate identity is now checked; cohort-wide identity checks and selected-only support checks are separate. Regression tests cover both substitutions and mixed normal/color cohorts. The64-image capture passed558callbacks with exact reference hashes and successful source/metadata restoration:63Default and1NormalMap,31needAlpha and33withoutAlpha. It extends observation coverage, not normal/HDR supplemental encoding support. The4096-squareNormalMap actually hadnormal-pack=false, so texture usage and encoder packing must remain distinct fields. `[verified: tests/test_unity_metadata.py; test_unity_supplement.py; unity-actual-options64.json; smoke1-receipt.json]`

## Unity supplemental quality and candidate probe, 2026-11-11

- The unchanged native PSNR/MS-SSIM/normal function region is extracted into a local-only source and compiled with MSVC precise floats. Engine source, extracted region, wrapper and DLL hashes are bound; no engine source copy is added to Git. `[verified: unity-quality-probe.json metric_build; quality.py]`
- The initial CMake command used backslashes in METRICS_SOURCE, causing invalid escape parsing. A new build directory with POSIX-form paths passed. The first metric comparator incorrectly required1e-4dB equality against2-decimal cache values; its record remains archived and the result now states rounded-record agreement. `[verified: native build logs; unity-quality-probe.json prior_comparison]`
- Two archived LDR Default alpha images now have40 separately timed candidate encodes/decodes,24 previously unmeasured candidates, exact original selected payload/decode parity and16 original quality comparisons within0.00501dB. Final collection guards include capture/manifest hashes, train/validation-only scope, unique indexes, dimensions and code hashes. `[verified: unity-supplement2-verified.json; supplement.py]`
- NeedAlpha and LDR metadata are replay-verified assumptions for this pilot, not observed callback fields. Formal production collection still needs direct metadata, split-aware capture, real normal/HDR branch validation and full candidate coverage. Per-channel error aggregation must preserve Unity's lossy-channel count and constant-alpha semantics. `[verified: supplemental config metadata_source; native CalculatePSNR; opinion: migration requirements]`
- Review found payload serialization inside the decode timer and an incomplete link from the supplemental DLL to the original capture identity. Both were fixed; the bound run verifies protocol-lock→identity/phase→original DLL and cohort order. A fresh40-candidate run passed, and6tests include the identity-tampering rejection plus actual native metric execution. Earlier attempts and the previous collector source remain archived. `[verified: unity-supplement2-bound.json; test_unity_supplement.py; sources/supplement-v2.py; review recheck]`

## V1 classification controls and patch regression, 2026-11-11

- Five serial CUDA classification controls retain RGB224, ResNet-18, frozen train10000/validation1000, seed20261109 and the historical cosine30 schedule. The baseline repeats66.3% and NLL0.828363 at epoch2. The other arms compare two learning rates with smoothing/weight decay or ordered cumulative loss; they do not isolate every changed component. `[verified: classification-controls/suite.json; baseline-ce.json history]`
- The ordinal variant uses one shared score with explicitly ordered softplus threshold gaps, three cumulative binary losses and class-probability argmax. It is a local rank-consistent variant, not an exact author-code reproduction. `[verified: models/ordinal.py; classification_control.py ordinal_variant]`
- Patch V1 adds monotone error outputs, optional EMA of parameters and buffers, raw/EMA validation, separate accuracy/RMSE checkpoints and validation-only margins. EMA advances only after actual optimizer updates. A checkpoint audit reloads selected weights and checks all saved validation PSNR predictions. `[verified: patch_regressor.py; patch_trainer.py track_update/audit_best; patch_metrics.py]`
- Empty threshold neighborhoods report RMSE=None and do not affect early stopping. Positive finite MSE keeps exact PSNR; predicted zero error remains infinity for decisions and uses a declared300dB placeholder only in numerical regression diagnostics. `[verified: patch_metrics.py; test_patch_metrics.py]`
- Initial formal patch trials keep the standard stem, monotone outputs, EMA0.999, AdamW/WD0.05, batch128, one warmup epoch and at most30epochs with RMSE patience5. Scratch uses lr1e-3 and pretrained3e-4, so this comparison is of V1 recipes rather than initialization alone. Group weighting, no-maxpool and image-level auxiliary loss remain later comparisons. `[verified: patch-v1/suite.json; opinion: comparison scope]`
- The archived Unity alpha reference was encoded through the actual shared DLL at10x10/exhaustive. Vertically flipped exported pixels reproduced the stored payload exactly; unflipped pixels did not. This one-image ABI/orientation probe does not establish complete candidate coverage or native quality-metric parity. `[verified: unity-dll-probe.json]`
- The initial live classification driver lacked a terminal suite summary on exceptions. Its exact started source is archived; the wrapper still records process failure. Subsequent drivers record failed/interrupted states, and both classification and patch drivers have failure-path tests. `[verified: jobs/classification-controls receipt; sources/run_classification_controls-started.py; test_classification_suite.py]`

## Unity classification90 goal, 2026-11-11

- Plan created before the active goal. The user selected Unity imported references and same-search labels for the90% target. Fixed ResNet-18 tuning precedes capacity and architecture changes. `[verified: user confirmation; create_goal result; unity-accuracy90-20261111/README.md]`
- Existing capture infrastructure assumes10000 train rows and archives a train-only manifest. Production data collection needs split-aware batches and a new cache fingerprint. `[verified: UnitySearchBaseline.prepare; UnityReferenceCapture.collect]`
- The initial probe reuses the measured LITE/RDO-off policy with a new isolated run. Editor and both DLL hashes match the prior capture identity, CUDA is available. `[verified: unity-accuracy90-20261111/preflight.json; new identity.json]`
- The user's training/validation curve prioritizes generalization diagnostics within fixed-capacity tuning. The plan includes matched eval-mode train probes, validation NLL, staged fine-tuning and early-stopping comparisons. `[verified: user image; plan fixed-model section]`
- The user selected random initialization as the main route. The initial SGD search and budget now target scratch training, with15-epoch screening and100-epoch finalists. Pretrained initialization remains a separately identified diagnostic comparison. `[verified: user steering; revised plan]`
- The first new capture launch used noUpm and produced missing Burst/Mathematics assembly errors. The owned Editor was stopped, metadata restoration reported0 conflicts, and retry1 uses the previously successful package-enabled startup. Initial failure logs and receipts are retained. `[verified: capture-probe logs; initial probe-receipt.json; capture-probe-retry1/job.json]`
- Retry1 loaded packages and compiled scripts, then failed copying Assembly-CSharp into the generated assembly directory. Both DLL/PDB currently allow exclusive read/write access. Retry2 uses a fresh run identity after those checks. `[verified: retry1 editor log and exit1 receipt; exclusive file access checks; retry2 job receipt]`
- Progress is recorded through per-job30-second heartbeats and per-epoch training histories, with public progress.json snapshots and local raw logs. `[verified: ReproductionJob.run; Trainer.fit; user progress-recording instruction]`
- Retry2 passed native2-image capture, source/policy validation and metadata restoration. Current production training remains pending complete reference data. `[verified: unity-accuracy90-20261111/probe.json]`
- Historical feature-tree preparation passed a synthetic CUDA smoke. The user's later V1 replaces that experiment with native patch regression; the unused XGBoost dependency was removed. `[verified: tree-cuda-smoke.json; user V1; uv remove result]`
- User cleared the old goal and requested a new V1 goal. The new objective references experiment plan/V1 directly, preserving Unity independent90% acceptance, CUDA, fixed-capacity comparisons and continuous repository delivery. `[verified: get_goal null; create_goal active; user request]`
- Exact240 patch targets passed for train10000/validation1000 in614.55s, with120276/12864 patches and maximum reconstructedPSNR error1.42e-14dB. The running extraction used an archived pre-cache-hardening source; its hash is retained. `[verified: patch-data-full.json]`
- CUDA regression smoke applied6updates with0AMP skips. It uses independent heads/no maxpool/no EMA and is an execution check, not the complete V1 recipe. Formal independent/monotone heads, stem, EMA and group-sampling comparisons remain tracked in the execution record. `[verified: patch-training-smoke.json; V1]`
- Twenty-image native-patch probe passed80/80 exact decode matches. Transform maxima are0.84/1.02/6.60dB for horizontal/vertical/rotation90, so initial training keeps augmentations disabled. Supplemental Unity candidate collection preserves original search labels/timing. `[verified: patch-equivalence20.json; opinion: execution decision]`
- Review fixed highest-quality fallback ties, cached sidecar identities/statistics and preprocessing config binding;10 targeted tests passed. Native standalone-patch equivalence and transform sensitivity are measured separately from full-imagePSNR reconstruction. `[verified: test_patch_targets.py; patch-equivalence-probe2.json]`

## Classification accuracy research, 2026-11-11

- Added the requested Chinese report with 35 primary sources and explicit reading depth. Recomputed frozen test confusion, feasible-candidate limits, winner margins and RGB224 cache identity. The report's hyperparameter/loss/architecture settings are proposals. `[verified: classification-accuracy-research-20261111 README.md、sources.json、diagnostics.json]`
- The current GDC reproduction CLI parses learning_rate but omits it in GDCTraining.train. Micro batch changes preserve default effective64 through accumulation. Both are documented as implementation prerequisites for a tuning sweep. `[verified: script/reproduce.py train branch; GDCTraining.train; Trainer.train_epoch]`
- Source-RGB historical experiments, Unity imported-reference production inputs and per-image policy/quality outcomes keep their own identities. Reported input-shift and candidate-ceiling conclusions retain those scopes. `[verified: report sections on input and labels; formal test2000 and captured-reference64 reports]`

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

## 2026-11-12 fixed-capacity group sampling

- Stem2 completed15epochs: selectedepoch14raw74.6%/2.5459dB, minus6.1pp against the standardstem LR0.0003 control. FrozenlastEMA with train-onlyBNreestimate reaches78.6%/2.1127dB, still below standardstem80.9%/1.3716dB; zerooptimizerupdates, process599.74seconds. `[verified: scratch-stem2-lr0003-result.json; normalization-scratch-stem2-lr0003.json; normalization-scratch-lr0003.json; correspondingjobreceipt]`
- Next single-factor control keeps standardstem/scratch/LR0.0003, caps each assetgroup at512effectiveimages and distributes imageweight across its patches. Train-only10000image analysis reduces maximumgroup share20.77%to6.41%; this is not class balancing. Defaultcap0exactly preserves prior weights; actual120276patch weights and9tests pass. CUDA48train/16validation smoke usescap2toexercise downweighting,2epochs and reload passed; fullcap512training started. `[verified: group-sampling-analysis.json; PatchSampling.weights; test_patch_sampling.py; scratch-group512smokesuite/summary; fulljobreceipt]`

## 2026-11-12：Unity四级法线评价与RGBA监督

两张开启mipmap的法线触发旧补测限制，保留首轮队列失败和已完成576train／2validation。扩展按导入设置与尺寸推导角度评价层数，逐原候选比较仍强制执行；真实40候选和原winner一致后启动新队列。历史完成producer只允许显式SHA绑定的归档复用，不重新执行旧版本。`[verified: unity-normal-multimip2.json；candidate_queue.py verify_capture_binding、run；unity-candidate-queue-multimip-v2-config.json]`

RGBA监督保存20候选×4通道int64 SSE；先整图聚合再应用恒定Alpha／非零误差通道规则。258图5160候选最大PSNR差3.74e-6dB。审查发现并修正manifest的candidate_receipt_sha256实际指向candidates.json、非单图receipt.json；补上公开报告→raw→单图内容身份链和缓存／元数据／test行反例。整图MS-SSIM与角度保留，后续模型聚合待实现。`[verified: patch_targets.py measured_image、prepare_image；test_unity_patch_targets.py；unity-patches-train256.json；opinion: 后续模型范围]`


## 2026-11-12 Unity V2 execution

### Deviations

- The always12 reference uses fastest; fixed12/medium is separately reported. Gaussian perturbations use three seeds, native dB/degrees, unbounded independent candidate noise and equal numerical sigma in the joint curve. These are explicit execution choices for the V2 precision diagnostic. `[verified: experiment report/unity-v2-20261112/launch-binding.json always12_baseline_preset、noise_model; rules-config.json seeds、sigmas]`

### Discovered edge cases

- Restricted execution denied Windows DataLoader worker pipes before any update. Preserve r0-smoke failure; the new r0-smoke-retry identity uses the same workers2 recipe with required execution permission and passed two epochs, four updates, zero AMP skips and checkpoint replay. Pytest temp access required the same execution-permission recovery and then passed50checks. `[verified: r0-smoke.json error、training_updates; r0-smoke-retry.json history、checkpoint_audit; pytest output 50passed]`
- Validation original native selections strictly pass87.4%; measured complete-quality rule replay matches100%. Keep these separate fields in reports. `[verified: experiment report/unity-v2-20261112/rules.json validation_baselines.original_rule_measured]`

### Questions for review

- Initialization promotion, production search variants and a fresh confirmation cohort remain the V2 plan's later decisions. `[verified: experiment plan/V2/README.md L111–115]`


## 2026-11-12 Unity V2 checkpoint replay repair

### Deviations

- Initial full R0 ended10epochs/6247updates with74.9% best validation but failed numeric checkpoint replay. Preserve its failed identity and11 source snapshots. New R0 retries the same recipe after fixed-order segmented sums remove repeat drift. `[verified: experiment report/unity-v2-20261112/r0.json history、error; recovery-verification.json original_training、original_recipe_matches]`

### Discovered edge cases

- Four old-pool full-validation probes preserve all1000 decisions and active quality values; repeated inactive heads/zero probabilities drift. Corrected sums yield bit-identical full-validation arrays. `[verified: r0-replay-diagnosis.json observations; r0-stable-sum-replay.json observations]`
- Initial segment-max repair changed negative upstream gradients for tied maxima. Restore original scatter_reduce amax, retain ordered sums, and add negative-tie plus CUDA repeat regressions. Intermediate smoke and code snapshots retained;55 checks and final two-epoch CUDA smoke passed. `[verified: pool-repair-review.json finding、resolution; r0-stable-sum-smoke.json status、checkpoint_audit; pytest55passed]`

### Questions for review

- The baseline retry remains active; full frozen-prediction attribution requires its successful terminal checkpoint audit. `[verified: progress.json current_training_report; script/attribute_unity_errors.py terminal-status guard]`


## 2026-11-12 native baseline completion and SSIM-weight control

- Stable-sum R0 completed8epochs/4996updates, selectedepoch5 gives73.9% and same-checkpoint2.9747dB; full checkpoint/prediction replay passed. Do not mix with epoch3 minimum RMSE2.8848dB. `[verified: baseline-result.json selected_checkpoint_metrics; r0-stable-sum.json history]`
- Frozen1000 validation replacements give MSE84.3%, zero73.9%, SSIM86.4%, angles76.6%, alltruth100%. These are conditional diagnostic replacements. `[verified: r0-attribution.json variants]`
- Next single-factor control changes only ssim_weight0.1to0.03, selected heuristically from selected-epoch patchloss0.06739 and weightedSSIM0.2353. Its32/16CUDA smoke passed4updates/reload; full trialstarted. `[verified: ssim-weight003-design.json; ssim-weight003-smoke.json; corresponding launch-preflight.json changed_training_fields]`


## 2026-11-12 validation calibration and mean-only image head

### Deviations

- The SSIMweight0.03 single-factor run completed6epochs, selected72.7%/3.6068dB and same-validation marginfit74.3%, below baseline73.9%/2.9747dB and fitted76.0%. Keep the baseline reference. `[verified: experiment report/unity-v2-20261112/comparison.json]`
- The planned mean-only pooling control reduces headinput1032to520 and71680parameters, total11305980. Initialize the full paired head then retain mean/metadata columns, preserving shared initialweights and nextRNGdraw atseed20261112. `[verified: mean-pooling-design.json]`

### Discovered edge cases

- Historical configs lack image_pooling. Model checkpoint factory defaultsmean_max, restoresmean whenexplicit, and is used by trainingaudit plus five native inference/confirmation consumers.61component and71caller checks passed; CUDA32/16smoke4updates/reload passed. `[verified: mean-pooling-verification.json; mean-pooling-smoke.json]`
- Old completed-run source hashes differ after extensions. Explicit archival binding reuses PatchNormalizationAudit.bind_training_sources, checks originalSHA and currentexecution identities.17sourcefiles frozen; full baseline attribution matches every metric andresidual after archivalreplay. `[verified: source-archive-before-mean/manifest.json; r0-attribution-archive.json training_source_binding; mean-pooling-design.json attribution_archive_replay_exact]`
- Calibration is a finite two-pass coordinatefit on the same1000validation predictions. It stores signs/parameters and exactzero-margin replay, without modelupdates/forward. `[verified: r0-calibration.json scope、best_parameters、model_forward_calls]`


## 2026-11-12 completed mean-only pooling control

- Mean-only completed10epochs/6246updates, selectedepoch9raw75.0%/3.3833dB, fullcheckpoint replay passed. Same-validation coordinatefit77.4%, withstrictquality52.0%raw/61.2%fit and354/262qualityregressions. Reports preserve both accuracy andquality under the existing Top1-only acceptance. `[verified: comparison.json results.mean_pooling; mean-pooling.json checkpoint_audit]`
- Mean-only becomes the current validation reference byTop1. Next planned factor is ImageNet initialization, with any mainline promotion governed by the plan's pending decision. Current implementation19sources preserved before initialization extensions. `[verified: comparison.json reference_model; progress.json next、source_archives; experiment plan/V2/README.md 待决定事项]`


## 2026-11-12 ImageNet initialization contrast

- Added optional RGB backbone state initialization. Raw officialResNet18 V1 weights are loaded before expandingconv1; RGBkernel copied exactly, Alpha/mask initializedzero. Actualcached44.7MiB artifactSHAf37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec,100backbone tensors verified. Nativeheads andnextRNGdraw match pairedscratchseed20261112. `[verified: imagenet-mean-design.json]`
- Trainerdefaults scratch; pretrained mode requires explicitfile+SHA, verifiedbefore/afterread andafterfinalaudit. Savedcheckpoints restore their selfcontainedstate, including when theinitializationfile isunavailable.64core/71caller checks passed andCUDA32/16smoke4updates/reload passed. `[verified: imagenet-mean-verification.json; tests/test_unity_quality.py; tests/test_unity_quality_training.py]`
- The fullImageNetmean-only contraststarted with the same otherrecipe fields. Mainlinepromotion remains the plan's pendingdecision after validation evidence. `[verified: corresponding launch-preflight.json; experiment plan/V2/README.md 待决定事项]`

## 2026-11-12 completed ImageNet contrast and full30 control

- ImageNet mean-only completed8epochs/4998updates, selectedepoch8 gives81.3% and3.4176dB, fullreload passed. Same-validation fit82.5%. The global minimumRMSE3.1267dB belongs to another epoch. `[verified: imagenet-mean-result.json; imagenet-mean.json history]`
- TrueMSE replacement90.3%, trueSSIM89.1%, trueangles83.1%, alltruth100%. Raw/fitted strictquality67.1%/70.3%, regressions203/171, costs andpayload retained. `[verified: imagenet-mean-attribution.json variants; imagenet-mean-result.json]`
- Early stopping tracks RMSE while modelselection tracksTop1. The finalepoch improvedTop1 but triggeredRMSEpatience. New scratchmean-full30 control changes onlypatience5to0 within the original30epochcap. Smoke4updates/reload passed beforefull launch. Pretrainedpromotion is pending the existing plan decision. `[verified: imagenet-mean.json history、stop_reason; mean-full30-config.json; mean-full30-smoke.json; progress.json]`

## 2026-11-13 completed full30 control and native BN diagnostic

- Scratchmean-full30 completed30epochs/18741updates, selectedepoch29 gives81.3%/2.1585dB, fullreload passed. Same-validation fit81.5%, withraw/fitted strictquality64.4%/63.9% and231/236regressions. This matches the early-stoppedImageNet Top1, so a same-budgetImageNet full30 independent contrast is prepared. `[verified: mean-full30-result.json; imagenet-full30-config.json]`
- The nativeBN script reuses PatchNormalizationAudit.recalibrate withRGBA/mask/localimageIDs/metadata, train-only4patchdraws, learnedparameter equality, original and re-estimated full1000 prediction/decision replay. Sourcearchives preserve15files. `[verified: script/audit_unity_normalization.py; source-archive-native30/manifest.json; native-bn-design.json]`
- Review caught a missing end-of-run corpus.json identity check. The expectedcorpus/config/trainingSHA now participates in prepare/end verification, with a manifest-drift regression. Realcheckpoint config uses tuple where JSON useslist, so comparison reuses ArtifactStore.fingerprint.9CPUchecks,ruff,basedpyright passed. `[verified: native-bn-design.json; tests/test_unity_normalization.py; actual mean-full30 checkpoint serializationprobe]`
- GitHub identitychecks show authenticatedlogin andrepositoryowner hamsterjiang23, but automatic approval still rejectedpush and required explicit externalpublicationauthorization. Local0f68d18 is preserved, GPUexperiments continue while that approval ispending. `[verified: GitHub get_user_login/get_repo outputs; gitpush rejection; progress.json external_push]`

- NativeBN smoke32images/128patch and full10000images/40000patch passed learnedparameter and double checkpoint replay checks. Full208.80s, BNstats88.68s, Top1fell81.3%to80.1%, RMSE2.3486dB, strictquality58.9%, regressions285. Retain the original weights. `[verified: native-bn-verification.json full_result; mean-full30-bn.json]`
- IndependentImageNet full30 smoke4updates/reload passed10.69s. Fulltrainingstartedserially, keeping mainlinepromotion pending. `[verified: imagenet-full30-smoke.json; progress.json]`

## 2026-11-13 ImageNet full30 completion and native EMA control

- ImageNetfull30 completed18743updates/7AMPskips, selectedepoch22raw85.7%/1.9217dB, selectedcheckpoint replay passed. Same-validation fit86.4%, strictquality64.5%raw/61.6%fit, regressions230/258. Nativeconfirmation remains sealed. `[verified: imagenet-full30-result.json; progress.json test_opened]`
- Existing PatchTrainer EMA code is reused for native parameters/buffers, with optimizer post-hook updates and raw/EMA Top1/RMSE selection. Default0 preserves legacy behavior. Decay0.99 is a heuristic singlecontrol.73component+71consumerchecks passed,19sources archived before extension. `[verified: mean-ema099-design.json; corresponding pytest outputs; source-archive-before-ema/manifest.json]`
- EMA follows the current scratch mainline while initializationpromotion awaits user decision. Both full30 controls use the same epochbudget, with ImageNet prefix8 matching original losses/updates/selectionmetrics exactly. `[verified: progress.json pretrained_mainline_promotion、paired_prefix_check; mean-ema099-config.json]`

- EMAoff CUDA smoke matches legacyloss/selectionmetrics for both epochs. EMAon smoke has4optimizer/4EMAupdates and identicalrawloss/metrics. Its selectedvariant israw, with selectedcheckpoint replay passed. ActualEMA126tensor checkpoint restoration is separately CPUverified and differsfromraw. The launch justification initially described the selectedvariant asEMA, corrected to the observedraw. `[verified: mean-ema099-design.json; mean-ema099-smoke.json checkpoint_audit.selected_variant; actual EMAcheckpoint probe output]`

## 2026-11-13 frozen image-head input controls

- Prepared paired sampled4/allpatch head-only refits from the same selected scratch checkpoint. Frozen RGBA/mask/metadata encodings, pixel weights and original headloss definitions are reused. Independent image/patch generators keep image order paired. Headstage uses30epochs, constantlr0.0003, batch16 and originalweightdecay/lossweights. These are execution choices within fixed-capacity E4. `[verified: image-head-refit-design.json; script/refit_unity_image_head.py; opinion: recipe choice]`
- Cache baseline must reproduce all1000 stored predictions/decisions before updates. Final best model runs the existing fresh-input nativeaudit, with all nonimagehead weights/buffers unchanged and source/corpus/cache hashes checked. CUDA testing ispending while EMA runs.150CPUchecks,ruff,basedpyright and read-only review passed. `[verified: image-head-refit-verification.json; UnityImageHeadRefit.run]`
- Staged training binds multiple JSON sources. Shared training_config_path resolution now accepts an explicit SHA-bound original native config, with the historical sole-JSON fallback. BN uses the original encoder patchdrawcount, including for allpatch headstages. Prior BN source is preserved in before-EMA archive and Git history. `[verified: UnityNormalizationAudit.training_config_path/run; tests/test_unity_normalization.py; source-archive-before-ema/manifest.json]`

## 2026-11-13 completed EMA and paired head controls

- EMA30 completed18741optimizer/EMAupdates, selectedraw epoch29 at81.3%/2.1585dB. Selectedstate/predictions equal the originalfull30 baseline exactly. BestEMAbranch80.7%/2.2188dB at30. Trainer2107.69s includes rawvalidation354.48s andEMAvalidation390.92s. `[verified: mean-ema099-result.json; mean-ema099-verification.json]`
- Frozenhead sampled4/all controls completed30epochs each, 18746updates, raw81.2%/81.1%, same-validation fits81.3%/81.4%. Full train/validation featurefiles byte-identical, frozenstatechecks andfreshnativeaudits passed. Head-onlystagecost353.17/353.99s, initial1651.94s separate. `[verified: image-head-refit-verification.json; corresponding result.json files]`
- IndependentImageNet head refit follows sampled4 mode selected by scratchcontrol rawTop1. Smoke4updates/nativeaudit passed, formalstage started. Promotionto mainline remains pending. `[verified: imagenet-head-sampled4-smoke.json; launch-preflight.json; progress.json]`
- Confirmationreadiness recheck found11train-confirmation nearpairs affecting10confirmationimages. Source/meta identities of first10frozen reserves verified, proposal preservesprimaryslots and usesreserveorder, no modelpredictions/quality used. Currentcohort unchanged, userdecision pending. `[verified: confirmation-overlap-readiness.json; privateproposal]`
- Oldconfirmation evidence expects originalpixelpipeline and legacyPythonargv. UTF8/absolute command identity now works, with unrelatedexecutionflags rejected and3real completed jobs verified. Revisedpixel evidence matches all11000developmentimages, while originalpipeline lacks18revisedassets. Staged-model and V2pixelevidence adapters remain required before final confirmation. `[verified: confirmation-job-interface-verification.json; confirmation_evidence.py; currentCPU152checks]`

## 2026-11-13 ImageNet head completion and PSNR preparation

- IndependentImageNet sampled4headstage completed30epochs/18746updates, selected25 at86.3%/1.9180dB, frozenstates/freshnativeaudit passed. Same-validation fit86.7%. Raw/fitted strictquality68.2%/64.9%, regressions193/225. Initial1647.19s andheadstage356.51s recorded separately. `[verified: imagenet-head-sampled4-result.json]`
- New PSNR preparation keeps zero supervision0.1, structural/angleweights0, selects nearRMSE thenTop1. The headstage can explicitly restore all threeimage-lossweights0.1 and usesTop1 selection. Defaultaccuracy path is unchanged numerically in the pairedCUDA smoke. Selectedcheckpoint accuracy is stored directly for both metric orders. `[verified: psnr-preparation-verification.json; UnityQualityTrainer.selection_key/fit; UnityImageHeadRefit.loss_config]`
- Preparation smoke4updates/reload passed, selectedaccuracy equals audit.154CPUchecks+ruff+bpy/review passed.39source/inputfiles623924481bytes frozen before extensions, including immutable featurecaches required by prior sourcecontracts. Fullpreparation startedserially. `[verified: psnr-preparation-verification.json; source-archive-before-psnr-warmup/manifest.json; corresponding launch-preflight.json]`

- Native PSNR-component preparation completed 30 epochs, 18,742 updates and 8 AMP skips. Epoch 25 was selected by near-threshold RMSE of 2.0059737137 dB. The complete native checkpoint audit passed and trainer wall time was 1636.34257 seconds. The preparation checkpoint scored 43.2% under the full rule. The next image-head stage explicitly restores zero/SSIM/angle weights to 0.1 and selects by Top-1. Its 32-train/1000-validation CUDA smoke completed 4 updates, passed frozen-state and native checkpoint audits, and took 117.64141 seconds. Full 30-epoch head training started. `[verified: unity-v2-20261112/psnr-preparation-result.json; psnr-head-sampled4-smoke.json; head launch-preflight.json]`
- Confirmation model admission now verifies staged lineage, complete initial training, source archives, selected artifacts and corpus identity. Initial stages may have accuracy below 90%. Final public admission requires at least 90%. Review found missing historical image_pooling handling. Both sides now default to mean_max and a regression covers omitted fields. The actual 86.3% staged model passed its 52-file structural lineage check and was rejected by final admission, with zero forward calls. `[verified: confirmation-stage-interface-verification.json; confirmation_evidence.py _model]`
- Revised pixel evidence uses the approved 18 development replacements and R.select, preserves original confirmation rows and order, and requires all 13,000 rows and the 2.0 RGBA8 RMSE threshold. The actual outer gate rejects the 11 train-confirmation near pairs. All 206 CPU checks, ruff, formatting, basedpyright and read-only review passed. The current cohort revision awaits the user's decision. `[verified: confirmation-v2-pixel-interface-verification.json; confirmation-stage-interface-verification.json cpu_tests/static_checks]`
- Head-launch resource recording initially passed a WindowsPath to psutil.disk_usage and stopped before training. The retry uses str(root), verifies the config and job files already written, completes preflight, and launches once. `[verified: jobs/psnr-head-sampled4-smoke/launch-preflight.json setup_retry; smoke receipt.json]`

- The PSNR two-stage control completed head training for 30 epochs and 18,747 updates with 3 AMP skips. Epoch 27 scored raw/fitted Top-1 of 76.4%/77.1% and selected-weight near-threshold RMSE of 2.0083839936 dB. Full frozen-state and native checkpoint audits passed. Head wall time was 352.18557 seconds and both training stages totalled 1988.52814 seconds. Keep the 81.3% scratch reference. The 22 source/input files for these completed stages were archived before future sampling changes, totalling 317,919,625 bytes. `[verified: psnr-head-sampled4-result.json; progress.json source_archives.before_image_sampling; source-archive-before-image-sampling/manifest.json]`
- Attribution completed successfully with status completed. An orchestration assertion expected passed and stopped before calibration setup. The corrected assertion used the observed status, then the new calibration job completed with 77.1% fitted Top-1 and zero forward calls. `[verified: psnr-head-sampled4-attribution.json; jobs/psnr-head-sampled4-calibration/launch-preflight.json; psnr-head-sampled4-calibration.json]`

- Native sampling controls use the existing DatasetSplitter.asset_group rule and casefold the resulting identity. The frozen training corpus has 2,325 direct parent directories and 1,318 asset families. The source row.group values remain part of the original corpus. The cap64 arm selects at most 64 distinct images per family uniformly each epoch and visits 5,622 images. The normal-repeat2 arm retains all 10,000 images and adds one visit for each of the 299 normals, giving 10,299 visits per epoch. These are chosen finite control values. `[verified: image-sampling-design.json; unity_image_sampling.py; opinion: control choices]`
- Both arms retain the reference 30-epoch schedule. Capping changes the optimizer-step budget and normal repeats add visits, so actual draws, steps and costs are recorded. Sampling uses input paths and canonical native normal metadata. Every enabled epoch compares the actual original_image_index sequence with the planned sampler order and writes a SHA-bound receipt. Training terminal checks and model admission bind those receipts. The image-head refit stage resets these fields to its own once-per-image recipe. `[verified: unity_quality_trainer.py; unity_image_sampling.py receipt; confirmation_evidence.py; refit_unity_image_head.py]`
- All 223 related CPU checks, ruff, formatting and basedpyright passed. Read-only review was CLEAN. CUDA default smoke reproduced old per-epoch losses, accuracy, full choice and RMSE exactly with 4 updates. Capping and normal-repeat smokes passed selected-weight reload with 2 and 6 updates. The cap64 full job started first because it has fewer epoch draws. `[verified: image-sampling-verification.json; jobs/mean-familycap64/launch-preflight.json; opinion: launch order]`

- Asset-family cap64 completed 30 epochs, 10,553 updates and 7 AMP skips. Epoch 30 scored raw/fitted Top-1 of 78.0%/79.0% and selected-weight near-threshold RMSE of 2.8969578093 dB. Native checkpoint audit passed. The 30 epoch receipts independently reconstruct all per-family quotas, 168,660 visits and 9,055 distinct training images from the 10,000 available images. The remaining 945 images were unvisited in this capped run. Trainer wall time was 1319.44076 seconds. The scratch reference remains 81.3%. `[verified: mean-familycap64-result.json; image-sampling-verification.json]`
- Confirmation structural admission bound all 30 sampling receipts and 52 evidence files, then final public admission rejected the 78.0% model below 90%. Normal-repeat2 formal training started after the cap job exited successfully. This next arm visits all 10,000 images each epoch, including two visits for each of the 299 normals. `[verified: image-sampling-verification.json; jobs/mean-normalrepeat2/launch-preflight.json]`
- The frozen report asset_group_macro uses 487 validation parent directories. A separate recomputation uses 189 historical asset families. The current ImageNet head control scores 88.53% on that family macro. Replacing all normal footprint predictions by labels while freezing other decisions gives 87.4% overall. Shared-model controls retain priority before specialization. `[verified: sampling-group-normal-diagnostics.json; opinion: priority]`

- Normal-repeat2 completed 30 epochs, 19,310 updates and 10 AMP skips. Epoch 30 scored raw/fitted Top-1 of 79.2%/79.8% and selected-weight near-threshold RMSE of 2.2757163144 dB. Native reload passed. Each of 30 receipts independently matches one visit per color image and two per normal image, with 308,970 visits, 10,000 distinct images and 17,940 normal visits. Trainer wall time was 1707.89297 seconds. The scratch reference remains 81.3%. `[verified: mean-normalrepeat2-result.json; image-sampling-verification.json]`
- Enter the planned ResNet-34 capacity control after these selected fixed-capacity controls stayed below the validation gate. A 23-file, 208,843-byte source/test snapshot preserves the completed sampler version. The larger encoder has 21,414,140 parameters and keeps 512-dimensional features, native inputs, shared head initialization and subsequent CPU RNG paired with the ResNet-18 control. Constructor pairing was checked against archived code and a real historical checkpoint lacking the architecture field. `[verified: resnet34-design.json; resnet34-legacy-initialization-probe.json; source-archive-before-resnet34/manifest.json; opinion: capacity choice]`
- The first synthetic CPU architecture probe used a float mask and was rejected by native input validation. Its bool-mask retry passed and both records remain private. Real CUDA ResNet-34 smoke completed four updates, passed native checkpoint replay, used 1,735,203,328 peak VRAM bytes, and took 11.73725 seconds. The post-change default ResNet-18 CUDA smoke reproduced old losses and validation metrics exactly. All 229 related CPU checks, static checks and read-only review passed before full30 launch. `[verified: resnet34-verification.json; mean-resnet34-smoke.json; mean-resnet34-default-smoke.json]`

## 2026-11-13 Unity V2测试资源分类修正

- 之前整组CPU检查的命名遗漏一项实际CUDA池化回归，206／223／229项结果分别补记205／222／228项CPU及1项CUDA，原命令与结果保留。历史窗口的GPU独占性未完整证明，实际训练wall time保留。后续训练期间显式排除CUDA项，空闲后单独串行运行。`[verified: tests/test_unity_quality.py L356–360；confirmation-stage-interface-verification.json cpu_tests；image-sampling-verification.json cpu_tests；resnet34-verification.json cpu_tests]`

- ResNet-34完整30轮重载通过，Top-1为79.2%、所选权重近阈值RMSE2.7386dB，同验证集拟合79.4%。保留负结果及原81.3%参照。推理计时新增显式历史源码归档绑定，完整输入与训练Dataset逐patch核对，批量耗时按图数摊销，加载与绑定审计成本单列。`[verified: mean-resnet34-full30-result.json；inference-cost-input-readiness.json；reproductions/unity_search_baseline/inference_benchmark.py bind_training_sources、timing_summary]`

- ResNet-34 ImageNet完成30轮／18,742更新，epoch29 raw为86.2%、近阈值RMSE1.6128dB，同验证集余量拟合86.8%，原生重载通过。真实MSE与MS-SSIM单独替换分别为92.6%与92.2%，继续复用sampled4整图头再训练协议，冻结encoder和channel head。确认集forward保持0。`[verified: imagenet-resnet34-full30-result.json；imagenet-resnet34-head-design.json；opinion: 下一项单项对照选择]`

- ResNet-34 ImageNet sampled4整图头完成30轮／18,746更新，选中epoch15／image_head_refit，原始Top-1为86.9%，同验证集拟合87.1%，同权重近阈值RMSE1.6135dB。冻结非头部状态和原生重载通过，正式模型准入以低于90%拒绝、forward为0。当前源码及绑定输入53份／333226055字节已归档，后续按V2容量路线准备ResNet-50。`[verified: imagenet-resnet34-head-sampled4-result.json；imagenet-resnet34-head-evidence.json；resnet50-source-readiness.json；opinion: 后续容量选择]`

- ResNet-50采用2048维Bottleneck编码器和配套FiLM／预测头，三处特征缓冲区统一由channel_head.in_features获取，均值模型24,003,068参数。旧18／34四组初始化状态和RNG、实际旧权重CPU恢复、旧18CUDA训练及旧34完整1000图CUDA预测重放均精确一致。新50模型4更新／重载及实际16图流式CUDA预检通过，完整30轮已启动。`[verified: resnet50-design.json；resnet50-legacy-cpu-verification.json；resnet50-verification.json；opinion: 容量实现选择]`

- ResNet-50随机初始化30轮完成，epoch26／raw为80.5%、近阈值RMSE2.6311dB，同验证拟合81.1%，原生重载通过，负结果保留。全1000图预测重放和22份只读模型血缘通过，正式90%准入拒绝。下一独立初始化显式选择官方IMAGENET1K_V1，实际CPU迁移及CUDA4更新预检通过，同配方完整训练已启动。`[verified: mean-resnet50-full30-result.json；mean-resnet50-full30-verification.json；imagenet-resnet50-design.json；opinion: 初始化版本选择]`

- ResNet-50 ImageNet IMAGENET1K_V1完整30轮完成，epoch25／raw为85.6%、近阈值RMSE1.6411dB，同验证拟合85.9%，原生重载通过。同1000图推理重放、22份模型血缘通过，正式90%准入拒绝。2048维整图头CUDA预检完成4更新、初始1000图复现、冻结及重载后启动完整对照。另将V2计划的进度链接从旧数据采集目录修正到当前V2实验目录。`[verified: imagenet-resnet50-full30-result.json；imagenet-resnet50-head-design.json；experiment plan/V2/README.md 运行约束]`

- ResNet-50 ImageNet V1整图头30轮完成，epoch7／image_head_refit为86.0%、近阈值RMSE1.6389dB，同验证拟合86.3%，冻结与重载通过。1000图重放及39份血缘通过，正式90%准入拒绝。下一同架构权重版本对照选择官方IMAGENET1K_V2，四项配置差异为权重路径／SHA和输出位置，实际CPU迁移、六个共同头／RNG配对及CUDA4更新预检通过。`[verified: imagenet-resnet50-head-sampled4-result.json；imagenet-resnet50-head-evidence.json；imagenet1k-v2-resnet50-design.json；opinion: 下一权重版本选择]`


## 2026-11-13 IMAGENET1K_V2 ResNet50完整结果

- 同架构权重版本对照完成30轮，原始／同集拟合Top-1均85.4%，所选epoch19／raw近阈值RMSE1.9043dB，22份只读来源绑定和原生重载通过，正式90%准入拒绝。`[verified: experiment report/unity-v2-20261112/imagenet1k-v2-resnet50-full30-result.json；imagenet1k-v2-resnet50-evidence.json]`
- 冻结预测实测MSE与MS-SSIM单项替换各91.9%，角度86.5%，全部实测100%；按既有sampled4配方准备独立整图头预检和完整配置。`[verified: imagenet1k-v2-resnet50-full30-attribution.json variants；imagenet1k-v2-resnet50-head-sampled4-config.json；opinion: 后续顺序]`
- 执行报告概览内残留的最佳独立ImageNet86.3%已与实际ResNet34头部结果86.9%对齐。`[verified: README.md“当前结果”；imagenet-resnet34-head-sampled4-result.json]`

- IMAGENET1K_V2整图头完成30轮，85.3%／同集拟合85.5%，epoch20近阈值RMSE1.8845dB；冻结状态和原生重载通过，正式90%准入拒绝，39份来源绑定通过。`[verified: experiment report/unity-v2-20261112/imagenet1k-v2-resnet50-head-sampled4-result.json；imagenet1k-v2-resnet50-head-evidence.json]`
- 首次内存监控的受限CIM查询失败，原日志及错误说明保留，转用通过权限核验的resource-monitor-v2.jsonl，实际训练顺序保持并成功结束。`[verified: .local/unity-v2-20261112/jobs/imagenet1k-v2-resnet50-head-sampled4/resource-monitor-v1-error.json；resource-monitor-v2.jsonl；receipt.json]`


## 2026-11-13 validation1000系统变体离线评估

- 依用户本次授权执行3模型、原始／已校准预测两口径、39变体共234组。输入为保存预测与开发语料20候选指标，运行守卫中模型、优化器、编码器、CUDA及确认集访问均为0。`[verified: experiment report/unity-v2-20261112/system-variants-verification.json runtime_guards、evaluated_arms]`
- ResNet34原始的预测preset双向K=2为94.0%／1.547次、K=3为95.3%／1.712次；向后续搜93.6%／1.627次、质量回退0。全局最少平均达到90%为ResNet18预训练原始双向K=2，92.6%／1.543次。`[verified: system-variants-result.json models.imagenet-resnet34-head-sampled4.raw、minimum_encoding_solutions_at90]`
- 原搜索与A法线路由主费用用原始search_ms，独立保留archive-matched估算；首版费用口径及17文件源码/配置/结果SHA归档保留。先写成本回归测试确认48ms与应有123ms冲突，修正后重跑小样本与全量并通过独立234臂费用重算。`[verified: system-variants-verification.json cost_correction、independent_readonly_review；tests/test_unity_system_variants.py test_native_route_uses_original_search_time_and_archive_reference]`
- 本轮切换前的训练集推理诊断已停止，原部分报告及中止回执保留。新离线评估采用独立身份和零执行守卫。`[verified: system-variants-verification.json preceding_development_fit_diagnostic、runtime_guards]`
