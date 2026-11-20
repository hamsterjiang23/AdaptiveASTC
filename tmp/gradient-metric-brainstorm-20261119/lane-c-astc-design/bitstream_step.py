"""Encoder-side metric: predicted in-block step = reference L* ramp amplitude / (actual weight levels - 1), read from the .astc bitstream."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from astc_modes import read_astc
from common import composite, gradient_mask, lab, native_paths, rgba, view_of
from prototypes import CONTROLS, JND, POSITIVE, plane

out = {}
for idx in POSITIVE + CONTROLS:
    r, d = native_paths(idx, "fastest")
    nat = rgba(r).astype(float)
    view = view_of(idx)
    disp = composite(nat, 64. if view == "dark" else None)
    mask = gradient_mask(lab(disp)); ls = lab(disp)[..., 0]
    res = {}
    for tag in (["8x8_fastest", "8x8_medium", "6x6_fastest"] if idx in POSITIVE else ["8x8_fastest"]):
        b, _, w, h, bl = read_astc(d.parent / f"{tag}.astc")
        steps = []
        for j, row in enumerate(bl):
            for i, blk in enumerate(row):
                y0, y1 = max(0, h - (j + 1) * b), h - j * b
                m = mask[y0:y1, i * b:(i + 1) * b]
                if m.size == 0 or m.mean() < .5 or min(m.shape) < 3:
                    continue
                _, amp = plane(ls[y0:y1, i * b:(i + 1) * b])
                q = blk["weight_levels"] if blk["kind"] == "normal" else 256
                steps.append(amp / (q - 1))
        s = np.asarray(steps)
        res[tag] = {"grad_blocks": int(len(s)), "step_p90": float(np.quantile(s, .9)) if len(s) else None,
                    "frac_step_ge_jnd": float(np.mean(s >= JND)) if len(s) else None,
                    "n_step_ge_jnd": int((s >= JND).sum())}
    out[idx] = res
(HERE / "bitstream-step.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
for k, v in out.items():
    print(k, {t: (x["grad_blocks"], None if x["step_p90"] is None else round(x["step_p90"], 2), None if x["frac_step_ge_jnd"] is None else round(x["frac_step_ge_jnd"], 3), x["n_step_ge_jnd"]) for t, x in v.items()})
