"""Where do the tiles below Y dB sit?  Reference | 8x8 fastest decode (bad tiles in red) | 4x error map
(smooth-gradient tiles in green, bad tiles in red) for chosen images; primary display view, 8x8 tiles."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from harness import load_items, read
from new_step_v2 import gradient_mask, lab
from tile_psnr import TILE, _blocks, tile_psnr

HERE = Path(__file__).resolve().parent


def panel(item_id: int, y: float, zoom: int) -> Image.Image:
    item = next(i for i in load_items() if i.id == item_id)
    ref, dec = read(item.display(None)), read(item.display(8))
    h, w = ref.shape[:2]
    top = (-h) % TILE  # grid anchored at the bottom row: tile row t starts at display row t*TILE - top
    bad = tile_psnr(ref, dec) < y
    mask = gradient_mask(lab(ref))
    cover = _blocks(mask.astype(float), "constant").sum(axis=2) / _blocks(np.ones(mask.shape), "constant").sum(axis=2)
    smooth = cover >= 0.5
    err = np.clip(np.abs(dec.astype(int) - ref.astype(int)).max(axis=2) * 4, 0, 255).astype(np.uint8)
    crops = [ref, dec, np.repeat(err[..., None], 3, axis=2)]
    pad, text = 8, 18
    out = Image.new("RGB", (3 * w * zoom + 4 * pad, h * zoom + text + 2 * pad), (24, 24, 24))
    draw = ImageDraw.Draw(out)
    draw.text((pad, pad), f"{item_id:04d} {item.view} {w}x{h}  tiles<{y:g}dB: {int(bad.sum())}"
              f" (inside smooth-gradient tiles: {int((bad & smooth).sum())}),  smooth tiles: {int(smooth.sum())}",
              fill=(235, 235, 235))
    for col, crop in enumerate(crops):
        left, upper = pad + col * (w * zoom + pad), pad + text
        out.paste(Image.fromarray(np.ascontiguousarray(crop)).resize((w * zoom, h * zoom), Image.NEAREST), (left, upper))
        for (ty, tx), flag in np.ndenumerate(bad | smooth):
            if not flag or col == 0 or (col == 1 and not bad[ty, tx]):
                continue
            y0 = max(ty * TILE - top, 0) * zoom + upper
            y1 = min(ty * TILE - top + TILE, h) * zoom + upper - 1
            x0, x1 = tx * TILE * zoom + left, min((tx + 1) * TILE, w) * zoom + left - 1
            colour = (255, 40, 40) if bad[ty, tx] else (40, 200, 80)
            draw.rectangle([x0, y0, x1, y1], outline=colour, width=2 if bad[ty, tx] else 1)
    return out


def main() -> None:
    ids = [int(a) for a in sys.argv[1:] if a.isdigit()] or [615, 616, 617]
    y = float(next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("y=")), 28))
    panels = [panel(i, y, 3) for i in ids]
    sheet = Image.new("RGB", (max(p.width for p in panels), sum(p.height for p in panels)), (24, 24, 24))
    top = 0
    for p in panels:
        sheet.paste(p, (0, top))
        top += p.height
    path = HERE / "sheets" / f"tile-psnr-y{y:g}-{'-'.join(map(str, ids))}.png"
    sheet.save(path)
    print(path)


if __name__ == "__main__":
    main()
