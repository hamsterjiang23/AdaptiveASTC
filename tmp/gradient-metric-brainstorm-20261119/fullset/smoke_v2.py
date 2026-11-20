"""Smoke checks for gradient-new-step-v2: B3 regression, synthetic battery, per-image cost on the largest assets."""
from __future__ import annotations

import json
import sys
import time

import numpy as np

from harness import KNOWN, ROOT, load_items, read
from new_step_v2 import _l2s, _s2l, gradient_mask, lab, measure, reference_windows, score_all, score_pair

sys.path.insert(0, str(ROOT / "tmp/gradient-metric-brainstorm-20261119/critic-perception"))
from synthetic_battery import cases  # noqa: E402

DISPLAY_B3 = {615: 11.357167193723411, 616: 5.674300391485293, 617: 9.928792895405685}  # structure-controls.csv real8
NATIVE_B3 = {615: 11.630582939016183, 616: 5.674300391485293, 617: 9.69815291210573}  # candidates-pop128.csv b3


def unrounded(path, alpha: bool) -> np.ndarray:
    px = read(path, "RGBA").astype(np.float64)
    if not alpha:
        return px[..., :3]
    a = px[..., 3:4] / 255
    return _l2s(a * _s2l(px[..., :3]) + (1 - a) * _s2l(np.full(3, 64.0)))


def main() -> None:
    items = {i.id: i for i in load_items()}
    report: dict[str, object] = {}
    for idx in KNOWN:
        item = items[idx]
        start = time.perf_counter()
        row = score_all(item, (8,), "fastest")[8]
        alpha = item.view == "dark"
        lr = lab(unrounded(item.native(None), alpha))
        mask = gradient_mask(lr)
        native = measure(reference_windows(lr, mask), int(mask.sum()), mask.shape,
                         lab(unrounded(item.native(8), alpha)))["L"]["p95"]
        report[str(idx)] = dict(display_L_p95=row["L_p95_primary"], display_expected=DISPLAY_B3[idx],
                                native_L_p95=native, native_expected=NATIVE_B3[idx],
                                S=row["S"], S_arg=row["S_arg"], S_2bg=row["S_2bg"], E_p95=row["E_p95"],
                                C_p95=row["C_p95"], E_plat=row["E_plat"], b1_frac=row["b1_frac"],
                                seconds=time.perf_counter() - start)
        assert abs(row["L_p95_primary"] - DISPLAY_B3[idx]) < 1e-6, (idx, row["L_p95_primary"])
        assert abs(native - NATIVE_B3[idx]) < 1e-6, (idx, native)
    battery = {}
    for name, (ref, dec, should, _note) in cases().items():
        r = score_pair(ref, dec, 8)
        battery[name] = dict(should=should, S=r["S"], E_p95=r["E_p95"], L_p95=r["L_p95"], C_p95=r["C_p95"],
                             E_plat=r["E_plat"], n=r["E_n"], mask_px=r["mask_px"], b1_frac=r["b1_frac"])
    report["battery"] = battery
    largest = sorted(items.values(), key=lambda i: (-(i.width * i.height), i.view != "dark"))[:2]
    for item in largest:
        start = time.perf_counter()
        score_all(item, (4, 6, 8), "fastest")
        report[f"timing_{item.id}_{item.width}x{item.height}_{item.view}"] = time.perf_counter() - start
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
