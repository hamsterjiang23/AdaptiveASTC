"""predicted-block-step-prescreen: original-only risk that an ASTC block flattens a ramp into visible steps.

For every block of the bottom-anchored ASTC grid that lies >= 50% in the reference gradient mask, a Lab plane
is fitted and A = largest corner-to-corner Delta E76 of the plane.  q_eff(b, preset, A-bin) is the median weight
level count the archived encoder actually used (read from the .astc headers of a fixed-seed 30% calibration
split), so h = A / max(q_eff - 1, 1) is the predicted in-block step.  Image fields at each block size:
R_n (blocks with h >= 3), R_frac, R_cc (largest 4-connected cluster), h_p90.  Alpha images: max over the
0/64/192/255 backgrounds.  Calibration also stores block-level checks against the measured decoded step.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import numpy as np  # noqa: E402
from scipy.ndimage import label  # noqa: E402

from harness import KNOWN, ROOT, Item, Row, load_items, read, spearman  # noqa: E402
from new_step_v2 import composite, display_path, gradient_mask, lab  # noqa: E402

sys.path.insert(0, str(ROOT / "tmp/gradient-metric-brainstorm-20261119/lane-c-astc-design"))
from astc_modes import read_astc  # noqa: E402

HERE = Path(__file__).resolve().parent
BLOCKS = (6, 8, 10, 12)
PRESET = "fastest"
COVER, STEP, VOID_LEVELS = 0.5, 3.0, 256
SEED, CAL_SHARE = 20261119, 0.30
CONFIG = dict(blocks=BLOCKS, preset=PRESET, cover=COVER, step=STEP, void_levels=VOID_LEVELS, seed=SEED,
              cal_share=CAL_SHARE, bins="A quartiles of calibration gradient blocks, per block size")


def split(items: list[Item]) -> tuple[set[int], set[int]]:
    pool = sorted(i.id for i in items if i.id not in KNOWN)
    order = np.random.default_rng(SEED).permutation(pool)
    cal = {int(i) for i in order[:round(CAL_SHARE * len(items))]}
    return cal, {i.id for i in items} - cal


def views(item: Item) -> dict[int | None, np.ndarray]:
    if item.view == "rgb":
        return {None: read(display_path(item, "rgb", None, PRESET))}
    return {0: composite(item.native(None), 0), 64: read(display_path(item, "dark", None, PRESET)),
            192: read(display_path(item, "light", None, PRESET)), 255: composite(item.native(None), 255)}


def tiles(a: np.ndarray, b: int, fill: object) -> np.ndarray:
    """(ny, nx, b*b, ...) tiles; tile row t is native ASTC block row ny-1-t (grid anchored at the bottom)."""
    h, w = a.shape[:2]
    pad = ((((-h) % b), 0), (0, (-w) % b)) + ((0, 0),) * (a.ndim - 2)
    p = np.pad(a, pad, constant_values=fill)
    ny, nx = p.shape[0] // b, p.shape[1] // b
    return p.reshape(ny, b, nx, b, *a.shape[2:]).swapaxes(1, 2).reshape(ny, nx, b * b, *a.shape[2:])


def block_fit(lr: np.ndarray, mask: np.ndarray, b: int) -> dict[str, np.ndarray]:
    """Gradient-block flags and plane amplitudes (Lab vector A and L*-only A_L) on the (ny, nx) block grid."""
    h, w = mask.shape
    valid = tiles(np.ones((h, w), bool), b, False)
    ext_u = valid.reshape(*valid.shape[:2], b, b).any(axis=2).sum(axis=2)
    ext_v = valid.reshape(*valid.shape[:2], b, b).any(axis=3).sum(axis=2)
    cover = tiles(mask, b, False).sum(axis=2) / valid.sum(axis=2)
    grad = (cover >= COVER) & (np.minimum(ext_u, ext_v) >= 3)
    amp = np.zeros(grad.shape)
    amp_l = np.zeros(grad.shape)
    if grad.any():
        wgt = valid[grad].astype(np.float64)
        val = tiles(lr, b, 0.0)[grad]  # (k, b*b, 3)
        v, u = np.divmod(np.arange(b * b, dtype=np.float64), b)

        def total(z: np.ndarray | float) -> np.ndarray:
            return np.sum(wgt * z, axis=1)

        su, sv, suv = total(u), total(v), total(u * v)
        normal = np.stack([np.stack([total(1.0), su, sv], 1), np.stack([su, total(u * u), suv], 1),
                           np.stack([sv, suv, total(v * v)], 1)], 1)
        rhs = np.stack([np.einsum("kp,kpc->kc", wgt, val), np.einsum("kp,kpc->kc", wgt * u, val),
                        np.einsum("kp,kpc->kc", wgt * v, val)], 1)  # (k, 3 terms, 3 channels)
        coef = np.linalg.solve(normal, rhs)
        du = coef[:, 1] * (ext_u[grad] - 1)[:, None]
        dv = coef[:, 2] * (ext_v[grad] - 1)[:, None]
        diag = np.maximum(np.linalg.norm(du + dv, axis=1), np.linalg.norm(du - dv, axis=1))
        amp[grad] = diag
        amp_l[grad] = np.maximum(np.abs(du[:, 0] + dv[:, 0]), np.abs(du[:, 0] - dv[:, 0]))
    return dict(grad=grad, A=amp, A_L=amp_l)


def measured_step(ld: np.ndarray, b: int) -> np.ndarray:
    """Largest adjacent Delta E76 between decoded pixels inside each block (no step crosses a block edge)."""
    h, w = ld.shape[:2]
    t = tiles(ld, b, np.nan).reshape(*tiles(ld[..., 0], b, np.nan).shape[:2], b, b, 3)
    with np.errstate(invalid="ignore"):
        dx = np.linalg.norm(np.diff(t, axis=3), axis=4)
        dy = np.linalg.norm(np.diff(t, axis=2), axis=4)
    return np.maximum(np.nanmax(dx.reshape(*dx.shape[:2], -1), axis=2, initial=0.0),
                      np.nanmax(dy.reshape(*dy.shape[:2], -1), axis=2, initial=0.0))


def astc_levels(path: Path, ny: int, nx: int) -> tuple[np.ndarray, np.ndarray]:
    """Weight levels per block on the display tile grid (void-extent = 256); also flags void-extent blocks."""
    b, _, w, h, rows = read_astc(path)
    levels = np.array([[blk["weight_levels"] if blk["kind"] == "normal" else VOID_LEVELS for blk in row]
                       for row in rows], dtype=float)[::-1]
    void = np.array([[blk["kind"] == "void" for blk in row] for row in rows])[::-1]
    assert levels.shape == (ny, nx), (path, levels.shape, ny, nx)
    return levels, void


def calibrate_one(item: Item) -> dict[int, dict[str, np.ndarray]]:
    """Primary view only (RGB or the 64 composite): weight levels do not depend on the display background."""
    view = "rgb" if item.view == "rgb" else "dark"
    lr = lab(read(display_path(item, view, None, PRESET)))
    mask = gradient_mask(lr)
    out = {}
    for b in BLOCKS:
        fit = block_fit(lr, mask, b)
        g = fit["grad"]
        levels, void = astc_levels(item.decoded_dir / f"{b}x{b}_{PRESET}.astc", *g.shape)
        step = measured_step(lab(read(display_path(item, view, b, PRESET))), b)
        ref_step = measured_step(lr, b)
        out[b] = dict(A=fit["A"][g], A_L=fit["A_L"][g], q=levels[g], void=void[g], step=step[g],
                      excess=step[g] - ref_step[g])
    return out


def table(values: np.ndarray, levels: np.ndarray) -> dict[str, list[float]]:
    edges = np.quantile(values, [.25, .5, .75]) if values.size else np.zeros(3)
    bins = np.searchsorted(edges, values, side="right")
    medians = [float(np.median(levels[bins == k])) if np.any(bins == k) else float(np.median(levels)) for k in range(4)]
    return dict(edges=[float(e) for e in edges], q_eff=medians,
                count=[int(np.sum(bins == k)) for k in range(4)])


def lookup(tab: dict[str, list[float]], values: np.ndarray) -> np.ndarray:
    return np.asarray(tab["q_eff"])[np.searchsorted(np.asarray(tab["edges"]), values, side="right")]


def risk(fit: dict[str, np.ndarray], tabs: dict[str, dict], key: str) -> Row:
    g = fit["grad"]
    if not g.any():
        return dict(R_n=0, R_frac=0.0, R_cc=0, h_p90=0.0, grad_blocks=0, no_gradient=1)
    amp = fit[key]
    h = np.zeros(g.shape)
    h[g] = amp[g] / np.maximum(lookup(tabs[key], amp[g]) - 1, 1)
    hot = g & (h >= STEP)
    labels, n = label(hot)
    largest = int(np.bincount(labels[hot]).max()) if n else 0
    return dict(R_n=int(hot.sum()), R_frac=float(hot.sum() / g.sum()), R_cc=largest,
                h_p90=float(np.quantile(h[g], .9)), grad_blocks=int(g.sum()), no_gradient=0)


def score_one(tables: dict[int, dict[str, dict]], item: Item) -> Row:
    start = time.perf_counter()
    row: Row = dict(id=item.id, asset=item.asset, group=item.group, view=item.view, width=item.width,
                    height=item.height, native_psnr=item.native_psnr)
    per_view: dict[int, list[tuple[object, Row, Row]]] = {b: [] for b in BLOCKS}
    for bg, px in views(item).items():
        lr = lab(px)
        mask = gradient_mask(lr)
        row["mask_frac" if bg in (None, 64) else f"mask_frac_bg{bg}"] = float(mask.mean())
        for b in BLOCKS:
            fit = block_fit(lr, mask, b)
            per_view[b].append((bg, risk(fit, tables[b], "A"), risk(fit, tables[b], "A_L")))
    for b, entries in per_view.items():
        bg, best, _ = max(entries, key=lambda e: (e[1]["R_cc"], e[1]["R_n"]))
        for field, value in best.items():
            row[f"{field}@{b}"] = value
        row[f"R_bg@{b}"] = "rgb" if bg is None else bg
        row[f"R_n_max@{b}"] = max(e[1]["R_n"] for e in entries)
        row[f"h_p90_max@{b}"] = max(e[1]["h_p90"] for e in entries)
        lum = max((e[2] for e in entries), key=lambda r: (r["R_cc"], r["R_n"]))
        row[f"R_cc_L@{b}"], row[f"R_n_L@{b}"] = lum["R_cc"], lum["R_n"]
    row["seconds"] = time.perf_counter() - start
    return row


def calibrate(items: list[Item], cal: set[int], workers: int) -> tuple[dict[int, dict[str, dict]], dict[str, object]]:
    chosen = [i for i in items if i.id in cal]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        parts = list(pool.map(calibrate_one, chosen, chunksize=2))
    tables: dict[int, dict[str, dict]] = {}
    checks: dict[str, object] = {}
    for b in BLOCKS:
        cat = {k: np.concatenate([p[b][k] for p in parts]) for k in ("A", "A_L", "q", "void", "step", "excess")}
        tables[b] = {key: table(cat[key], cat["q"]) for key in ("A", "A_L")}
        h_tab = cat["A"] / np.maximum(lookup(tables[b]["A"], cat["A"]) - 1, 1)
        h_oracle = cat["A"] / np.maximum(cat["q"] - 1, 1)
        checks[str(b)] = dict(
            blocks=int(cat["A"].size), void_share=float(cat["void"].mean()),
            level_hist={str(int(k)): int(v) for k, v in zip(*np.unique(cat["q"], return_counts=True))},
            share_q_le4=float(np.mean(cat["q"] <= 4)),
            spearman_h_table_vs_step=spearman(h_tab, cat["step"]),
            spearman_h_oracle_vs_step=spearman(h_oracle, cat["step"]),
            spearman_A_vs_step=spearman(cat["A"], cat["step"]),
            spearman_h_table_vs_excess=spearman(h_tab, cat["excess"]),
            spearman_h_oracle_vs_excess=spearman(h_oracle, cat["excess"]),
            excess_ge3_share=float(np.mean(cat["excess"] >= STEP)),
            precision_excess_ge3=float(np.mean(cat["excess"][h_tab >= STEP] >= STEP)) if np.any(h_tab >= STEP) else None,
            recall_excess_ge3=float(np.mean(h_tab[cat["excess"] >= STEP] >= STEP)) if np.any(cat["excess"] >= STEP) else None,
            spearman_A_vs_levels=spearman(cat["A"], cat["q"]),
            flagged_share=float(np.mean(h_tab >= STEP)),
            step_ge3_share=float(np.mean(cat["step"] >= STEP)),
            precision_step_ge3=float(np.mean(cat["step"][h_tab >= STEP] >= STEP)) if np.any(h_tab >= STEP) else None,
            recall_step_ge3=float(np.mean(h_tab[cat["step"] >= STEP] >= STEP)) if np.any(cat["step"] >= STEP) else None)
    return tables, checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    items = load_items()
    cal, hold = split(items)
    start = time.perf_counter()
    if args.smoke:
        sample = sorted(cal)[:12]
        tables, checks = calibrate(items, set(sample), args.workers)
        rows = [score_one(tables, i) for i in items if i.id in KNOWN + (790, 602, 207)]
        for r in rows:
            print(r["id"], {k: r[k] for k in r if k.startswith(("R_cc@", "R_n@", "R_bg@", "h_p90@"))}, round(r["seconds"], 2))
        print(json.dumps(dict(tables={str(b): t for b, t in tables.items()}, checks=checks), indent=1))
        return
    tables, checks = calibrate(items, cal, args.workers)
    calibration_s = time.perf_counter() - start
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(partial(score_one, tables), items, chunksize=4))
    for r in rows:
        r["split"] = "calibration" if r["id"] in cal else "holdout"
    import csv

    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (HERE / "prescreen.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (HERE / "prescreen-calibration.json").write_text(json.dumps(dict(
        config=CONFIG, calibration_ids=sorted(cal), holdout_ids=sorted(hold),
        tables={str(b): t for b, t in tables.items()}, checks=checks, calibration_s=calibration_s,
        scoring_s=time.perf_counter() - start - calibration_s), indent=1), encoding="utf-8")
    print(json.dumps(checks, indent=1))


if __name__ == "__main__":
    main()
