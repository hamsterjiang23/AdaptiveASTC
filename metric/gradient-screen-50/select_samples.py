"""Draw a deterministic quality-score-independent panel of real ASTC pairs."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from PIL import Image

DEST = Path(__file__).resolve().parent
ROOT = DEST.parents[1]
DATA = ROOT / "outputs/01a1eca4-b759-74d2-82d5-2d27a4db8e18/data.js"
NATIVE = ROOT / "tmp/multimetric-review-20261118/blocks/source/candidates.jsonl"
PRESETS = ["fastest", "fast", "medium", "thorough", "exhaustive"]
KNOWN = {615:("fast","fastest"),616:("thorough","exhaustive"),617:("thorough","exhaustive")}
SEED = "astc-gradient-50-v1"
Sample = dict[str, str | float | int | bool]


def key(text: str) -> str:
    return hashlib.sha256(f"{SEED}/{text}".encode("utf-8")).hexdigest()


@lru_cache(maxsize=None)
def pixels(path: str) -> str:
    with Image.open(ROOT / path) as image:
        assert image.size in ((128,128),(256,256),(512,512))
        return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def file_for(idx: int, preset: str, view: str) -> str:
    return (DATA.parent / "media" / f"{idx:04d}" / f"{preset}-{view}.png").relative_to(ROOT).as_posix()


def main() -> None:
    assets = {r["id"]:r for r in json.loads(DATA.read_text(encoding="utf-8").split("=",1)[1][:-1])["assets"]}
    pool = defaultdict(list)
    eligible_pairs = 0
    raw_pairs = 0
    scoped = [asset for asset in assets.values() if asset["w"]==asset["h"] and asset["w"] in (128,256,512) and asset["views"]!=["data"]]
    for asset in scoped:
        view = "dark" if "dark" in asset["views"] else "rgb"
        versions = {r["preset"]:r for r in asset["rows"] if r["view"]==view}
        idx = asset["id"]
        for preset_a,preset_b in itertools.combinations(PRESETS,2):
            raw_pairs += 1
            arow,brow=versions[preset_a],versions[preset_b]
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (arow["viewpsnr"],brow["viewpsnr"])):
                continue
            if max(abs(arow["psnr"]-brow["psnr"]),abs(arow["viewpsnr"]-brow["viewpsnr"])) > .5:
                continue
            presets = preset_a,preset_b
            paths = [file_for(idx,p,view) for p in presets]
            if pixels(paths[0]) == pixels(paths[1]):
                continue
            eligible_pairs += 1
            if idx in KNOWN and set(presets) != set(KNOWN[idx]):
                continue
            a,b = KNOWN[idx] if idx in KNOWN else presets
            def stat(preset: str, field: str) -> float:
                return float(versions[preset][field])
            native_a,native_b = stat(a,"psnr"),stat(b,"psnr")
            record = dict(id=idx,asset=assets[idx]["asset"],group=assets[idx]["group"],view=view,known=idx in KNOWN,
                          width=asset["w"],height=asset["h"],block="8x8",preset_a=a,preset_b=b,reference=file_for(idx,"ref",view),
                          decoded_a=file_for(idx,a,view),decoded_b=file_for(idx,b,view),native_psnr_a=native_a,native_psnr_b=native_b,
                          display_psnr_a=stat(a,"viewpsnr"),display_psnr_b=stat(b,"viewpsnr"),
                          stratum="both_ge35" if min(native_a,native_b)>=35 else "at_least_one_below35")
            priority = (-abs(PRESETS.index(a)-PRESETS.index(b)),key(f"pair/{idx}/{a}/{b}"))
            pool[idx].append((priority,record))
    assert raw_pairs == 10*len(scoped)
    chosen = [min(candidates,key=lambda item:item[0])[1] for candidates in pool.values()]
    final = [r for r in chosen if r["known"]]
    used = {r["group"] for r in final}
    assert {r["id"] for r in final} == set(KNOWN)
    quotas=itertools.product(((128,5),(256,10),(512,10)),("both_ge35","at_least_one_below35"))
    for (size,quota),stratum in quotas:
        options = sorted((r for r in chosen if r["width"]==size and r["stratum"]==stratum and not r["known"]),key=lambda r:key(f"asset/{r['id']}"))
        needed = quota - sum(r["width"]==size and r["stratum"]==stratum for r in final)
        for require_new in (True,False):
            for r in options:
                if needed == 0:
                    break
                if (require_new and r["group"] in used) or r in final:
                    continue
                final.append(r)
                used.add(r["group"])
                needed -= 1
        assert needed == 0
    assert len(final) == len({r["id"] for r in final}) == 50
    selected = {r["id"]:r for r in final}
    with NATIVE.open(encoding="utf-8") as f:
        for line in f:
            source = json.loads(line)
            r = selected.get(source["validation_index"])
            if r is None or source["block"] != 12 or source["preset"] != "fastest":
                continue
            assert source["asset"] == r["asset"]
            r["need_alpha"] = source["need_alpha"]
            r["native_reference"] = Path(source["reference_path"]).relative_to(ROOT).as_posix()
            for s in ("a","b"):
                fpath = Path(source["decoded_path"]).with_name(f"8x8_{r['preset_'+s]}.png")
                r["native_decoded_"+s] = fpath.relative_to(ROOT).as_posix()
                assert fpath.is_file()
    final.sort(key=lambda r:(not r["known"],r["id"]))
    for r in final:
        assert "native_reference" in r
        for k in ("reference","decoded_a","decoded_b"):
            r[k+"_rgb_sha256"] = pixels(r[k])
    counts = {"screened_images":len(scoped),"screened_size_counts":dict(Counter(r["w"] for r in scoped)),
              "screened_pairs":raw_pairs,"eligible_pixel_distinct_pairs":eligible_pairs,
              "eligible_assets":len(pool),"eligible_asset_strata":dict(Counter(r["stratum"] for r in chosen)),
              "selected":len(final),"selected_asset_groups":len(used),"selected_strata":dict(Counter(r["stratum"] for r in final)),
              "known":3,"additional":47,"selected_views":dict(Counter(r["view"] for r in final)),
              "selected_sizes":dict(Counter(r["width"] for r in final))}
    payload = dict(protocol={"scope":"development validation, all color images measuring exactly 128/256/512 square, original resolution, 8x8",
                         "psnr":"absolute Unity and display RGB PSNR differences both <=0.5 dB; distinct decoded RGB pixel SHA256",
                         "known":"615 fast/fastest; 616 and 617 thorough/exhaustive; prespecified known images from previous experiment",
                         "choose_pair":"largest difference in encoding-preset index, then lexical SHA256(seed/pair/id/a/b)",
                         "choose_image":"10 / 20 / 20 by native square size 128/256/512; split each size equally between both native PSNR >=35 and other; mandatory known images count towards quotas; order by SHA256(seed/asset/id); prefer one item per asset group across the full panel. Ascending size, high PSNR stratum then other. No quality scores except PSNR used for selection.","seed":SEED},
                   counts=counts,samples=final)
    (DEST/"selection.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(counts)


if __name__ == "__main__":
    main()
