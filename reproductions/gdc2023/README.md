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

The full manifest keeps 10,000 training, 1,000 validation, 1,000 calibration and 2,000 test images from the source split. Probe and smoke identities use smaller counts and are marked as smoke data. The measured smoke chain generated 64-image labels, trained on 32 images for ten epochs, and encoded 16 test images with predicted footprints. It passed the real encoding/decode/hash checks; strict quality passed for 5/16. The [smoke report](<../../experiment report/gdc2023/source-rgb35-medium-smoke/test16/README.md>) preserves that violation rate. Formal 14k label generation is running, and formal training/evaluation remain pending. `[verified: smoke pretrained-test.json quality, costs and protocol; current full label-run output]`

## Training and measured final encoding

The GDC training wrapper reuses the existing `Trainer` and validates the measured labels and RGB224 caches before fitting. It records attempt wall clocks, archives previous checkpoints on resume and retains unknown timing when prior work has no matching ledger. The generic `script/train.py` remains available; complete wall-clock accounting for this reproduction uses the wrapper below. `[verified: training.py GDCTraining.validate_data/train]`

```powershell
uv run --frozen python script/reproduce.py train --method gdc2023 --run-id source-rgb35-medium-full --epochs 30 --micro-batch 64 --workers 2
uv run --frozen python script/reproduce.py evaluate --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id test2000 --split test
uv run --frozen python script/reproduce.py report --method gdc2023 --run-id source-rgb35-medium-full --evaluation-id test2000
```

The evaluator verifies current training completion and all sources/labels before opening test inference. `EvaluationSeal` preserves probability-evaluation checkpoint/temperature bindings and adds compression-model identities. Model warmup is counted in setup. Per-image deployment time includes source RGB preparation, RGB224 normalization, inference and one final ASTC encode, with a separately measured fixed8 control. Auditing checks exact ASTC and decoded PNG agreement with frozen candidate measurements; audit time is separate. `[verified: evaluation.py completed_training/preflight_inputs/evaluate; utils/evaluation_seal.py; reporting.py write]`

Training distinguishes step attempts from actual optimizer calls through a post-step hook. Scheduler advancement and best-checkpoint selection require an applied update. The first two-image, one-epoch probe skipped its sole update under AMP and is retained as a diagnostic. The 32-image smoke applied ten optimizer updates without skips. This behavior is covered by CPU GradScaler overflow and normal-update tests. `[verified: training/trainer.py train_epoch/fit; source-rgb35-medium-smoke history.json; tests/test_amp_step_accounting.py]` [PyTorch 2.8 AMP example](https://docs.pytorch.org/docs/2.8/notes/amp_examples.html#typical-mixed-precision-training), [optimizer post-step hook](https://docs.pytorch.org/docs/2.8/generated/torch.optim.Optimizer.register_step_post_hook.html).
