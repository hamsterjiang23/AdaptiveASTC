# Nah 2023 adaptive astcenc

The author implementation is pinned in `source.json` and checked out in ignored `upstream/`. Build outputs and the encoder SHA-256 are stored under the experiment `.local/reproduction-binaries/` directory. `[verified: source.json; common/upstream.py]`

```powershell
uv run --frozen python script/reproduce.py build --method nah2023_adaptive_astcenc
```

The author's example is `astcenc -cl example.png example.astc 6x6 -medium -dbtarget 40`. The specified footprint initializes the search. Read the final footprint from the generated ASTC header and recompute final quality after decompression. `[verified: upstream README.md, A Note from Jae-Ho Nah]` `[opinion]`

The local Release encoder build completed with MSVC 19.44 and Windows SDK 10.0.22621.0. Formal image experiments follow the complete Unity baseline. `[verified: build.log and build-receipt.json under experiment report/.local/reproduction-binaries/nah2023_adaptive_astcenc; accepted plan]`
