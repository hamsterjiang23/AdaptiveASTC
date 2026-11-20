"""Screen for sustained gradient seams specific to the true ASTC grid."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
import numpy as np

from run_screen import HERE, KNOWN, MEDIA, Row, inputs
from seam_metric import gradient_mask, lab, rgb


def phase_peaks(reference_lab: np.ndarray, decoded_lab: np.ndarray, mask: np.ndarray, block: int = 8) -> list[float | None]:
    """Maximum four-pixel sustained Lab edge for each grid offset, pooling both axes."""
    if block < 2:
        raise ValueError("A block must have at least two grid phases")
    if mask.shape != reference_lab.shape[:2] or decoded_lab.shape != reference_lab.shape:
        raise ValueError("Input geometry differs")
    peaks = np.full(block, -np.inf)
    if not mask.any():
        return [None] * block
    for axis in (0, 1):
        ref = np.swapaxes(reference_lab, axis, 0)
        test = np.swapaxes(decoded_lab, axis, 0)
        valid = np.swapaxes(mask, axis, 0)
        if min(valid.shape) < 4:
            continue
        # Chunking only partitions the search. Three extra gradient samples support
        # the first/last cross-edge comparison in a chunk; segments run on axis 1.
        for start in range(2, len(ref)-1, 96):
            stop = min(len(ref)-1, start+96)
            tile = slice(start-2, stop+1)
            native_error = np.linalg.norm(np.diff(test[tile], axis=0), axis=2) - np.linalg.norm(np.diff(ref[tile], axis=0), axis=2)
            increments = np.maximum(0., native_error)
            extra = np.maximum(0., increments[1:-1] - (increments[:-2] + increments[2:])/2)
            mask_tile = valid[tile]
            supported = mask_tile[:-3] & mask_tile[1:-2] & mask_tile[2:-1] & mask_tile[3:]
            segments = np.lib.stride_tricks.sliding_window_view(extra, 4, axis=1).min(axis=-1)
            support = np.lib.stride_tricks.sliding_window_view(supported, 4, axis=1).all(axis=-1)
            per_edge = np.where(support, segments, -np.inf).max(axis=1)
            edge = np.arange(start, stop)
            native_edge = len(ref)-edge if axis == 0 else edge
            np.maximum.at(peaks, native_edge % block, per_edge)
    return [float(v) if np.isfinite(v) else None for v in peaks]


def phase_score(peaks: list[float | None]) -> tuple[float | None, float | None]:
    """Shifted-grid median and positive excess. Require evidence at every phase."""
    if any(x is None for x in peaks):
        return None, None
    median = float(np.median(peaks[1:]))
    return median, max(0., float(peaks[0]) - median)


def measure(row: Row) -> Row:
    folder = MEDIA / f"{int(row['id']):04d}"
    ref = lab(rgb(folder / f"ref-{row['view']}.png"))
    assert ref.shape[:2] == (row["height"], row["width"])
    mask = gradient_mask(ref)
    test = lab(rgb(folder / f"fastest-{row['view']}.png"))
    peaks = phase_peaks(ref, test, mask)
    median, score = phase_score(peaks)
    return {**row, "phase_adjusted":score, "continuous_seam":peaks[0], "shifted_median":median,
            "supported_phases":sum(p is not None for p in peaks), **{f"phase_{i}":v for i,v in enumerate(peaks)}}


def check() -> None:
    x = np.indices((128,128))[1]
    ref = (100+x/4)[:,:,None]
    mask = np.ones(x.shape, dtype=bool)
    assert phase_score(phase_peaks(ref,ref,mask)) == (0.,0.)
    isolated = ref.copy()
    isolated[50,48] += 18
    assert phase_score(phase_peaks(ref,isolated,mask)) == (0.,0.)
    for shift,expected in ((0,1.75),(3,0.)):
        stair = (100+((x+shift)//8)*2)[:,:,None]
        assert phase_score(phase_peaks(ref,stair,mask)) == (0.,expected)
    assert phase_score(phase_peaks(ref[:3],ref[:3],mask[:3])) == (None,None)


def describe(rows: list[Row]) -> dict[str, object]:
    valid = [r for r in rows if r["phase_adjusted"] is not None]
    result = {}
    metrics = ["phase_adjusted", "continuous_seam", "flip_p99", "native_psnr"]
    if rows and "grid_excess_p95" in rows[0]:
        metrics += ["grid_excess_p95","gradient_change_p95"]
    for metric in metrics:
        direction = 1 if metric == "native_psnr" else -1
        ordered = sorted(valid, key=lambda r:(direction*float(r[metric]),int(r["id"])))
        ranks = {int(r["id"]):i for i,r in enumerate(ordered,1) if r["id"] in KNOWN}
        cuts = {}
        for pct in (5,10,15,20):
            limit = math.ceil(len(ordered)*pct/100)
            hit = [i for i in KNOWN if ranks.get(i,math.inf)<=limit]
            cuts[pct] = {"budget":limit,"known_hits":len(hit),"ids":hit}
        result[metric] = {"known_ranks":ranks,"budgets":cuts,"top_20_ids":[r["id"] for r in ordered[:20]]}
    return {"population":len(rows),"common_valid":len(valid),"missing":len(rows)-len(valid),"metrics":result}


def summarize(scored: list[Row]) -> None:
    available = HERE / "fixed8-validation.csv"
    if available.is_file():
        with available.open(encoding="utf-8-sig", newline="") as handle:
            baseline = {int(r["id"]):r for r in csv.DictReader(handle)}
        assert len(baseline) == len(scored) == 938
        for r in scored:
            prior = baseline[int(r["id"])]
            raw_peak = r["continuous_seam"]
            assert (raw_peak is None and not prior["continuous_seam"]) or float(prior["continuous_seam"]) == raw_peak
            for key in ("grid_excess_p95","gradient_change_p95"):
                r[key] = float(prior[key]) if prior[key] else None
    subsets = {"all":scored,"native_psnr_ge35":[r for r in scored if r["native_psnr"] >= 35],
               "128x128":[r for r in scored if r["width"]==r["height"]==128],
               "128x128_psnr_ge35":[r for r in scored if r["width"]==r["height"]==128 and r["native_psnr"]>=35]}
    results = {"preset":"fastest", "block":8, "development_images":len(scored),
               "known_after_scoring":KNOWN, "known":[r for r in scored if r["id"] in KNOWN],
               "rank_method":"All metrics ranked on exactly the same population with all eight grid phases available. Greatest error first; lowest native PSNR first. Break ties by image ID; round review budgets up.",
               "subsets":{k:describe(v) for k,v in subsets.items()}}
    (HERE/"phase-summary.json").write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    for name,subset in results["subsets"].items():
        print(name, subset["population"], subset["common_valid"], subset["metrics"]["phase_adjusted"]["known_ranks"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers",type=int,default=3,choices=(1,2,3))
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--summarize",action="store_true",help="Rebuild the summary from saved scores after the baseline has finished.")
    args = parser.parse_args()
    check()
    rows = inputs()
    if args.summarize:
        with (HERE / "phase-validation.csv").open(encoding="utf-8-sig",newline="") as handle:
            cached = {int(r["id"]):r for r in csv.DictReader(handle)}
        assert len(cached) == len(rows)
        for r in rows:
            cached_row = cached[int(r["id"])]
            assert cached_row["asset"] == r["asset"] and cached_row["view"] == r["view"]
            for key in ("phase_adjusted","continuous_seam","shifted_median",*[f"phase_{i}" for i in range(8)]):
                r[key] = float(cached_row[key]) if cached_row[key] else None
            r["supported_phases"] = int(cached_row["supported_phases"])
        summarize(rows)
        return
    if args.smoke:
        expected = {615:13.030575778027341,616:11.159468128927706,617:10.443829215237498}
        for r in rows:
            if r["id"] in expected:
                assert np.isclose(measure(r)["phase_adjusted"],expected[r["id"]],rtol=1e-12)
            if r["id"] in (827,839,846):
                assert measure(r)["phase_adjusted"] is None
        print("Three known samples, three narrow images and synthetic grid controls passed.")
        return
    for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):
        os.environ[name] = "1"
    scored = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(measure, rows, chunksize=2):
            scored.append(row)
            if len(scored)%150 == 0:
                print(f"{len(scored)}/{len(rows)}", flush=True)
    scored.sort(key=lambda r:(r["phase_adjusted"] is None,-(r["phase_adjusted"] or 0),r["id"]))
    with (HERE / "phase-validation.csv").open("w",encoding="utf-8-sig",newline="") as handle:
        writer = csv.DictWriter(handle,fieldnames=list(scored[0]))
        writer.writeheader()
        writer.writerows(scored)
    summarize(scored)


if __name__ == "__main__":
    main()
