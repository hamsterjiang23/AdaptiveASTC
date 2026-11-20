"""Block-level check of A1 (alpha/RGB competition) vs actual 8x8 fastest visible error; ablation without the competition factor."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import composite, lab, native_paths, rgba, view_of
from prototypes import blocks

rows = []
for idx in (615, 617, 363, 630, 449, 602):
    r, d = native_paths(idx, "fastest")
    nat, dec = rgba(r).astype(float), rgba(d).astype(float)
    lr, ld = lab(composite(nat, 64.))[..., 0], lab(composite(dec, 64.))[..., 0]
    for y0, y1, x0, x1 in blocks(128, 128, 8):
        blk = nat[y0:y1, x0:x1].reshape(-1, 4)
        span = blk[:, 3].max() - blk[:, 3].min()
        if span < 8:
            continue
        x = blk - blk.mean(0)
        _, _, vt = np.linalg.svd(x, full_matrices=False)
        sc = x @ vt[0]
        ca = np.corrcoef(sc, blk[:, 3])[0, 1] if sc.std() > 1e-9 else 0.
        mean_rgb = blk[blk[:, 3] >= np.median(blk[:, 3]), :3].mean(0)
        lo = composite(np.r_[mean_rgb, blk[:, 3].min()][None, None], 64.)
        hi = composite(np.r_[mean_rgb, blk[:, 3].max()][None, None], 64.)
        vis = abs(lab(hi)[0, 0, 0] - lab(lo)[0, 0, 0])
        err = float(np.sqrt(np.mean((lr[y0:y1, x0:x1] - ld[y0:y1, x0:x1]) ** 2)))
        rgb_var = float(x[:, :3].var(0).sum()); a_var = float(x[:, 3].var())
        rows.append(dict(id=idx, vis=vis, comp=1 - ca ** 2, a1=(1 - ca ** 2) * vis, err=err, rgb_over_a=rgb_var / max(a_var, 1e-9)))
err = np.array([r["err"] for r in rows])
out = {"blocks": len(rows)}
for k in ("a1", "vis", "comp", "rgb_over_a"):
    v = np.array([r[k] for r in rows]); rho, p = spearmanr(v, err)
    out[f"spearman_{k}_vs_display_Lstar_rmse"] = [round(float(rho), 3), float(p)]
# high-competition vs low-competition blocks at similar visible amplitude
vis = np.array([r["vis"] for r in rows]); comp = np.array([r["comp"] for r in rows])
sel = vis >= 10
out["vis>=10_blocks"] = int(sel.sum())
out["median_err_comp>=0.5"] = float(np.median(err[sel & (comp >= .5)])) if np.any(sel & (comp >= .5)) else None
out["n_comp>=0.5"] = int(np.sum(sel & (comp >= .5)))
out["median_err_comp<0.1"] = float(np.median(err[sel & (comp < .1)])) if np.any(sel & (comp < .1)) else None
out["n_comp<0.1"] = int(np.sum(sel & (comp < .1)))
(HERE / "a1-block-check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
