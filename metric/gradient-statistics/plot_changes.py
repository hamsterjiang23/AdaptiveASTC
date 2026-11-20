"""Plot observed PSNR differences against three artifact measurements."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent


def read(name: str) -> list[dict[str, str]]:
    with (HERE/name).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(font)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=font).get_name()
    source = {r["id"]:r for r in read("reference.csv")}
    extras = {r["id"]:r for r in read("reference-banding.csv")}
    roles = {r["id"]:r["role"] for r in read("reference-partition.csv")}
    baseline = [r | extras[idx] for idx,r in source.items() if roles[idx] in ("fit","calibration")]
    panel = json.loads((HERE.parent/"gradient-screen-50/comparisons.json").read_bytes())["samples"]
    fig,axes = plt.subplots(1,3,figsize=(12,4.4))
    for ax,(key,title,example) in zip(axes,[("platform_score","渐变平台分",698),("phase_adjusted","连续接缝分（扣除错位网格）",615),
                                          ("wang_fr","参考匹配色带分（Wang 近似）",132)],strict=True):
        for row in baseline:
            if row[key]:
                gap = max(abs(float(row[k])) for k in ("unity_psnr_db","view_psnr_db"))
                ax.scatter(gap,abs(float(row[key])),s=8,color="#999fa6",alpha=.45,linewidth=0)
        for sample in panel:
            a,b = sample["values"]["a"],sample["values"]["b"]
            if a[key] is None or b[key] is None:
                continue
            gap=max(abs(b[k]-a[k]) for k in ("unity_psnr_db","view_psnr_db"))
            change=abs(b[key]-a[key])
            ax.scatter(gap,change,s=20,color="#287b8e",alpha=.85,linewidth=0)
            if sample["id"]==example:
                ax.scatter(gap,change,s=64,facecolors="none",edgecolors="#b54b24",linewidth=1.5)
                ax.annotate(f"{example:04d}",(gap,change),xytext=(-9,6),textcoords="offset points",fontsize=9,ha="right",color="#99432a")
        ax.axvline(.1,color="#aab1b6",linestyle="--",linewidth=.8)
        ax.set(xlim=(-.01,.51),xlabel="两种 PSNR 绝对差中的较大值（dB）",title=title)
        ax.set_ylim(bottom=-.022*ax.get_ylim()[1])
        ax.spines[["right","top"]].set_visible(False)
        ax.grid(axis="y",alpha=.18)
    axes[0].set_ylabel("同图两候选的指标绝对差 |B−A|")
    fig.legend(handles=[Line2D([0],[0],marker="o",linestyle="none",color="#999fa6",label="参考素材（每目录一张）"),
                        Line2D([0],[0],marker="o",linestyle="none",color="#287b8e",label="50 张复核面板"),
                        Line2D([0],[0],linestyle="--",color="#aab1b6",label="0.1 dB")],loc="lower center",ncol=3,frameon=False)
    fig.tight_layout(rect=(0,.12,1,1))
    fig.savefig(HERE/"metric-changes.png",dpi=170)
    plt.close(fig)


if __name__=="__main__":
    main()
