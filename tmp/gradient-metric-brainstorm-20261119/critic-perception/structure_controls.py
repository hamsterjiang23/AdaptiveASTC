"""Real 8x8 fastest vs equal-energy controls on the 196 native 128x128 colour assets.

Conditions per image (display RGB, dark composite for alpha assets):
  real8   archived 8x8 fastest decode
  scr8    same error vectors, randomly permuted among gradient-mask pixels (structure destroyed, mask SSE kept)
  smooth8 error low-passed (sigma 2) and rescaled to the same in-mask SSE (no steps, same energy)
  real4   archived 4x4 fastest decode (near-clean negative control), grid metrics use block 4
Writes structure-controls.csv next to this file only.
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.dont_write_bytecode = True
for _n in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_n, "1")
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from metrics_bridge import FIELDS, gradient_mask, lab, score  # noqa: E402

MEDIA = Path("E:/ASTC_Compression/outputs/01a1eca4-b759-74d2-82d5-2d27a4db8e18/media")
DATA = MEDIA.parent / "data.js"


def load(p: Path) -> np.ndarray:
    with Image.open(p) as im:
        return np.asarray(im.convert("RGB"))


def work(args: tuple[int, str, str, float]) -> dict:
    idx, view, asset, psnr = args
    folder = MEDIA / f"{idx:04d}"
    ref = load(folder / f"ref-{view}.png")
    dec = load(folder / f"fastest-{view}.png")
    m = gradient_mask(lab(ref))
    row: dict = {"id": idx, "asset": asset, "group": os.path.dirname(asset), "view": view, "native_psnr": psnr}
    e = dec.astype(float) - ref.astype(float)
    rng = np.random.default_rng(idx)
    conds = {"real8": (dec, 8)}
    if m.sum() >= 2:
        es = e.copy()
        vec = es[m]
        es[m] = vec[rng.permutation(len(vec))]
        conds["scr8"] = (np.clip(np.rint(ref + es), 0, 255).astype(np.uint8), 8)
        el = gaussian_filter(e, (2, 2, 0))
        num, den = float((e[m] ** 2).sum()), float((el[m] ** 2).sum())
        el2 = e.copy()
        el2[m] = el[m] * (np.sqrt(num / den) if den > 1e-12 else 0.0)
        conds["smooth8"] = (np.clip(np.rint(ref + el2), 0, 255).astype(np.uint8), 8)
    p4 = folder / f"4x4-fastest-{view}.png"
    if p4.exists():
        conds["real4"] = (load(p4), 4)
    for tag, (img, b) in conds.items():
        s = score(ref, img, b, mask=m)
        for k in (*FIELDS, "mse_display", "mse_in_mask"):
            row[f"{k}|{tag}"] = s[k]
    row["mask_px"] = int(m.sum())
    return row


def main() -> None:
    assets = json.loads(DATA.read_text(encoding="utf-8").removeprefix("window.REVIEW=").removesuffix(";"))["assets"]
    jobs = []
    for a in assets:
        if a["w"] != 128 or a["h"] != 128 or a["views"] == ["data"]:
            continue
        view = "dark" if "dark" in a["views"] else "rgb"
        native = next(r for r in a["rows"] if r["view"] == view and r["preset"] == "fastest")
        jobs.append((a["id"], view, a["asset"], float(native["psnr"])))
    if "--smoke" in sys.argv:
        jobs = [j for j in jobs if j[0] in (615, 616, 617, 587, 790)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(work, jobs, chunksize=4))
    name = "structure-controls-smoke.csv" if "--smoke" in sys.argv else "structure-controls.csv"
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (HERE / name).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "rows ->", name)


if __name__ == "__main__":
    main()
