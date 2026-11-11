# Unity / Nah / GDC shared64 comparison

The same 64 source-file identities are verified against the frozen Unity cohort. Nah and GDC use byte-identical full-resolution RGB PNG inputs and the same full-image RGB PSNR evaluator. Unity retains imported pixels and its native LITE policy. `[verified: comparison.json inputs, source_rgb_png_hashes_equal and unity_reference_pixel_equivalence]`

| Method | Source RGB >35 dB | Payload bytes | Preprocessing, decision and final encode s |
|---|---|---|---|
| nah2022_psnr_search | 64/64 | 37,145,456 | 557.003 `[verified: comparison.json source_rgb_methods]` |
| nah2023_adaptive_astcenc | 60/64 | 40,801,664 | 83.897 `[verified: comparison.json source_rgb_methods]` |
| gdc2023 | 48/64 | 30,741,520 | 82.950 `[verified: comparison.json source_rgb_methods]` |

GDC shared64 is a training diagnostic. Quality targets, presets and search scope differ between methods. The import-pixel audit is retained in unity_reference_pixel_equivalence. TexNN remains in its fixed-footprint report. `[verified: comparison.json limits]`

Full source identities, Unity native timings, protocols and per-image values are retained in [comparison.json](comparison.json). `[verified: accompanying JSON]`
