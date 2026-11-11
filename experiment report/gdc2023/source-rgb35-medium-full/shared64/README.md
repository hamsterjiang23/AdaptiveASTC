# GDC measured compression loop

Measured 64 train images with the pretrained model. The strict target passed for 48 images. Actual payload / fixed8 is 0.8408; complete model pipeline / fixed8 time is 0.9261. `[verified: accompanying JSON quality, payload and costs]`

Quality violations are retained. This is a source-RGB four-square reconstruction; the original published results and a direct Unity speedup are unverified. `[verified: accompanying JSON protocol and limits]`

| Offline fixed footprint | Strict target passed | Actual payload bytes |
|---|---|---|
| 6x6 | 57/64 | 65,090,688 `[verified: accompanying JSON offline_fixed_footprints]` |
| 8x8 | 47/64 | 36,560,832 `[verified: accompanying JSON offline_fixed_footprints]` |
| 10x10 | 30/64 | 23,445,568 `[verified: accompanying JSON offline_fixed_footprints]` |
| 12x12 | 26/64 | 16,310,384 `[verified: accompanying JSON offline_fixed_footprints]` |

All controls use the same full-resolution RGB inputs. Offline encoding times come from parallel label collection; the separately measured fixed8 pipeline remains the deployment latency control. `[verified: accompanying JSON protocol, offline_fixed_footprints and costs]`

Full per-image results and costs: [pretrained-train.json](pretrained-train.json). `[verified: accompanying JSON]`
