"""Temporary full-reference gradient artifact probe. Scores rank pairs, with no human cutoff."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import correlate1d, label, uniform_filter, uniform_filter1d

HERE = Path(__file__).resolve().parent
MEDIA = HERE.parents[1] / "outputs/01a1eca4-b759-74d2-82d5-2d27a4db8e18/media"
BLOCKS = (4, 6, 8, 10, 12)
XYZ = np.array([[.4124564, .3575761, .1804375], [.2126729, .7151522, .0721750],
                [.0193339, .1191920, .9503041]]) / np.array([.95047, 1., 1.08883])[:, None]


def rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def lab(pixels: np.ndarray) -> np.ndarray:
    encoded = pixels.astype(np.float64) / 255
    linear = np.where(encoded < .04045, encoded/12.92, ((encoded+.055)/1.055)**2.4)
    xyz = linear @ XYZ.T
    d = 6/29
    f = np.where(xyz > d**3, np.cbrt(xyz), xyz/(3*d**2) + 4/29)
    return np.stack((116*f[...,1]-16, 500*(f[...,0]-f[...,1]), 200*(f[...,1]-f[...,2])), axis=-1)


def gradient_mask(src: np.ndarray) -> np.ndarray:
    mask = np.zeros(src.shape[:2], dtype=bool)
    for width in (7, 15):
        if min(mask.shape) < width:
            continue
        radius = width//2
        axis = np.arange(-radius, radius+1, dtype=float)
        var_xy = np.mean(axis**2)
        filt = axis / np.dot(axis, axis)
        mean = uniform_filter(src, (width, width, 1), mode="nearest")
        variance = np.sum(uniform_filter(src**2, (width, width, 1), mode="nearest")-mean**2, axis=2)
        dx = uniform_filter1d(correlate1d(src, filt, axis=1, mode="nearest"), width, axis=0, mode="nearest")
        dy = uniform_filter1d(correlate1d(src, filt, axis=0, mode="nearest"), width, axis=1, mode="nearest")
        slope_sq = np.sum(dx**2 + dy**2, axis=2)
        in_patch = np.s_[radius:-radius, radius:-radius]
        good = (var_xy*slope_sq >= .85*np.maximum(variance, 1e-9)) & ((width-1)**2*slope_sq >= 2**2)
        mask[in_patch] |= good[in_patch]
    return mask


def evaluate(src: np.ndarray, dst: np.ndarray, mask: np.ndarray, block: int) -> tuple[dict[str, float | None], np.ndarray]:
    damaged = np.zeros(mask.shape, dtype=float)
    errors = []
    seams = []
    line_scores = []
    run = 4  # Use the same native-pixel segment length across all tested footprints.
    best_line: tuple[float, int, int, int] | None = None
    for axis in (0, 1):
        r = np.swapaxes(src, axis, 0)
        d = np.swapaxes(dst, axis, 0)
        m = np.swapaxes(mask, axis, 0)
        support = m[1:] & m[:-1]
        grad_ref = np.diff(r, axis=0)
        grad_dec = np.diff(d, axis=0)
        discrepancy = np.linalg.norm(grad_dec-grad_ref, axis=2)
        errors.append(discrepancy[support])
        plane = np.swapaxes(damaged, axis, 0)
        np.maximum(plane[1:], np.where(support, discrepancy, 0), out=plane[1:])
        extra = np.maximum(0, np.linalg.norm(grad_dec, axis=2)-np.linalg.norm(grad_ref, axis=2))
        positions = np.arange(1, len(r))
        native = len(r)-positions if axis == 0 else positions
        for k in np.flatnonzero((native % block == 0) & (positions >= 2) & (positions <= len(r)-2)):
            valid = support[k] & support[k-1] & support[k+1]
            surplus = np.maximum(0, extra[k] - (extra[k-1]+extra[k+1])/2)
            seams.append(surplus[valid])
            if len(valid) >= run:
                segment = np.lib.stride_tricks.sliding_window_view(surplus,run)
                accepted = np.lib.stride_tricks.sliding_window_view(valid,run).all(axis=1)
                if accepted.any():
                    minima = np.where(accepted,np.min(segment,axis=1),-np.inf)
                    start = int(minima.argmax())
                    value = float(minima[start])
                    line_scores.append(value)
                    if best_line is None or value > best_line[0]:
                        best_line = (value,axis,int(k)+1,start)
    err = np.concatenate(errors)
    grid = np.concatenate(seams) if seams else np.array([])
    labels, ncomp = label(mask)
    largest = int(np.bincount(labels[mask]).max()) if ncomp else 0
    return {"gradient_area_pct": float(100*mask.mean()), "largest_component_px": largest,
            "gradient_change_p95": float(np.quantile(err,.95)) if err.size else None,
            "grid_excess_p95": float(np.quantile(grid,.95)) if grid.size else None,
            "continuous_seam": max(line_scores,default=None),
            "seam_x": (best_line[2] if best_line[1] else best_line[3]) if best_line else None,
            "seam_y": (best_line[3] if best_line[1] else best_line[2]) if best_line else None}, damaged


def synthetic() -> None:
    yy, xx = np.mgrid[:128,:128]
    signals = {"smooth": 40+xx, "hard_edge": np.where(xx < 64, 40, 150), "constant": 100+0*xx,
               "checker": 80 + 30*((xx+yy)%2)}
    cases = {}
    for key, source in signals.items():
        pixels = np.repeat(source[...,None],3,axis=2).astype("uint8")
        a = lab(pixels)
        m = gradient_mask(a)
        cases[key] = {}
        for kind, candidate in (("lossless",pixels),("steps_8", (pixels//8)*8)):
            stats, _ = evaluate(a,lab(candidate),m,8)
            cases[key][kind] = stats
        if key == "smooth":
            assert m.mean() > .8 and cases[key]["lossless"]["gradient_change_p95"] == 0
            assert cases[key]["steps_8"]["gradient_change_p95"] > 0
        else:
            assert not m.any(), (key,m.sum())
    (HERE/"synthetic.json").write_text(json.dumps(cases,indent=2),encoding="utf-8")
    print("Synthetic controls passed",flush=True)


def visuals(cases: list[tuple[str,str,str]], preset: str) -> None:
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.is_file():
        font_manager.fontManager.addfont(font)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font).get_name()
    figures, axes = plt.subplots(len(cases), 4, figsize=(10, 2.6*len(cases)), squeeze=False,
                                layout="constrained")
    rows = []
    for line,(asset,view,title) in enumerate(cases):
        folder = MEDIA / f"{int(asset):04}"
        original = rgb(folder/f"ref-{view}.png")
        src = lab(original)
        mask = gradient_mask(src)
        for b in BLOCKS:
            candidate = folder / (("" if b==8 else f"{b}x{b}-")+f"{preset}-{view}.png")
            decoded = rgb(candidate)
            metrics, heat = evaluate(src,lab(decoded),mask,b)
            rows.append({"sample": asset, "view": view, "preset": preset, "block": b, **metrics})
            if b == 8:
                scale = np.quantile(heat[(heat>0)&mask], .99) if np.any((heat>0)&mask) else 1
                show = np.zeros((*heat.shape,3))
                show[:,:,:] = np.array([.9,.32,.08])[None,None,:] * np.clip(heat[:,:,None]/max(scale,1e-9),0,1)
                panel = [original,np.where(mask[...,None], np.array([72,205,157])*.72+original*.28, original*.36).astype("uint8"),decoded,show]
                for col,a in enumerate(axes[line]):
                    a.imshow(panel[col],interpolation="nearest")
                    a.set_xticks([])
                    a.set_yticks([])
                    for spine in a.spines.values():
                        spine.set_visible(False)
                    if not line:
                        a.set_title(("原图","原图渐变候选区（绿）",f"8×8 · {preset}","梯度误差 / 最强接缝位置")[col], fontsize=11)
                if metrics["seam_x"] is not None:
                    axes[line,3].scatter(metrics["seam_x"],metrics["seam_y"],s=130,facecolors="none",edgecolors="cyan",linewidths=1)
                axes[line,0].set_ylabel(f"{title}\n#{int(asset):04}",fontsize=10)
    figures.savefig(HERE/"examples.png",dpi=150,facecolor="white")
    plt.close(figures)
    with (HERE/"pairs.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(rows,ensure_ascii=True),flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case",action="append",default=[],help="asset,view,title")
    ap.add_argument("--preset",default="medium")
    args = ap.parse_args()
    synthetic()
    if args.case:
        visuals([tuple(c.split(",",2)) for c in args.case],args.preset)


if __name__ == "__main__":
    main()
