"""Screen original vs one decoded 8x8-fastest image at a fixed high PSNR gate."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
METRIC = HERE.parent
KNOWN = (615, 616, 617)
SIGNALS = ("grid_excess_p95", "phase_adjusted", "flip_p99")
MIN_REFERENCE = 30
Row = dict[str, str | int | float | None]


def load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def size_group(pixels: int) -> str:
    if pixels <= 128**2:
        return "through_128sq"
    if pixels <= 512**2:
        return "through_512sq"
    return "above_512sq"


def source_rows() -> list[Row]:
    old = load(METRIC/"gradient-screen/fixed8-validation.csv")
    new = {r["id"]:r for r in load(METRIC/"gradient-screen/phase-validation.csv")}
    assert len(new) == len(old) == 938
    rows = []
    for r in old:
        if float(r["native_psnr"]) < 35:
            continue
        w,h = int(r["width"]), int(r["height"])
        row: Row = dict(id=int(r["id"]), asset=r["asset"],group=PurePosixPath(r["asset"]).parent.as_posix(),
                        width=w,height=h,area_stratum=size_group(w*h),view=r["view"],
                        native_psnr=float(r["native_psnr"]),display_psnr=r["display_rgb_psnr"])
        for k in ("grid_excess_p95","continuous_seam","flip_p99","gradient_change_p95","seam_x","seam_y"):
            row[k] = float(r[k]) if r[k] else None
        v = new[r["id"]]["phase_adjusted"]
        row["phase_adjusted"] = float(v) if v else None
        assert r["native_psnr"] == new[r["id"]]["native_psnr"]
        rows.append(row)
    return rows


def scores(rows: list[Row]) -> list[Row]:
    valid = [r for r in rows if all(r[k] is not None for k in SIGNALS)]
    for row in valid:
        others = [r for r in valid if r["group"] != row["group"]]
        neighbors = [r for r in others if r["area_stratum"] == row["area_stratum"]]
        matched = neighbors if len(neighbors) >= MIN_REFERENCE else others
        assert len(matched) >= MIN_REFERENCE
        row["ref_n"] = len(matched)
        row["ref_directories"] = len({r["group"] for r in matched})
        row["ref_scope"] = "same_area_other_directories" if matched is neighbors else "all_areas_other_directories"
        tails = []
        for k in SIGNALS:
            upper = (1+sum(r[k] >= row[k] for r in matched))/(1+len(matched))
            row["tail_"+k] = upper
            tails.append(upper)
        row["any_tail"] = min(tails)
        row["two_tail"] = sorted(tails)[1]
        row["most_extreme_signal"] = SIGNALS[tails.index(min(tails))]
        row["two_strongest_signals"] = "|".join(sorted(SIGNALS,key=lambda k:row["tail_"+k])[:2])
    return valid


def evaluate(valid: list[Row], key: str, low_first: bool) -> dict:
    ordered = sorted(valid,key=lambda r:(r[key] if low_first else -r[key], r["id"]))
    ranks = {}
    for i,r in enumerate(ordered,1):
        r["rank_"+key] = i
        if r["id"] in KNOWN:
            ranks[r["id"]] = i
    result = {}
    for budget in (10,15):
        n = math.ceil(len(valid)*budget/100)
        selected = ordered[:n]
        result[str(budget)] = dict(n=n,known=[i for i in KNOWN if ranks[i]<=n],
                                   distinct_asset_dirs=len({r["group"] for r in selected}))
    return dict(ranks=ranks,budgets=result)


def sampled_pairs() -> list[dict]:
    rows = load(METRIC/"gradient-screen-50/individual-scores.csv")
    result = []
    for idx in KNOWN:
        pair = [r for r in rows if int(r["id"])==idx]
        assert {r["variant"] for r in pair} == {"ref","a","b"}
        v = {r["variant"]:r for r in pair}
        signals = ("unity_psnr_db","view_psnr_db","phase_adjusted","grid_excess_p95","platform_score","flip_p99","gmsd","masked_flip_p95","ring_p95_px")
        measures = {k:{slot:(float(v[slot][k]) if v[slot][k] and v[slot][k]!="∞" else v[slot][k] or None) for slot in ("ref","a","b")} for k in signals}
        result.append(dict(id=idx,preset_a=v["a"]["preset"],preset_b=v["b"]["preset"],values=measures))
    return result


def main() -> None:
    all_rows = source_rows()
    valid = scores(all_rows)
    methods = [("native_psnr",True),*((k,False) for k in SIGNALS),
               *(("tail_"+k,True) for k in SIGNALS),("any_tail",True),("two_tail",True)]
    evaluation = {k:evaluate(valid,k,direction) for k,direction in methods}
    for r in valid:
        r["two_tail_tie_start"] = 1+sum(v["two_tail"] < r["two_tail"] for v in valid)
        r["two_tail_tie_end"] = sum(v["two_tail"] <= r["two_tail"] for v in valid)
    fieldnames = list(valid[0])
    with (HERE/"fixed8-absolute.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(all_rows,key=lambda r:(r.get("rank_two_tail",10000),r["id"])))
    diagnostics = {group:{"all":sum(r["area_stratum"]==group for r in all_rows),
                          "common_valid":sum(r["area_stratum"]==group for r in valid)} for group in sorted({r["area_stratum"] for r in all_rows})}
    result=dict(protocol="fixed 8x8 fastest, native PSNR >=35 dB; always compare against original; three metrics jointly observed; area strata, exclude same direct asset directory; conservative empirical upper-tail fraction, ties included, +1 correction; low priority number first, break ties by asset id. List budgets ceil(10%,15%).",
                all_colors=938,high_psnr=len(all_rows),common_valid=len(valid),
                raw_nonmissing={k:sum(r[k] is not None for r in all_rows) for k in SIGNALS},
                fallback=sum(r["ref_scope"]!="same_area_other_directories" for r in valid),
                by_area=diagnostics,metrics=evaluation,known=[r for r in valid if r["id"] in KNOWN],
                comparison50=sampled_pairs())
    (HERE/"fixed8-summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"n":len(valid),"by_area":diagnostics,"fallback":result["fallback"],"metrics":evaluation},ensure_ascii=True))


if __name__=="__main__":
    main()
