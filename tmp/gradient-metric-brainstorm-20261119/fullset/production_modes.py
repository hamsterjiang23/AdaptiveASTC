"""Production-facing checks for gradient-new-step-v2.

gt:      score the shipped label (manifest gt_block / gt_preset) of every image.
replay:  for images where the plain first-valid rule applies (w*h < 512^2; all 938 are sRGB colour), score all
         20 candidates with their archived payload / PSNR / MS-SSIM so a metric gate can be replayed offline.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

from harness import KNOWN, MANIFEST, PRESETS, Item, Row, load_items  # noqa: E402
from new_step_v2 import score_all  # noqa: E402

HERE = Path(__file__).resolve().parent
BLOCKS = (12, 10, 8, 6)
KEEP = ("E_p95", "L_p95", "C_p95", "S", "E_a6", "E_plat", "L_p95_primary", "E_p95_2bg", "S_2bg", "E_n",
        "mask_px", "S_arg", "win_x", "win_y", "b1_frac")


def manifest() -> dict[int, dict]:
    return {r["validation_index"]: r for r in json.loads(MANIFEST.read_bytes()) if r["preset"] == "fastest"}


def candidates(item: Item) -> dict[tuple[int, str], dict]:
    return {(c["block"], c["preset"]): c for c in json.loads((item.decoded_dir / "candidates.json").read_bytes())}


def base(item: Item, m: dict) -> Row:
    return dict(id=item.id, asset=item.asset, group=item.group, view=item.view, width=item.width,
                height=item.height, t_psnr=m["target_psnr_db"], t_ms=m["target_ms_ssim_db"],
                gt=f"{m['gt_block']}_{m['gt_preset']}")


def gt_task(meta: dict[int, dict], item: Item) -> list[Row]:
    m = meta[item.id]
    block, preset = int(m["gt_block"].split("x")[0]), m["gt_preset"]
    start = time.perf_counter()
    scored = score_all(item, (block,), preset)[block]
    c = candidates(item)[(block, preset)]
    row = base(item, m) | dict(block=block, preset=preset, payload=c["payload_bytes"], psnr=c["metrics"]["psnr"],
                               ms=c["metrics"]["ms_ssim_db"])
    return [row | {k: scored.get(k) for k in KEEP} | dict(seconds=time.perf_counter() - start)]


def replay_task(meta: dict[int, dict], item: Item) -> list[Row]:
    m = meta[item.id]
    cands = candidates(item)
    rows = []
    for preset in PRESETS:
        scored = score_all(item, BLOCKS, preset)
        for block in BLOCKS:
            c = cands[(block, preset)]
            rows.append(base(item, m) | dict(block=block, preset=preset, payload=c["payload_bytes"],
                                             psnr=c["metrics"]["psnr"], ms=c["metrics"]["ms_ssim_db"])
                        | {k: scored[block].get(k) for k in KEEP})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("gt", "replay"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    meta = manifest()
    items = load_items()
    if args.mode == "replay":
        items = [i for i in items if i.width * i.height < 512 * 512]
    if args.smoke:
        items = [i for i in items if i.id in KNOWN]
    task = partial(gt_task if args.mode == "gt" else replay_task, meta)
    start = time.perf_counter()
    rows: list[Row] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for n, part in enumerate(pool.map(task, items, chunksize=2), 1):
            rows.extend(part)
            if n % 100 == 0:
                print(f"{n}/{len(items)} {time.perf_counter() - start:.0f}s", flush=True)
    name = f"production-{args.mode}{'-smoke' if args.smoke else ''}.csv"
    with (HERE / name).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        writer.writerows(rows)
    print(name, len(rows), f"wall {time.perf_counter() - start:.1f}s", flush=True)


if __name__ == "__main__":
    main()
