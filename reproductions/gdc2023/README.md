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

The full manifest keeps 10,000 training, 1,000 validation, 1,000 calibration and 2,000 test images from the source split. Probe and smoke identities use smaller counts and are marked as smoke data. Training uses the existing `script/train.py` with explicit `--run-dir` and `--report-dir`; source labels are prepared first and the model/compression evaluation follows the agreed literature-first order. Current preparation code has unit/static checks only; native label generation and a fresh GDC training/evaluation chain have not run. The eleven GDC tests cover strict selection, artifact admission and rejecting unsupported full-input requests in Nah. `[verified: script/reproduce.py gdc2023 branch; dataset.py assemble/validate_receipt; tests/test_gdc_labels.py; verification.json]`
