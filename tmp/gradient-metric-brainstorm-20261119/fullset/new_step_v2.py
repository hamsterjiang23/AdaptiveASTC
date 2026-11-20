"""gradient-new-step-v2: does the decode squeeze a smooth monotone ramp into fewer, larger steps?

Per background view (opaque: RGB; alpha: 0/64/192/255 composites, 4x4 only 64/192), the reference gradient
mask M (seam_metric) selects 16 px row/column windows (stride 4) lying fully inside M.  Groups E=(L*,a*,b*),
L=(L*), C=(a*,b*).  A window is valid when TV_ref >= 4 and the ramp is monotone (net >= 0.8 TV_ref).
Window score s = max(0, c_dec - c_ref) * TV_ref, where c = largest step / total variation.
Aggregates: P95 of s, share of M covered by windows with s >= tau, and the same share restricted to
windows whose largest decoded step sits next to a plateau of >= 3 near-flat steps.
The L-group P95 on the primary view reproduces lane C's B3.  All thresholds are frozen below.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from harness import REVIEW, ROOT, Item, Row, read

sys.path.insert(0, str(ROOT / "metric/gradient-screen"))
from seam_metric import gradient_mask, lab  # noqa: E402

WINDOW, STRIDE = 16, 4
TV_MIN, MONOTONE = 4.0, 0.8
TAUS = {"a2": 2.0, "a3": 3.0, "a45": 4.5, "a6": 6.0}
TAU, PLATEAU_STEP, PLATEAU_MIN = 3.0, 0.5, 3
MIN_WINDOWS = 8
NATIVE_BLOCKS = (6, 8, 10, 12)
GROUPS = {"E": slice(0, 3), "L": slice(0, 1), "C": slice(1, 3)}
FIELDS = ("n", "p95", "a2", "a3", "a45", "a6", "plat")
B1 = dict(cover=0.5, n_ref=4, ratio=0.5, step=3.0, min_blocks=4)
Background = int | None  # None = opaque RGB view

RefWindows = dict[tuple[int, str], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, tuple[int, int, int]]]


def _norm(values: np.ndarray) -> np.ndarray:
    return np.abs(values[..., 0]) if values.shape[-1] == 1 else np.sqrt(np.sum(values * values, axis=-1))


def _s2l(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64) / 255
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def _l2s(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return 255 * np.where(x <= .0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - .055)


def composite(path: Path, background: int) -> np.ndarray:
    """Alpha blend in linear light over a flat sRGB background, rounded like the archived display PNGs."""
    px = read(path, "RGBA").astype(np.float64)
    alpha = px[..., 3:4] / 255
    out = _l2s(alpha * _s2l(px[..., :3]) + (1 - alpha) * _s2l(np.full(3, float(background))))
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def display_path(item: Item, view: str, block: int | None, preset: str) -> Path:
    folder = REVIEW / "media" / f"{item.id:04d}"
    if block is None:
        return folder / f"ref-{view}.png"
    prefix = "" if block == 8 else f"{block}x{block}-"
    return folder / f"{prefix}{preset}-{view}.png"


def backgrounds(item: Item, block: int) -> tuple[Background, ...]:
    if item.view == "rgb":
        return (None,)
    return (0, 64, 192, 255) if block in NATIVE_BLOCKS else (64, 192)


def image(item: Item, background: Background, block: int | None, preset: str) -> np.ndarray:
    if background is None:
        return read(display_path(item, "rgb", block, preset))
    if background in (64, 192):
        return read(display_path(item, "dark" if background == 64 else "light", block, preset))
    return composite(item.native(block, preset), background)


def reference_windows(lr: np.ndarray, mask: np.ndarray) -> RefWindows:
    """Valid windows per (direction, group): row index, window index, TV_ref and c_ref."""
    out: RefWindows = {}
    for direction, (img, m) in enumerate(((lr, mask), (lr.swapaxes(0, 1), mask.T))):
        h, w = m.shape
        n = len(range(0, w - WINDOW, STRIDE))
        if n <= 0:
            continue
        starts = np.arange(n) * STRIDE
        count = np.zeros((h, w + 1), np.int32)
        np.cumsum(m, axis=1, out=count[:, 1:])
        inside = count[:, starts + WINDOW] - count[:, starts] == WINDOW
        if not inside.any():
            continue
        diff = np.diff(img, axis=1)
        for group, channels in GROUPS.items():
            norm = _norm(diff[..., channels])
            windows = sliding_window_view(norm, WINDOW - 1, axis=1)[:, ::STRIDE][:, :n]
            tv = windows.sum(axis=2)
            net = _norm(img[:, starts + WINDOW - 1, channels] - img[:, starts, channels])
            rows, cols = np.nonzero(inside & (tv >= TV_MIN) & (net >= MONOTONE * tv))
            total = tv[rows, cols]
            out[direction, group] = (rows.astype(np.int32), cols.astype(np.int32), total,
                                     windows[rows, cols].max(axis=1) / total, (h, w, n))
    return out


def _plateau(small: np.ndarray, peak: np.ndarray) -> np.ndarray:
    """Longer run of near-flat decoded steps directly left or right of the largest step, inside the window."""
    k = small.shape[1]
    left, right = np.zeros(small.shape, np.int16), np.zeros(small.shape, np.int16)
    left[:, 0], right[:, -1] = small[:, 0], small[:, -1]
    for i in range(1, k):
        left[:, i] = (left[:, i - 1] + 1) * small[:, i]
        right[:, k - 1 - i] = (right[:, k - i] + 1) * small[:, k - 1 - i]
    idx = np.arange(len(peak))
    before = np.where(peak > 0, left[idx, np.maximum(peak - 1, 0)], 0)
    after = np.where(peak < k - 1, right[idx, np.minimum(peak + 1, k - 1)], 0)
    return np.maximum(before, after)


def window_scores(ld: np.ndarray, ref: RefWindows) -> dict[tuple[int, str], tuple[np.ndarray, np.ndarray, np.ndarray]]:
    out = {}
    for direction, img in enumerate((ld, ld.swapaxes(0, 1))):
        keys = [(direction, g) for g in GROUPS if (direction, g) in ref]
        if not keys:
            continue
        diff = np.diff(img, axis=1)
        for key in keys:
            rows, cols, tv, c_ref, _ = ref[key]
            if not len(rows):
                out[key] = (np.zeros(0), np.zeros(0, np.int16), np.zeros(0, np.int64))
                continue
            norm = _norm(diff[..., GROUPS[key[1]]])
            sel = sliding_window_view(norm, WINDOW - 1, axis=1)[:, ::STRIDE][rows, cols]
            peak = sel.argmax(axis=1)
            c_dec = sel[np.arange(len(peak)), peak] / np.maximum(sel.sum(axis=1), 1e-9)
            out[key] = (np.maximum(0.0, c_dec - c_ref) * tv, _plateau(sel < PLATEAU_STEP, peak), peak)
    return out


def _covered(parts: Iterable[tuple[int, np.ndarray, np.ndarray, tuple[int, int, int], np.ndarray]],
             shape: tuple[int, int]) -> int:
    """Pixels covered by flagged windows (union of both directions); window j covers pixels 4j..4j+15."""
    cover = np.zeros(shape, bool)
    for direction, rows, cols, (h, w, n), flag in parts:
        if not flag.any():
            continue
        quarter = np.zeros((h, n + 3), bool)
        for t in range(4):
            quarter[rows[flag], cols[flag] + t] = True
        width = min(w, 4 * (n + 3))
        plane = np.repeat(quarter, 4, axis=1)[:, :width]
        if direction == 0:
            cover[:, :width] |= plane
        else:
            cover[:width, :] |= plane.T
    return int(cover.sum())


def measure(ref: RefWindows, mask_px: int, shape: tuple[int, int], ld: np.ndarray) -> dict[str, Row]:
    scores = window_scores(ld, ref)
    result: dict[str, Row] = {}
    for group in GROUPS:
        keys = [(d, group) for d in (0, 1) if (d, group) in scores]
        n = sum(len(scores[k][0]) for k in keys)
        entry: Row = dict(n=n) | {f: None for f in FIELDS[1:]}
        if mask_px and n >= MIN_WINDOWS:
            values = np.concatenate([scores[k][0] for k in keys])
            entry["p95"] = float(np.quantile(values, .95))

            def share(flag_of: object) -> float:
                parts = [(k[0], ref[k][0], ref[k][1], ref[k][4], flag_of(*scores[k])) for k in keys]
                return _covered(parts, shape) / mask_px

            for name, tau in TAUS.items():
                entry[name] = share(lambda s, p, _k, tau=tau: s >= tau)
            entry["plat"] = share(lambda s, p, _k: (s >= TAU) & (p >= PLATEAU_MIN))
            if group == "E":
                best = max(keys, key=lambda k: scores[k][0].max() if len(scores[k][0]) else -1.0)
                i = int(scores[best][0].argmax())
                along = int(ref[best][1][i]) * STRIDE + int(scores[best][2][i])
                across = int(ref[best][0][i])
                entry["win"] = (along, across, "row", float(scores[best][0][i])) if best[0] == 0 else \
                    (across, along, "col", float(scores[best][0][i]))
        result[group] = entry
    return result


def _distinct(values: np.ndarray, keep: np.ndarray) -> np.ndarray:
    ordered = np.sort(np.where(keep, values, np.inf), axis=1)
    finite = np.isfinite(ordered)
    with np.errstate(invalid="ignore"):
        step = np.diff(ordered, axis=1) != 0
    return finite[:, 0].astype(int) + (step & finite[:, 1:]).sum(axis=1)


def b1v2(lr: np.ndarray, ld: np.ndarray, mask: np.ndarray, block: int) -> Row:
    """Level collapse inside true ASTC blocks (grid anchored at the bottom row), L* only; diagnostic."""
    h, w = mask.shape
    pad_h, pad_w = (-h) % block, (-w) % block

    def tiles(a: np.ndarray, fill: object) -> np.ndarray:
        p = np.pad(a, ((pad_h, 0), (0, pad_w)), constant_values=fill)
        ny, nx = p.shape[0] // block, p.shape[1] // block
        return p.reshape(ny, block, nx, block).swapaxes(1, 2).reshape(ny * nx, block * block)

    valid, m = tiles(np.ones((h, w), bool), False), tiles(mask, False)
    ext_u = valid.reshape(-1, block, block).any(axis=1).sum(axis=1)
    ext_v = valid.reshape(-1, block, block).any(axis=2).sum(axis=1)
    grad = (m.sum(axis=1) >= B1["cover"] * valid.sum(axis=1)) & (np.minimum(ext_u, ext_v) >= 3)
    out: Row = dict(b1_blocks=int(grad.sum()), b1_collapsed=None, b1_frac=None)
    if grad.sum() < B1["min_blocks"]:
        return out
    wgt = valid[grad].astype(np.float64)
    ref, dec = tiles(lr, 0.0)[grad], tiles(ld, 0.0)[grad]
    v, u = np.divmod(np.arange(block * block, dtype=np.float64), block)

    def total(z: np.ndarray | float) -> np.ndarray:
        return np.sum(wgt * z, axis=1)

    su, sv = total(u), total(v)
    normal = np.stack([np.stack([total(1.0), su, sv], 1), np.stack([su, total(u * u), total(u * v)], 1),
                       np.stack([sv, total(u * v), total(v * v)], 1)], 1)
    coef = np.linalg.solve(normal, np.stack([total(ref), total(u * ref), total(v * ref)], 1)[..., None])[..., 0]
    amp = np.abs(coef[:, 1]) * (ext_u[grad] - 1) + np.abs(coef[:, 2]) * (ext_v[grad] - 1)
    n_ref, n_dec = _distinct(np.round(ref), m[grad]), _distinct(np.round(dec), m[grad])
    collapsed = (n_ref >= B1["n_ref"]) & (n_dec <= B1["ratio"] * n_ref) & (amp / np.maximum(n_dec - 1, 1) >= B1["step"])
    return out | dict(b1_collapsed=int(collapsed.sum()), b1_frac=float(collapsed.mean()))


def _max(values: Iterable[object]) -> object:
    present = [v for v in values if v is not None]
    return max(present) if present else None


def assemble(results: dict[Background, dict[str, Row]], masks: dict[Background, int], b1: Row) -> Row:
    views = list(results)
    two = [bg for bg in views if bg in (None, 64, 192)]
    row: Row = {}
    for group in GROUPS:
        for field in FIELDS:
            row[f"{group}_{field}"] = _max(results[bg][group][field] for bg in views)
        for field in ("p95", "a3", "plat"):
            row[f"{group}_{field}_2bg"] = _max(results[bg][group][field] for bg in two)
    row["S"], row["S_2bg"] = row["E_a3"], row["E_a3_2bg"]
    for bg in (0, 64, 192, 255):
        row[f"S_bg{bg}"] = results[bg]["E"]["a3"] if bg in results else None
    scored = [(results[bg]["E"]["a3"], bg) for bg in views if results[bg]["E"]["a3"] is not None]
    arg = max(scored, key=lambda t: t[0])[1] if scored else "none"
    row["S_arg"] = "rgb" if arg is None else arg
    win = results[arg]["E"].get("win") if arg != "none" else None
    row |= dict(zip(("win_x", "win_y", "win_dir", "win_s"), win or (None,) * 4))
    primary = None if None in results else 64
    row["L_p95_primary"] = results[primary]["L"]["p95"]
    row["mask_px"] = max(masks.values())
    row["no_gradient"] = int(max(masks.values()) == 0)
    return row | b1


def score_all(item: Item, blocks: tuple[int, ...], preset: str) -> dict[int, Row]:
    results: dict[int, dict[Background, dict[str, Row]]] = {b: {} for b in blocks}
    masks: dict[int, dict[Background, int]] = {b: {} for b in blocks}
    b1: dict[int, Row] = {}
    views = list(dict.fromkeys(bg for b in blocks for bg in backgrounds(item, b)))
    for bg in views:
        lr = lab(image(item, bg, None, preset))
        mask = gradient_mask(lr)
        ref = reference_windows(lr, mask)
        for block in blocks:
            if bg not in backgrounds(item, block):
                continue
            ld = lab(image(item, bg, block, preset))
            results[block][bg] = measure(ref, int(mask.sum()), mask.shape, ld)
            masks[block][bg] = int(mask.sum())
            if bg in (None, 64):
                b1[block] = b1v2(lr[..., 0], ld[..., 0], mask, block)
    return {b: assemble(results[b], masks[b], b1[b]) for b in blocks}


score_all.batched = True  # type: ignore[attr-defined]


def score_pair(ref_rgb: np.ndarray, dec_rgb: np.ndarray, block: int = 8) -> Row:
    """Single-view score for synthetic cases and controls (uint8 RGB arrays)."""
    lr = lab(ref_rgb)
    mask = gradient_mask(lr)
    ld = lab(dec_rgb)
    result = measure(reference_windows(lr, mask), int(mask.sum()), mask.shape, ld)
    return assemble({None: result}, {None: int(mask.sum())}, b1v2(lr[..., 0], ld[..., 0], mask, block))


METRICS = [("S", True), ("S_2bg", True), ("E_p95", True), ("L_p95", True), ("C_p95", True), ("E_plat", True),
           ("L_a3", True), ("C_a3", True), ("E_a2", True), ("E_a45", True), ("E_a6", True), ("L_p95_primary", True),
           ("b1_frac", True)]

if __name__ == "__main__":
    from runner import main

    main(score_all, "new-step-v2", METRICS, blocks=(4, 6, 8))
