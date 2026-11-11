# GDC measured compression loop

Measured 16 test images with the pretrained model. The strict target passed for 5 images. Actual payload / fixed8 is 0.4514; complete model pipeline / fixed8 time is 0.8725. `[verified: accompanying JSON quality, payload and costs]`

Quality violations are retained. This is a source-RGB four-square reconstruction; the original published results and a direct Unity speedup are unverified. `[verified: accompanying JSON protocol and limits]`

| Offline fixed footprint | Strict target passed | Actual payload bytes |
|---|---|---|
| 6x6 | 16/16 | 6,087,616 `[verified: accompanying JSON offline_fixed_footprints]` |
| 8x8 | 15/16 | 3,407,872 `[verified: accompanying JSON offline_fixed_footprints]` |
| 10x10 | 11/16 | 2,209,984 `[verified: accompanying JSON offline_fixed_footprints]` |
| 12x12 | 5/16 | 1,538,368 `[verified: accompanying JSON offline_fixed_footprints]` |

All controls use the same full-resolution RGB inputs. Offline encoding times come from parallel label collection; the separately measured fixed8 pipeline remains the deployment latency control. `[verified: accompanying JSON protocol, offline_fixed_footprints and costs]`

Full per-image results and costs: [pretrained-test.json](pretrained-test.json). `[verified: accompanying JSON]`
