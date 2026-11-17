# V3 implementation notes

## Deviations

- The launch preflight found no `pueue` executable. Long jobs used the existing `ReproductionJob` runner, which recorded command arguments, stdout/stderr, process IDs and exit receipts, with one GPU job at a time. `[verified: launch preflight Get-Command; jobs/development-suite-v1/receipt.json; reproductions/common/jobs.py ReproductionJob.run]`
- The first CUDA training smoke failed before any update because the Windows sandbox denied the DataLoader pipe. A new v2 smoke identity ran the same workers=2 recipe with reviewed elevation and passed. `[verified: train-unity-full-smoke-v1.json training_updates; jobs/train-unity-full-smoke-v1/stderr.log; train-unity-full-smoke-v2.json checkpoint_audit]`
- File-to-ASTC and pixels-ready timings are measured in separate calls. Pixels-ready throughput uses bounded groups of eight images, while the files batch predicts the full validation set; each report records that grouping. Single-image latency always runs fresh per-image inference. `[verified: v3_benchmark.py measure; v3_deployment.py _single_image_trials]`

## Discovered edge cases

- Candidate identity must remain canonical20 even when four exhaustive candidates are disabled; existing V2 rules hard-code 20 and five presets per block. V3 uses an independent policy implementation and preserves V2 source bytes. `[verified: reproductions/unity_search_baseline/system_variant_policy.py L92–118; opinion: V3 implementation]`
- Raw source files can be matched to captured labels through the candidate manifest's `source_md4`; source path equality alone is insufficient. `[verified: candidate manifest original row source_md4; opinion: input binding]`
- All11000 sources decode and match captured MD4. Effective dimensions differ for3167training and368validation assets, so source-native and target-aligned inputs remain distinct controls. `[verified: source-input-audit.json counts; opinion: controls]`
- The execution entry has help/status handling and an execution lock. The launcher source used by the completed serial run is archived under `.local/unity-v3-20261113/controller-launch-source`. Stage implementations are bound to their own SHA snapshots. `[verified: script/execute_unity_v3.py; controller-launch-source/execute_unity_v3.py; benchmark configuration execution_sources_sha256; jobs/development-suite-v1/receipt.json status]`
- Concurrent Blender CPU activity was observed during timing. The original-search files/single totals were468.65,522.54,640.14seconds; resource observations and individual repeats remain available for interpreting timing variability. `[verified: benchmark-v2-full1000-v1.json original-full20 files/single; resource-observations.jsonl; live psutil output]`
- Encoded source-file SHA256 identities have0cross-split groups in the10000/1000development split. This check covers encoded file identity. `[verified: source-file-duplicates.json]`
- Final diagnostics compare target-aligned source RGB and Alpha with their bound Unity reference pixels, preserve per-asset channel errors, and report size/color/Alpha/normal groups for pure prediction and actual forward search. The two-image CPU check passed exact-channel-error and reference-identity rejection assertions. `[verified: v3_input_diagnostics.py pixel_differences/group_indices; local diagnostic check output "PASS pixel-difference grouping, BICUBIC target dimensions, channel errors, reference identity rejection"]`

## Questions for review

- Formal confirmation remains unauthorized by this development plan. The existing 2000-image cohort is not used for training, tuning or development inference. `[verified: approved V3 plan section 5]`
