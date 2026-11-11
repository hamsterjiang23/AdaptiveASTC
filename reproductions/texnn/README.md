# TexNN paper reimplementation

The user-supplied main paper is archived in `materials/paper.pdf`. Its 13-page Appendix is archived in `materials/appendix.pdf`, SHA-256 `beb6457e1aedb9c53028af812a3058fdc9560ff834e6b513b7dd828dcd2e0bf9`. `source.json` records both original paths and hashes. The main paper contains 12 pages, journal pages 328–339, DOI 10.1111/cgf.13534. `[verified: source.json; pdfinfo and SHA-256 outputs]`

P-NN predicts the lexicographically ordered partition count/index label from block pixels. DEM-NN jointly predicts endpoint/decimation configuration from block pixels and computed base colors. Top-k predictions must feed a real encoder before encoding quality and speed can be evaluated. `[verified: supplied PDF p.7, §3.5 and Fig.5–6]`

The paper trains separate 4×4, 6×6 and 8×8 networks using cross entropy, an 85/15 block split, batch sizes 100–200, learning rates around 1e-4 and dropout 0.6. The main paper's S1/S2 appear as Tables 1 and 2 on Appendix p.1. Their dimensions are encoded in `architectures.json` and `models.py`. `[verified: main paper pp.7–8 §3.6 and p.12 Supporting Information; Appendix p.1; architectures.json]`

| Block | P-NN layers | DEM-NN layers |
|---|---|---|
| 4×4 | 256 → 512 → 1024 → 2048 → 3069 | 128 → 256 → 512 → 1024 → 1314 `[verified: Appendix p.1 Tables 1–2]` |
| 6×6 | 256 → 512 → 512 → 1024 → 2048 → 3069 | 128 → 256 → 512 → 1024 → 2048 → 3650 `[verified: Appendix p.1 Tables 1–2]` |
| 8×8 | 256 → 512 → 512 → 1024 → 1024 → 2048 → 3069 | 128 → 256 → 512 → 1024 → 2048 → 4096 → 7154 `[verified: Appendix p.1 Tables 1–2]` |

Six networks passed CPU forward-shape probes. The local feature packing uses native bottom-left RGB blocks, followed by 24 padded ideal RGB endpoint values for DEM-NN. Default ReLU, Gaussian standard deviation 0.01, zero biases and hidden-layer dropout probability 0.6 are explicit reconstruction choices. Training protocols must record overrides. `[verified: models.py TexNNClassifier; network-shape-probe.json; native/labels.cpp]` `[opinion]`

## Historical reference encoder and labels

The reference source is pinned to `ddadf547770ddbe8261cfd854b2a5f21b3a9074c`, the latest upstream main revision before the citation's access date of 2017-06-20. This snapshot selection is a reconstruction choice. Author code and the exact author-used revision remain source artifacts to locate. The original license is retained in `reference-license.txt`. `[verified: upstream git log origin/main --before=2017-06-21; main paper reference ARM12; source.json; reference-license.txt]` `[opinion]`

`reference.py` builds the original codec and a label observer. It generates the hooked top-level file under the ignored build directory and preserves the clean upstream checkout. `native/labels.cpp` exports the final physical ASTC block, partition pair, endpoint modes, block/decimation/quantization/dual-plane fields, normalized RGB and computed ideal endpoints. `[verified: reference.py build; native/labels.cpp texnn_export_block]`

The historical stb loader flips PNG rows. Pixel checking therefore uses bottom-left coordinates, nearest-edge padding and the exact input image dimensions. The collector verifies every label against its ASTC payload, source pixels and legal native configuration catalog, then compares the complete observer output with original-codec output. Native probes cover all three footprints, constant blocks and two actual project textures. `[verified: upstream astc_stb_tga.cpp L31/L76; data.py verify_labels/collect; reference probe report]`

```powershell
uv run --frozen python script/reproduce.py fetch --method texnn
uv run --frozen python script/reproduce.py build --method texnn
uv run --frozen python script/reproduce.py collect --method texnn --source path/to/image.png --footprint 4x4 --run-id new-label-run
```

Each collection uses a fresh run directory. Supported footprints are 4×4, 6×6 and 8×8, with historical veryfast/fast/medium/thorough/exhaustive presets. Collection stores raw JSONL, catalog, ASTC, decoded TGA and hashed receipts under `experiment report/.local/reproduction-runs/texnn/`. The shared full Unity-baseline acceptance gate is checked before collection. `[verified: script/reproduce.py TexNN branch; data.py collect]`

## Cascaded training and native encoding

The project adaptation has completed label collection from 64 training-image crops, six-network training and 48 learned/reference encoding pairs on eight separate validation-image crops. All ASTCs were decoded again during report generation: 96 reconstructions matched the original saved hashes. The [measured report](<../../experiment report/texnn/source-rgb64-patch64-v2/README.md>) records quality losses, bytes, model/data hashes and complete pipeline times. This scale does not reproduce the paper's original training corpus or reported performance. `[verified: source-rgb64-patch64-v2/validation8-patch128.json training, groups, audit and limits]`

Features use `partition_single_plane_rgb24_v2`: ideal RGB endpoints are fitted from pixels and a partition alone. Both teacher collection and inference call the same native helper. The earlier v1 observer used the teacher's dual-plane decision for some endpoint fits; its archived probes establish physical-block/pixel pairing only and cannot supply current training inputs. The corpus packer rejects v1 labels. `[verified: native/labels.cpp texnn_ideal_endpoints; corpus.py rows; tests/test_texnn_runtime.py test_native_teacher_configurations_and_partition_features]`

P-NN classes use the clean codec's legal partition catalog in lexicographic order. DEM-NN classes use observed canonical `(physical block mode, dual component, endpoint modes)` tuples, padded by repeating the last active endpoint mode. Delta encoding families share their base packing format. Unused Appendix-sized logits are masked during inference; training retains full-width cross entropy and reports both raw and masked accuracy. This reconstructs a usable label identity because author class maps are unavailable. It does not assert identity with the author's enumeration. Class overflow fails explicitly instead of truncating labels. `[verified: corpus.py prepare; runtime.py TexNNConfiguration; inference.py _top; training.py epoch]` `[opinion]`

`texnn-predict` accepts P-NN partitions, computes endpoints for DEM-NN, then encodes candidate configurations with the pinned codec's fixed-partition solvers. It selects the lowest measured weighted error among feasible candidates. Invalid candidate sets fall back to the original full search, with that work included in encoding time. Constant blocks retain the reference fast path. The implementation still computes ideal weights for all grids and uses Python/native file exchange; those costs are retained in measurements. `[verified: native/prediction.cpp texnn_process_block; native/solver.inc; reference.py build; evaluation.py evaluate]`

```powershell
uv run --frozen python script/reproduce.py dataset --method texnn --run-id source-rgb64-patch64-v2 --images 64 --patch-size 64 --workers 2
uv run --frozen python script/reproduce.py train --method texnn --run-id source-rgb64-patch64-v2 --all-footprints --epochs 100 --patience 8
uv run --frozen python script/reproduce.py benchmark --method texnn --run-id source-rgb64-patch64-v2 --evaluation-id validation8-patch128 --images 8 --patch-size 128
uv run --frozen python script/reproduce.py report --method texnn --run-id source-rgb64-patch64-v2 --evaluation-id validation8-patch128
```

Use new run/evaluation identities for new experiments. Collection can resume an identical frozen recipe; training uses `--resume` with data/optimizer compatibility checks and archives previous checkpoints before replacing them. Incomplete training can resume from `last.pt`. Batch evaluation requires the same frozen manifest as the training corpus and uses the separate validation split. No test-split images are consumed here. `[verified: corpus.py collect/prepare; training.py train; evaluation.py TexNNBatchEvaluation.run]`

The older [reference probe report](<../../experiment report/texnn/reference-probe-20261111/README.md>) remains evidence of the first label observer and network widths. Larger training, additional input modalities and published performance remain further validation work. `[verified: reference probe report scope; measured report limits]`
