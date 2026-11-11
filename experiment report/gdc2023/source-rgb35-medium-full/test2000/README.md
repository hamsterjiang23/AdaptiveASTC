# GDC measured compression loop

Measured 2000 test images with the pretrained model. The strict target passed for 1540 images. Actual payload / fixed8 is 0.9877; complete model pipeline / fixed8 time is 0.9733. `[verified: accompanying JSON quality, payload and costs]`

Quality violations are retained. This is a source-RGB four-square reconstruction; the original published results and a direct Unity speedup are unverified. `[verified: accompanying JSON protocol and limits]`

| Offline fixed footprint | Strict target passed | Actual payload bytes |
|---|---|---|
| 6x6 | 1782/2000 | 305,944,208 `[verified: accompanying JSON offline_fixed_footprints]` |
| 8x8 | 1505/2000 | 171,018,320 `[verified: accompanying JSON offline_fixed_footprints]` |
| 10x10 | 1211/2000 | 110,664,080 `[verified: accompanying JSON offline_fixed_footprints]` |
| 12x12 | 1008/2000 | 77,042,928 `[verified: accompanying JSON offline_fixed_footprints]` |

All controls use the same full-resolution RGB inputs. Offline encoding times come from parallel label collection; the separately measured fixed8 pipeline remains the deployment latency control. `[verified: accompanying JSON protocol, offline_fixed_footprints and costs]`

Full per-image results and costs: [pretrained-test.json](pretrained-test.json). `[verified: accompanying JSON]`
