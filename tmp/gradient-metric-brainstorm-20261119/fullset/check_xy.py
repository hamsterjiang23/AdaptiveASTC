"""Read-only follow-up for choosing X / Y in the bad-tile rule ("X% of 8x8 tiles below Y dB").

Prints: denominators for the known images, where the bad tiles sit (smooth-gradient vs other content tiles),
a smooth-only variant, tile PSNR inside the gradient tiles of 615/616/617, a budget table, RMSE equivalents
and the manifest whole-image targets.  Reads tile-psnr.csv / new-step-v2.csv / archive PNGs; writes nothing.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from harness import KNOWN, MANIFEST, load_items, read
from new_step_v2 import gradient_mask, lab
from tile_psnr import _blocks, tile_psnr

HERE = Path(__file__).resolve().parent


def num(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def rank(values: dict[int, float], k: int) -> int | None:
    if k not in values or not math.isfinite(values[k]):
        return None
    return 1 + sum(v > values[k] for v in values.values() if math.isfinite(v))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = [{k: num(v) for k, v in r.items()}
            for r in csv.DictReader((HERE / "tile-psnr.csv").open(encoding="utf-8-sig"))]
    by = {int(r["id"]): r for r in rows}

    print("== known, display view: (bad all, bad & content, bad & smooth) per Y")
    for k in KNOWN:
        r = by[k]
        cells = {y: (int(r[f"bad_display_{y}"]), int(r[f"badc_display_{y}"]), int(r[f"bads_display_{y}"]))
                 for y in (28, 30, 32, 34)}
        print(k, f"tiles={int(r['tiles'])} content={int(r['content'])} smooth={int(r['smooth'])}", cells,
              f"share28 all={r['bad_display_28'] / r['tiles']:.4f} content={r['badc_display_28'] / r['content']:.4f}")

    pool = [r for r in rows if r["native_psnr"] >= 35]
    content = sum(r["content"] for r in pool)
    smooth = sum(r["smooth"] for r in pool)
    print(f"== pool native PSNR >= 35: n={len(pool)} content={content:.0f} smooth={smooth:.0f} "
          f"smooth/content={smooth / content:.4f}")
    for y in (28, 30, 32, 34):
        bad = sum(r[f"bad_display_{y}"] for r in pool)
        badc = sum(r[f"badc_display_{y}"] for r in pool)
        bads = sum(r[f"bads_display_{y}"] for r in pool)
        print(f"Y={y} bad={bad:.0f} in_smooth={bads:.0f} ({bads / bad:.4f})  "
              f"P(bad|smooth)={bads / smooth:.5f}  P(bad|other content)={(badc - bads) / (content - smooth):.5f}")

    step = {int(r["id"]): num(r["L_p95_primary@8"])
            for r in csv.DictReader((HERE / "new-step-v2.csv").open(encoding="utf-8-sig"))}
    print("== smooth-only variant: share of smooth-gradient tiles below Y (pool images with >= 8 smooth tiles)")
    for y in (28, 30, 32, 34):
        share = {int(r["id"]): r[f"bads_display_{y}"] / r["smooth"] for r in pool if r["smooth"] >= 8}
        top = sorted(share, key=lambda i: -share[i])[:20]
        top_step = sorted((i for i in share if math.isfinite(step.get(i, math.nan))), key=lambda i: -step[i])[:20]
        print(f"Y={y} n={len(share)} nonzero={sum(v > 0 for v in share.values())}",
              {k: (rank(share, k), round(share.get(k, math.nan), 3)) for k in KNOWN},
              "top20 overlap with L_p95_primary:", len(set(top) & set(top_step)))

    print("== tile PSNR (display view, 8x8 fastest): smooth-gradient tiles vs other content tiles")
    items = {i.id: i for i in load_items()}
    for k in KNOWN:
        item = items[k]
        ref, dec = read(item.display(None)), read(item.display(8))
        p = tile_psnr(ref, dec)
        mask = gradient_mask(lab(ref))
        cover = _blocks(mask.astype(float), "constant").sum(axis=2) / _blocks(np.ones(mask.shape), "constant").sum(axis=2)
        edge = _blocks(ref.astype(np.int16), "edge")
        is_content = (edge.max(axis=2) - edge.min(axis=2)) >= 2
        for name, sel in (("smooth", cover >= 0.5), ("other content", is_content & (cover < 0.5))):
            v = p[sel]
            finite = v[np.isfinite(v)]
            q = np.percentile(finite, [0, 10, 50, 90]).round(1).tolist() if finite.size else []
            print(k, f"{name}: n={v.size} lossless={int((~np.isfinite(v)).sum())} min/p10/median/p90={q}")

    print("== budget table (pool, display view, share of all tiles)")
    for y in (28, 30):
        share = {int(r["id"]): r[f"bad_display_{y}"] / r["tiles"] for r in pool}
        for x in (0.01, 0.02, 0.03, 0.05, 0.10):
            flagged = {i for i, v in share.items() if v >= x}
            print(f"Y={y} X={x:.0%} flagged={len(flagged)} known={sum(k in flagged for k in KNOWN)}")

    print("== RMSE per 8-bit channel for tile PSNR Y:", {y: round(255 / 10 ** (y / 20), 2) for y in (26, 28, 30, 32, 34, 40)})
    meta = {r["validation_index"]: r for r in json.loads(MANIFEST.read_bytes()) if r["preset"] == "fastest"}
    print("== manifest whole-image targets (psnr, ms-ssim):", len(meta),
          Counter((r["target_psnr_db"], r["target_ms_ssim_db"]) for r in meta.values()).most_common(),
          "known:", {k: meta[k]["target_psnr_db"] for k in KNOWN})


if __name__ == "__main__":
    main()
