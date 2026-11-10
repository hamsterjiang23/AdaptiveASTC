# Reproduction task costs

| Task | Classification | Observed cost and state |
|---|---|---|
| Native Editor link, four build threads | Moderate | Link observed at approximately 3 GiB working set; native output target completed. Full package validation failed in UPM. `[verified: native-output-build.log; process snapshot]` |
| Unity two-texture probe | Unknown | First startup failed before imports. Diagnostic retry is recorded in the baseline run directory. `[verified: probe receipts and attempts/]` |
| 64-texture smoke and 10,000-texture baseline | Unknown | Run only after the two-texture probe passes; measure cost before expansion. `[opinion]` |
| TexNN training | Heavy | Paper reports roughly 40–48 hours per network on a Pascal GPU; current-machine cost remains unmeasured. `[verified: user-supplied TexNN PDF p.8 §3.6]` |

## I/O dependencies

The baseline reads the frozen coverage-v2 train manifest, project assets and importer metadata. It writes Unity Library artifacts, an isolated parameter-cache namespace and run-specific logs. Keep model training and other CPU-heavy encoding jobs out of measured baseline runs. `[verified: UnitySearchBenchmark.cs; benchmark.py]` `[opinion]`
