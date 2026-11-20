"""Join the three measured views per asset and export matched differences."""
from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
Number = int | float | str | None


def dictionary() -> list[dict[str,str]]:
    sections = {
        "全图与局部像素": [
            ("unity_psnr_db","Unity 原生 PSNR","dB","高","沿用原生 RGBA 的质量分支和通道规则"),
            ("view_psnr_db","展示 RGB PSNR","dB","高","统一显示背景后，三个通道等权计算"),
            ("display_mse","展示 RGB 均方误差","码值²","低","展示 RGB 的逐通道 8 位像素均方误差"),
            ("worst_patch_psnr_db","最差 32×32 窗口 PSNR","dB","高","按不重叠 32×32 窗口计算，定位到最差窗口"),
            *((f"area_under_{t}",f"局部 PSNR 低于 {t} dB 的面积","%","低","窗口内有效像素累计，占整图像素的百分比") for t in (28,30,32)),
        ],
        "结构与感知": [
            ("ssim","亮度 SSIM","","高","11×11 高斯窗口内比较均值、方差及协方差"),
            ("unity_ms_ssim_db","Unity 原生 MS-SSIM","dB","高","原生多尺度亮度结构分再转 dB"),
            ("ssimulacra2","SSIMULACRA2","","高","多尺度结构、模糊及多余边缘的感知保真分"),
            ("lpips_alex","LPIPS-Alex","","低","两幅展示图的预训练特征距离"),
            ("flip_mean","FLIP 均值","","低","LDR-FLIP 可见误差图平均值，固定 67 像素/视角度"),
            ("flip_p95","FLIP P95","","低","整图 FLIP 误差第 95 百分位"),
            ("flip_p99","FLIP P99","","低","整图 FLIP 误差第 99 百分位"),
            ("masked_flip_p95","渐变区 FLIP P95","","低","在固定原图渐变掩膜内取 FLIP P95"),
            ("gmsd","GMSD","","低","亮度梯度幅值相似度图的标准差"),
            ("psnrb_db","PSNR-B","dB","高","在亮度 MSE 中加入真实块边界效应惩罚"),
            ("psnrb_bef","PSNR-B 块边界惩罚","码值²","低","PSNR-B 中的块效应附加量；原图也可有正值"),
        ],
        "渐变与块边界": [
            ("mask_area_pct","渐变面积占比","%","描述","在每个版本自身重算渐变掩膜，用于观察面积变化"),
            ("mask_largest_px","最大连续渐变区","px","描述","在各版本的掩膜上取最大四连通区像素数"),
            ("mask_largest_pct","最大连续渐变区占比","%","描述","最大四连通区除以该图总面积"),
            ("gradient_change_p95","渐变区梯度误差 P95","Lab","低","原图掩膜内相邻颜色变化向量差的 P95"),
            ("grid_excess_p95","块边界额外跳变 P95","Lab","低","原图掩膜内跨真实块边界的新增跳变扣除近邻后取 P95"),
            ("continuous_seam","最强连续接缝","Lab","低","固定 4 个连续边界像素，按其最弱点取全图最大"),
            ("shifted_median","错位网格接缝中位数","Lab","描述","七种错位网格最强连续接缝的中位数"),
            ("phase_adjusted","扣除错位网格的接缝分","Lab","低","真实网格最强接缝扣除错位网格中位数，截零"),
            ("platform_score","平台分","码值·像素","低","原图同向亮度斜坡被压平后，平台长度减一乘末端新增跳变"),
            ("plateau_px","最强平台的长度","px","描述","报告平台分最高处的等亮像素数；没有平台时按实现记 1"),
            ("plateau_jump_decoded","最强平台的末端跳变","码值","描述","在当前版本最强平台的末端，读取其亮度跳变幅度"),
            ("plateau_jump_ref","同一位置原图的末端跳变","码值","描述","定位到当前版本最强平台后，对应原图同一末端的亮度变化"),
            ("ring_p95_px","圆环等亮轮廓位移 P95","px","低","仅 0617 在已核实的圆心和三个亮度层级估算径向位移"),
        ],
        "色带与透明度": [
            ("cambi_nr","CAMBI 单图色带分","","低","libvmaf 多尺度亮度色带分，按原生尺寸测量"),
            ("cambi_fr","CAMBI 全参考新增色带分","","低","max(0，解码单图分减原图单图分)"),
            ("bband","BBAND 单图色带分","","低","作者单帧算法；无法形成可汇总的分布则留空"),
            ("wang_nr","Wang 色带分 · 单图复现","","低","对同亮度的大片相邻区域提取高一致性边界，按长度乘对比度汇总"),
            ("wang_fr","Wang 色带分 · 参考匹配近似","","低","在原图相邻 11×11 窗内寻找一致性相近的原有边界，度量剩余边界"),
            ("alpha_only_mse","仅替换 Alpha 的 MSE","码值²","低","固定原 RGB、替换解码 Alpha；仅适用需 Alpha 图"),
            ("rgb_only_mse","仅替换 RGB 的 MSE","码值²","低","固定原 Alpha、替换解码 RGB；仅适用需 Alpha 图"),
        ],
        "编码成本": [
            ("payload","mip0 像素或 ASTC 载荷","B","描述","原图列是等价 RGBA8 像素字节；候选列是 ASTC 载荷，不含头"),
            ("encode_ms","归档编码耗时","ms","低","单次编码归档计时，仅作成本观察"),
            ("decode_ms","归档解码耗时","ms","低","单次解码归档计时，仅作成本观察"),
        ],
        "本组无法直接测量": [
            ("pim","PIM","","低","官方 PIM-1 和 PIM-5 权重下载均返回 HTTP 403，保留未测"),
            ("denes","Denes 色带检出概率","%","描述","缺游戏目标亮度、观看距离及可标定的渐变斜率，保留未测"),
            ("normal_mean_deg","法线平均角度误差","°","低","本次 50 张均为颜色展示图"),
            ("normal_p95_deg","法线角度误差 P95","°","低","本次 50 张均为颜色展示图"),
        ],
    }
    return [dict(key=k,label=l,unit=u,better=b,group=g,note=n) for g,items in sections.items() for k,l,u,b,n in items]


def load(path: Path) -> dict | list:
    return json.loads(path.read_bytes())


def to_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w",encoding="utf-8-sig",newline="") as out:
        writer = csv.DictWriter(out,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def coordinate(record: dict, x: str, y: str) -> list[int] | None:
    return [int(record[x]),int(record[y])] if record.get(x) is not None and record.get(y) is not None else None


def difference(left: Number, right: Number) -> float | None:
    if isinstance(left,(int,float)) and isinstance(right,(int,float)):
        return right-left
    return None


def main() -> None:
    metrics = dictionary()
    panel = load(HERE/"selection.json")["samples"]
    evidence = HERE / "evidence"
    general = {(r["id"],r["slot"].lower()):r for r in load(evidence/"general.json")["records"]}
    special = {(r["id"],r["variant"]):r for r in load(evidence/"special.json")}
    band = load(evidence/"banding.json")
    with (HERE/"storage-timing.csv").open(encoding="utf-8-sig") as file:
        costs = {(int(r["id"]),r["variant"].lower()):r for r in csv.DictReader(file)}
    assert len(general)==len(special)==150 and len(band)==50 and len(costs)==100
    rows, changes = [], []
    for item in panel:
        idx = item["id"]
        values,points = {},{}
        for tag in ("ref","a","b"):
            raw = {**general[idx,tag],**special[idx,tag],**band[str(idx)][tag]}
            assert raw["sha256"] == general[idx,tag]["decoded_sha256"]
            raw["payload"] = 4*item["width"]*item["height"] if tag=="ref" else int(costs[idx,tag]["astc_payload_bytes"])
            for field in ("encode_ms","decode_ms"):
                raw[field] = float(costs[idx,tag][field]) if tag!="ref" else None
            for threshold in (28,30,32):
                raw[f"area_under_{threshold}"] *= 100
            scores = {m["key"]:raw.get(m["key"]) for m in metrics}
            for k,v in scores.items():
                if v == "infinity":
                    scores[k] = "∞"
                elif isinstance(v,float):
                    assert math.isfinite(v)
            points[tag] = {
                "seam":coordinate(raw,"seam_x","seam_y") if (raw["continuous_seam"] or 0)>0 else None,
                "patch":coordinate(raw,"worst_x","worst_y") if tag!="ref" else None,
                "platform":coordinate(raw,"plateau_x","plateau_y") if raw["platform_score"]>0 else None,
            }
            values[tag] = scores
            rows.append(dict(id=f"{idx:04}",asset=item["asset"],width=item["width"],height=item["height"],
                             view=item["view"],variant=tag,preset=item.get("preset_"+tag,"ref"),**scores))
        item.update(values=values,points=points)
        changes.append(dict(id=f"{idx:04}",asset=item["asset"],known=item["known"],a=item["preset_a"],b=item["preset_b"],
                            **{m["key"]:difference(values["a"][m["key"]],values["b"][m["key"]]) for m in metrics}))
    out = dict(metrics=metrics,samples=panel)
    (HERE/"comparisons.json").write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    to_csv(HERE/"individual-scores.csv",rows)
    to_csv(HERE/"paired-changes.csv",changes)
    summary = []
    for metric in metrics:
        k = metric["key"]
        finite = [c for c in changes if c[k] is not None]
        magnitude = [abs(c[k]) for c in finite]
        maximum = max(finite,key=lambda c:abs(c[k]),default=None)
        summary.append(dict(**metric,eligible_pairs=len(finite),median_abs_delta=statistics.median(magnitude) if magnitude else None,
                            p90_abs_delta=float(np.percentile(magnitude,90)) if magnitude else None,
                            max_abs_delta=max(magnitude,default=None),max_id=maximum["id"] if maximum else None,
                            signed_delta_at_max=maximum[k] if maximum else None))
    to_csv(HERE/"metric-summary.csv",summary)
    print("Exported",len(metrics),"fields,",len(rows),"image measurements,",len(changes),"matched pairs")


if __name__=="__main__":
    main()
