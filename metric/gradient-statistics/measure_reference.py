"""Compute signed B-A changes on the frozen, group-disjoint reference manifest."""
from __future__ import annotations

import argparse
import csv
import hashlib
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
from scipy.ndimage import label

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT/"tmp/multimetric-review-20261118"
sys.path[:0] = [str(BASE/"work"),str(BASE/"blocks/metrics/runtime"),str(ROOT/"metric/gradient-screen"),
               str(ROOT/"tmp/metric-handbook-20261119/special"),str(ROOT/"tmp/gradient-psnr-pair-experiment/matched")]
import flip_evaluator
from metrics import gmsd, psnrb
from phase_screen import phase_peaks, phase_score
from prepare import LUT
from run import accelerated_platform
from seam_metric import evaluate, gradient_mask, lab, rgb
from reference_selection import DATA, PANEL, sha

Row = dict[str, object]
ARCHIVE = {"psnr":"unity_psnr_db","viewpsnr":"view_psnr_db","ms":"unity_ms_ssim_db","ssim":"ssim","ss2":"ssimulacra2",
           "lpips":"lpips_alex","flip":"flip_mean","fp99":"flip_p99","worst":"worst_patch_psnr_db",
           "a28":"area_under_28","a30":"area_under_30","a32":"area_under_32"}


def valid(value: object) -> bool:
    return isinstance(value,(int,float)) and math.isfinite(value)


def rgba(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA"))


def mse(ref: np.ndarray, test: np.ndarray) -> float:
    return float(np.square(ref.astype(np.int32)-test.astype(np.int32)).mean())


def support(mask: np.ndarray) -> int:
    count = 0
    for axis in (0,1):
        m = np.swapaxes(mask,axis,0)
        valid_edge = m[:-3]&m[1:-2]&m[2:-1]&m[3:]
        grid = np.arange(2,len(m)-1)
        native = len(m)-grid if axis==0 else grid
        count += int(valid_edge[native%8==0].sum())
    return count


def measure(item: Row) -> Row:
    ref = rgb(ROOT/item["reference"])
    ref_lab = lab(ref)
    mask = gradient_mask(ref_lab)
    weights = np.array([.299,.587,.114])
    ref_y = ref.astype(float)@weights
    ref_srgb = ref.astype(np.float32)/255
    raw_ref = rgba(Path(item["native_reference"])) if item["view"]=="dark" else None
    saved = []
    for tag in ("a","b"):
        test = rgb(ROOT/item["decoded_"+tag])
        assert test.shape == ref.shape
        test_lab = lab(test)
        base,_ = evaluate(ref_lab,test_lab,mask,8)
        shifted,phase = phase_score(phase_peaks(ref_lab,test_lab,mask))
        own = gradient_mask(test_lab)
        groups,n = label(own)
        largest = int(np.bincount(groups[own]).max()) if n else 0
        y = test.astype(float)@weights
        profile = accelerated_platform(ref_y,y)
        block = psnrb(ref_y,y,8)
        heat,mean,_ = flip_evaluator.evaluate(ref_srgb,test.astype(np.float32)/255,"LDR",inputsRGB=True,applyMagma=False,
                computeMeanError=True,parameters={"ppd":67.})
        archive = item["archive_"+tag]
        flip_p95,flip_p99 = np.quantile(heat,[.95,.99])
        assert np.isclose(mean,archive["flip"],rtol=0,atol=1e-7)
        assert np.isclose(flip_p99,archive["fp99"],rtol=0,atol=1e-7)
        values = {dest:archive[key] for key,dest in ARCHIVE.items()}
        for t in (28,30,32):
            name = f"area_under_{t}"
            values[name] *= 100
        values.update(display_mse=mse(ref,test),flip_p95=float(flip_p95),masked_flip_p95=float(np.quantile(heat[:,:,0][mask],.95)) if mask.any() else None,
                      alpha_only_mse=None,rgb_only_mse=None,gmsd=gmsd(ref_y,y),psnrb_db=block["score_db"],psnrb_bef=block["bef"],
                      mask_area_pct=100*float(own.mean()),mask_largest_px=largest,mask_largest_pct=100*largest/own.size,
                      gradient_change_p95=base["gradient_change_p95"],grid_excess_p95=base["grid_excess_p95"],continuous_seam=base["continuous_seam"],
                      shifted_median=shifted,phase_adjusted=phase,platform_score=profile["score"],plateau_px=profile["plateau_px"],
                      plateau_jump_ref=profile["jump_R"],plateau_jump_decoded=profile["jump_D"])
        if raw_ref is not None:
            raw_test = rgba(Path(item["native_"+tag]))
            assert np.array_equal(LUT["dark"][raw_test[...,3,None],raw_test[...,:3]],test)
            values.update(alpha_only_mse=mse(ref,LUT["dark"][raw_test[...,3,None],raw_ref[...,:3]]),
                          rgb_only_mse=mse(ref,LUT["dark"][raw_ref[...,3,None],raw_test[...,:3]]))
        saved.append(values)
    row = {k:item[k] for k in ("id","asset","group","view","width","height","stratum","preset_a","preset_b","native_psnr_a","native_psnr_b","display_psnr_a","display_psnr_b")}
    row.update(reference_gradient_pixels=int(mask.sum()),boundary_pairs=support(mask))
    a,b = saved
    for field in a:
        row[field] = b[field]-a[field] if valid(a[field]) and valid(b[field]) else None
    return row


def join_inputs(records: list[Row]) -> list[Row]:
    display = {r["id"]:r for r in json.loads(DATA.read_text(encoding="utf-8").split("=",1)[1][:-1])["assets"]}
    native = {(r["validation_index"],r["preset"]):r for r in json.loads((BASE/"population/fixed8_manifest.json").read_bytes())}
    for r in records:
        for t in ("a","b"):
            idx,preset = r["id"],r["preset_"+t]
            r["archive_"+t] = next(v for v in display[idx]["rows"] if (v["preset"],v["view"])==(preset,r["view"]))
            source = native[idx,preset]
            assert source["block"]==8
            r["native_"+t] = source["decoded_path"]
            r["native_reference"] = source["reference_path"]
    return records


def smoke() -> None:
    seed = json.loads((PANEL/"comparisons.json").read_bytes())["samples"]
    for r in join_inputs([u.copy() for u in seed if u["id"] in (615,520,698)]):
        result = measure(r)
        for field,left in r["values"]["a"].items():
            if field not in result:
                continue
            right = r["values"]["b"][field]
            if valid(left) and valid(right):
                assert math.isclose(result[field],right-left,abs_tol=2e-7), (r["id"],field,result[field],right-left)
            else:
                assert result[field] is None
    print("Matched all available reference metric changes on 3 prior panel pairs (dark/RGB, small/supported/unsupported).",flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--workers",type=int,default=4,choices=range(1,5))
    args=parser.parse_args()
    smoke()
    if args.smoke:
        return
    manifest = HERE/"reference-selection.json"
    inputs = join_inputs(json.loads(manifest.read_bytes())["pairs"])
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = []
        for r in pool.map(measure,inputs,chunksize=2):
            rows.append(r)
            if len(rows)%30 == 0:
                print(f"{len(rows)}/{len(inputs)}",flush=True)
    assert len(rows)==len(inputs)
    output = HERE/"reference.csv"
    with output.open("w",encoding="utf-8-sig",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    count = {k:sum(valid(r[k]) for r in rows) for k in rows[0] if k not in ("id","width","height") and any(valid(r[k]) for r in rows)}
    receipt = dict(assets=len(rows), groups=len({r["group"] for r in rows}),selection_sha256=sha(manifest),
                   scores_sha256=sha(output), workers=args.workers, valid_counts=count, orientation="B minus A, native input size",
                   smoke="Independent comparison with three saved 50-panel pairs for every overlapping field; excluded from reference after smoke.")
    (HERE/"reference-checks.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(count,flush=True)


if __name__ == "__main__":
    main()
