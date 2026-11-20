"""Merge B1/B2 into the candidate table and repeat monotonicity, known ranks and gate simulation."""
from __future__ import annotations
import csv, json, sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode = True
import analyze as A

imgs = A.load("pop128")
for r in csv.DictReader((A.HERE / "b12-pop128.csv").open(encoding="utf-8-sig")):
    c = imgs[int(r["id"])][(int(r["block"]), r["preset"])]
    for k in ("b1", "b2_area", "b2_p90"):
        c[k] = A.num(r[k])
labels = {i: A.pick(c)[0] for i, c in imgs.items()}
res = {}
for m in ("b1", "b2_area", "b2_p90"):
    pres, blk = [], []
    for c in imgs.values():
        for b in (12, 10, 8, 6):
            s = [c[(b, p)][m] for p in A.PRESETS]
            pres.append(None if all(v is None for v in s) else all(
                y <= x + .05 for x, y in zip([v for v in s if v is not None], [v for v in s if v is not None][1:])))
        for p in A.PRESETS:
            s = [c[(b, p)][m] for b in (6, 8, 10, 12)]
            blk.append(None if all(v is None for v in s) else all(
                y >= x - .05 for x, y in zip([v for v in s if v is not None], [v for v in s if v is not None][1:])))
    pv, bv = [x for x in pres if x is not None], [x for x in blk if x is not None]
    ranks = {}
    for name, key in (("label", lambda i: labels[i]), ("fixed8_medium", lambda i: (8, "medium")), ("fixed8_fastest", lambda i: (8, "fastest"))):
        vals = sorted(((imgs[i][key(i)][m] or 0., i) for i in imgs), reverse=True)
        order = [i for _, i in vals]
        ranks[name] = {str(k): [order.index(k) + 1, round(imgs[k][key(k)][m] or 0., 3)] for k in A.KNOWN}
    tau = min(imgs[k][(8, "fastest")][m] for k in A.KNOWN)
    moved, kinds, nb = 0, Counter(), 0
    known = {}
    for i, c in imgs.items():
        key, kind = A.pick(c, m, tau)
        kinds[kind] += 1; nb += c[key]["payload"]; moved += key != labels[i]
        if i in A.KNOWN:
            known[str(i)] = f"{key[0]}x{key[0]}_{key[1]}"
    base = sum(imgs[i][labels[i]]["payload"] for i in imgs)
    res[m] = {"preset_monotone_tol0.05": f"{sum(pv)}/{len(pv)}", "block_monotone_tol0.05": f"{sum(bv)}/{len(bv)}",
              "ranks": ranks, "gate": {"tau": round(tau, 3), "moved": moved, "kinds": dict(kinds), "bytes_ratio": round(nb / base, 3), "known": known}}
(A.HERE / "analysis-b12.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
