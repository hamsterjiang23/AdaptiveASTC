# Published ASTC method reproductions

Execution order is Unity search baseline, Nah 2023, Nah 2022, TexNN, then GDC 2023. This order follows the accepted implementation plan. `[verified: user implementation request, 2026-11-10]`

| Directory | Implementation | Current evidence |
|---|---|---|
| `unity_search_baseline` | Timing observer plus Unity batch runner | Preparation covers 10,000 training textures and a fixed 64-texture smoke subset. Runtime acceptance requires native telemetry. `[verified: unity_search_baseline/benchmark.py, prepare and summarize]` |
| `nah2023_adaptive_astcenc` | Author source pinned in `source.json` | Upstream checkout uses commit `4a3a3a61b2f961efe63e00c913876576315872fb`. `[verified: upstream git checkout output]` |
| `nah2022_psnr_search` | Paper reimplementation | astcenc 3.3, class thresholds and missing manual initialization data are recorded in `source.json`. `[verified: source.json; Nah 2022 Table 1 and §4]` |
| `texnn` | Paper reimplementation | User-supplied 12-page PDF verified by SHA-256. Separate network architecture Appendix is referenced on its p.12. `[verified: texnn/source.json; supplied PDF p.12]` |
| `gdc2023` | Talk reimplementation | Existing historical LITE classification is recorded separately from the pending compression-loop reproduction. `[verified: gdc2023/source.json; existing training_report.md L56–60]` |

Method-specific code and configurations live here. Public launch scripts live in `../script/`. Reports live in `../experiment report/`; raw data, logs, binaries and checkpoints live in its ignored `.local/` directory. `[verified: accepted plan]`

## Unity baseline commands

Run these from `E:\ASTC_Compression` after building the instrumented Editor. Each phase requires a new empty parameter-cache namespace. `[verified: unity_search_baseline/benchmark.py, run]`

For another baseline repetition after the complete experiment, supply the same new `--run-id` to prepare and every run/report command. This creates a separate artifact and parameter-cache namespace. `[verified: benchmark.py __init__/prepare; script/reproduce.py baseline construction]`

```powershell
uv run --frozen python script/reproduce.py prepare
uv run --frozen python script/reproduce.py instrument
```

Compile the instrumented Editor after applying the patch. The installer rejects repeated application and preserves original source files before editing. Then run the phases below. `[verified: unity_search_baseline/engine_patch.py]`

`timing.patch` contains zero-context hunks. Manual application to the recorded original revision uses `git apply --unidiff-zero --ignore-whitespace`; the primary installer preserves source newline style and checks unique anchors. `[verified: temporary original-source application matched all three active instrumented files; engine_patch.py apply]`

```powershell
uv run --frozen python script/reproduce.py run --phase probe
uv run --frozen python script/reproduce.py run --phase smoke1
uv run --frozen python script/reproduce.py run --phase smoke2
uv run --frozen python script/reproduce.py run --phase smoke3
uv run --frozen python script/reproduce.py run --phase full
```

`--no-upm` is an explicit startup diagnostic option. Record it with the launch command when used. Full runs require all three smoke receipts to pass. The native observer must record actual search, positive candidate counts, successful selection, no parameter-cache hits, and valid nested timings. `[verified: script/reproduce.py; unity_search_baseline/benchmark.py, run and summarize]`

Benchmark processes use `-disable-cache-server` and forced synchronous reimport. Parameter cache namespaces are also isolated. The current isolated Editor assembly uses `BenchmarkRunner.cs` and `ASTCSearchBaseline.asmdef`. `[verified: benchmark.py run; BenchmarkRunner.cs Run]`

The observer is enabled with `ASTC_BENCHMARK_LOG`; it uses a monotonic clock. `search_ms` covers candidate search and final selection. `select_and_encode_ms` covers `CompressTextureWithMultipleImages`, including payload reuse and the texture's mip/image loop. `format_ms` is nested and must not be added to these totals. Unity import wall time is recorded separately. `[verified: ASTCBenchmark.h; timing.patch; BenchmarkRunner.cs ImportOne]`

To make every selected image enter ASTC, the runner temporarily overrides the Android target to ASTC 8×8. Native search then selects the final footprint and preset. Original `.meta` bytes are backed up and restored after Editor exit if the current hash matches the expected benchmark write. Subsequent changes are reported as conflicts. Recovery refuses to run while this project is open in Unity. `[verified: BenchmarkRunner.cs ImportOne; benchmark.py restore_metadata/require_project_closed]`

```powershell
uv run --frozen python script/reproduce.py report
uv run --frozen python script/reproduce.py recover --phase full
```

The [measured report](<../experiment report/unity-search-baseline-lite-rdo-off/README.md>) links phase-level aggregates. `protocol-lock.json` freezes identity and input lists. Acceptance also checks the native cache's actual source MD4 values and complete quality-policy header. The full-run gate revalidates all three smoke receipts against this identity. `[verified: benchmark.py prepare/verify_protocol/audit/run]`

The training list includes Cubemap imports. An additional two-Cubemap probe passed actual search and metadata restoration. The full run records actual texture dimensions, with search measured on the first image's mip0 and final compression measured across all faces/mips. `[verified: .local/unity-search-baseline-cubemap-probe/probe-receipt.json; ImageOperations.cpp CompressTextureWithMultipleImages; BenchmarkRunner.cs ImportOne]`

The initial full attempt exposed a metadata-sidecar path failure at 265 characters, after copying a 249-character backup path. The revised runner uses flat SHA-256 backup names and a mapping index. Existing nested backups remain supported, with conservative reconstruction of the four intended Android settings for interrupted writes. The revised code has regression coverage; its native retry validation follows completion of the initial full attempt. `[verified: full-imports.jsonl first failed record; long-path-recovery-evidence.json; BenchmarkRunner.cs ImportOne; recovery.py; metadata regression checks]`

```powershell
uv run --frozen python script/reproduce.py repair
uv run --frozen python script/reproduce.py assemble
uv run --frozen python script/reproduce.py report
```

`repair` runs only failed import rows in a new empty cache after restoring their original metadata. `assemble` retains the original cohort, its failed rows and original process exit code, then combines successful measurements into one result per frozen asset. A recovered full baseline uses `passed_with_retries`, records both process outcomes and pins raw inputs/assembled outputs by SHA-256. Formal literature runs require complete 10,000-image coverage, successful recovery and verified provenance. `[verified: recovery.py run/assemble; benchmark.py audit; common/upstream.py BaselineGate]`

## Nah encoder commands

Source preparation and compilation are available before full baseline acceptance. Image experiments require the passed 10,000-image baseline receipt. Both native builds retain clean pinned upstream source and record the executable SHA-256. `[verified: common/upstream.py EncoderSource/BaselineGate; common/nah_experiment.py run]`

```powershell
uv run --frozen python script/reproduce.py fetch --method nah2023_adaptive_astcenc
uv run --frozen python script/reproduce.py build --method nah2023_adaptive_astcenc
uv run --frozen python script/reproduce.py run --method nah2023_adaptive_astcenc --input-set probe --run-id author-example-probe
uv run --frozen python script/reproduce.py run --method nah2023_adaptive_astcenc --input-set smoke --run-id source-rgb64-target40
uv run --frozen python script/reproduce.py fetch --method nah2022_psnr_search
uv run --frozen python script/reproduce.py build --method nah2022_psnr_search
uv run --frozen python script/reproduce.py run --method nah2022_psnr_search --input-set probe --run-id game-probe
uv run --frozen python script/reproduce.py run --method nah2022_psnr_search --input-set smoke --run-id source-rgb64-game
```

These runs use the same fixed source-image subset converted to RGB8 at original resolution, linear LDR CLI mode, one CPU thread, no mip chain and a separately encoded fixed-8×8 control. They record actual ASTC bytes, decode quality and preprocessing/search/final-encoding costs. The 2022 initial footprint is reconstructed as 6×6, with the published Game class target 37.3873 dB and thorough final encoding. The 2023 author example uses target 40 dB and medium. Its time-seeded sampling remains as upstream implemented. These are explicit project adaptations. `[verified: common/nah_experiment.py protocol/_measure; nah2022_psnr_search/source.json; 2023 upstream README L1–9 and astcenc_entry.cpp L833–836]`

## Source and result provenance

Keep original publication settings and project-adapted settings as separate experiment identities. Unity uses LITE 30 dB with RDO off; the GDC original label target is PSNR >35 dB. Preserve encoder commits, input hashes, importer configuration, color profile, mip handling and timing boundaries in each report. `[verified: accepted plan; gdc2023/source.json]` `[opinion]`

Build success, smoke acceptance and full experiment completion are separate statuses. Only measured results may be marked complete. `[opinion]`
