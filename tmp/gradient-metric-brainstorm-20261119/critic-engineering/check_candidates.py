"""Reviewer E check: score all 20 archived Unity candidates with seam / step metrics and replay the
first-valid label rule with an added gate. Read-only on the repo; writes only next to this file."""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import numpy as np  # noqa: E402
from numpy.lib.stride_tricks import sliding_window_view  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, "E:/ASTC_Compression/metric/gradient-screen")
sys.path.insert(0, str(HERE.parent / "lane-c-astc-design"))
from seam_metric import evaluate, gradient_mask, lab  # noqa: E402
from astc_modes import read_astc  # noqa: E402

MANIFEST = Path("E:/ASTC_Compression/tmp/multimetric-review-20261118/population/fixed8_manifest.json")
BLOCKS = (12, 10, 8, 6)
PRESETS = ("fastest", "fast", "medium", "thorough", "exhaustive")
JND = 3.0


def s2l(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64) / 255
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def l2s(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return 255 * np.where(x <= .0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - .055)


def view(px: np.ndarray, alpha: bool, bg: float = 64.) -> np.ndarray:
    p = px.astype(np.float64)
    if not alpha:
        return p[..., :3]
    a = p[..., 3:4] / 255
    return l2s(a * s2l(p[..., :3]) + (1 - a) * s2l(np.full(3, bg)))


def rgba(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA"))


def b3(lr: np.ndarray, ld: np.ndarray, mask: np.ndarray) -> tuple[float | None, int]:
    """Vectorised port of lane C B3 (16 px windows, stride 4, monotone ramps with TV>=4)."""
    vals = []
    for r_, d_, m_ in ((lr, ld, mask), (lr.T, ld.T, mask.T)):
        w = r_.shape[1]
        n = len(range(0, w - 16, 4))
        if n <= 0:
            continue
        dr = sliding_window_view(np.diff(r_, axis=1), 15, axis=1)[:, ::4][:, :n]
        dd = sliding_window_view(np.diff(d_, axis=1), 15, axis=1)[:, ::4][:, :n]
        mk = sliding_window_view(m_, 16, axis=1)[:, ::4][:, :n].all(axis=2)
        tv = np.abs(dr).sum(axis=2)
        keep = mk & (tv >= 4) & (np.abs(dr.sum(axis=2)) >= .8 * tv)
        cr = np.abs(dr).max(axis=2) / np.maximum(tv, 1e-12)
        cd = np.abs(dd).max(axis=2) / np.maximum(np.abs(dd).sum(axis=2), 1e-9)
        vals.append((np.maximum(0., cd - cr) * tv)[keep])
    v = np.concatenate(vals) if vals else np.array([])
    return (float(np.quantile(v, .95)) if v.size else None), int(v.size)


def plane_amp(values: np.ndarray) -> float:
    hh, ww = values.shape
    yy, xx = np.mgrid[:hh, :ww]
    a = np.column_stack((np.ones(values.size), yy.ravel(), xx.ravel()))
    coef, *_ = np.linalg.lstsq(a, values.ravel(), rcond=None)
    fit = a @ coef
    return float(fit.max() - fit.min())


def e1(astc: Path, lstar: np.ndarray, mask: np.ndarray) -> tuple[float | None, int, int]:
    b, _, w, h, bl = read_astc(astc)
    steps = []
    for j, row in enumerate(bl):
        for i, blk in enumerate(row):
            y0, y1 = max(0, h - (j + 1) * b), h - j * b
            m = mask[y0:y1, i * b:(i + 1) * b]
            if m.size == 0 or m.mean() < .5 or min(m.shape) < 3:
                continue
            q = blk["weight_levels"] if blk["kind"] == "normal" else 256
            steps.append(plane_amp(lstar[y0:y1, i * b:(i + 1) * b]) / (q - 1))
    s = np.asarray(steps)
    return (float(np.quantile(s, .9)) if s.size else None), int((s >= JND).sum()), int(s.size)


def load(ids: list[int] | None, pop128: bool) -> list[dict]:
    rows = [r for r in json.loads(MANIFEST.read_bytes()) if r["preset"] == "fastest"]
    if pop128:
        return [r for r in rows if r["width"] == r["height"] == 128 and r["srgb"] and not r["is_normal"]]
    return [r for r in rows if r["validation_index"] in set(ids or [])]


def score_image(r: dict) -> list[dict]:
    folder = Path(r["decoded_path"]).parent
    alpha = bool(r["need_alpha"]) and not bool(r["alpha_constant"])
    ref_px = rgba(Path(r["reference_path"]))
    src = lab(view(ref_px, alpha))
    mask = gradient_mask(src)
    cands = {(c["block"], c["preset"]): c for c in json.loads((folder / "candidates.json").read_bytes())}
    out = []
    for b in BLOCKS:
        for p in PRESETS:
            dec = lab(view(rgba(folder / f"{b}x{b}_{p}.png"), alpha))
            res, _ = evaluate(src, dec, mask, b)
            b3v, b3n = b3(src[..., 0], dec[..., 0], mask)
            e1v, e1n, e1blocks = e1(folder / f"{b}x{b}_{p}.astc", src[..., 0], mask)
            c = cands[(b, p)]
            out.append({"id": r["validation_index"], "w": r["width"], "h": r["height"], "alpha": int(alpha),
                        "group": r["group"][-40:], "gt": f"{r['gt_block']}_{r['gt_preset']}",
                        "t_psnr": r["target_psnr_db"], "t_ms": r["target_ms_ssim_db"], "block": b, "preset": p,
                        "payload": c["payload_bytes"], "psnr": c["metrics"]["psnr"], "ms": c["metrics"]["ms_ssim_db"],
                        "encode_s": c["timings"]["encode_seconds"],
                        "area_pct": res["gradient_area_pct"], "seam": res["continuous_seam"],
                        "grid_p95": res["grid_excess_p95"], "change_p95": res["gradient_change_p95"],
                        "b3": b3v, "b3_n": b3n, "e1_p90": e1v, "e1_ge_jnd": e1n, "e1_blocks": e1blocks})
    return out


def main() -> None:
    pop = "--pop128" in sys.argv
    ids = [int(a) for a in sys.argv[1:] if a.isdigit()]
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "smoke"
    rows = []
    t0 = time.perf_counter()
    for r in load(ids, pop):
        rows += score_image(r)
    with (HERE / f"candidates-{tag}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(rows)} rows, {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
