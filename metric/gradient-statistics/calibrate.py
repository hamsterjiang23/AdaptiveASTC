"""Screen PSNR-matched ASTC pairs against a family-disjoint development reference."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import numpy as np

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent / "gradient-screen-50"
SEED = "astc-gradient-stats-group-split-v1"
HIGH = "both_ge35"
FAMILIES = {
    "block_seam": ("grid_excess_p95", "continuous_seam", "phase_adjusted"),
    "flat_steps": ("platform_score", "plateau_px"),
    "banding": ("wang_fr", "cambi_fr"),
    "local_error": ("masked_flip_p95", "worst_patch_psnr_db", "area_under_28"),
    "overall": ("ssim", "ssimulacra2", "lpips_alex", "flip_p99", "gmsd"),
}
METRICS = tuple(k for fields in FAMILIES.values() for k in fields)
HIGHER_QUALITY = {"ssim", "ssimulacra2", "worst_patch_psnr_db"}
Key = tuple[str, int, str]
Value = str | int | float | None
Record = dict[str, Value]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(filename: str, rows: list[Record]) -> None:
    with (HERE / filename).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def numeric(value: object) -> float | None:
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def difference(a: object, b: object) -> float | None:
    a, b = numeric(a), numeric(b)
    return None if a is None or b is None else b-a


@dataclass
class Asset:
    idx: int
    group: str
    width: int
    stratum: str
    psnr_delta: float
    view_psnr_delta: float
    deltas: dict[str, float | None]
    boundary_pairs: int | None = None

    def strict(self) -> bool:
        return max(abs(self.psnr_delta), abs(self.view_psnr_delta)) <= 0.1


@dataclass(frozen=True)
class Scale:
    denom: float
    label: str
    n: int


@dataclass
class Score:
    asset: Asset
    normalized: dict[str, float]
    by_family: dict[str, float]

    def max_score(self) -> float:
        return max(self.by_family.values())

    def family_winner(self, family: str) -> str:
        return max((k for k in FAMILIES[family] if k in self.normalized), key=self.normalized.get)


def stable_key(value: str) -> str:
    return hashlib.sha256(f"{SEED}/{value}".encode()).hexdigest()


def dimensions(lst: list[dict], key: str) -> dict[int, dict]:
    indexed = {int(r[key]):r for r in lst}
    assert len(indexed) == len(lst)
    return indexed


def inputs() -> tuple[list[Asset], list[Asset]]:
    base = dimensions(load_csv(HERE / "reference.csv"), "id")
    color = dimensions(load_csv(HERE / "reference-banding.csv"), "id")
    assert set(base) == set(color)
    refs = []
    for idx, raw in base.items():
        merged = {**raw, **color[idx]}
        deltas = {k:numeric(merged[k]) for k in METRICS}
        refs.append(Asset(idx, raw["group"], int(raw["width"]), raw["stratum"],
                          float(raw["unity_psnr_db"]), float(raw["view_psnr_db"]), deltas,
                          int(raw["boundary_pairs"])))
    comparison = json.loads((PANEL / "comparisons.json").read_bytes())["samples"]
    support = dimensions(json.loads((PANEL / "evidence/mask-support.json").read_bytes()), "id")
    targets = []
    for raw in comparison:
        a,b = raw["values"]["a"],raw["values"]["b"]
        deltas = {k:difference(a[k], b[k]) for k in METRICS}
        targets.append(Asset(raw["id"], raw["group"], raw["width"], raw["stratum"],
                             b["unity_psnr_db"]-a["unity_psnr_db"], b["view_psnr_db"]-a["view_psnr_db"], deltas,
                             support[raw["id"]]["boundary_pairs"]))
    assert len(targets) == 50
    assert not ({r.group for r in refs} & {r.group for r in targets})
    assert not ({r.idx for r in refs} & {r.idx for r in targets})
    assert all(max(abs(r.psnr_delta), abs(r.view_psnr_delta)) <= .5 for r in refs+targets)
    return refs,targets


def split_reference(refs: list[Asset]) -> tuple[list[Asset], list[Asset], list[Record]]:
    families = defaultdict(list)
    for sample in refs:
        families[sample.group].append(sample)
    chosen = [min(group,key=lambda r: stable_key(f"image/{r.idx}")) for group in families.values()]
    ordered = sorted(chosen,key=lambda r:stable_key(f"partition/{r.group}"))
    fit, calibration = ordered[::2], ordered[1::2]
    sets = {r.idx:"fit" for r in fit} | {r.idx:"calibration" for r in calibration}
    rows = [dict(id=r.idx,group=r.group,width=r.width,stratum=r.stratum,role=sets.get(r.idx,"other_same_group"),
                 native_delta=r.psnr_delta,display_delta=r.view_psnr_delta)
            for r in sorted(refs,key=lambda r:r.idx)]
    return fit,calibration,rows


def fit_scales(fit: list[Asset], widths: set[int], strata: set[str]) -> dict[Key,Scale]:
    scales = {}
    for width in sorted(widths):
        for stratum in sorted(strata):
            same_stratum = [r for r in fit if r.stratum == stratum]
            cohorts = [("same_size_psnr", [r for r in same_stratum if r.width == width]),
                       ("same_psnr", same_stratum), ("all_fitting", fit)]
            for metric in METRICS:
                for label,cohort in cohorts:
                    absolute = [abs(r.deltas[metric]) for r in cohort if r.deltas[metric] is not None]
                    if len(absolute) < 20 or not any(absolute):
                        continue
                    denom = float(np.quantile(absolute, .90))
                    if denom <= 0:
                        denom = median(x for x in absolute if x > 0)
                        label += "_positive_median"
                    scales[metric,width,stratum] = Scale(denom,label,len(absolute))
                    break
    return scales


def apply_scales(asset: Asset, scales: dict[Key,Scale]) -> Score:
    norm = {}
    for metric,delta in asset.deltas.items():
        scale = scales.get((metric,asset.width,asset.stratum))
        if delta is not None and scale:
            norm[metric] = abs(delta)/scale.denom
    families = {}
    for family,metrics in FAMILIES.items():
        vals = [norm[m] for m in metrics if m in norm]
        if vals:
            families[family] = max(vals)
    assert families
    return Score(asset, norm, families)


def tail(score: float | None, reference: list[float]) -> float | None:
    if score is None or not reference:
        return None
    return (1 + sum(v >= score for v in reference)) / (1+len(reference))


def holm(pvalues: dict[int,float]) -> dict[int,float]:
    out = {}
    cumulative = 0.
    for i,(idx,p) in enumerate(sorted(pvalues.items(),key=lambda it:(it[1],it[0]))):
        cumulative = max(cumulative,(len(pvalues)-i)*p)
        out[idx] = min(1.,cumulative)
    return out


def direction(metric: str, delta: float | None) -> str:
    if delta is None:
        return "missing"
    if delta == 0:
        return "same"
    if metric == "plateau_px":
        return "B_longer" if delta > 0 else "A_longer"
    return "A_worse" if (delta>0) == (metric in HIGHER_QUALITY) else "B_worse"


def outputs(test: list[Score], calibration: list[Score], scales: dict[Key,Scale]) -> tuple[list[Record],list[Record],list[Record]]:
    rows, families, details = [], [], []
    for score in test:
        t = score.asset
        cohort = [s for s in calibration if s.asset.stratum == t.stratum]
        exact_size = [s for s in cohort if s.asset.width == t.width]
        strict = [s for s in cohort if s.asset.strict()]
        exact_mask = [s for s in cohort if s.normalized.keys() == score.normalized.keys()]
        maxscore = score.max_score()
        family = max(score.by_family,key=score.by_family.get)
        leading = score.family_winner(family)
        primary = tail(maxscore,[s.max_score() for s in cohort])
        row = dict(id=t.idx, group=t.group, width=t.width, stratum=t.stratum, native_psnr_delta=t.psnr_delta,
                   display_psnr_delta=t.view_psnr_delta, n_metrics=len(score.normalized), n_families=len(score.by_family),
                   strongest_family=family, strongest_metric=leading, delta_strongest=t.deltas[leading], direction=direction(leading,t.deltas[leading]),
                   score=maxscore, n_cal=len(cohort), p_any=primary, p_any_holm50=None,
                   n_cal_same_size=len(exact_size), p_any_same_size=tail(maxscore,[s.max_score() for s in exact_size]),
                   n_cal_same_metric_pattern=len(exact_mask),p_any_same_metric_pattern=tail(maxscore,[s.max_score() for s in exact_mask]),
                   qualifies_both_0p1=int(t.strict()), n_cal_within_0p1=len(strict) if t.strict() else None,
                   p_any_within_0p1=tail(maxscore,[s.max_score() for s in strict]) if t.strict() else None,
                   boundary_pairs=t.boundary_pairs, small_boundary_support=int(0 < t.boundary_pairs < 20))
        rows.append(row)
        for f,items in FAMILIES.items():
            available = [m for m in items if m in score.normalized]
            rivals = [r.by_family[f] for r in cohort if f in r.by_family]
            win = score.family_winner(f) if available else None
            fp = tail(score.by_family.get(f),rivals)
            flags = []
            for m in items:
                rs = [r.normalized[m] for r in cohort if m in r.normalized]
                v = score.normalized.get(m)
                p = tail(v,rs)
                scale = scales.get((m,t.width,t.stratum))
                delta = t.deltas[m]
                d = direction(m,delta)
                details.append(dict(id=t.idx,family=f,metric=m,signed_delta_B_minus_A=delta,direction=d,
                                    n_fit=scale.n if scale else 0,scale_abs_delta=scale.denom if scale else None,
                                    scale_origin=scale.label if scale else None,relative_abs_delta=v,
                                    n_cal=len(rs),marginal_tail=p))
                if p is not None and p<=.1:
                    flags.append(f"{m}:{d}")
            families.append(dict(id=t.idx,family=f,n_available=len(available),n_cal=len(rivals),
                                 strongest_metric=win,direction=direction(win,t.deltas[win]) if win else "missing",
                                 score=score.by_family.get(f),family_tail=fp,
                                 marginal_top10_direction=";".join(flags),all_family_select_adjustment=row["p_any"]))
    corrected = holm({r["id"]:r["p_any"] for r in rows})
    for row in rows:
        row["p_any_holm50"] = corrected[row["id"]]
    rows.sort(key=lambda r:(r["p_any"],-r["score"],r["id"]))
    return rows,families,details


def checks() -> None:
    assert tail(1.,[1.,1.,1.]) == 1.
    assert tail(2.,[0.,1.,1.]) == .25
    assert direction("ssim",-.1) == direction("lpips_alex",.1) == "B_worse"
    assert direction("ssim",.2) == direction("lpips_alex",-.2) == "A_worse"
    assert holm({1:.02,2:.01,3:.78}) == {2:.03,1:.04,3:.78}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke",action="store_true")
    smoke = parser.parse_args().smoke
    checks()
    if smoke:
        print("Conservative tied tails, signed directions, Holm example passed.")
        return
    refs,targets = inputs()
    fit,calibration,split_rows = split_reference(refs)
    all_assets = [*refs,*targets]
    scales = fit_scales(fit,{r.width for r in all_assets},{r.stratum for r in all_assets})
    test = [apply_scales(r,scales) for r in targets]
    cal = [apply_scales(r,scales) for r in calibration]
    rows,families,details = outputs(test,cal,scales)
    write_csv("reference-partition.csv",split_rows)
    write_csv("calibration-scores.csv",[dict(id=s.asset.idx,width=s.asset.width,stratum=s.asset.stratum,
              n_metrics=len(s.normalized),n_families=len(s.by_family),max_all=s.max_score(),**{f:s.by_family.get(f) for f in FAMILIES}) for s in cal])
    write_csv("statistical-screen.csv",rows)
    write_csv("family-tail.csv",families)
    write_csv("metric-tail.csv",details)
    write_csv("fit-scales.csv",[dict(metric=k[0],width=k[1],stratum=k[2],denominator=v.denom,scope=v.label,n=v.n)
                                for k,v in scales.items()])
    report = dict(seed=SEED,families=FAMILIES,n_refs=len(refs),n_heldout_test_groups=len({s.group for s in targets}),
                  n_fit=len(fit),n_calibration=len(calibration),fit_strata=dict(Counter(r.stratum for r in fit)),
                  calibration_strata=dict(Counter(r.stratum for r in calibration)),n_test=len(test),
                  per_image_alpha_05=[r["id"] for r in rows if r["p_any"]<=.05],
                  per_image_alpha_10=[r["id"] for r in rows if r["p_any"]<=.1],
                  holm_50_alpha_05=[r["id"] for r in rows if r["p_any_holm50"]<=.05],
                  strict_0p1=[r for r in rows if r["qualifies_both_0p1"]],
                  known=[r for r in rows if r["id"] in (615,616,617)])
    (HERE / "statistical-screen.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    assert len(rows)==50 and len(families)==250 and len(details)==len(rows)*len(METRICS)
    print("fit",len(fit),"calibration",len(calibration),"50 cases",report["per_image_alpha_05"],report["per_image_alpha_10"])
    print("Known",[(r["id"],r["p_any"],r["strongest_metric"],r["direction"]) for r in report["known"]])


if __name__ == "__main__":
    main()
