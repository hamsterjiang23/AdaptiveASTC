"""Follow-up: block-level max pooling of the ERT smooth-block weighted MSE (8x8 footprint), restricted to non-flat blocks."""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np
import industry_probe as ip

def main() -> None:
    with ip.SCREEN.open(encoding="utf-8-sig") as f:
        screen = {int(r["id"]): r for r in csv.DictReader(f)}
    paths = {}
    with ip.NATIVE.open(encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            if s["validation_index"] in screen and s["validation_index"] not in paths:
                paths[s["validation_index"]] = s
    rows = []
    for i, meta in sorted(paths.items()):
        ref = ip.load(Path(meta["reference_path"])); dec = ip.load(Path(meta["decoded_path"]).with_name("8x8_fastest.png"))
        need_alpha = bool(meta["need_alpha"]) and not bool(meta.get("alpha_constant", False))
        ch = [0, 1, 2, 3] if need_alpha else [0, 1, 2]
        rb = ip.block_view(ref[..., ch], 8); db = ip.block_view(dec[..., ch], 8)
        flat_r = rb.reshape(16, 16, 64, len(ch)); flat_d = db.reshape(16, 16, 64, len(ch))
        sd = flat_r.std(axis=2).max(axis=-1)
        mse_b = ((flat_r - flat_d) ** 2).mean(axis=(2, 3))
        scale = 10 + (1 - 10) * np.clip(sd / 18, 0, 1) ** 2
        w = mse_b * scale
        gradient_blocks = (sd >= 2) & (sd < 18)   # smooth but not flat
        wg = np.where(gradient_blocks, w, 0.0)
        top = np.sort(wg.ravel())[::-1]
        rows.append(dict(id=i, psnr=float(screen[i]["psnr_native"]), rank_seam=screen[i]["rank_continuous_seam"],
                         max_block=float(top[0]), top4_mean=float(top[:4].mean()), n_grad_blocks=int(gradient_blocks.sum())))
    for key in ("max_block", "top4_mean"):
        rows.sort(key=lambda r: -r[key])
        for k, r in enumerate(rows, 1): r["rank_" + key] = k
    rows.sort(key=lambda r: r["id"])
    with open("block-pool-probe.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
    print({r["id"]: r for r in rows if r["id"] in ip.KNOWN})
    print("top10 by top4_mean:", [(r["id"], round(r["top4_mean"], 1)) for r in sorted(rows, key=lambda r: r["rank_top4_mean"])[:10]])

if __name__ == "__main__":
    main()
