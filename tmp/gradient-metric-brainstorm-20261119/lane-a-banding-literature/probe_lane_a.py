"""Lane A probe: display-magnified CAMBI and JND-normalised new-step contours on the 196 native 128x128 colour assets.

Read-only on the repository; writes only next to this file.
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import label, uniform_filter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIAG = ROOT / "tmp/gradient-diagnostics-20261119"
sys.path.insert(0, str(DIAG))
from probe import MEDIA, gradient_mask, lab  # noqa: E402

KNOWN = (615, 616, 617)
LUMA = np.array([.2126, .7152, .0722])


def load(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def chou_li_jnd(y: np.ndarray) -> np.ndarray:
    """Chou-Li 1995 full-band JND, eqs (1)-(5) as restated by Ghouti & Bouridane (EUSIPCO 2005).

    Approximation: bg is a 5x5 box mean and mg the largest of four 3x3 directional differences / 8,
    instead of the original 5x5 weighted operators (not available in the restating source).
    """
    bg = uniform_filter(y, 5, mode="nearest")
    p = np.pad(y, 1, mode="edge")
    gx = (p[:-2, 2:] + 2*p[1:-1, 2:] + p[2:, 2:] - p[:-2, :-2] - 2*p[1:-1, :-2] - p[2:, :-2]) / 8
    gy = (p[2:, :-2] + 2*p[2:, 1:-1] + p[2:, 2:] - p[:-2, :-2] - 2*p[:-2, 1:-1] - p[:-2, 2:]) / 8
    d1 = (p[1:-1, 2:] + 2*p[2:, 2:] + p[2:, 1:-1] - p[:-2, 1:-1] - 2*p[:-2, :-2] - p[1:-1, :-2]) / 8
    d2 = (p[1:-1, :-2] + 2*p[2:, :-2] + p[2:, 1:-1] - p[:-2, 1:-1] - 2*p[:-2, 2:] - p[1:-1, 2:]) / 8
    mg = np.max(np.abs(np.stack((gx, gy, d1, d2))), axis=0)
    f1 = mg * (bg*.0001 + .115) + (.5 - bg*.001)
    f2 = np.where(bg <= 127, 17*(1 - np.sqrt(np.clip(bg, 0, 127)/127)) + 3, 3/128*(bg - 127) + 3)
    return np.maximum(f1, f2)


def jnd_contours(ref: np.ndarray, dec: np.ndarray, mask: np.ndarray, block: int = 8) -> dict[str, float | int | None]:
    yr = ref.astype(float) @ LUMA
    yd = dec.astype(float) @ LUMA
    jnd = chou_li_jnd(yr)
    visible = np.zeros(yr.shape, dtype=bool)
    ratios: list[np.ndarray] = []
    grid_hits = 0
    total_hits = 0
    longest_run = 0
    for axis in (0, 1):
        r = np.swapaxes(yr, axis, 0)
        d = np.swapaxes(yd, axis, 0)
        m = np.swapaxes(mask, axis, 0)
        j = np.swapaxes(jnd, axis, 0)
        support = m[1:] & m[:-1]
        excess = np.abs(np.diff(d, axis=0) - np.diff(r, axis=0))
        ratio = excess / (.5*(j[1:] + j[:-1]))
        ratios.append(ratio[support])
        hit = support & (ratio > 1)
        plane = np.swapaxes(visible, axis, 0)
        plane[1:] |= hit
        plane[:-1] |= hit
        n = len(r)
        # pair k joins pixel k and k+1 (display order); display rows are flipped vs native storage,
        # but n is a multiple of the block for the 128x128 cohort so the boundary set is identical.
        on_grid = ((np.arange(n - 1) + 1) % block == 0)
        grid_hits += int(hit[on_grid].sum())
        total_hits += int(hit.sum())
        # longest straight run of supra-threshold pairs along the boundary direction
        for k in range(n - 1):
            row = hit[k]
            if not row.any():
                continue
            padded = np.concatenate(([0], row.astype(np.int8), [0]))
            edges = np.flatnonzero(np.diff(padded))
            longest_run = max(longest_run, int((edges[1::2] - edges[::2]).max()))
    allr = np.concatenate(ratios) if ratios else np.array([])
    if allr.size == 0:
        return dict(jnd_pairs=0, jnd_visible_frac=None, jnd_p95=None, jnd_longest_cc=None, jnd_longest_run=None, jnd_grid_share=None)
    labels, count = label(visible, structure=np.ones((3, 3)))
    longest_cc = int(np.bincount(labels.ravel())[1:].max()) if count else 0
    return dict(jnd_pairs=int(allr.size), jnd_visible_frac=float((allr > 1).mean()), jnd_p95=float(np.percentile(allr, 95)),
                jnd_longest_cc=longest_cc, jnd_longest_run=longest_run,
                jnd_grid_share=(grid_hits/total_hits) if total_hits else None)


def yuv_frame(rgb: np.ndarray, scale: int) -> bytes:
    if scale != 1:
        h, w = rgb.shape[:2]
        rgb = np.asarray(Image.fromarray(rgb).resize((w*scale, h*scale), Image.BILINEAR))
    y = np.rint(16 + 219*(rgb.astype(float) @ LUMA)/255).astype(np.uint8)
    return y.tobytes() + bytes([128])*(y.size//2)


def cambi_batch(pairs: list[tuple[np.ndarray, np.ndarray]], scale: int, options: str) -> list[dict[str, float]]:
    size = 128*scale
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        directory = Path(tmp)
        for column in (0, 1):
            with (directory/f"{column}.yuv").open("wb") as out:
                for pair in pairs:
                    out.write(yuv_frame(pair[column], scale))
        cmd = [shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-loglevel", "error"]
        for n in (1, 0):  # distorted first, reference second, matching metric/gradient-screen-50/banding.py
            cmd += ["-f", "rawvideo", "-pixel_format", "yuv420p", "-video_size", f"{size}x{size}", "-framerate", "1", "-i", f"{n}.yuv"]
        feature = "name=cambi\\:full_ref=true" + (f"\\:{options}" if options else "")
        cmd += ["-lavfi", f"libvmaf=feature='{feature}':log_fmt=json:log_path=out.json:n_threads=4", "-f", "null", "-"]
        subprocess.run(cmd, cwd=directory, check=True)
        frames = json.loads((directory/"out.json").read_bytes())["frames"]
    assert len(frames) == len(pairs)
    return [f["metrics"] for f in frames]


def ranks(rows: list[dict], field: str, subset: set[int] | None = None) -> dict[int, int | None]:
    pool = [r for r in rows if isinstance(r.get(field), (int, float)) and (subset is None or r["id"] in subset)]
    out: dict[int, int | None] = {}
    for k in KNOWN:
        row = next((r for r in pool if r["id"] == k), None)
        out[k] = None if row is None else 1 + sum(r[field] > row[field] for r in pool)
    out[0] = len(pool)  # denominator
    return out


def main() -> None:
    smoke = "--smoke" in sys.argv
    assets = json.loads((MEDIA.parent/"data.js").read_text(encoding="utf-8").removeprefix("window.REVIEW=").removesuffix(";"))["assets"]
    seam = {int(r["id"]): r for r in csv.DictReader((DIAG/"screen-128.csv").open(encoding="utf-8-sig"))}
    chosen = [a for a in assets if a["w"] == 128 and a["h"] == 128 and a["views"] != ["data"]]
    if smoke:
        chosen = [a for a in chosen if a["id"] in (*KNOWN, 587, 790)]
    rows: list[dict] = []
    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for a in chosen:
        idx = a["id"]
        view = "dark" if "dark" in a["views"] else "rgb"
        folder = MEDIA/f"{idx:04d}"
        ref = load(folder/f"ref-{view}.png")
        dec = load(folder/f"fastest-{view}.png")
        mask = gradient_mask(lab(ref))
        s = seam[idx]
        row = dict(id=idx, asset=a["asset"], view=view, **jnd_contours(ref, dec, mask),
                   continuous_seam=float(s["continuous_seam"]) if s["continuous_seam"] else None,
                   grid_excess_p95=float(s["grid_excess_p95"]) if s["grid_excess_p95"] else None,
                   flip_p99=float(s["flip_p99"]), psnr_native=float(s["psnr_native"]))
        rows.append(row)
        pairs.append((ref, dec))
    for scale, options, tag in ((1, "", "x1"), (4, "", "x4"), (8, "", "x8"), (4, "max_log_contrast=5", "x4_mlc5")):
        if scale == 1:
            continue  # official implementation rejects 128x128 (CAMBI_MIN_WIDTH_HEIGHT=216)
        res = cambi_batch(pairs, scale, options)
        for row, r in zip(rows, res, strict=True):
            row[f"cambi_fr_{tag}"] = r["cambi_full_reference"]
            row[f"cambi_src_{tag}"] = r["cambi_source"]
            row[f"cambi_dis_{tag}"] = r.get("Cambi_feature_cambi_score", r.get("cambi"))
    seam_valid = {r["id"] for r in rows if r["continuous_seam"] is not None}
    fields = ["jnd_visible_frac", "jnd_p95", "jnd_longest_cc", "jnd_longest_run", "cambi_fr_x4", "cambi_fr_x8",
              "cambi_fr_x4_mlc5", "continuous_seam", "grid_excess_p95", "flip_p99"]
    summary = {"assets": len(rows), "known": KNOWN,
               "rank_all": {f: ranks(rows, f) for f in fields},
               "rank_seam_valid_set": {f: ranks(rows, f, seam_valid) for f in fields},
               "top10": {f: [(r["id"], r["asset"].split("/Texture/")[-1] if "/Texture/" in r["asset"] else r["asset"], r[f])
                             for r in sorted((r for r in rows if isinstance(r.get(f), (int, float))), key=lambda r: -r[f])[:10]]
                         for f in fields},
               "known_rows": [r for r in rows if r["id"] in KNOWN]}
    name = "smoke" if smoke else "probe"
    with (HERE/f"{name}-rows.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (HERE/f"{name}-summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("assets", "rank_all", "rank_seam_valid_set")}))


if __name__ == "__main__":
    main()
