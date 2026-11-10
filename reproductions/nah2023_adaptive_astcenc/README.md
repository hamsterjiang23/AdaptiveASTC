# Nah 2023 adaptive astcenc

The author implementation is pinned in `source.json` and checked out in ignored `upstream/`. Build outputs and the encoder SHA-256 are stored under the experiment `.local/reproduction-binaries/` directory. `[verified: source.json; common/upstream.py]`

```powershell
uv run --frozen python script/reproduce.py build --method nah2023_adaptive_astcenc
```

The author's example is `astcenc -cl example.png example.astc 6x6 -medium -dbtarget 40`. The specified footprint initializes the search. Read the final footprint from the generated ASTC header and recompute final quality after decompression. `[verified: upstream README.md, A Note from Jae-Ho Nah]` `[opinion]`

The local Release encoder build completed with MSVC 19.44 and Windows SDK 10.0.22621.0. After Unity baseline acceptance, the two-image probe and fixed 64-image source-RGB experiment completed actual encoding and decoding. The [64-image report](<../../experiment report/nah2023_adaptive_astcenc/source-rgb64-target40/README.md>) records 73.248 seconds of search plus final encoding, 46/64 meeting full-image RGBA 40 dB and 26/64 meeting full-image RGB 40 dB. `[verified: build-receipt.json; author-example-probe and source-rgb64-target40 summary.json]`

The reference PNG loader supplies four channels. The author's search uses time-seeded random block samples and a fixed one-tenth full-image pixel denominator. Final output quality is audited separately on all decoded pixels. Source RGB8 conversion removes source alpha, and this adaptation retains original resolution with no mip chain. Published benchmark results remain separately recorded. `[verified: upstream Source/astcenccli_image_load_store.cpp L118–146; astcenc_entry.cpp L833–879; astcenccli_error_metrics.cpp L250–265 and L333–392; measured summary.json protocol/quality_audit]`
