"""Bad-tile share check: 8x8 tiles, tile PSNR below Y, on the 938 dev images (8x8 fastest decodes).

Tiles follow the bottom-anchored ASTC grid in display orientation.  Tile PSNR is computed from the tile MSE
over the channels of three views: native RGB, native RGBA and the primary display view (RGB, or the alpha
image composited over grey 64).  Content tiles: display reference range >= 2.  Smooth tiles: >= 50% inside
the reference gradient mask.  Read-only on the archive; writes tile-psnr.csv / tile-psnr-summary.json here.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import numpy as np  # noqa: E402

from harness import KNOWN, Item, load_items, read, spearman  # noqa: E402
from new_step_v2 import gradient_mask, lab  # noqa: E402

HERE = Path(__file__).resolve().parent
TILE = 8
YS = (24, 26, 28, 30, 32, 34)
VIEWS = ("native_rgb", "native_rgba", "display")


def _blocks(a: np.ndarray, mode: str) -> np.ndarray:
    """(ny, nx, TILE*TILE*c) tiles; padding on top / right so the grid is anchored at the bottom row."""
    h, w = a.shape[:2]
    pad = (((-h) % TILE, 0), (0, (-w) % TILE)) + ((0, 0),) * (a.ndim - 2)
    p = np.pad(a, pad, mode=mode)
    ny, nx = p.shape[0] // TILE, p.shape[1] // TILE
    return p.reshape(ny, TILE, nx, TILE, -1).swapaxes(1, 2).reshape(ny, nx, -1)


def tile_psnr(ref: np.ndarray, dec: np.ndarray) -> np.ndarray:
    err = _blocks((dec.astype(np.float64) - ref.astype(np.float64)) ** 2, "constant").sum(axis=2)
    count = _blocks(np.ones(ref.shape[:2]), "constant").sum(axis=2) * ref.shape[2]
    with np.errstate(divide="ignore"):
        return 10 * np.log10(255.0 ** 2 * count / err)


def score(item: Item) -> dict[str, object]:
    ref_d, dec_d = read(item.display(None)), read(item.display(8))
    pairs = {"native_rgb": (read(item.native(None), "RGB"), read(item.native(8), "RGB")),
             "native_rgba": (read(item.native(None), "RGBA"), read(item.native(8), "RGBA")),
             "display": (ref_d, dec_d)}
    edge = _blocks(ref_d.astype(np.int16), "edge")
    content = (edge.max(axis=2) - edge.min(axis=2)) >= 2
    mask = gradient_mask(lab(ref_d))
    cover = _blocks(mask.astype(float), "constant").sum(axis=2) / _blocks(np.ones(mask.shape), "constant").sum(axis=2)
    smooth = cover >= 0.5
    row: dict[str, object] = dict(id=item.id, group=item.group, view=item.view, width=item.width,
                                  height=item.height, native_psnr=item.native_psnr, tiles=int(content.size),
                                  content=int(content.sum()), smooth=int(smooth.sum()))
    for name, (ref, dec) in pairs.items():
        assert ref.shape == dec.shape, (item.id, name, ref.shape, dec.shape)
        p = tile_psnr(ref, dec)
        row[f"min_{name}"] = float(p.min())
        for y in YS:
            bad = p < y
            row[f"bad_{name}_{y}"] = int(bad.sum())
            row[f"badc_{name}_{y}"] = int((bad & content).sum())
            row[f"bads_{name}_{y}"] = int((bad & smooth).sum())
    return row


def num(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return math.nan


def rank(values: dict[int, float], k: int) -> int | None:
    if k not in values or not math.isfinite(values[k]):
        return None
    return 1 + sum(v > values[k] for v in values.values() if math.isfinite(v))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    items = load_items()
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(score, items, chunksize=4))
    with (HERE / "tile-psnr.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by = {r["id"]: r for r in rows}
    step = {int(r["id"]): r for r in csv.DictReader((HERE / "new-step-v2.csv").open(encoding="utf-8-sig"))}
    out: dict[str, object] = {}
    out["known_bad28_by_view"] = {k: {v: f"{by[k][f'bad_{v}_28']}/{by[k]['tiles']}" for v in VIEWS}
                                  | dict(content=by[k]["content"], smooth=by[k]["smooth"]) for k in KNOWN}
    sub = [r for r in rows if r["width"] == r["height"] == 128 and r["native_psnr"] >= 35]
    out["subset_128_psnr35_n"] = len(sub)
    budget: dict[str, object] = {}
    for v in VIEWS:
        for y in YS:
            counts = sorted((r[f"bad_{v}_{y}"] for r in sub), reverse=True)
            x20 = counts[19]
            flagged = [r["id"] for r in sub if r[f"bad_{v}_{y}"] >= x20]
            budget[f"{v}@{y}"] = dict(x_tiles_for_top20=x20, flagged=len(flagged),
                                      known_in=sum(k in flagged for k in KNOWN),
                                      flagged_at_3_5_10pct=[sum(r[f"bad_{v}_{y}"] >= math.ceil(s * 256) for r in sub)
                                                            for s in (0.03, 0.05, 0.10)],
                                      known_counts={k: by[k][f"bad_{v}_{y}"] for k in KNOWN})
    out["subset_budget20"] = budget
    full: dict[str, object] = {}
    lp = {i: num(step[i]["L_p95_primary@8"]) for i in step}
    pool35 = [r for r in rows if r["native_psnr"] >= 35]
    for v in ("native_rgb", "display"):
        for y in (28, 30, 32):
            share_all = {r["id"]: r[f"bad_{v}_{y}"] / r["tiles"] for r in pool35}
            share_con = {r["id"]: r[f"badc_{v}_{y}"] / max(r["content"], 1) for r in pool35}
            count = {r["id"]: float(r[f"bad_{v}_{y}"]) for r in pool35}
            bad_total = sum(r[f"bad_{v}_{y}"] for r in pool35)
            bad_smooth = sum(r[f"bads_{v}_{y}"] for r in pool35)
            top_tile = sorted(share_con, key=lambda i: -share_con[i])[:20]
            top_step = sorted((i for i in share_con if math.isfinite(lp.get(i, math.nan))), key=lambda i: -lp[i])[:20]
            full[f"{v}@{y}"] = dict(
                n=len(pool35),
                known_rank_share_all={k: rank(share_all, k) for k in KNOWN},
                known_rank_share_content={k: rank(share_con, k) for k in KNOWN},
                known_rank_count={k: rank(count, k) for k in KNOWN},
                flagged_share_content_ge_3pct=sum(s >= 0.03 for s in share_con.values()),
                bad_tiles_in_smooth=bad_smooth / max(bad_total, 1),
                spearman_vs_L_p95_primary=spearman([share_con[i] for i in share_con], [lp.get(i, math.nan) for i in share_con]),
                spearman_vs_native_psnr=spearman([share_con[i] for i in share_con], [by[i]["native_psnr"] for i in share_con]),
                top20_overlap_with_L_p95_primary=len(set(top_tile) & set(top_step)))
    out["psnr_ge35_all_sizes"] = full
    content_all = sum(r["content"] for r in pool35)
    out["smooth_share_of_content_tiles_psnr35"] = sum(r["smooth"] for r in pool35) / content_all
    out["content_share_known"] = {k: round(by[k]["content"] / by[k]["tiles"], 3) for k in KNOWN}
    (HERE / "tile-psnr-summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
