"""Apply the 50-panel native-size banding protocol to the frozen reference pairs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "gradient-screen-50"))
from banding import cambi, display_luma, edge_pixels, wang

Metadata = dict[str, object]


def wang_pair(asset: Metadata) -> dict[str, float | int | None]:
    paths = [ROOT / str(asset[key]) for key in ("reference", "decoded_a", "decoded_b")]
    source_image = display_luma(paths[0])
    source = edge_pixels(source_image)
    values = []
    for path in paths[1:]:
        decoded = display_luma(path)
        assert decoded.shape == source_image.shape
        values.append(wang(source, edge_pixels(decoded), decoded.shape))
    return {"id":int(asset["id"]), "wang_nr":values[1][0]-values[0][0],
            "wang_fr":values[1][1]-values[0][1], "cambi_nr":None, "cambi_fr":None}


def fill_cambi(assets: list[Metadata], result: dict[int, dict]) -> None:
    for size in (256, 512):
        selected = [s for s in assets if s["width"] == size]
        for start in range(0,len(selected),24):
            chunk = selected[start:start+24]
            pairs = [(ROOT / str(s["reference"]), ROOT / str(s[k])) for s in chunk for k in ("decoded_a","decoded_b")]
            values = cambi(size,pairs)
            for s,a,b in zip(chunk,values[::2],values[1::2],strict=True):
                assert a["cambi_source"] == b["cambi_source"]
                row = result[int(s["id"])]
                row["cambi_nr"] = b["cambi"] - a["cambi"]
                row["cambi_fr"] = b["cambi_full_reference"] - a["cambi_full_reference"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke",action="store_true")
    args = parser.parse_args()
    if args.smoke:
        panel = HERE.parent/"gradient-screen-50"
        selected = json.loads((panel/"selection.json").read_bytes())["samples"]
        checks = json.loads((panel/"evidence/banding.json").read_bytes())
        sample = [next(s for s in selected if s["width"]==w) for w in (128,256,512)]
        rows = {int(s["id"]):wang_pair(s) for s in sample}
        fill_cambi(sample,rows)
        for idx,row in rows.items():
            a,b = [checks[str(idx)][k] for k in ("a","b")]
            for k in ("wang_nr","wang_fr","cambi_nr","cambi_fr"):
                assert (row[k] is None and a[k] is None and b[k] is None) or abs(row[k]-(b[k]-a[k]))<1e-6
        print("3 sizes, 12 differences and missing values reproduced.")
        return
    manifest = HERE / "reference-selection.json"
    assets = json.loads(manifest.read_bytes())["pairs"]
    for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
        os.environ[name] = "1"
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows = {row["id"]:row for row in pool.map(wang_pair,assets,chunksize=4)}
    print("Wang",len(rows),flush=True)
    fill_cambi(assets,rows)
    output = HERE / "reference-banding.csv"
    with output.open("w",encoding="utf-8-sig",newline="") as file:
        writer = csv.DictWriter(file,fieldnames=["id","wang_fr","wang_nr","cambi_fr","cambi_nr"])
        writer.writeheader()
        writer.writerows(rows.values())
    print("CAMBI",sum(r["cambi_fr"] is not None for r in rows.values()),
          "reference list SHA256",hashlib.sha256(manifest.read_bytes()).hexdigest(),flush=True)


if __name__=="__main__":
    main()
