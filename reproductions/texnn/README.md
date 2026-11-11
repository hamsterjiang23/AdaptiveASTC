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

Current measured coverage is reference label export and network dimensions. Dataset construction, six-network training, predicted-configuration integration and learned-encoder quality/timing evaluation continue under the active goal. [Reference probe report](<../../experiment report/texnn/reference-probe-20261111/README.md>). `[verified: current implementation and probe report scope]`
