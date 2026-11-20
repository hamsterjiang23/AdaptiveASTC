"""Parallel full-set runner: score every item at chosen block sizes, then rank the known examples and summarise."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

from harness import KNOWN, Item, Row, common_rows, family_report, load_items, rank_known, spearman  # noqa: E402

Score = Callable[[Item, int, str], Row]
HERE = Path(__file__).resolve().parent
CONTROLS = (2, 120, 587, 698, 939)


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def task(score: Score, blocks: tuple[int, ...], preset: str, item: Item) -> Row:
    row: Row = dict(id=item.id, asset=item.asset, group=item.group, view=item.view, width=item.width,
                    height=item.height, native_psnr=item.native_psnr, display_psnr=item.display_psnr,
                    flip_p99=item.flip_p99)
    start = time.perf_counter()
    if getattr(score, "batched", False):  # score(item, blocks, preset) -> {block: fields}, reuses reference work
        per_block = score(item, blocks, preset)
    else:
        per_block = {block: score(item, block, preset) for block in blocks}
    for block in blocks:
        for key, value in per_block[block].items():
            row[f"{key}@{block}"] = value
    row["seconds"] = time.perf_counter() - start
    return row


def summarise(rows: list[Row], metrics: list[tuple[str, bool]], blocks: tuple[int, ...]) -> dict[str, object]:
    common = {i for i, r in common_rows().items()
              if all(_number(r.get(k)) for k in ("grid_excess_p95", "phase_adjusted", "flip_p99"))}
    subsets = {"all": rows,
               "native_psnr_ge35": [r for r in rows if r["native_psnr"] >= 35],
               "common442": [r for r in rows if r["id"] in common],
               "128x128": [r for r in rows if r["width"] == r["height"] == 128]}
    result: dict[str, object] = {}
    for metric, descending in metrics:
        key = f"{metric}@8"
        entry: dict[str, object] = {name: rank_known(subset, key, descending) for name, subset in subsets.items()}
        entry["families_top45_common442"] = family_report(subsets["common442"], key, 45, descending)
        entry["spearman_vs_native_psnr"] = spearman(
            [r[key] if _number(r.get(key)) else math.nan for r in rows], [r["native_psnr"] for r in rows])
        ordered = sorted(b for b in blocks)
        if len(ordered) > 1:
            keys = [f"{metric}@{b}" for b in ordered]
            both = [r for r in rows if all(_number(r.get(k)) for k in keys)]
            sign = 1 if descending else -1
            monotone = sum(all(sign * r[a] <= sign * r[b] for a, b in zip(keys, keys[1:])) for r in both)
            entry["smaller_blocks_not_worse"] = dict(valid=len(both), monotone=monotone,
                                                     share=(monotone / len(both) if both else None))
        result[metric] = entry
    seconds = [float(r["seconds"]) for r in rows]
    result["runtime"] = dict(images=len(rows), total_cpu_s=sum(seconds), max_s=max(seconds) if seconds else None)
    return result


def main(score: Score, name: str, metrics: list[tuple[str, bool]], blocks: tuple[int, ...] = (8,)) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="known images plus five controls")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--blocks", type=lambda s: tuple(int(v) for v in s.split(",")), default=blocks)
    parser.add_argument("--preset", default="fastest")
    args = parser.parse_args()
    items = load_items()
    if args.smoke:
        items = [i for i in items if i.id in KNOWN + CONTROLS]
    run = partial(task, score, args.blocks, args.preset)
    start = time.perf_counter()
    if args.workers <= 1 or args.smoke:
        rows = [run(i) for i in items]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            rows = []
            for row in pool.map(run, items, chunksize=4):
                rows.append(row)
                if len(rows) % 200 == 0:
                    print(f"{len(rows)}/{len(items)}", flush=True)
    wall = time.perf_counter() - start
    suffix = "-smoke" if args.smoke else ""
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (HERE / f"{name}{suffix}.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    if args.smoke:
        for r in rows:
            print(r["id"], {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()
                            if "@" in k or k in ("native_psnr", "seconds")})
        return
    summary = summarise(rows, metrics, args.blocks) | {"wall_s": wall, "workers": args.workers,
                                                       "blocks": list(args.blocks), "preset": args.preset}
    (HERE / f"{name}-summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({m: {s: summary[m][s] for s in ("all", "native_psnr_ge35", "common442", "128x128")}
                      for m, _ in metrics}, ensure_ascii=False))
