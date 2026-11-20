"""Lane C B1 (in-block level collapse) and B2 (in-block slope loss) for all 20 candidates of the 128² sRGB colour set."""
from __future__ import annotations
import csv, json, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
from check_candidates import BLOCKS, MANIFEST, PRESETS, gradient_mask, lab, load, rgba, view

def fit(values: np.ndarray) -> tuple[np.ndarray, float]:
    hh, ww = values.shape
    yy, xx = np.mgrid[:hh, :ww]
    a = np.column_stack((np.ones(values.size), yy.ravel(), xx.ravel()))
    coef, *_ = np.linalg.lstsq(a, values.ravel(), rcond=None)
    f = a @ coef
    return coef[1:], float(f.max() - f.min())

def blocks(h: int, w: int, b: int):
    j = 0
    while j * b < h:
        y0, y1 = max(0, h - (j + 1) * b), h - j * b
        for i in range(0, w, b):
            yield y0, y1, i, min(w, i + b)
        j += 1

out = []
t0 = time.perf_counter()
for r in load(None, True):
    folder = Path(r["decoded_path"]).parent
    alpha = bool(r["need_alpha"]) and not bool(r["alpha_constant"])
    src = lab(view(rgba(Path(r["reference_path"])), alpha)); mask = gradient_mask(src); lr = src[..., 0]
    h, w = lr.shape
    for b in BLOCKS:
        ref = []
        for y0, y1, x0, x1 in blocks(h, w, b):
            m = mask[y0:y1, x0:x1]
            if m.size < 4 or m.mean() < .5 or min(y1 - y0, x1 - x0) < 3:
                continue
            sr, ar = fit(lr[y0:y1, x0:x1])
            if ar < 2:
                continue
            ref.append((y0, y1, x0, x1, m, sr, ar, len(np.unique(np.round(lr[y0:y1, x0:x1][m])))))
        for p in PRESETS:
            ld = lab(view(rgba(folder / f"{b}x{b}_{p}.png"), alpha))[..., 0]
            flat, poster, amps = [], [], []
            for y0, y1, x0, x1, m, sr, ar, nr in ref:
                sd, _ = fit(ld[y0:y1, x0:x1])
                keep = float(np.dot(sd, sr) / max(np.dot(sr, sr), 1e-12))
                flat.append(max(0., 1 - keep) * ar)
                nd = len(np.unique(np.round(ld[y0:y1, x0:x1][m])))
                poster.append(max(0., 1 - nd / nr) if nr >= 4 else 0.)
                amps.append(ar)
            f, po, am = map(np.asarray, (flat, poster, amps))
            out.append({"id": r["validation_index"], "block": b, "preset": p,
                        "b1": float(np.mean((po >= .5) & (am >= 4))) if len(f) else None,
                        "b2_area": float(np.mean(f >= 3)) if len(f) else None,
                        "b2_p90": float(np.quantile(f, .9)) if len(f) else None, "gblocks": len(f)})
with (Path(__file__).parent / "b12-pop128.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=list(out[0])); wr.writeheader(); wr.writerows(out)
print(len(out), f"{time.perf_counter() - t0:.1f}s")
