# Reproduction task costs

| Task | Classification | Observed cost and state |
|---|---|---|
| Native Editor link, four build threads | Moderate | Link observed at approximately 3 GiB working set; native output target completed. Full package validation failed in UPM. `[verified: native-output-build.log; process snapshot]` |
| Unity two-texture probe | Unknown | First startup failed before imports. Diagnostic retry is recorded in the baseline run directory. `[verified: probe receipts and attempts/]` |
| 64-texture smoke and 10,000-texture baseline | Unknown | Run only after the two-texture probe passes; measure cost before expansion. `[opinion]` |
| TexNN training | Heavy | Paper reports roughly 40–48 hours per network on a Pascal GPU; current-machine cost remains unmeasured. `[verified: user-supplied TexNN PDF p.8 §3.6]` |
| TexNN 64 source-image labels, 64-pixel crops, two workers | Light | 77.47 s for three footprints; 8,377 / 3,724 / 2,340 nonconstant blocks. `[verified: source-rgb64-patch64-v2 collection.json and prepared manifests]` |
| TexNN six-network pilot training | Light | CUDA training loops total about 69.5 s, batch 128, up to 100 epochs with patience 8. The largest network has 40.5M parameters. `[verified: source-rgb64-patch64-v2 models training_complete.json; network-shape-probe.json]` |
| TexNN independent validation pilot | Light | 8 center crops of at most 128×128, 48 encoding pairs, 133.64 s batch wall. CPU inference and encoding use one thread. `[verified: validation8-patch128 receipt.json and protocol.json]` |

## I/O dependencies

The baseline reads the frozen coverage-v2 train manifest, project assets and importer metadata. It writes Unity Library artifacts, an isolated parameter-cache namespace and run-specific logs. Keep model training and other CPU-heavy encoding jobs out of measured baseline runs. `[verified: UnitySearchBenchmark.cs; benchmark.py]` `[opinion]`
