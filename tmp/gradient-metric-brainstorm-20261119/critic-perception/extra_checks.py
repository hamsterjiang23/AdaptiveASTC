"""Extra critic checks: ultrasmooth rule on synthetic flats, CAMBI FR with nearest vs bilinear magnification on
synthetic shallow banding, inter-metric Spearman, and where the known images' 4x4 values fall in the 8x8 distribution."""
from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
ROOT = Path("E:/ASTC_Compression")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tmp/gradient-metric-brainstorm-20261119/lane-b-texture-practice"))
from industry_probe import ultrasmooth  # noqa: E402
from synthetic_battery import cases  # noqa: E402

LUMA = np.array([0.2126, 0.7152, 0.0722])
KNOWN = (615, 616, 617)


def yuv(rgb: np.ndarray, scale: int, resample: int) -> bytes:
    h, w = rgb.shape[:2]
    if scale != 1:
        rgb = np.asarray(Image.fromarray(rgb).resize((w * scale, h * scale), resample))
    y = np.rint(16 + 219 * (rgb.astype(float) @ LUMA) / 255).astype(np.uint8)
    return y.tobytes() + bytes([128]) * (y.size // 2)


def cambi(pairs: list[tuple[np.ndarray, np.ndarray]], scale: int, resample: int) -> list[dict]:
    size = 128 * scale
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        d = Path(tmp)
        for col in (0, 1):
            with (d / f"{col}.yuv").open("wb") as out:
                for p in pairs:
                    out.write(yuv(p[col], scale, resample))
        cmd = [shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-loglevel", "error"]
        for n in (1, 0):
            cmd += ["-f", "rawvideo", "-pixel_format", "yuv420p", "-video_size", f"{size}x{size}", "-framerate", "1", "-i", f"{n}.yuv"]
        cmd += ["-lavfi", "libvmaf=feature='name=cambi\:full_ref=true':log_fmt=json:log_path=out.json:n_threads=4", "-f", "null", "-"]
        subprocess.run(cmd, cwd=d, check=True)
        frames = json.loads((d / "out.json").read_bytes())["frames"]
    return [f["metrics"] for f in frames]


def main() -> None:
    out: dict = {}
    cs = cases()
    # 1. ultrasmooth on synthetic references (original-only rule)
    out["ultrasmooth_blocks_on_synthetic_refs"] = {k: ultrasmooth(v[0].astype(float)) for k, v in cs.items()}
    # 2. CAMBI FR on synthetic pairs, nearest vs bilinear x4
    names = list(cs)
    pairs = [(cs[k][0], cs[k][1]) for k in names]
    for tag, rs in (("nearest_x4", Image.NEAREST), ("bilinear_x4", Image.BILINEAR)):
        try:
            res = cambi(pairs, 4, rs)
            out[f"cambi_fr_{tag}"] = {k: round(float(r.get("cambi_full_reference", math.nan)), 4) for k, r in zip(names, res)}
        except Exception as e:  # noqa: BLE001
            out[f"cambi_fr_{tag}"] = f"failed: {e!r}"
    # 3. inter-metric Spearman on 196 real8 + 4x4 positions of known
    rows = list(csv.DictReader((HERE / "structure-controls.csv").open(encoding="utf-8-sig")))
    def col(k: str) -> np.ndarray:
        return np.array([float(r[k]) if r[k] not in ("", "None", "nan") else np.nan for r in rows])
    ms = ["continuous_seam", "grid_excess_p95", "B1_poster_frac", "B2_flat_area", "B3_conc_p95", "jnd_p95", "jnd_longest_cc", "mse_in_mask"]
    corr = {}
    for i, a in enumerate(ms):
        for b in ms[i + 1:]:
            x, y = col(f"{a}|real8"), col(f"{b}|real8")
            k = np.isfinite(x) & np.isfinite(y)
            corr[f"{a}~{b}"] = [round(float(spearmanr(x[k], y[k]).statistic), 3), int(k.sum())]
    out["spearman_real8"] = corr
    ids = np.array([int(r["id"]) for r in rows])
    pos = {}
    for m in ms[:-1]:
        r8, r4 = col(f"{m}|real8"), col(f"{m}|real4")
        v = r8[np.isfinite(r8)]
        pos[m] = {int(i): (int(np.sum(v > r4[ids == i][0])) + 1 if np.isfinite(r4[ids == i][0]) else None) for i in KNOWN}
        pos[m]["n_real8"] = int(len(v))
    out["known_real4_value_rank_among_real8"] = pos
    # 4. coverage: share of 196 with a value
    out["coverage_real8"] = {m: int(np.isfinite(col(f"{m}|real8")).sum()) for m in ms}
    (HERE / "extra-checks.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
