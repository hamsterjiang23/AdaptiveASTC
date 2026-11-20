# Lane A notes: detecting and judging the visibility of banding, false contours and block edges

Scope: find methods that flag smooth gradients compressed into plateaus, steps, blocks or bands, focusing on methods not yet in `metric/README.md`. Repository was read-only; everything below lives in this directory.

## 1. Sources actually read in this session

| Source | Where | What was verified |
|---|---|---|
| Kapoor, Sapra, Wang, "Capturing Banding in Images: Database Construction and Objective Assessment", ICASSP 2021 preprint | https://ece.uwaterloo.ca/~z70wang/publications/icassp21_banding.pdf (fetched through exa) | §2: 1,250 images at 1920×1080, banding made by bit-depth reduction then promotion at 6 quantization levels; 169,501 patches of 235×235, labelled banded if >30% overlap. §3.1: 7-layer CNN with 6.7K params, threshold 0.2 (F1 0.9). §3.2 eq.(1): the score combines each patch with its 8 neighbours, S̃i = Wp·Si + Wn·ΣSj/N; DBI is the mean; eq.(2) builds a sliding-window map with stride 5. Table 2: AUC-ROC 0.95, 0.0487 s per patch. §3.3: the model "struggles with ... macroblocking artifacts or wave-like patterns in the original content or created by artificial design". Code is at github.com/akshay-kap/Meng-699-Image-Banding-detection; data on Zenodo (footnote 1). |
| Wang, Bovik, Evans, "Blind measurement of blocking artifacts in images", ICIP 2000 | https://utw10503.utweb.utexas.edu/publications/2000/zw_icip_2000_blindblock.pdf (exa) | §2: g = abs(horizontal difference), rows concatenated into a 1-D signal s (eq.1); segments of length N go through FFT, giving a power spectrum P averaged over segments; median-filter smoothing P_M (N=512, K=4); the blockiness measure is the excess power P−P_M at N/8, 2N/8, 3N/8, 4N/8, with DC replaced by 7×(...). §3: optional masking multiplies g by a masker map built from Chou–Li [10] luminance and texture masking. The method assumes B=8 and M a multiple of B. |
| Netflix CAMBI doc and source | raw.githubusercontent.com/Netflix/vmaf/master/resource/doc/cambi.md and libvmaf/src/feature/cambi.c, saved to `src/` | Options: window_size default 63 (~1° at 4K, 1.5H), topk 0.6, tvi_threshold 0.019, max_log_contrast default 2 (= 4 luma levels at 10-bit = 1 level at 8-bit; max 5), full_ref = MAX(0, dist−src), enc_width/enc_height. cambi.c L65 sets CAMBI_MIN_WIDTH_HEIGHT 216; L507–512 reject inputs whose width and height are both below it; L415–425 `adjust_window_size` scales the window by (w+h)/(3840+2160); L464–468 marks a pixel zero-derivative when it equals its right and bottom neighbours; L943–947 and L950–985 give the 7×7 flat-pixel mask; L1058–1086 c_value = max over d of w_d·p0·pd/(p0+pd) with the TVI visibility gate; L73 scale weights {16,8,4,2,1}; L1235–1240 top-k pooling. |
| Chou & Li 1995 JND, as restated by Ghouti & Bouridane, EUSIPCO 2005 cr1435 | https://eurasip.org/Proceedings/Eusipco/Eusipco2005/defevent/papers/cr1435.pdf, saved to `src/`; extracted text in `src/eusipco_extract.txt` L110–152 | Eq.(1) JND = max(f1, f2). (2) f1 = mg·α(bg)+β(bg). (3) f2 = T0(1−(bg/127)^½)+3 when bg≤127, else γ(bg−127)+3. (4) α = 0.0001·bg+0.115. (5) β = λ−0.001·bg (as printed). T0=17, γ=3/128, λ=1/2. |
| Wu, Qi, Shi, "An improved model of pixel adaptive JND estimation" | scispace PDF (exa highlight) | Restates the Chou–Li luminance threshold as a0+a1·sqrt(B/B0) with a0=20, a1=−17, B0=127, γ=3/128. This matches the formula above. |
| ColorVideoVDP README and LICENSE | raw.githubusercontent.com/gfxdisp/ColorVideoVDP/main/{README.md,LICENSE}, saved to `src/` | MIT license, Copyright 2024 Graphics and Displays group. README L66 gives `pip install cvvdp`. L146–150: the metric needs a physical display spec and viewing conditions; an image smaller than the display "occupies ... the central portion"; `--full-screen-resize` currently works for video only. Per the search summary, the paper defines n_ppd = π/(360·atan(0.5·d_width/(r_w·d_v))). |
| BAND-2k (Chen et al., TCSVT 2024; arXiv 2311.17752) | WebSearch summary of arXiv, IEEE and GitHub pages | 2,000 banded images, 15 compression/quantization settings, 870+ source videos, H.264/H.265/VP9/bit-depth reduction, 44,371 ratings from 23 subjects; code and data at github.com/zijianchen98/BAND-2k. Full text not read, so the model details are unverified. |
| Daly & Feng 2004, SPIE 5292:130–149 | WebSearch summary only | "Decontouring" (prevention by dither; removal by predictive cancellation, i.e. blur, re-quantize, subtract). Full text not read. |
| Lee et al. 2006, IEEE TCE 52(1):179–188; ICCE 2006 short version | WebSearch summary of eurekamag abstracts | Stage 1 removes smooth regions by bit-depth reduction or re-quantization. Stage 2 uses directional contrast features to separate false contours from edges and texture, giving a binary false-contour map. Full text not read. |
| Huang et al. 2018, IEEE TCSVT 28(2):378–391 | WebSearch summary of NYCU and KHU abstracts | Pixel-wise false contour candidate (FCC) map, refined by constraints added one at a time to separate false contours from real edges and texture. Full text not read. |
| Ross, Morrone, Burr 1989, Vision Res. 29(6):699–715 | PubMed abstract via WebSearch | Mach bands on trapezoidal waveforms (ramp knees). A local-energy model predicts when they appear and the contrast needed; lateral-inhibition models do not. Full text not read. |
| Griffin & Olano, I3D 2014; TVCG 2015 | WebSearch summary of NIST and UMBC pages | Evaluate texture compression on rendered multi-viewpoint images, with geometric and texture-set masking. According to the TVCG abstract, hardware formats are "too conservative". Full text not read. |

## 2. Local probe (CPU, 196 native 128×128 colour assets, 8×8 fastest)

Script: `probe_lane_a.py`, with the same asset selection as `tmp/gradient-diagnostics-20261119/screen.py`: dark composite for alpha assets, otherwise RGB; display PNGs from `outputs/.../media`. Commands:

```
uv run --no-sync python tmp/gradient-metric-brainstorm-20261119/lane-a-banding-literature/probe_lane_a.py --smoke   # 5 images, ~1.5 s
uv run --no-sync python tmp/gradient-metric-brainstorm-20261119/lane-a-banding-literature/probe_lane_a.py           # 196 images, 20.3 s wall
```

The RGB-channel JND variant was computed with an inline script; results are in `probe-rgbjnd-summary.json`. Outputs are `probe-rows.csv`, `probe-summary.json`, `smoke-rows.csv` and `smoke-summary.json`.

Metric definitions used in the probe:
- **Luma JND step**. Y = sRGB-code luma using the BT.709 weights from banding.py. The JND map is Chou–Li eqs (1)–(5) on the reference. Approximation: bg is a 5×5 box mean and mg is the largest of four 3×3 directional differences divided by 8, because the original 5×5 operators were not in the restating source. For each horizontal and vertical neighbour pair inside the existing gradient mask (`probe.gradient_mask`, Lab plane fit), ratio = |ΔY_dec − ΔY_ref| / mean JND of the pair. Statistics:
  - `jnd_p95`: P95 of the ratio.
  - `jnd_visible_frac`: fraction of pairs with ratio > 1.
  - `jnd_longest_cc`: size of the largest 8-connected component of pixels touching a supra-threshold pair.
  - `jnd_longest_run`: longest straight run of supra-threshold pairs.
  - `jnd_grid_share`: share of supra-threshold pairs lying on native 8-px block boundaries. Chance level is 1/8.
- **RGB-max JND**. The same ratio computed per R, G, B channel with a per-channel Chou–Li JND, taking the maximum over channels.
- **Magnified CAMBI**. Display RGB is bilinearly upscaled (PIL BILINEAR) ×4 to 512² and ×8 to 1024², converted to limited-range Y as in banding.py, then run through ffmpeg 9.0.1 libvmaf CAMBI with full_ref=true. Settings tried: default, and ×4 with max_log_contrast=5.

Ranks count values strictly greater, so ties at 0 share a rank. Denominators differ per metric.

| Metric | 0615 / 0616 / 0617 rank, all valid | Same 138-image set as the continuous seam score |
|---|---|---|
| continuous seam (existing) | 7 / 12 / 20 of 138 | 7 / 12 / 20 |
| block-boundary excess P95 (existing) | 31 / 40 / 30 of 166 | 26 / 35 / 25 |
| FLIP P99 (existing) | 68 / 33 / 49 of 196 | 46 / 24 / 32 |
| luma JND step P95 (new) | 9 / 78 / 12 of 181 | **5 / 57 / 7** |
| luma JND visible fraction (new) | 11 / 76 / 26 of 181 | 4 / 56 / 14 |
| luma JND largest contour component (new) | 9 / 32 / 6 of 181 | 9 / 32 / 6 |
| luma JND longest straight run (new) | 26 / 41 / 10 of 181 | 26 / 41 / 10 |
| RGB-max JND step P95 (new) | 19 / 60 / 13 of 181 | 12 / 43 / 7 |
| RGB-max JND visible fraction (new) | 19 / 54 / 37 of 181 | 7 / 34 / 20 |
| CAMBI FR ×4 bilinear | 90 / 92 / 52 of 196 | 51 / 53 / 24 |
| CAMBI FR ×8 bilinear | 72 / 60 / 72 of 196 | 35 / 28 / 35 |
| CAMBI FR ×4, max_log_contrast=5 | 99 / 71 / 137 of 196 | 65 / 50 / 89 |

Raw values for the known images, from `probe-rows.csv`:
- 0615: jnd_p95 3.77, visible fraction 0.448, largest component 1,151 px, longest run 21, grid share 0.196. CAMBI FR ×4 0.0033 (source 0.345), ×8 0.0, ×4 with mlc5 0.651.
- 0616: jnd_p95 1.08, visible fraction 0.061, largest component 191, grid share 0.362. CAMBI FR ×4 0.0, ×8 0.077. RGB-max P95 2.24.
- 0617: jnd_p95 3.57, visible fraction 0.320, largest component 1,610, longest run 40, grid share 0.186. CAMBI FR ×4 0.337, ×8 0.0, ×4 with mlc5 0.0.

CAMBI FR was exactly 0 on 105/196 images at ×4 and 125/196 at ×8.

Top-10 composition, from `probe-summary.json` top10:
- jnd_p95: 5 Effects/Common (Magic, Ring ×3, Decal), 2 UI BattleAnimIcon atlas, 2 Effects/TempTexture, plus 0615.
- jnd_longest_cc: 9 of 10 are Ring/SD (the same family as the known images) and 1 is TempTexture. This is a circularity warning: the Ring family dominates, which could mean real damage or simply large soft halos.

### Reading of the probe (inference)
- Magnify-then-CAMBI does not reach the known cases. CAMBI's contrast set is d ∈ {1,2,4} 10-bit codes by default and at most 32 (cambi.c L59 doc and L1058–1086). Its flat mask needs exact-equal neighbours (L464–468). ASTC 8×8 on 0615 produces a 57-code (8-bit) jump after an 8-px plateau, far outside CAMBI's step range, and bilinear upscaling turns the jump into a ramp. CAMBI targets 1-code quantization banding, not ASTC endpoint/weight steps.
- Luma-JND normalisation raises 0615/0617 (5 and 7 of 138, against 7 and 20 for the seam score) but drops 0616. The blue halo's damage is mostly chromatic: blue carries 0.0722 luma weight. The RGB-max variant helps 0616 only a little (43 of 138), so a proper opponent-colour model is needed (Denes, castleCSF, ColorVideoVDP).
- Only about 19–20% of JND-visible steps on 0615/0617 lie on block boundaries (chance level 12.5%). Most visible steps are inside blocks, consistent with weight-quantisation contours and plateaus. Grid-only seam scores therefore see a minority of the visible steps. Grid-agnostic contour scoring is complementary, not redundant.

## 3. Methods considered, and why they are or are not candidates

- **Wang–Bovik–Evans 2000 spectral blockiness.** Phase-free periodicity at k·N/B. It is mostly a duplicate of the phase-adjusted seam score already in `metric/`. Its only gain is phase-free operation and arbitrary B; restricting it to the gradient mask and differencing against the reference spectrum would be the improvement. Not probed.
- **GBIM / PSNR-B family (Wu & Yuen 1997, cited in Wang 2000 ref [7]).** Weighted MSD along block boundaries. Duplicate of PSNR-B and the block-boundary excess already in `metric/`.
- **DBI (Kapoor 2021) and BAND-2k.** Learned NR detectors. Their 235² patches exceed 128² textures, they were trained on bit-depth or codec banding of natural video, and the DBI paper itself reports failure on macroblocking and artificial wave-like content.
- **Lee 2006 and Huang 2018 two-stage false contour detectors.** Smooth-region gate, then directional contrast features to reject true edges. Useful as a grid-agnostic, full-reference-capable contour detector, but the full text was not read, so thresholds are unknown.
- **ColorVideoVDP.** Full-reference with explicit display geometry (ppd) and photometry, castleCSF chromatic channels, MIT license. This is the cleanest way to encode "magnified on screen" and chroma banding together. Not run this session because of the time budget.
- **Mach-band and slope-kink visibility (Ross–Morrone–Burr 1989).** ASTC's per-block linear interpolation creates slope discontinuities even without value jumps. It is a hypothesis-level candidate and was not probed.

## 4. Unreachable or unread
- WebFetch refused ece.uwaterloo.ca, utexas.edu and github.com ("Unable to verify if domain ... is safe"); exa fetch and curl of raw.githubusercontent.com were used instead.
- zread MCP returned HTTP 429 (no balance).
- Not read in full: Lee 2006 (IEEE TCE), Huang 2018 (TCSVT), Daly & Feng 2004 (SPIE), Bhagavathy 2009 (not searched), Wu 2013 pattern-masking JND, Yang 2005 NAMM, Barten CSF, Denes 2020 chromatic banding, CAMBI PCS 2021 paper, Ross–Morrone–Burr full text, GBIM, Perra, NPBM (not searched), BAND-2k full text, Griffin–Olano full text.
- The FLIP README was fetched, but grep did not return the ppd text, so the 67 ppd statement relies on `metric/README.md` L37, not on FLIP's README.
