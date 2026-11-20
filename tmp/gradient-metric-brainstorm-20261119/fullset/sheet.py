"""Contact sheet of the top-N images for one metric column in a runner CSV (crop at the given x/y columns)."""
from __future__ import annotations

import argparse
import csv
import math

from harness import KNOWN, common_rows, load_items, review_sheet
from runner import HERE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("metric")
    parser.add_argument("--x", default="")
    parser.add_argument("--y", default="")
    parser.add_argument("--top", type=int, default=16)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--subset", choices=("all", "common442", "ge35"), default="common442")
    parser.add_argument("--ascending", action="store_true")
    parser.add_argument("--skip-known", action="store_true")
    parser.add_argument("--skip-group", default="", help="exclude rows whose group equals this")
    parser.add_argument("--preset", default="fastest")
    parser.add_argument("--block", type=int, default=8)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    items = {i.id: i for i in load_items()}
    common = {i for i, r in common_rows().items()
              if all(isinstance(r.get(k), (int, float)) for k in ("grid_excess_p95", "phase_adjusted", "flip_p99"))}
    with (HERE / args.csv).open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    keep = []
    for r in rows:
        value = r.get(args.metric, "")
        if value in ("", "None"):
            continue
        v = float(value)
        if not math.isfinite(v):
            continue
        i = int(r["id"])
        if args.subset == "common442" and i not in common:
            continue
        if args.subset == "ge35" and float(r["native_psnr"]) < 35:
            continue
        if args.skip_known and i in KNOWN:
            continue
        if args.skip_group and r.get("group") == args.skip_group:
            continue
        keep.append((v, i, r))
    keep.sort(key=lambda t: (t[0] if args.ascending else -t[0], t[1]))
    entries = []
    for rank, (v, i, r) in enumerate(keep[args.offset:args.offset + args.top], args.offset + 1):
        item = items[i]
        x = int(float(r[args.x])) if args.x and r.get(args.x) not in ("", "None", None) else item.width // 2
        y = int(float(r[args.y])) if args.y and r.get(args.y) not in ("", "None", None) else item.height // 2
        title = f"#{rank} {args.metric}={v:.3g} psnr={item.native_psnr:.2f} {item.view} {item.width}x{item.height} {item.asset[-60:]}"
        entries.append((item, x, y, title))
    review_sheet(entries, HERE / args.out, block=args.block, preset=args.preset)
    print(HERE / args.out, len(entries))


if __name__ == "__main__":
    main()
