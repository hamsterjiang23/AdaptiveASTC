"""Lane B probe: industry encoder weightings re-used as detectors on the 196 native 128x128 colour textures.

Read-only on repo data; writes only next to this file.
Metrics (all on native RGBA, 8x8 fastest decode, 128x128 so grid phase is flip-invariant):
  ert_smooth_wmse      bc7enc_rdo/ERT smooth-block MSE scaling (ert.cpp L342-346) at the ASTC 8x8 footprint
  ert_smooth_share     share of total weighted SSE that sits in blocks with scale>1 (sigma_max<18)
  ultrasmooth_blocks   bc7enc_rdo compute_block_mse_scales rule (rdo_bc_encoder.cpp L31-175), 4x4 blocks, original only
  deblock_wpsnr        astcenc 3.3 -b 1.8 per-texel weight pow(dist,1.8) (astcenc_compress_symbolic.cpp L940-968)
  activity_wpsnr       astcenc 3.3 -v weight 1/(1+50*sigma^2), radius 3 (astcenc_entry.cpp L671-676; compress_symbolic L1055-1100)
  blend_bound_rmse     worst-case over-background composite error, background in {0,1} linear (derivation in notes.md)
  blend_bound_smooth   same, ERT smooth-weighted
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import label, uniform_filter

ROOT = Path("E:/ASTC_Compression")
HERE = Path(__file__).resolve().parent
SCREEN = ROOT / "tmp/gradient-diagnostics-20261119/screen-128.csv"
NATIVE = ROOT / "tmp/multimetric-review-20261118/blocks/source/candidates.jsonl"
KNOWN = (615, 616, 617)
B = 8


def load(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA")).astype(np.float64)


def lin(c: np.ndarray) -> np.ndarray:
    c = c / 255.0
    return np.where(c < .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def block_view(a: np.ndarray, b: int) -> np.ndarray:
    h, w = a.shape[:2]
    return a[: h // b * b, : w // b * b].reshape(h // b, b, w // b, b, -1).swapaxes(1, 2)


def ert_scale(ref: np.ndarray, chans: list[int], b: int, max_scale: float = 10.0, t: float = 18.0) -> np.ndarray:
    blocks = block_view(ref[..., chans], b)
    sd = blocks.reshape(*blocks.shape[:2], -1, len(chans)).std(axis=2).max(axis=-1)
    yl = np.clip(sd / t, 0, 1) ** 2
    return max_scale + (1.0 - max_scale) * yl  # lerp(max_scale, 1, yl)


def ultrasmooth(ref: np.ndarray) -> int:
    """bc7enc_rdo compute_block_mse_scales on 4x4 RGB blocks; returns #ultrasmooth blocks."""
    blocks = block_view(ref[..., :3], 4)
    flat = blocks.reshape(*blocks.shape[:2], 16, 3)
    sd = flat.std(axis=2).max(axis=-1)
    luma = (flat[..., 0] * 13938 + flat[..., 1] * 46869 + flat[..., 2] * 4729 + 32768) / 65536.0
    y_avg = luma.mean(axis=2)
    yl = np.clip(sd / 2.9, 0, 1) ** 2
    yl[(y_avg < 13) | (y_avg >= 222)] = 1.0
    vis = np.minimum((yl * 255 + .5).astype(int), 255)
    pad = np.pad(vis == 255, 1, mode="edge")
    any255 = np.zeros_like(vis, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            any255 |= pad[1 + dy: 1 + dy + vis.shape[0], 1 + dx: 1 + dx + vis.shape[1]]
    v = np.where(any255, 255, 0)
    for _ in range(32):
        pad = np.pad(v == 255, 1, mode="edge")
        cnt = sum(pad[1 + dy: 1 + dy + v.shape[0], 1 + dx: 1 + dx + v.shape[1]].astype(int)
                  for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        v = np.where((v < 255) & (cnt >= 5), 255, v)
    lab, n = label(v == 0)
    keep = np.zeros_like(v, dtype=bool)
    for k in range(1, n + 1):
        region = lab == k
        if region.sum() >= 64:
            keep |= region
    return int(keep.sum())


def deblock_weights(b: int, power: float = 1.8) -> np.ndarray:
    c = (b - 1) * .5
    x = (np.arange(b) - c) / b
    d = np.sqrt(x[None, :] ** 2 + x[:, None] ** 2 + .36 ** 2)
    return d ** power


def main() -> None:
    with SCREEN.open(encoding="utf-8-sig") as f:
        screen = {int(r["id"]): r for r in csv.DictReader(f)}
    paths: dict[int, dict] = {}
    with NATIVE.open(encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            i = s["validation_index"]
            if i in screen and i not in paths:
                paths[i] = s
    rows = []
    wdb = np.tile(deblock_weights(B), (128 // B, 128 // B))
    for i, meta in sorted(paths.items()):
        ref = load(Path(meta["reference_path"]))
        dec_path = Path(meta["decoded_path"]).with_name("8x8_fastest.png")
        dec = load(dec_path)
        if ref.shape != dec.shape or ref.shape[0] != 128 or ref.shape[1] != 128:
            continue
        # orientation: pick the flip that matches (Unity decoded PNG may be stored bottom-up)
        e0 = np.mean((ref - dec) ** 2)
        e1 = np.mean((ref - dec[::-1]) ** 2)
        flipped = e1 < e0
        if flipped:
            dec = dec[::-1]
        need_alpha = bool(meta["need_alpha"]) and not bool(meta.get("alpha_constant", False))
        chans = [0, 1, 2, 3] if need_alpha else [0, 1, 2]
        err2 = ((ref - dec)[..., chans] ** 2).mean(axis=-1)  # per-pixel mean over used channels, 8-bit^2
        scale = np.kron(ert_scale(ref, chans, B), np.ones((B, B)))
        wsse = err2 * scale
        ert_wmse = float(wsse.mean())
        smooth_share = float(wsse[scale > 1.0].sum() / max(wsse.sum(), 1e-12))
        # astcenc -b 1.8 per-texel deblock weighting, normalised weighted MSE
        db = float((err2 * wdb).sum() / wdb.sum())
        # astcenc -v radius 3 stdev weight 50 on 0..1 data, rgb/alpha separately, mix 0
        r01 = ref / 255.0
        m = uniform_filter(r01, (7, 7, 1), mode="nearest")
        var = np.maximum(uniform_filter(r01 ** 2, (7, 7, 1), mode="nearest") - m ** 2, 0)
        wact = 1.0 / (1.0 + 50.0 * var)  # weight = 1/(base + stdev_w * stdev^2) with stdev^2 = var
        act = float(((ref - dec)[..., chans] ** 2 * wact[..., chans]).sum() / wact[..., chans].sum())
        # blend-aware worst-background bound (linear light), alpha images only
        if need_alpha:
            a0, a1 = ref[..., 3:] / 255.0, dec[..., 3:] / 255.0
            c0, c1 = lin(ref[..., :3]), lin(dec[..., :3])
            p0, p1 = a0 * c0, a1 * c1
            dpre = p1 - p0
            da = a1 - a0
            # composite over background Bg: out = P + (1-a) Bg ; error = dP - da*Bg ; linear in Bg -> extremes at 0 / 1
            e_black = np.abs(dpre)
            e_white = np.abs(dpre - da)
            ew = np.maximum(e_black, e_white).max(axis=-1) * 255.0
            bb = float(np.sqrt(np.mean(ew ** 2)))
            bbs = float(np.sqrt(np.mean(ew ** 2 * scale)))
        else:
            bb = bbs = float("nan")
        rows.append(dict(id=i, asset=meta["asset"], need_alpha=need_alpha, flipped=flipped,
                         psnr_native=float(screen[i]["psnr_native"]),
                         continuous_seam=screen[i]["continuous_seam"], rank_seam=screen[i]["rank_continuous_seam"],
                         ert_smooth_wmse=ert_wmse, ert_smooth_share=smooth_share,
                         ultrasmooth_blocks=ultrasmooth(ref),
                         deblock_wpsnr=10 * np.log10(255 ** 2 / max(db, 1e-12)),
                         activity_wpsnr=10 * np.log10(255 ** 2 / max(act, 1e-12)),
                         blend_bound_rmse=bb, blend_bound_smooth=bbs))
    # ranks: higher = more suspicious
    def rank(key: str, higher_bad: bool, subset=None) -> None:
        pool = [r for r in rows if not np.isnan(r[key]) and (subset is None or subset(r))]
        pool.sort(key=lambda r: -r[key] if higher_bad else r[key])
        for k, r in enumerate(pool, 1):
            r[f"rank_{key}"] = k
        return len(pool)
    denom = {}
    for key, hb in (("ert_smooth_wmse", True), ("ert_smooth_share", True), ("deblock_wpsnr", False),
                    ("activity_wpsnr", False), ("blend_bound_rmse", True), ("blend_bound_smooth", True),
                    ("psnr_native", False)):
        denom[key] = rank(key, hb)
    out = HERE / "industry-probe.csv"
    keys = list(rows[0].keys()) + sorted({k for r in rows for k in r} - set(rows[0].keys()))
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    summary = dict(n=len(rows), denominators=denom,
                   flipped=sum(r["flipped"] for r in rows),
                   known={r["id"]: {k: v for k, v in r.items() if k != "asset"} for r in rows if r["id"] in KNOWN})
    (HERE / "industry-probe-summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=float))
    top = sorted(rows, key=lambda r: r["rank_ert_smooth_wmse"])[:12]
    print("top12 ert_smooth_wmse:", [(r["id"], round(r["ert_smooth_wmse"], 1), r["asset"].split("/")[-2]) for r in top])


if __name__ == "__main__":
    main()
