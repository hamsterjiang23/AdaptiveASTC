"""Enumerate distinct real 8x8 outputs under two near-zero PSNR differences."""
from __future__ import annotations

import csv
import itertools
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for setting in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[setting] = "1"
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0,str(ROOT/"metric/gradient-screen-50"))
sys.path.insert(0,str(ROOT/"tmp/gradient-psnr-pair-experiment/matched"))
from select_samples import DATA, PRESETS, file_for, pixels
from run import accelerated_platform


def luminance(path: str) -> np.ndarray:
    with Image.open(ROOT/path) as im:
        return np.asarray(im.convert("RGB"),dtype=float)@np.array([.299,.587,.114])


def measure_asset(asset: dict) -> list[dict]:
    view = "dark" if "dark" in asset["views"] else "rgb"
    idx = asset["id"]
    candidates = {r["preset"]:r for r in asset["rows"] if r["view"]==view}
    source = None
    profiles = {}
    rows = []
    for a,b in itertools.combinations(PRESETS,2):
        first,second=candidates[a],candidates[b]
        if not all(isinstance(r[k],(float,int)) and math.isfinite(r[k]) for r in (first,second) for k in ("psnr","viewpsnr")):
            continue
        tolerance=max(abs(first[k]-second[k]) for k in ("psnr","viewpsnr"))
        if tolerance>.1 or pixels(file_for(idx,a,view))==pixels(file_for(idx,b,view)):
            continue
        if source is None:
            source=luminance(file_for(idx,"ref",view))
        for preset in (a,b):
            if preset not in profiles:
                profiles[preset] = accelerated_platform(source,luminance(file_for(idx,preset,view)))
        p, q = profiles[a], profiles[b]
        rows.append(dict(id=idx,asset=asset["asset"],view=view,width=asset["w"],preset_a=a,preset_b=b,
                         unity_a=first["psnr"],unity_b=second["psnr"],display_a=first["viewpsnr"],display_b=second["viewpsnr"],
                         tolerance=tolerance,score_a=p["score"],score_b=q["score"],abs_platform_delta=abs(q["score"]-p["score"]),
                         a_x=p.get("x"),a_y=p.get("y"),b_x=q.get("x"),b_y=q.get("y")))
    return rows


def main() -> None:
    data=json.loads(DATA.read_text(encoding="utf-8").split("=",1)[1][:-1])["assets"]
    assets=[a for a in data if a["w"]==a["h"] and a["w"] in (128,256,512) and a["views"]!=["data"]]
    if "--smoke" in sys.argv:
        out=measure_asset(next(a for a in assets if a["id"]==602))
        test=next(r for r in out if (r["preset_a"],r["preset_b"])==("fastest","fast"))
        assert 0 < test["tolerance"] < .022 and all(k in test for k in ("score_a","score_b"))
        print("A real known pair passed",test["score_a"],test["score_b"])
        return
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows=[r for group in pool.map(measure_asset,assets,chunksize=4) for r in group]
    rows.sort(key=lambda r:(-r["abs_platform_delta"],r["id"],r["preset_a"],r["preset_b"]))
    with (HERE/"near-equal-pairs.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result={}
    for limit in (.1,.01,0):
        for gate in (False,True):
            subset=[r for r in rows if r["tolerance"]<=limit and (not gate or min(r["unity_a"],r["unity_b"])>=35)]
            result[f"{limit}{'_both_native_ge35' if gate else ''}"]=dict(
                pairs=len(subset),assets=len({r["id"] for r in subset}),
                positive_change=sum(r["abs_platform_delta"]>0 for r in subset),
                max_pair=subset[0] if subset else None,median_abs_delta=float(np.median([r["abs_platform_delta"] for r in subset])) if subset else None)
    (HERE/"near-equal-summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print([(k,v["pairs"],v["assets"],v["max_pair"]["abs_platform_delta"] if v["pairs"] else None) for k,v in result.items()])


if __name__=="__main__":
    main()
