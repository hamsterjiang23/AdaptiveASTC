from __future__ import annotations

import csv
import json
from pathlib import Path

from probe import HERE, MEDIA, evaluate, gradient_mask, lab, rgb

Row = dict[str, str | int | float | None]


def main() -> None:
    path = MEDIA.parent / "data.js"
    assets = json.loads(path.read_text(encoding="utf-8").removeprefix("window.REVIEW=").removesuffix(";"))["assets"]
    rows: list[Row] = []
    for asset in assets:
        if asset["w"] != 128 or asset["h"] != 128 or asset["views"] == ["data"]:
            continue
        idx = asset["id"]
        view = "dark" if "dark" in asset["views"] else "rgb"
        folder = MEDIA / f"{idx:04d}"
        ref = lab(rgb(folder/f"ref-{view}.png"))
        decoded = lab(rgb(folder/f"fastest-{view}.png"))
        mask = gradient_mask(ref)
        stats, _ = evaluate(ref, decoded, mask, 8)
        native = next(r for r in asset["rows"] if r["view"] == view and r["preset"] == "fastest")
        rows.append({"id": idx, "asset": asset["asset"], "view": view, **stats,
                     "psnr_native": native["psnr"], "area_below_28": native["a28"], "flip_p99": native["fp99"]})
    ranking = {}
    for field, desc in (("gradient_change_p95",True),("grid_excess_p95",True),("continuous_seam",True),("gradient_area_pct",True),
                        ("flip_p99",True),("psnr_native",False)):
        ranked = [r for r in rows if isinstance(r[field],(int,float))]
        for row in rows:
            if not isinstance(row[field], (int,float)):
                row["rank_"+field] = None
                continue
            row["rank_"+field] = 1+sum((r[field]>row[field] if desc else r[field]<row[field]) for r in ranked)
        ranking[field] = len(ranked)
    supported = [r for r in rows if r["continuous_seam"] is not None]
    for row in rows:
        for field,desc in (("psnr_native",False),("flip_p99",True)):
            row["same_set_rank_"+field] = None if row["continuous_seam"] is None else 1+sum(
                (r[field] > row[field] if desc else r[field] < row[field]) for r in supported)
    ordered = sorted(rows, key=lambda r: -1 if r["continuous_seam"] is None else r["continuous_seam"], reverse=True)
    assert len(ordered) == 196 and len({r["id"] for r in rows}) == len(rows)
    with (HERE/"screen-128.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(ordered)
    result = {"assets": len(rows), "valid_rank_denominators": ranking,
              "method": "All 128x128 color assets, 8x8 fastest, dark composite for alpha, otherwise RGB. Ranks counted strictly greater (strictly lower for native PSNR).",
              "examples": [r for r in rows if r["id"] in (615,616,617)]}
    (HERE/"screen-summary.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=True))


if __name__ == "__main__":
    main()
