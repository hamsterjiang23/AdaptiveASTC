"""Freeze disjoint reference pairs with the existing 50-panel pair-selection rule."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PANEL = ROOT / "metric/gradient-screen-50"
sys.path.insert(0, str(PANEL))
from select_samples import DATA, PRESETS, file_for, key, pixels


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    target = json.loads((PANEL / "selection.json").read_bytes())["samples"]
    target_groups = {r["group"] for r in target}
    target_ids = {r["id"] for r in target}
    assets = json.loads(DATA.read_text(encoding="utf-8").split("=",1)[1][:-1])["assets"]
    frozen = []
    counts = Counter()
    for raw in assets:
        if raw["w"] != raw["h"] or raw["w"] not in (128,256,512) or raw["views"] == ["data"]:
            continue
        index = raw["id"]
        view = "dark" if "dark" in raw["views"] else "rgb"
        rows = {r["preset"]:r for r in raw["rows"] if r["view"] == view}
        choices = []
        for a,b in itertools.combinations(PRESETS,2):
            x,y = rows[a],rows[b]
            if not all(isinstance(n,(int,float)) and math.isfinite(n) for n in (x["viewpsnr"],y["viewpsnr"])):
                continue
            if max(abs(x["psnr"]-y["psnr"]),abs(x["viewpsnr"]-y["viewpsnr"])) > .5:
                continue
            if pixels(file_for(index,a,view)) == pixels(file_for(index,b,view)):
                continue
            choices.append((-abs(PRESETS.index(a)-PRESETS.index(b)),key(f"pair/{index}/{a}/{b}"),a,b))
        if not choices:
            continue
        counts["eligible_assets"] += 1
        counts["eligible_pairs"] += len(choices)
        if index in target_ids:
            counts["excluded_target_assets"] += 1
            continue
        if raw["group"] in target_groups:
            counts["excluded_additional_same_group"] += 1
            continue
        _,_,a,b = min(choices)
        ra,rb = rows[a],rows[b]
        frozen.append(dict(id=index,asset=raw["asset"],group=raw["group"],view=view,width=raw["w"],height=raw["h"],
                           stratum="both_ge35" if min(ra["psnr"],rb["psnr"])>=35 else "at_least_one_below35",
                           preset_a=a,preset_b=b,reference=file_for(index,"ref",view),decoded_a=file_for(index,a,view),
                           decoded_b=file_for(index,b,view),native_psnr_a=ra["psnr"],native_psnr_b=rb["psnr"],
                           display_psnr_a=ra["viewpsnr"],display_psnr_b=rb["viewpsnr"]))
    counts.update(reference_assets=len(frozen),reference_groups=len({r["group"] for r in frozen}))
    assert counts["eligible_assets"] == 666 and counts["eligible_pairs"] == 1622 and counts["excluded_target_assets"]==50
    assert not {r["group"] for r in frozen} & target_groups
    out = dict(protocol="Same validation pool and 0.5 dB double-PSNR eligibility. One eligible pair per asset, hard exclusion of all 48 panel asset groups, including other Ring sprites. The fastest-to-exhaustive ordering defines the signed change B-A. Equal span ties use original seed SHA256. Asset groups can repeat inside this reference pool.",
               input_sha=sha(DATA),panel_sha=sha(PANEL/"selection.json"),counts=dict(counts),
               sizes=dict(Counter(r["width"] for r in frozen)),strata=dict(Counter(r["stratum"] for r in frozen)),
               views=dict(Counter(r["view"] for r in frozen)),pairs=frozen)
    (HERE/"reference-selection.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(counts,out["sizes"],out["strata"],out["views"],flush=True)


if __name__ == "__main__":
    main()
