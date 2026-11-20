"""Lane A luma JND step ratio (P95), copied formula from lane-a probe_lane_a.py chou_li_jnd, on all 20 candidates."""
from __future__ import annotations
import csv, json, sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
from scipy.ndimage import uniform_filter
from check_candidates import BLOCKS, PRESETS, gradient_mask, lab, load, rgba, view
import analyze as A
LUMA = np.array([.2126, .7152, .0722])

def chou_li_jnd(y: np.ndarray) -> np.ndarray:
    bg = uniform_filter(y, 5, mode="nearest")
    p = np.pad(y, 1, mode="edge")
    gx = (p[:-2, 2:] + 2*p[1:-1, 2:] + p[2:, 2:] - p[:-2, :-2] - 2*p[1:-1, :-2] - p[2:, :-2]) / 8
    gy = (p[2:, :-2] + 2*p[2:, 1:-1] + p[2:, 2:] - p[:-2, :-2] - 2*p[:-2, 1:-1] - p[:-2, 2:]) / 8
    d1 = (p[1:-1, 2:] + 2*p[2:, 2:] + p[2:, 1:-1] - p[:-2, 1:-1] - 2*p[:-2, :-2] - p[1:-1, :-2]) / 8
    d2 = (p[1:-1, :-2] + 2*p[2:, :-2] + p[2:, 1:-1] - p[:-2, 1:-1] - 2*p[:-2, 2:] - p[1:-1, 2:]) / 8
    mg = np.max(np.abs(np.stack((gx, gy, d1, d2))), axis=0)
    f1 = mg * (bg*.0001 + .115) + (.5 - bg*.001)
    f2 = np.where(bg <= 127, 17*(1 - np.sqrt(np.clip(bg, 0, 127)/127)) + 3, 3/128*(bg - 127) + 3)
    return np.maximum(f1, f2)

def jnd_p95(yr, yd, jnd, mask):
    vals = []
    for axis in (0, 1):
        r, d, m, j = (np.swapaxes(a, axis, 0) for a in (yr, yd, mask, jnd))
        sup = m[1:] & m[:-1]
        vals.append((np.abs(np.diff(d, axis=0) - np.diff(r, axis=0)) / (.5*(j[1:] + j[:-1])))[sup])
    v = np.concatenate(vals)
    return float(np.quantile(v, .95)) if v.size else None

imgs = A.load("pop128")
for r in load(None, True):
    folder = Path(r["decoded_path"]).parent
    alpha = bool(r["need_alpha"]) and not bool(r["alpha_constant"])
    ref = view(rgba(Path(r["reference_path"])), alpha)
    mask = gradient_mask(lab(ref)); yr = ref @ LUMA; jnd = chou_li_jnd(yr)
    for b in BLOCKS:
        for p in PRESETS:
            imgs[r["validation_index"]][(b, p)]["jnd"] = jnd_p95(yr, view(rgba(folder / f"{b}x{b}_{p}.png"), alpha) @ LUMA, jnd, mask)
labels = {i: A.pick(c)[0] for i, c in imgs.items()}
def mono(seq, inc):
    v = [x for x in seq if x is not None]
    if len(v) < 2 or max(v) < 1: return None
    return all((y >= x - max(.1, .1*x)) if inc else (y <= x + max(.1, .1*x)) for x, y in zip(v, v[1:]))
pres = [mono([c[(b, p)]["jnd"] for p in PRESETS], False) for c in imgs.values() for b in BLOCKS]
blk = [mono([c[(b, p)]["jnd"] for b in (6, 8, 10, 12)], True) for c in imgs.values() for p in PRESETS]
pv, bv = [x for x in pres if x is not None], [x for x in blk if x is not None]
out = {"preset_monotone(tol max(0.1,10%),floor1)": f"{sum(pv)}/{len(pv)}", "block_monotone": f"{sum(bv)}/{len(bv)}"}
for name, key in (("label", lambda i: labels[i]), ("fixed8_medium", lambda i: (8, "medium")), ("fixed8_fastest", lambda i: (8, "fastest"))):
    order = [i for _, i in sorted(((imgs[i][key(i)]["jnd"] or 0., i) for i in imgs), reverse=True)]
    out[name] = {str(k): [order.index(k) + 1, round(imgs[k][key(k)]["jnd"] or 0., 3)] for k in A.KNOWN}
tau = min(imgs[k][(8, "fastest")]["jnd"] for k in A.KNOWN)
moved, kinds, nb, known = 0, Counter(), 0, {}
for i, c in imgs.items():
    key, kind = A.pick(c, "jnd", tau)
    kinds[kind] += 1; nb += c[key]["payload"]; moved += key != labels[i]
    if i in A.KNOWN: known[str(i)] = f"{key[0]}x{key[0]}_{key[1]}"
out["gate"] = {"tau": round(tau, 3), "moved": moved, "kinds": dict(kinds),
               "bytes_ratio": round(nb / sum(imgs[i][labels[i]]["payload"] for i in imgs), 3), "known": known}
(A.HERE / "analysis-jnd.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
