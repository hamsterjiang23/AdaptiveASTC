"""Ground-truth-by-construction battery: which candidates fire on true banding, which on look-alike nuisances.

Every case is 128x128 sRGB; 'should' says whether a banding detector ought to fire.
Writes synthetic-battery.csv / .json next to this file only.
"""
from __future__ import annotations

import csv
import json
import sys

sys.dont_write_bytecode = True
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from metrics_bridge import FIELDS, score  # noqa: E402

N = 128
yy, xx = np.mgrid[:N, :N].astype(float)
rng = np.random.default_rng(7)


def grey(v: np.ndarray) -> np.ndarray:
    return np.repeat(np.clip(np.rint(v), 0, 255)[..., None], 3, axis=2).astype(np.uint8)


def cases() -> dict[str, tuple[np.ndarray, np.ndarray, str, str]]:
    ramp = 40 + 1.0 * xx                      # 1 code/px horizontal ramp (smooth, like a soft halo flank)
    r = np.hypot(xx - 64, yy - 64)
    radial = np.clip(200 - 2.0 * r, 30, 255)   # curved ramp, 2 codes/px
    out: dict[str, tuple[np.ndarray, np.ndarray, str, str]] = {}
    # true banding variants
    out["S1_grid_plateau_steps"] = (grey(ramp), grey(40 + 8 * np.floor(xx / 8)), "yes", "8-px plateaus, jumps ON block edges")
    out["S2_offgrid_plateau_steps"] = (grey(ramp), grey(40 + 8 * np.floor((xx - 4) / 8) + 4), "yes", "same steps shifted 4 px OFF grid")
    out["S3_curved_bands"] = (grey(radial), grey(np.clip(200 - 16 * np.floor(r / 8), 30, 255)), "yes", "radial ramp -> 16-code rings, curved, off grid")
    inblock = 40 + 8 * np.floor(xx / 8) + np.round((xx % 8) / 7 * 2) / 2 * 7   # 3 weight levels inside each block
    out["S4_inblock_3level"] = (grey(ramp), grey(inblock), "yes", "3 levels inside each 8-px block, small edge jumps")
    out["S5_small_bands_2code"] = (grey(40 + 0.25 * xx), grey(40 + 2 * np.floor(0.25 * xx / 2)), "yes(weak)", "gentle ramp, 2-code steps every 8 px (classic banding)")
    # nuisances that should NOT fire
    edge = np.where(xx < 64, 50.0, 180.0)
    ring = np.where(np.abs(xx - 63.5) < 3, 6 * np.sign(xx - 63.5) * np.cos((xx - 63.5) * np.pi / 2), 0)
    out["N1_hard_edge_ringing"] = (grey(edge), grey(edge + ring), "no", "hard edge, decoded adds +-6 ringing")
    noise = 128 + gaussian_filter(rng.normal(0, 30, (N, N)), 0.7)
    out["N2_noise_blurred"] = (grey(noise), grey(gaussian_filter(noise, 1.2)), "no", "noise texture smoothed by codec")
    stair = 40 + 4 * np.floor(xx / 4)
    out["N3_posterized_original_smoothed"] = (grey(stair), grey(ramp), "no", "original already stair-stepped; codec SMOOTHS it")
    out["N4_smooth_lowfreq_shift"] = (grey(ramp), grey(ramp + 6 * np.sin(xx / 20) * np.cos(yy / 25)), "no", "equal-ish energy, smooth low-frequency error")
    out["N5_white_noise_error"] = (grey(ramp), grey(ramp + rng.normal(0, 4, (N, N))), "no(grain)", "sigma-4 grain on the ramp, no contours")
    flat = np.full((N, N), 120.0)
    flat[40:88, 40:88] = 200
    out["N6_ui_flat_blocks"] = (grey(flat), grey(flat + np.where((xx // 8 + yy // 8) % 2 == 0, 2, -2)), "no", "flat UI fills, +-2 block-wise tint")
    # chromatic, nearly iso-luminant band: blue ramp, steps only in blue
    blue = np.stack([np.full((N, N), 20.0), np.full((N, N), 40.0), 60 + 1.2 * xx], axis=2)
    blue_dec = blue.copy()
    blue_dec[..., 2] = 60 + 1.2 * 8 * np.floor(xx / 8)
    out["C1_blue_chroma_steps"] = (np.clip(np.rint(blue), 0, 255).astype(np.uint8), np.clip(np.rint(blue_dec), 0, 255).astype(np.uint8),
                                   "yes", "blue-only ramp, 8-px plateaus in B channel (0616-like)")
    return out


def main() -> None:
    rows = []
    for name, (ref, dec, should, note) in cases().items():
        s = score(ref, dec, 8)
        rows.append({"case": name, "should_fire": should, "note": note, **{k: s[k] for k in (*FIELDS, "mse_display", "mse_in_mask", "mask_px")}})
        print(name, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in rows[-1].items() if k not in ("note",)}, flush=True)
    with (HERE / "synthetic-battery.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (HERE / "synthetic-battery.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
