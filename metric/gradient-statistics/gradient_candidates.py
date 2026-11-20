"""Add original-only gradient coverage to the statistically screened sample list."""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
METRIC = HERE.parent


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    samples = {s["id"]:s for s in json.loads((METRIC/"gradient-screen-50/comparisons.json").read_bytes())["samples"]}
    partition = read(HERE/"reference-partition.csv")
    selected = {int(r["id"]) for r in partition if r["role"] in ("fit","calibration")}
    fixed = read(METRIC/"gradient-screen/fixed8-validation.csv")
    reference = [r for r in fixed if int(r["id"]) in selected]
    assert len(reference)==277
    rows = []
    for row in read(HERE/"statistical-screen.csv"):
        idx = int(row["id"])
        s = samples[idx]
        area = s["values"]["ref"]["mask_area_pct"]
        connected = s["values"]["ref"]["mask_largest_pct"]
        same = [r for r in reference if int(r["width"])==s["width"]]
        sizes = [100*float(v["largest_component_px"])/(int(v["height"])*int(v["width"])) for v in same]
        # Strictly smaller percentile leaves an asset with no connected area at zero.
        lower = 100*sum(v<connected for v in sizes)/len(sizes)
        rows.append(dict(id=f"{idx:04}",asset=s["asset"],original_gradient_area_pct=area,
                         original_largest_gradient_component_pct=connected,same_size_reference_n=len(same),
                         pct_reference_with_strictly_smaller_component=lower,
                         empirical_tail=row["p_any"],native_psnr_delta=row["native_psnr_delta"],
                         display_psnr_delta=row["display_psnr_delta"],family=row["strongest_family"],
                         strongest_metric=row["strongest_metric"],signed_change=row["delta_strongest"],direction=row["direction"],
                         review_page=f"../gradient-screen-50/review.html#{idx:04}"))
    rank=lambda r: 0 if float(r["empirical_tail"])<=.05 else 1 if float(r["empirical_tail"])<=.10 else 2
    rows.sort(key=lambda r:(rank(r),-r["original_largest_gradient_component_pct"],float(r["empirical_tail"]),r["id"]))
    with (HERE/"gradient-candidates.csv").open("w",encoding="utf-8-sig",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for r in rows:
        if rank(r)==0 or r["id"] in ("0615","0616","0617"):
            print(r["id"],round(r["original_largest_gradient_component_pct"],3),round(r["pct_reference_with_strictly_smaller_component"],1),r["same_size_reference_n"])


if __name__=="__main__":
    main()
