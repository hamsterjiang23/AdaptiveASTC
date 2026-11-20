"""Time the reusable seam pipeline (lab + gradient_mask + evaluate) and the B3/E1 prototypes on larger
archived validation images. Read-only; prints JSON and writes timing.json next to this file."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check_candidates import MANIFEST, b3, e1, evaluate, gradient_mask, lab, rgba, view  # noqa: E402


def main() -> None:
    rows = [r for r in json.loads(MANIFEST.read_bytes()) if r["preset"] == "fastest" and r["srgb"] and not r["is_normal"]]
    out = []
    for size in (128, 256, 512, 1024, 2048):
        picks = [r for r in rows if r["width"] == r["height"] == size][:2]
        for r in picks:
            folder = Path(r["decoded_path"]).parent
            alpha = bool(r["need_alpha"]) and not bool(r["alpha_constant"])
            t = {}
            s = time.perf_counter(); ref = rgba(Path(r["reference_path"])); dec_px = rgba(folder / "8x8_medium.png"); t["read_png"] = time.perf_counter() - s
            s = time.perf_counter(); src = lab(view(ref, alpha)); dec = lab(view(dec_px, alpha)); t["lab_both"] = time.perf_counter() - s
            s = time.perf_counter(); mask = gradient_mask(src); t["gradient_mask"] = time.perf_counter() - s
            s = time.perf_counter(); res, _ = evaluate(src, dec, mask, 8); t["evaluate"] = time.perf_counter() - s
            s = time.perf_counter(); b3(src[..., 0], dec[..., 0], mask); t["b3_vectorised"] = time.perf_counter() - s
            s = time.perf_counter(); e1(folder / "8x8_medium.astc", src[..., 0], mask); t["e1_python_loop"] = time.perf_counter() - s
            out.append({"id": r["validation_index"], "size": size, "alpha": alpha, "mask_pct": round(res["gradient_area_pct"], 2),
                        **{k: round(v, 4) for k, v in t.items()}})
            print(json.dumps(out[-1]), flush=True)
    (HERE / "timing.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
