"""Mechanism probe: what did the real encoder choose for the gradient blocks of 0615/0616/0617?"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from astc_modes import read_astc  # noqa: E402
from common import MANIFEST, display_mask, native_paths, rgba  # noqa: E402


def orientation(blocks: list[list[dict]], decoded: np.ndarray, b: int) -> dict[str, int]:
    h = decoded.shape[0]
    score = {"top_down": 0, "bottom_up": 0, "voids": 0}
    for j, row in enumerate(blocks):
        for i, blk in enumerate(row):
            if blk["kind"] != "void":
                continue
            score["voids"] += 1
            want = np.array(blk["rgba8"])
            td = decoded[j * b:(j + 1) * b, i * b:(i + 1) * b].reshape(-1, 4)
            bu = decoded[h - (j + 1) * b:h - j * b, i * b:(i + 1) * b].reshape(-1, 4)
            score["top_down"] += int(np.all(np.abs(td.astype(int) - want) <= 1))
            score["bottom_up"] += int(np.all(np.abs(bu.astype(int) - want) <= 1))
    return score


def main() -> None:
    out: dict[str, object] = {}
    for idx in (615, 616, 617):
        ref_path, dec_path = native_paths(idx, "fastest")
        ref = rgba(ref_path)
        folder = dec_path.parent
        mask = display_mask(idx)  # display orientation (top-down)
        h = ref.shape[0]
        per: dict[str, object] = {}
        for tag in ("8x8_fastest", "8x8_medium", "8x8_exhaustive", "6x6_fastest", "4x4_fastest"):
            if not (folder / f"{tag}.astc").is_file():
                continue
            b, _, w, hh, blocks = read_astc(folder / f"{tag}.astc")
            dec = rgba(folder / f"{tag}.png")
            ori = orientation(blocks, dec, b)
            # Native block row j covers display rows [h-(j+1)b, h-jb) when the PNG is top-down display order.
            stats: Counter = Counter()
            grads = []
            for j, row in enumerate(blocks):
                for i, blk in enumerate(row):
                    y0, y1 = max(0, h - (j + 1) * b), h - j * b
                    region = mask[y0:y1, i * b:(i + 1) * b]
                    if region.size == 0 or region.mean() < 0.5:
                        continue
                    if blk["kind"] != "normal":
                        stats[blk["kind"]] += 1
                        continue
                    grads.append(blk)
                    stats[f"grid{blk['grid'][0]}x{blk['grid'][1]}"] += 1
                    stats[f"wlev{blk['weight_levels']}"] += 1
                    stats[f"elev{blk['endpoint_levels']}"] += 1
                    stats[f"parts{blk['partitions']}"] += 1
                    stats[f"dual{int(blk['dual'])}"] += 1
                    stats["cem" + "-".join(map(str, blk["cem"]))] += 1
            n = len(grads)
            per[tag] = {"orientation_void_matches": ori, "gradient_blocks": n,
                        "median_grid_weights": float(np.median([g["grid"][0] * g["grid"][1] for g in grads])) if n else None,
                        "median_weight_levels": float(np.median([g["weight_levels"] for g in grads])) if n else None,
                        "median_endpoint_levels": float(np.median([g["endpoint_levels"] or 0 for g in grads])) if n else None,
                        "counts": dict(sorted(stats.items()))}
        out[str(idx)] = per
    # The 0615 column x=56, display y=88..96 lives in native block row (128-96)/8 = 4, column 7.
    ref_path, dec_path = native_paths(615, "fastest")
    ref, dec = rgba(ref_path), rgba(dec_path)
    _, _, _, _, blocks = read_astc(dec_path.parent / "8x8_fastest.astc")
    blk = blocks[4][7]
    ys = slice(88, 96)
    window = {"block_mode": blk, "ref_column_x56_rgba": ref[ys, 56].tolist(), "dec_column_x56_rgba": dec[ys, 56].tolist(),
              "ref_next_y96": ref[96, 56].tolist(), "dec_next_y96": dec[96, 56].tolist(),
              "ref_block_alpha": ref[88:96, 56:64, 3].tolist(), "dec_block_alpha": dec[88:96, 56:64, 3].tolist(),
              "ref_block_rgb_std": ref[88:96, 56:64, :3].reshape(-1, 3).std(0).tolist(),
              "ref_block_alpha_std": float(ref[88:96, 56:64, 3].std()),
              "dec_block_rgb": dec[88:96, 56:64, :3].reshape(-1, 3)[::9].tolist(),
              "ref_block_rgb": ref[88:96, 56:64, :3].reshape(-1, 3)[::9].tolist(),
              "next_block_mode": blocks[3][7]}
    out["0615_block_x56_y88"] = window
    (HERE / "mechanism.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=None)[:6000])
    _ = MANIFEST


if __name__ == "__main__":
    main()
