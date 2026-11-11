# Unity / Nah / GDC captured-reference comparison

All methods received identical captured mip0 RGB PNG bytes on the frozen64 training cohort. Common evaluation uses full-image RGB PSNR >35 dB and actual ASTC payload. `[verified: comparison.json all_input_png_hashes_equal, common_rgb_strict_target and scope]`

| Method | RGB >35 dB | Payload bytes | Measured pipeline seconds |
|---|---|---|---|
| nah2022_psnr_search | 64/64 | 20,584,992 | 221.095 `[verified: comparison.json methods]` |
| nah2023_adaptive_astcenc | 62/64 | 20,942,896 | 48.703 `[verified: comparison.json methods]` |
| gdc2023 | 46/64 | 11,881,536 | 56.461 `[verified: comparison.json methods]` |
| gdc_fixed8 | 46/64 | 8,735,312 | 55.760 `[verified: comparison.json methods]` |
| unity_lite | 27/64 | 9,690,816 | 150.385 `[verified: comparison.json methods]` |

Unity timing covers the original native mip0 search and selected payload. Other rows include preprocessing, decision and final encoding. Native quality objectives, presets, alpha and color treatment remain method-specific. `[verified: comparison.json methods.unity_lite.time_scope and limits]`

[Per-image results, protocols and provenance](comparison.json). `[verified: accompanying JSON]`
