"""Bridge to the candidate metrics as implemented by the lanes (read-only imports, no bytecode written elsewhere)."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
from pathlib import Path

import numpy as np

ROOT = Path("E:/ASTC_Compression")
DIAG = ROOT / "tmp/gradient-diagnostics-20261119"
LANE_A = ROOT / "tmp/gradient-metric-brainstorm-20261119/lane-a-banding-literature"
LANE_C = ROOT / "tmp/gradient-metric-brainstorm-20261119/lane-c-astc-design"
for p in (DIAG, LANE_A, LANE_C):
    sys.path.insert(0, str(p))

from probe import evaluate, gradient_mask, lab  # noqa: E402  (seam family, Lab mask)
from probe_lane_a import jnd_contours  # noqa: E402  (lane A luma JND)
from prototypes import full_reference  # noqa: E402  (lane C B1-B4)

FIELDS = ("gradient_change_p95", "grid_excess_p95", "continuous_seam", "jnd_p95", "jnd_visible_frac",
          "jnd_longest_cc", "B1_poster_frac", "B2_flat_area", "B2_flat_p90", "B3_conc_p95", "B4_axis_shift")


def score(ref: np.ndarray, dec: np.ndarray, block: int, mask: np.ndarray | None = None) -> dict[str, float | None]:
    """All grid-bound / grid-free candidates on display RGB uint8 images; mask from the reference."""
    lr = lab(ref)
    m = gradient_mask(lr) if mask is None else mask
    seam, _ = evaluate(lr, lab(dec), m, block)
    out: dict[str, float | None] = {k: seam[k] for k in ("gradient_change_p95", "grid_excess_p95", "continuous_seam")}
    j = jnd_contours(ref, dec, m, block)
    out |= {k: j[k] for k in ("jnd_p95", "jnd_visible_frac", "jnd_longest_cc")}
    c = full_reference(ref, dec, m, block)
    out |= {k: c[k] for k in ("B1_poster_frac", "B2_flat_area", "B2_flat_p90", "B3_conc_p95", "B4_axis_shift")}
    diff = dec.astype(float) - ref.astype(float)
    out["mse_display"] = float(np.mean(diff ** 2))
    out["mse_in_mask"] = float(np.mean(diff[m] ** 2)) if m.any() else None
    out["mask_px"] = int(m.sum())
    return out
