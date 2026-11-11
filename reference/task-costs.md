# Reproduction task costs

| Task | Classification | Observed cost and state |
|---|---|---|
| Native Editor link, four build threads | Moderate | Link observed at approximately 3 GiB working set; native output target completed. Full package validation failed in UPM. `[verified: native-output-build.log; process snapshot]` |
| Unity two-texture probe | Light | Final measured probe wall 267.97 s; initial startup failures remain archived separately. `[verified: unity-search-baseline-lite-rdo-off/probe-receipt.json process_wall_seconds]` |
| 64-texture smoke and 10,000-texture baseline | Heavy for full cohort | First64 smoke wall 434.38 s; complete10k plus technical retries wall 24,416.51 s, native search 4,060.47 s. Keep the machine free of competing benchmarks for a new timing run. `[verified: smoke1-receipt.json; full-receipt.json]` `[opinion]` |
| TexNN training | Heavy | Paper reports roughly 40–48 hours per network on a Pascal GPU; current-machine cost remains unmeasured. `[verified: user-supplied TexNN PDF p.8 §3.6]` |
| TexNN 64 source-image labels, 64-pixel crops, two workers | Light | 77.47 s for three footprints; 8,377 / 3,724 / 2,340 nonconstant blocks. `[verified: source-rgb64-patch64-v2 collection.json and prepared manifests]` |
| TexNN six-network pilot training | Light | CUDA training loops total about 69.5 s, batch 128, up to 100 epochs with patience 8. The largest network has 40.5M parameters. `[verified: source-rgb64-patch64-v2 models training_complete.json; network-shape-probe.json]` |
| TexNN independent validation pilot | Light | 8 center crops of at most 128×128, 48 encoding pairs, 133.64 s batch wall. CPU inference and encoding use one thread. `[verified: validation8-patch128 receipt.json and protocol.json]` |
| TexNN expanded 1,024-source adaptation | Moderate | Four-worker collection 836.39 s; six CUDA training loops total 1,865.59 s; independent 48-pair validation 135.06 s. `[verified: source-rgb1024-patch64-v2 data.json and validation8-patch128.json]` |
| GDC smoke compression loop | Light | 64-image label generation 49.90 s with two workers; 32-image ten-epoch training 2.59 s; 16-image model pipeline 8.54 s and complete evaluation wall 22.33 s. `[verified: source-rgb35-medium-smoke/test16/pretrained-test.json costs]` |
| GDC formal 14k candidate labels | Heavy | Running with four workers over 6.793 billion source pixels. Preflight available RAM 41.8 GiB, free disk 983 GiB and CPU load 7.5%; largest source 8,870×5,014. Whole-image float64 RGB quality checks determine conservative memory headroom. `[verified: full manifest/resource preflight and running command]` |

## I/O dependencies

The baseline reads the frozen coverage-v2 train manifest, project assets and importer metadata. It writes Unity Library artifacts, an isolated parameter-cache namespace and run-specific logs. Keep model training and other CPU-heavy encoding jobs out of measured baseline runs. `[verified: UnitySearchBenchmark.cs; benchmark.py]` `[opinion]`
