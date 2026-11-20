"""Which original-block properties make the 8x8 fastest encoder pick dense-grid / <=4-level weight modes?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from astc_modes import read_astc  # noqa: E402
from common import composite, gradient_mask, lab, native_paths, rgba, view_of  # noqa: E402
from prototypes import CONTROLS, POSITIVE, plane  # noqa: E402


def main() -> None:
    out = {}
    pooled = []
    for idx in POSITIVE + CONTROLS:
        ref_path, dec_path = native_paths(idx, "fastest")
        nat = rgba(ref_path).astype(float)
        view = view_of(idx)
        disp = composite(nat, 64. if view == "dark" else None)
        mask = gradient_mask(lab(disp))
        lstar = lab(disp)[..., 0]
        res = {}
        for preset in ("fastest", "medium"):
            b, _, w, h, bl = read_astc(dec_path.parent / f"8x8_{preset}.astc")
            low = dense = n = 0
            feats = []
            for j, row in enumerate(bl):
                for i, blk in enumerate(row):
                    y0, y1 = max(0, h - (j + 1) * b), h - j * b
                    m = mask[y0:y1, i * b:(i + 1) * b]
                    if m.size == 0 or m.mean() < .5 or blk["kind"] != "normal":
                        continue
                    n += 1
                    lowq = blk["weight_levels"] <= 4
                    low += lowq
                    dense += blk["grid"][0] * blk["grid"][1] >= 36
                    if preset == "fastest":
                        cells = nat[y0:y1, i * b:(i + 1) * b]
                        chans = range(4) if view == "dark" else range(3)
                        resid = np.sqrt(np.mean([np.var(cells[..., c] - (cells[..., c].mean() + 0)) - 0 for c in chans]))
                        # encoder-space high-frequency residual: plane-fit residual RMS over stored channels
                        hf = []
                        for c in chans:
                            _, _ = plane(cells[..., c])
                            yy, xx = np.mgrid[:cells.shape[0], :cells.shape[1]]
                            a = np.column_stack((np.ones(cells[..., c].size), yy.ravel(), xx.ravel()))
                            coef, *_ = np.linalg.lstsq(a, cells[..., c].ravel(), rcond=None)
                            hf.append(np.mean((cells[..., c].ravel() - a @ coef) ** 2))
                        _, amp = plane(lstar[y0:y1, i * b:(i + 1) * b])
                        feats.append({"lowq": bool(lowq), "hf_rms": float(np.sqrt(np.mean(hf))), "std": float(resid),
                                      "ramp_lstar": amp})
            res[preset] = {"gradient_blocks": n, "frac_weight_levels_le4": low / n if n else None,
                           "frac_grid_ge36": dense / n if n else None}
            if preset == "fastest":
                pooled += [dict(f, id=idx) for f in feats]
        out[idx] = res
    # Pooled association between block features and the fastest low-precision choice.
    lowq = np.array([f["lowq"] for f in pooled])
    hf = np.array([f["hf_rms"] for f in pooled])
    amp = np.array([f["ramp_lstar"] for f in pooled])
    summary = {"pooled_blocks": int(len(pooled)), "frac_lowq": float(lowq.mean())}
    for name, v in (("hf_rms", hf), ("ramp_lstar", amp)):
        qs = np.quantile(v, [0, .25, .5, .75, 1])
        summary[name] = {}
        for k in range(4):
            sel = (v >= qs[k]) & (v <= qs[k + 1])
            summary[name][f"q{k + 1}[{qs[k]:.2f},{qs[k + 1]:.2f}]"] = {"n": int(sel.sum()), "frac_lowq": float(lowq[sel].mean())}
    out["pooled"] = summary
    (HERE / "mode-choice.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
