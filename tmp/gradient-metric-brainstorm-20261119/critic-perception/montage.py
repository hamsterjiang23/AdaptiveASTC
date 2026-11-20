"""Side-by-side ref / 8x8-fastest decode / |error|x4 at nearest x2, for eyeballing top-ranked non-known images."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = Path("E:/ASTC_Compression/outputs/01a1eca4-b759-74d2-82d5-2d27a4db8e18")


def views() -> dict[int, str]:
    text = (OUT / "data.js").read_text(encoding="utf-8").strip()
    data = json.loads(text.removeprefix("window.REVIEW=").removesuffix(";"))
    return {a["id"]: ("dark" if "dark" in a["views"] else "rgb") for a in data["assets"]}


def panel(ids: list[int], name: str, tags: dict[int, str]) -> None:
    v = views()
    s, gap, lab = 2, 6, 16
    w = 3 * 128 * s + 4 * gap
    h = len(ids) * (128 * s + lab + gap) + gap
    canvas = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    for row, i in enumerate(ids):
        folder = OUT / "media" / f"{i:04d}"
        ref = np.asarray(Image.open(folder / f"ref-{v[i]}.png").convert("RGB")).astype(int)
        dec = np.asarray(Image.open(folder / f"fastest-{v[i]}.png").convert("RGB")).astype(int)
        err = np.clip(np.abs(dec - ref).max(axis=2) * 4, 0, 255).astype(np.uint8)
        tiles = [ref.astype(np.uint8), dec.astype(np.uint8), np.repeat(err[..., None], 3, axis=2)]
        y = gap + row * (128 * s + lab + gap)
        draw.text((gap, y), f"{i:04d} {v[i]} {tags.get(i, '')}  [ref | 8x8 fastest | |err|x4]", fill=(0, 0, 0))
        for c, t in enumerate(tiles):
            im = Image.fromarray(t).resize((128 * s, 128 * s), Image.NEAREST)
            canvas.paste(im, (gap + c * (128 * s + gap), y + lab))
    canvas.save(HERE / name)
    print(name, canvas.size)


if __name__ == "__main__":
    panel([615, 512, 953, 954, 443], "montage-energy-top.png",
          {615: "KNOWN", 512: "jnd_p95 #1 Magic/SD", 953: "jnd_p95 #2 UI atlas", 954: "jnd_p95 #5 UI atlas", 443: "jnd_p95 #6 Decal/SD"})
    panel([616, 351, 368, 644, 474], "montage-structure-top.png",
          {616: "KNOWN", 351: "B3 #1 TempTexture", 368: "B3 #4 TempTexture", 644: "B1 #1 Ring/SD", 474: "B2area #1 Decal/SD"})
