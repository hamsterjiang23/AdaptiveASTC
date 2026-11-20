"""Make a native-coordinate spot-check sheet of absolute gradient alerts."""
from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    here = Path(__file__).resolve().parent
    media = here.parents[1]/"outputs/01a1eca4-b759-74d2-82d5-2d27a4db8e18/media"
    with (here/"fixed8-absolute.csv").open(encoding="utf-8-sig",newline="") as file:
        rows = list(csv.DictReader(file))
    selected = [next(r for r in rows if int(r["id"])==i) for i in (615,616,617)]
    existing = {r["group"] for r in selected}
    for row in rows:
        if row["rank_two_tail"] and row["group"] not in existing:
            selected.append(row)
            existing.add(row["group"])
        if len(selected) == 6:
            break
    bold = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc",24)
    regular = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",17)
    small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",14)
    sheet = Image.new("RGB",(1000,1230),"#f7f5ef")
    draw = ImageDraw.Draw(sheet)
    draw.text((20,12),"原图对照固定 8×8 · fastest",font=bold,fill="#172722")
    draw.text((20,50),"前 3 行为用户反馈图；后 3 行为按合议排名选出的不同目录新候选，等待人工判断。",font=regular,fill="#293e35")
    for x,s in zip((20,188,356,524,708),("原图","解码图","同位置原图放大","同位置解码放大","复核信息"),strict=True):
        draw.text((x,88),s,font=regular,fill="#293e35")
    for i,r in enumerate(selected):
        y=119+i*184
        idx=int(r["id"])
        folder=media/f"{idx:04}"
        x1,y1 = int(float(r["seam_x"])),int(float(r["seam_y"]))
        side=32
        for col,which in enumerate(("ref","fastest")):
            with Image.open(folder/f"{which}-{r['view']}.png") as im:
                im=im.convert("RGB")
                im.thumbnail((156,156),Image.Resampling.LANCZOS)
                sheet.paste(im,(20+col*168+(156-im.width)//2,y+(156-im.height)//2))
            with Image.open(folder/f"{which}-{r['view']}.png") as im:
                left=min(max(x1-side//2,0),im.width-side)
                top=min(max(y1-side//2,0),im.height-side)
                crop=im.crop((left,top,left+side,top+side)).convert("RGB").resize((160,160),Image.Resampling.NEAREST)
                sheet.paste(crop,(356+col*168,y))
        details=[f"{idx:04} · 队列 #{r['rank_two_tail']}",f"原生 PSNR  {float(r['native_psnr']):.2f} dB",
                 f"块边界 P95  {float(r['grid_excess_p95']):.2f}",f"接缝分  {float(r['phase_adjusted']):.2f}",
                 f"FLIP P99  {float(r['flip_p99']):.3f}",f"定位 ({x1}, {y1}) · {r['width']}×{r['height']}"]
        for line,s in enumerate(details):
            draw.text((708,y+5+25*line),s,font=regular if line==0 else small,fill="#152c21")
        draw.line((20,y+170,975,y+170),fill="#d8dcd4")
    sheet.save(here/"fixed8-examples.png",optimize=True)
    print("Known examples / top first unseen directories:",[r["id"] for r in selected])


if __name__=="__main__":
    main()
