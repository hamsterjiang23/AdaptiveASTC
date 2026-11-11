# GDC 2023 block-size classification

The talk implementation follows offline ASTC candidate compression, decompression, PSNR-based label selection, ResNet classification and one final encode using the predicted footprint. Original label selection uses PSNR >35 dB. `[verified: archived talk 11:00, 11:28 and 12:28; source.json]`

The existing historical LITE experiment remains under `experiment report/gdc-lite-rgb-resnet18-seed20261109`. It uses RGB source images and historical mixed-preset/RDO labels. Final compression quality and byte benefits have not been measured there. `[verified: existing training_report.md L56–60]`

The new compression-loop reproduction follows Nah 2023, Nah 2022 and TexNN. Preserve the talk's reconstructed settings and the project LITE adaptation as separate experiment identities. `[verified: accepted plan]` `[opinion]`

## Fresh measured label preparation

`dataset.py` prepares new candidate-compression labels and a manifest accepted by the existing ResNet trainer. Source splits and their RGB224 classifier cache remain frozen. Labels are regenerated from original-resolution source RGB8 with Linear LDR, no mipmaps and no RDO. The project reconstruction uses the already pinned official astcenc 3.3 with medium encoding and one encoding thread; decode uses the CLI default. This reconstructs settings absent from the talk. `[verified: dataset.py GDCMeasuredDataset.collect/_collect_one; common/encoder.py decode]` `[opinion]`

The first project candidate set is 6×6, 8×8, 10×10 and 12×12, matching the existing four-output model. This is a recorded four-square adaptation, not a claim that it is the talk's complete candidate set. All four candidates are encoded and decoded. Selection uses strict RGB PSNR >35 dB and minimum measured ASTC payload. Rounded-byte ties prefer larger footprint area. If no candidate passes, the highest measured PSNR is retained and flagged as a quality violation; this fallback is a local reconstruction. `[verified: dataset.py GDCLabelSelection.choose and collect protocol; config.py CLASSES; source.json missing_original_artifacts]` `[opinion]`

```powershell
uv run --frozen python script/reproduce.py dataset --method gdc2023 --run-id source-rgb35-medium-probe --input-set probe --workers 2
uv run --frozen python script/reproduce.py dataset --method gdc2023 --run-id source-rgb35-medium-full --input-set full --workers 4
uv run --frozen python script/reproduce.py assemble --method gdc2023 --run-id source-rgb35-medium-full
```

The full manifest keeps10,000 training,1,000 validation,1,000 calibration and2,000 test images from the source split. Formal label generation and full admission passed. CUDA training completed30epochs in689.862s with4709 applied updates and1AMP skip, using the best validation checkpoint at epoch2. Independent [test2000](<../../experiment report/gdc2023/source-rgb35-medium-full/test2000/README.md>) passed final encoding and report audit. Strict RGB35 passed1540 images for the model,1505 for fixed8 and1782 for offline best labels. Quality violations are retained. The [smoke report](<../../experiment report/gdc2023/source-rgb35-medium-smoke/test16/README.md>) preserves the earlier32-train/16-test chain. `[verified: formal manifest.json; training_complete.json; history.json; wall-clock.json; test2000/pretrained-test.json quality]`

## Training and measured final encoding

The GDC training wrapper reuses the existing `Trainer` and validates the measured labels and RGB224 caches before fitting. It records attempt wall clocks, archives previous checkpoints on resume and retains unknown timing when prior work has no matching ledger. The generic `script/train.py` remains available; complete wall-clock accounting for this reproduction uses the wrapper below. `[verified: training.py GDCTraining.validate_data/train]`

```powershell
uv run --frozen python script/reproduce.py train --method gdc2023 --run-id source-rgb35-medium-full --epochs 30 --micro-batch 64 --workers 2
uv run --frozen python script/reproduce.py evaluate --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id test2000 --split test
uv run --frozen python script/reproduce.py report --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id test2000
```

The evaluator verifies current training completion and all sources/labels before opening test inference. `EvaluationSeal` preserves probability-evaluation checkpoint/temperature bindings and adds compression-model identities. Model warmup is counted in setup. Per-image deployment time includes source RGB preparation, RGB224 normalization, inference and one final ASTC encode, with a separately measured fixed8 control. Auditing checks exact ASTC and decoded PNG agreement with frozen candidate measurements; audit time is separate. `[verified: evaluation.py completed_training/preflight_inputs/evaluate; utils/evaluation_seal.py; reporting.py write]`

The report also audits all four offline candidates on the evaluation inputs and publishes fixed6/8/10/12 quality and actual payload controls. Candidate encode times retain their parallel label-collection scope. The separately measured fixed8 pipeline is the paired deployment latency control. `[verified: reporting.py write offline_fixed_footprints; smoke/test16/pretrained-test.json]`

The original preparation observer was interrupted by an OS reboot. Its archived receipt retains unknown exit duration. The successful complete assembly retry is recorded in `preparation-process.json`, with candidate collection5263.531s, successful assembly1666.137s and failed assembly325.604s as separate known components. The original startup and partial assembly duration remains unknown. Evaluation binds timing metadata by SHA and the report verifies protocol, collection and manifest identities. `[verified: preparation-process.json known_components and prior_interrupted_process_sha256; costs.py PreparationCost; reporting.py]`

## Shared Unity64 diagnostic

The existing Unity/Nah shared64 cohort belongs to the training split. The following additional evaluation uses the completed formal GDC model and records resubstitution results; the independent test2000 remains the generalization evaluation. The cohort config is checked against its frozen protocol-lock hash, which is checked against the baseline receipt. Its name, config hash and ordered paths are bound into evaluation and report metadata. `[verified: common/cohort.py EvaluationCohort.unity64/rows; evaluation.py evaluate; reporting.py write]`

```powershell
uv run --frozen python script/reproduce.py evaluate --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id shared64 --split train --cohort unity64
uv run --frozen python script/reproduce.py report --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id shared64
uv run --frozen python script/compare_reproductions.py --gdc-report "experiment report/gdc2023/source-rgb35-medium-full/shared64/pretrained-train.json" --output "experiment report/reproduction-shared64"
```

The completed [source64 comparison](<../../experiment report/reproduction-shared64/README.md>) verifies source identities, identical RGB PNG hashes across Nah/GDC and recomputed RGB PSNR. Nah ASTCs are freshly decoded by each pinned binary. Native capture measured38/64 source-equal RGB references and26 changed references. The additional [captured-reference64 comparison](<../../experiment report/reproduction-unity-reference64/README.md>) gives all methods the same imported mip0 RGB inputs. Method targets, presets, import processing and timing scope remain explicit. `[verified: both comparison.json files; common/comparison.py and reference_comparison.py]`

## Captured Unity reference inputs

Native export measured38/64 source-equal RGB inputs and26 changed inputs. [The capture report](<../../experiment report/unity-reference64-lite-rdo-off/README.md>) records dimensions, hashes, selected ASTCs and vertical row-origin normalization. Nah and GDC can consume these exported RGB pixels for common-input quality measurement. Unity retains its import Alpha and texture-usage policy. `[verified: capture summary.json; common/unity_reference.py; reference evaluator]`

```powershell
uv run --frozen python script/reproduce.py prepare --run-id unity-reference64-lite-rdo-off --capture-references
uv run --frozen python script/reproduce.py run --phase probe --run-id unity-reference64-lite-rdo-off --capture-references
uv run --frozen python script/reproduce.py run --phase smoke1 --run-id unity-reference64-lite-rdo-off --capture-references
uv run --frozen python script/reproduce.py collect --phase smoke1 --run-id unity-reference64-lite-rdo-off --capture-references
uv run --frozen python script/reproduce.py evaluate --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id unity-reference64 --split train --reference-capture "experiment report/.local/unity-reference64-lite-rdo-off-retry1/references/normalized-smoke1" --images 64
uv run --frozen python script/reproduce.py report --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id unity-reference64
```

The normal `report` action recognizes the reference schema and verifies model/capture identities, per-image receipts, input bytes, native output hashes and recomputed RGB quality. The two-image smoke and complete64-image evaluation/report passed. On captured inputs the source-trained model and fixed8 each pass46/64 strict RGB35, with11,881,536 versus8,735,312 payload bytes. This is a training-cohort input-shift diagnostic. Model training requires CUDA in both GDC and TexNN entry points. `[verified: reference_reporting.py; unity-reference64/pretrained-unity-reference.json; training/trainer.py and texnn/training.py]`

## Interrupted evaluation recovery

The formal test evaluation encountered a Windows progress-file replacement failure after218 complete image receipts. A new process identity continues the same evaluation with `--resume`, the same sealed model and unchanged data binding. Completed images pass source/candidate/artifact, ASTC header, RGB quality and timing checks before reuse. Earlier valid progress entries additionally bind receipt hashes. Partial image attempts are archived. `[verified: evaluate-test2000 job receipt and stderr.log; evaluation.py; recovery.py]`

```powershell
uv run --frozen python script/reproduce.py evaluate --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id test2000 --split test --resume
uv run --frozen python script/compare_reproductions.py --unity-reference --gdc-report "experiment report/gdc2023/source-rgb35-medium-full/unity-reference64/pretrained-unity-reference.json" --output "experiment report/reproduction-unity-reference64"
```

Public costs include each matching broker job, its command/configuration and log hashes, failed attempts and known wall time. A missing historical process duration leaves the cumulative duration unknown. Per-image pipeline totals retain each admitted measurement once. `[verified: costs.py EvaluationProcessCost; reporting.py costs; evaluation.py receipt fields]`

Training distinguishes step attempts from actual optimizer calls through a post-step hook. Scheduler advancement and best-checkpoint selection require an applied update. The first two-image, one-epoch probe skipped its sole update under AMP and is retained as a diagnostic. The 32-image smoke applied ten optimizer updates without skips. This behavior is covered by CPU GradScaler overflow and normal-update tests. `[verified: training/trainer.py train_epoch/fit; source-rgb35-medium-smoke history.json; tests/test_amp_step_accounting.py]` [PyTorch 2.8 AMP example](https://docs.pytorch.org/docs/2.8/notes/amp_examples.html#typical-mixed-precision-training), [optimizer post-step hook](https://docs.pytorch.org/docs/2.8/generated/torch.optim.Optimizer.register_step_post_hook.html).
