"""Single-frame banding scores for the 50 ASTC pairs, using native display RGB."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


@dataclass
class EdgePixels:
    yx: np.ndarray
    coherence: np.ndarray
    contrast: np.ndarray


def display_luma(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
    return np.rint(rgb @ np.array([.2126, .7152, .0722])).astype(np.uint8)


def uniform_regions(y: np.ndarray) -> np.ndarray:
    index = np.arange(y.size, dtype=np.int32).reshape(y.shape)
    same_h = y[:, 1:] == y[:, :-1]
    same_v = y[1:] == y[:-1]
    left = np.r_[index[:, :-1][same_h], index[:-1][same_v]]
    right = np.r_[index[:, 1:][same_h], index[1:][same_v]]
    graph = coo_matrix((np.ones(len(left), dtype=np.uint8), (left, right)), shape=(y.size, y.size)).tocsr()
    _, labels = connected_components(graph, directed=False)
    counts = np.bincount(labels)
    return np.where(counts[labels] > .002*y.size, labels+1, 0).reshape(y.shape)


def edge_pixels(y: np.ndarray) -> EdgePixels:
    regions = uniform_regions(y)
    boundary = np.zeros(y.shape, dtype=bool)
    for axis in (0, 1):
        r = np.swapaxes(regions, 0, axis)
        b = np.swapaxes(boundary, 0, axis)
        change = r[1:] != r[:-1]
        b[1:] |= change
        b[:-1] |= change
    # Treat image borders as outside the measurement. Search windows are clipped.
    coords = np.argwhere(boundary & (regions > 0))
    positions, coherences, contrasts = [], [], []
    widths = np.arange(-5, 6)
    for start in range(0, len(coords), 512):
        points = coords[start:start+512]
        py, px = points.T
        yy, xx = py[:,None,None]+widths[None,:,None], px[:,None,None]+widths[None,None,:]
        inside = (yy>=0)&(yy<y.shape[0])&(xx>=0)&(xx<y.shape[1])
        yy, xx = yy.clip(0,y.shape[0]-1), xx.clip(0,y.shape[1]-1)
        outside = inside & (regions[yy,xx] != regions[py,px][:,None,None])
        diff = y[py,px].astype(np.int16)[:,None,None]-y[yy,xx]
        equal = (outside & (diff==0)).sum((1,2))
        other = (outside & (diff!=0)).sum((1,2))
        coherence = 1 - np.minimum(1, equal/np.maximum(1,other))
        partner = outside & boundary[yy,xx] & (regions[yy,xx]>0) & (diff>0) & (diff<5)
        # Count each brighter-side point once per distinct adjacent region j.
        for i in np.flatnonzero(partner.any((1,2))):
            keep = partner[i]
            _, first = np.unique(regions[yy,xx][i][keep],return_index=True)
            for delta in diff[i][keep][first]:
                positions.append(points[i])
                coherences.append(coherence[i])
                contrasts.append(delta)
    return EdgePixels(np.array(positions,dtype=int).reshape(-1,2),np.asarray(coherences),np.asarray(contrasts))


def wang(source: EdgePixels, test: EdgePixels, shape: tuple[int, int]) -> tuple[float,float]:
    usable = test.coherence >= .95
    diagonal = math.hypot(*shape)
    absolute = float(test.contrast[usable].sum()/diagonal)
    if not usable.any() or not len(source.yx):
        return absolute, absolute
    # Paper gives a reference-region matching procedure, without a pixelwise tie rule.
    # Here any reference edge in the 11x11 patch with similar coherence is a match.
    neighborhoods = cKDTree(source.yx).query_ball_point(test.yx[usable], 5, p=np.inf)
    has_match = np.fromiter((any(abs(source.coherence[j]-value)<.2 for j in neighbors)
                             for neighbors,value in zip(neighborhoods,test.coherence[usable],strict=True)),dtype=bool)
    relative = float(test.contrast[usable][~has_match].sum()/diagonal)
    return absolute,relative


def frame(path: Path) -> bytes:
    with Image.open(path) as im:
        display = np.asarray(im.convert("RGB"), dtype=float)
    y = np.rint(16 + 219 * (display @ np.array([.2126,.7152,.0722])) / 255).astype(np.uint8)
    return y.tobytes() + bytes([128])*(y.size//2)


def cambi(size: int, pairs: list[tuple[Path,Path]]) -> list[dict[str,float]]:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for column in (0, 1):
            with (directory/f"{column}.yuv").open("wb") as output:
                for pair in pairs:
                    output.write(frame(pair[column]))
        cmd = [shutil.which("ffmpeg") or "ffmpeg","-hide_banner","-loglevel","error"]
        for n in [1,0]:
            cmd += ["-f","rawvideo","-pixel_format","yuv420p","-video_size",f"{size}x{size}","-framerate","1","-i",f"{n}.yuv"]
        cmd += ["-lavfi","libvmaf=feature='name=cambi\\:full_ref=true':log_fmt=json:log_path=out.json:n_threads=2","-f","null","-"]
        subprocess.run(cmd,cwd=directory,check=True)
        scores = json.loads((directory/"out.json").read_bytes())["frames"]
        assert len(scores)==len(pairs)
        return [r["metrics"] for r in scores]


def smoke() -> None:
    base = ROOT/"metric/examples"
    y0, y1 = [display_luma(base/f"wang-{side}.png") for side in ("ref","decoded")]
    r,d = edge_pixels(y0),edge_pixels(y1)
    assert wang(r,r,y0.shape) == (0,0)
    assert math.isclose(wang(r,d,y0.shape)[1],7*256*4/math.hypot(*y0.shape),abs_tol=1e-8)
    assert wang(d,d,y1.shape)[1] == 0
    known = json.loads((base/"measurements.json").read_bytes())["cambi"]
    got = cambi(512,[(ROOT/k["reference"],ROOT/k["decoded"]) for k in known])
    assert all(abs(a["cambi"]-b["cambi"])<1e-6 for a,b in zip(got,known,strict=True))
    print("Wang controlled values and all three archived CAMBI scores reproduced",flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke",action="store_true")
    args = p.parse_args()
    smoke()
    if args.smoke:
        return
    selection = json.loads((HERE/"selection.json").read_bytes())["samples"]
    rows: dict[str,dict[str,dict[str,float | None]]] = {}
    batches: dict[int,list[tuple[str,str,Path,Path]]] = {}
    for item in selection:
        idx = str(item["id"])
        paths = [ROOT/item[key] for key in ("reference","decoded_a","decoded_b")]
        ys = [display_luma(path) for path in paths]
        assert ys[0].shape==ys[1].shape==ys[2].shape
        source = edge_pixels(ys[0])
        rows[idx] = {}
        for tag,image,path in zip(("ref","a","b"),ys,paths,strict=True):
            nr,fr = wang(source,source if tag=="ref" else edge_pixels(image),image.shape)
            assert tag!="ref" or fr==0
            rows[idx][tag] = dict(wang_nr=nr, wang_fr=fr, cambi_nr=None,cambi_fr=None)
            if image.shape[0] >=216:
                batches.setdefault(image.shape[0],[]).append((idx,tag,paths[0],path))
    for size,batch in batches.items():
        result = cambi(size,[(r,d) for _,_,r,d in batch])
        for (idx,tag,_,_),scores in zip(batch,result,strict=True):
            rows[idx][tag].update(cambi_nr=scores["cambi"],cambi_fr=scores["cambi_full_reference"])
            assert tag!="ref" or scores["cambi_full_reference"]==0
    out = HERE/"evidence"
    out.mkdir(parents=True, exist_ok=True)
    (out/"banding.json").write_text(json.dumps(rows,indent=2,allow_nan=False),encoding="utf-8")
    print(f"{len(rows)} triples, CAMBI on {sum(map(len,batches.values()))} inputs")


if __name__ == "__main__":
    main()
