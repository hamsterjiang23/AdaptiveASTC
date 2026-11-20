"""Rank real development-validation ASTC 8x8 fastest outputs at native resolution."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from seam_metric import evaluate, gradient_mask, lab, rgb

HERE = Path(__file__).resolve().parent
MEDIA = HERE.parents[1] / "outputs" / "01a1eca4-b759-74d2-82d5-2d27a4db8e18" / "media"
Row = dict[str, str | int | float | None]
KNOWN = (615, 616, 617)


def inputs() -> list[Row]:
    raw = (MEDIA.parent / "data.js").read_text(encoding="utf-8")
    assets = json.loads(raw.removeprefix("window.REVIEW=").removesuffix(";"))["assets"]
    assert len(assets) == len({asset["id"] for asset in assets}) == 1000
    rows = []
    for asset in assets:
        if asset["views"] == ["data"]:
            continue
        view = "dark" if "dark" in asset["views"] else "rgb"
        candidate = next(r for r in asset["rows"] if (r["view"], r["preset"]) == (view, "fastest"))
        rows.append(dict(id=asset["id"], asset=asset["asset"], view=view,
                         width=asset["w"], height=asset["h"], native_psnr=candidate["psnr"],
                         flip_p99=candidate["fp99"]))
    assert len(rows) == 938
    return rows


def score(row: Row) -> Row:
    folder = MEDIA / f"{row['id']:04d}"
    reference = rgb(folder / f"ref-{row['view']}.png")
    test = rgb(folder / f"fastest-{row['view']}.png")
    assert reference.shape == test.shape == (row["height"], row["width"], 3)
    delta = reference.astype(np.int32) - test.astype(np.int32)
    sse = int(np.sum(delta * delta, dtype=np.int64))
    source_lab = lab(reference)
    result, _ = evaluate(source_lab, lab(test), gradient_mask(source_lab), 8)
    return {**row, "display_rgb_psnr": (10*math.log10(255**2 * reference.size / sse) if sse else "inf"),
            "display_rgb_sse": sse, **result}


def rank_table(rows: list[Row]) -> dict[str, object]:
    result = {}
    for name, subset in [
        ("all_valid", [r for r in rows if r["continuous_seam"] is not None]),
        ("native_psnr_ge35_valid", [r for r in rows if r["continuous_seam"] is not None and r["native_psnr"] >= 35]),
        ("128x128_valid", [r for r in rows if r["continuous_seam"] is not None and r["width"] == r["height"] == 128]),
    ]:
        group = {}
        for metric, descending in [("continuous_seam", True), ("grid_excess_p95", True),
                                   ("gradient_change_p95", True), ("flip_p99", True), ("native_psnr", False)]:
            ordered = sorted(subset, key=lambda r: (-r[metric] if descending else r[metric], r["id"]))
            group[metric] = {str(r["id"]):1+sum((v[metric]>r[metric] if descending else v[metric]<r[metric]) for v in subset)
                             for r in ordered if r["id"] in KNOWN}
        result[name] = {"n":len(subset), "ranks":group}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    rows = inputs()
    if args.smoke:
        for row in rows:
            if row["id"] in KNOWN:
                measured = score(row)
                assert round(measured["continuous_seam"], 2) == {615:15.71,616:12.92,617:10.69}[row["id"]]
        print("3 native-size 8x8 archive examples reproduced.")
        return
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        scored = []
        for row in pool.map(score, rows, chunksize=2):
            scored.append(row)
            if len(scored) % 100 == 0:
                print(f"{len(scored)}/{len(rows)}", flush=True)
    ordered = sorted(scored, key=lambda r: (r["continuous_seam"] is None, -(r["continuous_seam"] or 0), r["id"]))
    with (HERE / "fixed8-validation.csv").open("w", newline="", encoding="utf-8-sig") as out:
        writer = csv.DictWriter(out, fieldnames=list(ordered[0]))
        writer.writeheader()
        writer.writerows(ordered)
    result = dict(count=len(ordered), unscorable=sum(r["continuous_seam"] is None for r in ordered),
                  psnr_ge35=sum(r["native_psnr"] >= 35 for r in ordered), groups=rank_table(ordered))
    (HERE / "fixed8-summary.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
