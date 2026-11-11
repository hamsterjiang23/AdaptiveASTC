# Published ASTC method reproductions

Execution order is Unity search baseline, Nah 2023, Nah 2022, TexNN, then GDC 2023. This order follows the accepted implementation plan. `[verified: user implementation request, 2026-11-10]`

| Directory | Implementation | Current evidence |
|---|---|---|
| `unity_search_baseline` | Timing observer plus Unity batch runner | All 10,000 measured with 32 successful technical retries, source-hash/policy/selection checks and zero metadata conflicts. Search totals 4,060.47 s. `[verified: measured baseline summary.json phases.full]` |
| `nah2023_adaptive_astcenc` | Author source pinned in `source.json` | Native source-RGB 64-image run completed. Full-decode RGBA 40 dB passed 46/64 and RGB passed 26/64. [Measured report](<../experiment report/nah2023_adaptive_astcenc/source-rgb64-target40/README.md>). `[verified: measured summary.json quality_audit]` |
| `nah2022_psnr_search` | Paper reimplementation | Native source-RGB 64-image run completed with the Game target 37.3873 dB. RGBA passed 64/64 and RGB passed 62/64. [Measured report](<../experiment report/nah2022_psnr_search/source-rgb64-game/README.md>). `[verified: measured receipt.json reference_target_met/target_met]` |
| `texnn` | Paper reimplementation | Six networks trained on 64 source-image patches. Cascaded predictions fed the native 4×4/6×6/8×8 encoder in 48 independent-validation-crop experiments, with 96 fresh decode audits. Quality loss and complete pipeline time are reported. Original million-block scale and published performance remain unverified. [Measured adaptation](<../experiment report/texnn/source-rgb64-patch64-v2/README.md>). `[verified: validation8-patch128.json training, groups, audit and limits]` |
| `gdc2023` | Talk reimplementation | Existing historical LITE classification is recorded separately from the pending compression-loop reproduction. `[verified: gdc2023/source.json; existing training_report.md L56–60]` |

Method-specific code and configurations live here. Public launch scripts live in `../script/`. Reports live in `../experiment report/`. Raw data, logs, binaries and checkpoints live in its ignored `.local/` directory. `[verified: accepted plan]`

## Unity baseline commands

Run these from `E:\ASTC_Compression` after building the instrumented Editor. Each phase requires a new empty parameter-cache namespace. `[verified: unity_search_baseline/benchmark.py, run]`

For another baseline repetition after the complete experiment, supply the same new `--run-id` to prepare and every run/report command. This creates a separate artifact and parameter-cache namespace. `[verified: benchmark.py __init__/prepare; script/reproduce.py baseline construction]`

```powershell
uv run --frozen python script/reproduce.py prepare
uv run --frozen python script/reproduce.py instrument
```

Compile the instrumented Editor after applying the patch. The installer rejects repeated application and preserves original source files before editing. Then run the phases below. `[verified: unity_search_baseline/engine_patch.py]`

`timing.patch` contains zero-context hunks. Manual application to the recorded original revision uses `git apply --unidiff-zero --ignore-whitespace`. The primary installer preserves source newline style and checks unique anchors. `[verified: temporary original-source application matched all three active instrumented files; engine_patch.py apply]`

```powershell
uv run --frozen python script/reproduce.py run --phase probe
uv run --frozen python script/reproduce.py run --phase smoke1
uv run --frozen python script/reproduce.py run --phase smoke2
uv run --frozen python script/reproduce.py run --phase smoke3
uv run --frozen python script/reproduce.py run --phase full
```

`--no-upm` is an explicit startup diagnostic option. Record it with the launch command when used. Full runs require all three smoke receipts to pass. The native observer must record actual search, positive candidate counts, successful selection, no parameter-cache hits, and valid nested timings. `[verified: script/reproduce.py; unity_search_baseline/benchmark.py, run and summarize]`

Benchmark processes use `-disable-cache-server` and forced synchronous reimport. Parameter cache namespaces are also isolated. The current isolated Editor assembly uses `BenchmarkRunner.cs` and `ASTCSearchBaseline.asmdef`. `[verified: benchmark.py run; BenchmarkRunner.cs Run]`

The observer is enabled with `ASTC_BENCHMARK_LOG` and uses a monotonic clock. `search_ms` covers candidate search and final selection. `select_and_encode_ms` covers `CompressTextureWithMultipleImages`, including payload reuse and the texture's mip/image loop. `format_ms` is nested and must not be added to these totals. Unity import wall time is recorded separately. `[verified: ASTCBenchmark.h; timing.patch; BenchmarkRunner.cs ImportOne]`

To make every selected image enter ASTC, the runner temporarily overrides the Android target to ASTC 8×8. Native search then selects the final footprint and preset. Original `.meta` bytes are backed up and restored after Editor exit if the current hash matches the expected benchmark write. Subsequent changes are reported as conflicts. Recovery refuses to run while this project is open in Unity. `[verified: BenchmarkRunner.cs ImportOne; benchmark.py restore_metadata/require_project_closed]`

```powershell
uv run --frozen python script/reproduce.py report
uv run --frozen python script/reproduce.py recover --phase full
```

The [measured report](<../experiment report/unity-search-baseline-lite-rdo-off/README.md>) links phase-level aggregates. `protocol-lock.json` freezes identity and input lists. Acceptance also checks the native cache's actual source MD4 values and complete quality-policy header. The full-run gate revalidates all three smoke receipts against this identity. `[verified: benchmark.py prepare/verify_protocol/audit/run]`

The training list includes Cubemap imports. An additional two-Cubemap probe passed actual search and metadata restoration. The full run records actual texture dimensions, with search measured on the first image's mip0 and final compression measured across all faces/mips. `[verified: .local/unity-search-baseline-cubemap-probe/probe-receipt.json; ImageOperations.cpp CompressTextureWithMultipleImages; BenchmarkRunner.cs ImportOne]`

The initial full attempt exposed a metadata-sidecar path failure at 265 characters, after copying a 249-character backup path. The revised runner uses flat SHA-256 backup names and a mapping index. Existing nested backups remain supported, with conservative reconstruction of the four intended Android settings for interrupted writes. Regression tests and all 32 actual retry imports passed with the revised runner. `[verified: full-imports.jsonl first failed record; long-path-recovery-evidence.json; BenchmarkRunner.cs ImportOne; repair-receipt.json; metadata regression checks]`

The native short-path retry completed all 32 imports and restored its metadata without conflicts. Full validation combines the compacted JSON snapshot and the JSONL append log, then checks all 10,000 source hashes and selected block/preset pairs against native telemetry. Original and retry process exit codes remain recorded as 1 and 0. `[verified: repair-receipt.json; full-receipt.json; benchmark.py read_parameter_cache/audit]`

```powershell
uv run --frozen python script/reproduce.py repair
uv run --frozen python script/reproduce.py assemble
uv run --frozen python script/reproduce.py report
```

`repair` runs only failed import rows in a new empty cache after restoring their original metadata. `assemble` retains the original cohort, its failed rows and original process exit code, then combines successful measurements into one result per frozen asset. A recovered full baseline uses `passed_with_retries`, records both process outcomes and pins raw inputs/assembled outputs by SHA-256. Formal literature runs require complete 10,000-image coverage, successful recovery and verified provenance. `[verified: recovery.py run/assemble; benchmark.py audit; common/upstream.py BaselineGate]`

Four failed assets also exercised legacy Unity metadata migration. Their exact original/current SHA-256 pairs were reviewed against the observed diffs and the importer's version-conversion code. Recovery requires both hashes and the same protocol/Editor identity for those cases, while later file changes remain conflicts. `[verified: .local/unity-search-baseline-lite-rdo-off/reviewed-metadata-overrides.json; TextureImporter.cpp L769–920 and L953–970; TextureImporterTypes.cpp L66–110; recovery.py _recover_interrupted_metadata; reviewed-pair regression test]`

## Nah encoder commands

Source preparation and compilation are available before full baseline acceptance. Image experiments require the passed 10,000-image baseline receipt. Both native builds retain clean pinned upstream source and record the executable SHA-256. `[verified: common/upstream.py EncoderSource/BaselineGate; common/nah_experiment.py run]`

```powershell
uv run --frozen python script/reproduce.py fetch --method nah2023_adaptive_astcenc
uv run --frozen python script/reproduce.py build --method nah2023_adaptive_astcenc
uv run --frozen python script/reproduce.py run --method nah2023_adaptive_astcenc --input-set probe --run-id author-example-probe
uv run --frozen python script/reproduce.py run --method nah2023_adaptive_astcenc --input-set smoke --run-id source-rgb64-target40
uv run --frozen python script/reproduce.py report --method nah2023_adaptive_astcenc --run-id source-rgb64-target40
uv run --frozen python script/reproduce.py fetch --method nah2022_psnr_search
uv run --frozen python script/reproduce.py build --method nah2022_psnr_search
uv run --frozen python script/reproduce.py run --method nah2022_psnr_search --input-set probe --run-id game-probe
uv run --frozen python script/reproduce.py run --method nah2022_psnr_search --input-set smoke --run-id source-rgb64-game
uv run --frozen python script/reproduce.py report --method nah2022_psnr_search --run-id source-rgb64-game
```

These runs use the same fixed source-image subset converted to RGB8 at original resolution, linear LDR CLI mode, one encoding thread, no mip chain and a separately encoded fixed-8×8 control. Decode verification uses the CLI default thread settings. They record actual ASTC bytes, decode quality and preprocessing/search/final-encoding costs. The 2022 initial footprint is reconstructed as 6×6, with the published Game class target 37.3873 dB and thorough final encoding. The 2023 author example uses target 40 dB and medium. Its time-seeded sampling remains as upstream implemented. These are explicit project adaptations. `[verified: common/nah_experiment.py protocol/_measure; common/encoder.py encode/decode; nah2022_psnr_search/source.json; 2023 upstream README L1–9 and astcenc_entry.cpp L833–836]`

The reference PNG loader expands RGB to RGBA. The 2022 reimplementation searches on full-image RGBA PSNR, and the 2023 author code estimates RGBA PSNR on sampled blocks. Reports use the pinned binary for a fresh decode, require exact PNG SHA-256 matches, recompute full-image RGB and RGBA quality and retain both target counts. The report audit binds the original protocol, per-image log and output files by SHA-256. `[verified: upstream astcenccli_image_load_store.cpp load_image_with_stb; astcenccli_error_metrics.cpp compute_error_metrics; common/nah_experiment.py; common/reporting.py]`

The Nah 2022 `source-rgb64-game` validation ran alongside repository checks and a separate offline quality audit on the same host. Its measured wall clocks are retained with this context. Input pixels, quality targets, encoder versions and mip scopes also differ from Unity. Method-specific fixed-8×8 controls and these per-run costs remain separately reported. `[verified: concurrent exec sessions 92587, 15732 and 18013; method protocols; implementation-notes.md]`

## Source and result provenance

Keep original publication settings and project-adapted settings as separate experiment identities. Unity uses LITE 30 dB with RDO off. The GDC original label target is PSNR >35 dB. Preserve encoder commits, input hashes, importer configuration, color profile, mip handling and timing boundaries in each report. `[verified: accepted plan; gdc2023/source.json]` `[opinion]`

Build success, smoke acceptance and full experiment completion are separate statuses. Only measured results may be marked complete. `[opinion]`

## Validation recorded with the Nah project runs

- `uv run --frozen pytest -q` passed 56 tests. `uv run --frozen ruff check src script tests reproductions` and `uv run --frozen basedpyright` passed. `[verified: test/check outputs, 2026-11-11]`
- Both 64-image runs and their two-image probes passed fresh selected/fixed8 ASTC decoding with the recorded native binary. Saved PNG SHA-256 values matched the new decodes. `[verified: each measured summary.json quality_audit.decode_verification]`
- A temporary copy of the 2023 probe passed normally, then a same-header, same-size ASTC payload replacement was rejected by fresh-decode comparison. The original artifact hash stayed unchanged. `[verified: experiment report/.local/reproduction-audit-checks.json]`
- Local Markdown file and anchor checks passed 135 references across 10 edited/report documents. External URL availability was outside this local check. `[verified: experiment report/.local/reproduction-markdown-check.json]`
