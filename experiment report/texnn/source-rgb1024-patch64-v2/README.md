# TexNN project adaptation

The measured chain includes native labels, six Appendix-sized networks, cascaded prediction, actual ASTC encoding and decoding. This is a bounded project adaptation. Original published performance remains unverified. `[verified: accompanying JSON scope, training, audit and limits]`

| Footprint / top-k | Images | Predicted / fallback blocks | Mean PSNR delta | Pipeline / reference time |
|---|---|---|---|---|
| 4x4-top1x1 | 8 | 5929 / 0 | -5.634 dB | 0.182x `[verified: validation8-patch128.json groups.4x4-top1x1]` |
| 4x4-top3x10 | 8 | 5929 / 0 | -1.073 dB | 0.678x `[verified: validation8-patch128.json groups.4x4-top3x10]` |
| 6x6-top1x1 | 8 | 2888 / 0 | -5.513 dB | 0.112x `[verified: validation8-patch128.json groups.6x6-top1x1]` |
| 6x6-top3x10 | 8 | 2888 / 0 | -1.631 dB | 0.702x `[verified: validation8-patch128.json groups.6x6-top3x10]` |
| 8x8-top1x1 | 8 | 1593 / 0 | -6.535 dB | 0.122x `[verified: validation8-patch128.json groups.8x8-top1x1]` |
| 8x8-top3x10 | 8 | 1593 / 0 | -2.365 dB | 0.796x `[verified: validation8-patch128.json groups.8x8-top3x10]` |

The ratio includes RGB preparation, P-NN inference, native ideal-endpoint features, DEM-NN inference, prediction-file I/O, CLI starts and final encoding. Source-crop preparation, model loading, label generation, training and verification are recorded separately. Lower ratios mean less elapsed time. `[verified: accompanying JSON per_image.timings, costs and training; evaluation.py evaluate]`

Fallback uses the unchanged historical full search when predicted candidates are invalid. Its time is included. Lossless pairs are excluded from finite PSNR deltas and retained per image. `[verified: native/prediction.cpp texnn_process_block; accompanying JSON groups and per_image]`

## Reproduction limits

- Bounded project training patches differ from the original 2050-texture corpus. `[verified: accompanying JSON limits]`
- Training uses an 85/15 block split; evaluation uses separate validation images. `[verified: accompanying JSON limits]`
- Snapshot, class mapping, endpoint padding, Gaussian scale, Adam and patience are reconstructed. `[verified: accompanying JSON limits]`
- CLI, file exchange and debug decision logging remain timed overheads. `[verified: accompanying JSON limits]`
- Model loading is separate from inference; Unity/Nah times are not comparable. `[verified: accompanying JSON limits]`
- Published performance and million-block training scale are not reproduced. `[verified: accompanying JSON limits]`

Full per-image records, model/data fingerprints and audit results: [validation8-patch128.json](validation8-patch128.json). `[verified: accompanying JSON]`
