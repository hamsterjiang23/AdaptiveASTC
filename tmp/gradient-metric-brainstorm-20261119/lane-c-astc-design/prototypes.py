"""Lane C prototypes: original-only ASTC risk (A*) and full-reference in-block damage (B*) metrics.

Display images: outputs/.../media (dark view for alpha assets, rgb for opaque). Native RGBA: fixed8 manifest paths.
Grid phase: native block row j covers display rows [H-(j+1)b, H-jb) (verified with void-extent blocks, mechanism.json).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import sobel

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import MEDIA, assets, composite, gradient_mask, lab, native_paths, rgb, rgba, view_of  # noqa: E402

POSITIVE = [615, 616, 617]
CONTROLS = [207, 580, 608, 363, 867, 384, 630, 449, 16, 62, 790, 350, 602]
JND = 3.0  # L* units used as a visibility unit (assumption, not calibrated)


def blocks(h: int, w: int, b: int):
    j = 0
    while j * b < h:
        y0, y1 = max(0, h - (j + 1) * b), h - j * b
        for i in range(0, w, b):
            yield y0, y1, i, min(w, i + b)
        j += 1


def plane(values: np.ndarray) -> tuple[np.ndarray, float]:
    """Least-squares plane over a block; returns slope (dy, dx) per pixel and fitted range."""
    hh, ww = values.shape
    yy, xx = np.mgrid[:hh, :ww]
    a = np.column_stack((np.ones(values.size), yy.ravel(), xx.ravel()))
    coef, *_ = np.linalg.lstsq(a, values.ravel(), rcond=None)
    fit = a @ coef
    return coef[1:], float(fit.max() - fit.min())


def full_reference(ref_rgb: np.ndarray, dec_rgb: np.ndarray, mask: np.ndarray, b: int) -> dict[str, float | int | None]:
    lr, ld = lab(ref_rgb)[..., 0], lab(dec_rgb)[..., 0]
    h, w = lr.shape
    flat, poster, amps = [], [], []
    for y0, y1, x0, x1 in blocks(h, w, b):
        m = mask[y0:y1, x0:x1]
        if m.size < 4 or m.mean() < .5 or min(y1 - y0, x1 - x0) < 3:
            continue
        sr, ar = plane(lr[y0:y1, x0:x1])
        if ar < 2:
            continue
        sd, _ = plane(ld[y0:y1, x0:x1])
        keep = float(np.dot(sd, sr) / max(np.dot(sr, sr), 1e-12))
        flat.append(max(0., 1 - keep) * ar)  # B2: lost in-block ramp amplitude (L*)
        nr = len(np.unique(np.round(lr[y0:y1, x0:x1][m])))
        nd = len(np.unique(np.round(ld[y0:y1, x0:x1][m])))
        poster.append(max(0., 1 - nd / nr) if nr >= 4 else 0.)  # B1: distinct-level collapse
        amps.append(ar)
    flat_a, poster_a, amp_a = map(np.asarray, (flat, poster, amps))
    # B3: grid-agnostic step concentration along rows / columns, windows of 16 px, stride 4.
    conc = []
    for arr_r, arr_d, mk in ((lr, ld, mask), (lr.T, ld.T, mask.T)):
        for r in range(arr_r.shape[0]):
            for s in range(0, arr_r.shape[1] - 16, 4):
                if not mk[r, s:s + 16].all():
                    continue
                dr, dd = np.diff(arr_r[r, s:s + 16]), np.diff(arr_d[r, s:s + 16])
                tv = np.abs(dr).sum()
                if tv < 4 or abs(dr.sum()) < .8 * tv:  # monotone, substantial ramp only
                    continue
                cr = np.abs(dr).max() / tv
                cd = np.abs(dd).max() / max(np.abs(dd).sum(), 1e-9)
                conc.append(max(0., cd - cr) * tv)
    conc_a = np.asarray(conc)
    # B4: axis concentration of gradient orientations inside the mask (magnitude weighted).
    def axis_fraction(img: np.ndarray) -> float:
        gy, gx = sobel(img, 0), sobel(img, 1)
        mag = np.hypot(gx, gy)[mask]
        ang = np.degrees(np.arctan2(gy, gx))[mask] % 90
        near = (ang < 11.25) | (ang > 78.75)
        return float((mag * near).sum() / max(mag.sum(), 1e-9))
    return {"grad_blocks": int(len(flat_a)),
            "B1_poster_frac": float(np.mean((poster_a >= .5) & (amp_a >= 4))) if len(flat_a) else None,
            "B2_flat_p90": float(np.quantile(flat_a, .9)) if len(flat_a) else None,
            "B2_flat_area": float(np.mean(flat_a >= JND)) if len(flat_a) else None,
            "B3_conc_p95": float(np.quantile(conc_a, .95)) if len(conc_a) else None,
            "B3_segments": int(len(conc_a)),
            "B4_axis_shift": axis_fraction(ld) - axis_fraction(lr) if mask.sum() >= 32 else None}


def original_only(native: np.ndarray, view: str, disp_mask: np.ndarray, b: int, background: float = 64.) -> dict[str, float | None]:
    """A1: alpha/RGB competition under a shared weight plane; A2: in-block ramp amplitude in L*."""
    h, w = native.shape[:2]
    disp = composite(native, background if view == "dark" else None)
    lstar = lab(disp)[..., 0]
    a1, a2 = [], []
    for y0, y1, x0, x1 in blocks(h, w, b):
        m = disp_mask[y0:y1, x0:x1]
        blk = native[y0:y1, x0:x1].reshape(-1, 4).astype(float)
        if view == "dark":
            span = blk[:, 3].max() - blk[:, 3].min()
            if span >= 8:
                x = blk - blk.mean(0)
                _, _, vt = np.linalg.svd(x, full_matrices=False)
                score = x @ vt[0]
                ca = np.corrcoef(score, blk[:, 3])[0, 1] if score.std() > 1e-9 else 0.
                # visible amplitude of the alpha ramp: L* of the block mean colour at alpha min vs max
                mean_rgb = blk[blk[:, 3] >= np.median(blk[:, 3]), :3].mean(0)
                lo = composite(np.r_[mean_rgb, blk[:, 3].min()][None, None], background)
                hi = composite(np.r_[mean_rgb, blk[:, 3].max()][None, None], background)
                vis = abs(lab(hi)[0, 0, 0] - lab(lo)[0, 0, 0])
                a1.append((1 - ca ** 2) * vis)
        if m.size and m.mean() >= .5 and min(y1 - y0, x1 - x0) >= 3:
            _, amp = plane(lstar[y0:y1, x0:x1])
            a2.append(amp)
    a1_a, a2_a = np.asarray(a1), np.asarray(a2)
    return {"A1_alpha_competition_max": float(a1_a.max()) if len(a1_a) else None,
            "A1_blocks_ge_jnd": int((a1_a >= JND).sum()) if len(a1_a) else 0,
            "A2_ramp_p90": float(np.quantile(a2_a, .9)) if len(a2_a) else None,
            "A2_q3_step_blocks": int((a2_a / 2 >= JND).sum()) if len(a2_a) else 0,
            "A2_grad_blocks": int(len(a2_a))}


def main() -> None:
    rows = []
    seam = {int(r["id"]): r for r in csv.DictReader(open(Path("E:/ASTC_Compression/tmp/gradient-diagnostics-20261119/screen-128.csv"), encoding="utf-8-sig"))}
    for idx in POSITIVE + CONTROLS:
        view = view_of(idx)
        folder = MEDIA / f"{idx:04d}"
        ref = rgb(folder / f"ref-{view}.png")
        mask = gradient_mask(lab(ref))
        native_ref, _ = native_paths(idx, "fastest")
        nat = rgba(native_ref)
        variants = [("8x8", "fastest", 8)]
        if idx in POSITIVE:
            variants += [("8x8", "medium", 8), ("8x8", "exhaustive", 8), ("6x6", "fastest", 6), ("4x4", "fastest", 4),
                         ("12x12", "fastest", 12)]
        for tag, preset, b in variants:
            name = (f"{preset}-{view}.png" if tag == "8x8" else f"{tag}-{preset}-{view}.png")
            dec = rgb(folder / name)
            fr = full_reference(ref, dec, mask, b)
            oo = original_only(nat, view, mask, b)
            native = next(r for r in assets()[idx]["rows"] if r["preset"] == preset and r["view"] == view) if tag == "8x8" else {}
            rows.append({"id": idx, "group": "positive" if idx in POSITIVE else "control", "view": view, "block": tag,
                         "preset": preset, "native_psnr": native.get("psnr"), "fp99": native.get("fp99"),
                         "continuous_seam_8x8_fastest": seam.get(idx, {}).get("continuous_seam") if (tag, preset) == ("8x8", "fastest") else None,
                         **fr, **oo, "asset": assets()[idx]["asset"][-48:]})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    with (HERE / "prototype-results.csv").open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


if __name__ == "__main__":
    main()
