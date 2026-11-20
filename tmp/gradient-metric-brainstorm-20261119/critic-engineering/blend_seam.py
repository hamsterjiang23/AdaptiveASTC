"""Lane B blend-bound idea, seam version: continuous seam on black / dark-64 / white composites (alpha 128² images)."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
from check_candidates import MANIFEST, evaluate, gradient_mask, lab, rgba, view

rows = [r for r in json.loads(MANIFEST.read_bytes()) if r["preset"] == "fastest" and r["width"] == r["height"] == 128
        and r["srgb"] and not r["is_normal"] and r["need_alpha"] and not r["alpha_constant"]]
out = []
for r in rows:
    folder = Path(r["decoded_path"]).parent
    ref = rgba(Path(r["reference_path"]))
    gb, gp = int(r["gt_block"].split("x")[0]), r["gt_preset"]
    rec = {"id": r["validation_index"]}
    for bg in (0., 64., 255.):
        src = lab(view(ref, True, bg)); mask = gradient_mask(src)
        for tag, b, p in (("f8", 8, "fastest"), ("m8", 8, "medium"), ("label", gb, gp)):
            res, _ = evaluate(src, lab(view(rgba(folder / f"{b}x{b}_{p}.png"), True, bg)), mask, b)
            rec[f"{tag}_bg{int(bg)}"] = res["continuous_seam"]
    for tag in ("f8", "m8", "label"):
        vals = [rec[f"{tag}_bg{b}"] for b in (0, 255) if rec[f"{tag}_bg{b}"] is not None]
        rec[f"{tag}_bw"] = max(vals) if vals else None
    out.append(rec)
summary = {"n_alpha_images": len(out)}
for key in [f"{t}_{s}" for t in ("f8", "m8", "label") for s in ("bg0", "bg64", "bg255", "bw")]:
    valid = sorted((x[key], x["id"]) for x in out if x[key] is not None)[::-1]
    order = [i for _, i in valid]
    summary[key] = {"n_valid": len(valid), **{str(k): (order.index(k) + 1 if k in order else None) for k in (615, 617)}}
(Path(__file__).parent / "blend-seam.json").write_text(json.dumps({"summary": summary, "rows": out}, indent=1), encoding="utf-8")
print(json.dumps(summary, indent=0))
