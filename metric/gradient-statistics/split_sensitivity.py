"""Keep the 277 representatives and frozen scoring rule; vary only the reference split."""
from __future__ import annotations

import hashlib
from collections import defaultdict

import numpy as np

import calibrate as model


def main() -> None:
    refs, targets = model.inputs()
    original_fit, original_cal, _ = model.split_reference(refs)
    representatives = original_fit + original_cal
    strata = {r.stratum for r in representatives}
    sizes = {r.width for r in representatives}
    tails = defaultdict(list)
    for repeat in range(30):
        def order(asset: model.Asset) -> str:
            return hashlib.sha256(f"fixed-reps-sensitivity-v1/{repeat}/{asset.group}".encode()).hexdigest()
        ordered = sorted(representatives,key=order)
        fitting,calibration = ordered[::2],ordered[1::2]
        scales = model.fit_scales(fitting,sizes,strata)
        calibration_by_stratum = defaultdict(list)
        for asset in calibration:
            calibration_by_stratum[asset.stratum].append(model.apply_scales(asset,scales).max_score())
        for asset in targets:
            score = model.apply_scales(asset,scales).max_score()
            tails[asset.idx].append(model.tail(score,calibration_by_stratum[asset.stratum]))
    rows = [dict(id=idx,splits=len(values),in_05=sum(x<=.05 for x in values),in_10=sum(x<=.1 for x in values),
                 min_tail=min(values),median_tail=float(np.median(values)),max_tail=max(values))
            for idx,values in sorted(tails.items())]
    model.write_csv("split-sensitivity.csv",rows)
    print([(r["id"],r["in_05"],r["in_10"]) for r in rows if r["id"] in (698,544,755,132,615,616,617)])


if __name__=="__main__":
    main()
