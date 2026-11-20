"""Build a network-free statistical triage index linked to the 50-image viewer."""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>近 PSNR 贴图 · 指标异常复核</title>
<style>
:root{color-scheme:light;--ink:#172820;--muted:#4c6257;--green:#075c42;--line:#c4d1c8;--bg:#f7f8f4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1500px;margin:auto;padding:clamp(12px,3vw,40px)}a{color:var(--green);text-underline-offset:3px}h1{font-size:clamp(25px,3vw,38px);margin:0 0 6px;line-height:1.3}
header p{color:var(--muted);margin:5px 0}nav{display:flex;gap:9px 24px;flex-wrap:wrap;margin:14px 0 24px}
.bar{border-block:1px solid var(--line);padding:10px 0;display:flex;gap:10px 14px;flex-wrap:wrap;align-items:end}
.bar label{display:grid;gap:3px;font-size:13px;font-weight:600}.bar .check{display:flex;align-items:center;padding-bottom:7px;gap:5px}
select,input[type=search],button{font:inherit;color:var(--ink);background:white;padding:6px 9px;border:1px solid #a6b5aa;border-radius:4px}
button{cursor:pointer}button:hover,select:hover{border-color:var(--green)}:focus-visible{outline:3px solid #65b29a;outline-offset:2px}
.meta{color:var(--muted);font-size:14px;margin:12px 0}.tablewrap{overflow:auto;}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:13px;white-space:nowrap;color:var(--muted)}.num{text-align:right;white-space:nowrap}.asset{max-width:265px;min-width:140px;word-break:break-word}
small{display:block;color:var(--muted)}.strong{font-weight:700;color:var(--green)}.exp{padding:2px 8px;font-size:13px}
.details td{background:#edf3ee}.details table{margin:8px 0;max-width:1000px}.details p{margin:4px 0;overflow-wrap:anywhere}
.details summary{cursor:pointer}.foot{max-width:1000px;color:var(--muted);font-size:14px}#empty{padding:16px 0}
</style></head><body><main><header><h1>近 PSNR 贴图的统计复核名单</h1><p id="guide"></p></header>
<nav aria-label="相关资料"><a href="../gradient-screen-50/review.html">打开 50 张图片对照</a><a href="fixed8-examples.png">看固定 8×8 的原图及局部放大</a><a href="fixed8-findings.md">固定 8×8 单个版本如何筛</a><a href="statistical-screen.csv">下载统计 CSV</a></nav>
<div class="bar"><label>排列依据<select id="order"><option value="any">整图尾部比例小到大</option><option value="gradient">候选内先看大片渐变</option><option value="reverse">整图尾部比例大到小</option><option value="all">跨 50 图校正值小到大</option><option value="strict">严格子集尾部比例小到大</option><option value="id">样本编号</option></select></label>
<label>变化最突出的指标组<select id="family"><option value="">全部指标组</option></select></label>
<label>主指标方向<select id="direction"><option value="">全部方向</option><option value="A_worse">A 失真较重</option><option value="B_worse">B 失真较重</option><option value="A_longer">A 平台较长</option><option value="B_longer">B 平台较长</option></select></label>
<label>查找样本或指标<input type="search" id="query" placeholder="编号、素材路径、指标"></label>
<label class="check"><input id="strict" type="checkbox">两种 PSNR 差均 ≤0.1 dB</label><button id="reset" type="button">清除筛选</button></div>
<p id="count" class="meta" aria-live="polite"></p>
<div class="tablewrap"><table><thead><tr><th>图片对照</th><th class="num">原图最大连续<br>渐变区占比</th><th>编码 A → B</th><th class="num">Δ Unity PSNR<br>Δ 展示 PSNR</th><th>变化最突出的指标</th><th>该指标方向</th><th class="num">整图尾部比例</th><th class="num">跨 50 图校正值</th><th>分项</th></tr></thead><tbody id="rows"></tbody></table></div>
<p id="empty" hidden>没有符合当前条件的图片。</p>
<p class="foot">两项 PSNR 差均为 B − A，单位为 dB。“候选内先看大片渐变”先分整图尾部 ≤5%、5% 至 10%、>10% 三档，再在档内按原图最大连续渐变区占比从大到小排。方向依据变化最突出的指标，人工观感请点开图片确认。整图尾部比例越小，多个指标中最突出的变化在校准样本里越少见。跨 50 图校正值使用 Holm 方法。展开后可看每组的两档实测值和同尺寸、同缺测模式的敏感性结果。</p></main>
<script id="dataset" type="application/json">__DATA__</script><script>
"use strict";const data=JSON.parse(document.getElementById("dataset").textContent);const $=id=>document.getElementById(id);
const txt=(e,s)=>{e.textContent=s;return e}, el=(tag,s)=>txt(document.createElement(tag),s??"");const pct=v=>v===null?"—":(v*100).toFixed(2)+"%";
const pretty=v=>v===null||v===undefined?"—":typeof v==="number"?Number(v.toPrecision(5)).toString():String(v);
const signed=v=>(v>0?"+":"")+v.toFixed(3);const repr=d=>data.directions[d]||d||"—";
const anchor=(url,name)=>{const a=el("a",name);a.href=url;return a}; const expanded=new Set();
const cell=(row,value,cls)=>{const c=el("td");if(value instanceof Node)c.append(value);else c.textContent=value;if(cls)c.className=cls;row.append(c);return c};
for(const [k,v] of Object.entries(data.families))$("family").add(new Option(v,k));
const n05=data.rows.filter(o=>o.p<=.05).length, nh=data.rows.filter(o=>o.holm<=.05).length;
$("guide").textContent=data.rows.length+" 个同图 A/B 配对，两种 PSNR 差均 ≤0.5 dB。整图尾部比例 ≤5% 的有 "+n05+" 张；同时对 "+data.rows.length+" 张做 Holm 校正后，校正值 ≤5% 的有 "+nh+" 张。";
function link(s,m,sdir){const id=String(s.id).padStart(4,"0"),side=(sdir||"")[0]?.toLowerCase();
 const where={platform_score:"platform",plateau_px:"platform",phase_adjusted:"seam",continuous_seam:"seam",worst_patch_psnr_db:"patch"}[m];
 const pt=s.points?.[side]?.[where];return ["../gradient-screen-50/review.html#"+id+(where&&pt?"/"+side+"/"+where:""),where&&pt];}
function detail(s){const tr=el("tr");tr.className="details";const c=cell(tr,"");c.colSpan=9;c.append(el("p",s.asset));
 let context="原图最大连续渐变区占全图 "+s.component.toFixed(3)+"%，同尺寸 "+s.component_n+" 张参照中有 "+s.component_pct.toFixed(1)+"% 的占比严格小于本图。整图校准样本 "+s.n+" 个。相同尺寸 "+s.nsize+" 个，尾部 "+pct(s.psize)+"。同一指标可用模式 "+s.npattern+" 个，尾部 "+pct(s.ppattern)+"。";
 if(s.strict)context+=" 双 PSNR ≤0.1 dB 校准样本 "+s.nstrict+" 个，严格子集尾部 "+pct(s.pstrict)+"。";
 if(s.small)context+=" 边界像素对仅 "+s.pairs+" 个，边界 P95 对个别位置较敏感。";c.append(el("p",context));
 const t=el("table"),head=el("tr");for(const h of ["指标组","组内最突出指标","A / B","B − A","方向","组内尾部 / 校准图数","看同位置"])head.append(el("th",h));t.append(head);
 for(const f of s.fams){const r=el("tr");cell(r,data.families[f.f]);cell(r,f.label);cell(r,pretty(f.a)+" / "+pretty(f.b));cell(r,pretty(f.delta));cell(r,repr(f.d));
 cell(r,pct(f.p)+" / "+f.n);const [url,loc]=link(s,f.k,f.d);cell(r,f.k?anchor(url,loc?"定位局部":"看整图"):"—");t.append(r)}c.append(t);
 c.append(el("p","组内尾部仅在该指标组内比较。极端单项或同组多个相关指标可以来自同一处误差。"));return tr}
function render(){const order=$("order").value,q=$("query").value.trim().toLowerCase(),family=$("family").value,dir=$("direction").value,strict=$("strict").checked;
 const arr=data.rows.filter(s=>(!q||[String(s.id).padStart(4,"0"),s.asset,s.metric,s.label,data.families[s.family]].join(" ").toLowerCase().includes(q))&&(!family||s.family===family)&&(!dir||s.dir===dir)&&(!strict||s.strict));
 const asNum=s=>order==="gradient"?s.gradient_rank:order==="id"?s.id:order==="all"?s.holm:order==="reverse"?-s.p:order==="strict"?s.pstrict??Infinity:s.p;
 arr.sort((x,y)=>asNum(x)-asNum(y)||x.id-y.id);$("rows").replaceChildren();$("empty").hidden=!!arr.length;
 $("count").textContent="显示 "+arr.length+" / "+data.rows.length+" 张。"+(strict?" 已限制两种 PSNR 差均 ≤0.1 dB。":"");
 for(const s of arr){const tr=el("tr");tr.dataset.id=s.id;const [url,loc]=link(s,s.metric,s.dir);
 const a=anchor(url,String(s.id).padStart(4,"0")+(loc?" · 定位局部":" · 对照图片"));a.title=s.asset;const name=cell(tr,a,"asset");name.append(el("small",s.asset.split("/").pop()));
 cell(tr,s.component.toFixed(3)+"%","num");cell(tr,s.a+" → "+s.b);const dm=cell(tr,signed(s.du),"num");dm.append(el("small",signed(s.dv)));const met=cell(tr,s.label);met.append(el("small",data.families[s.family]));cell(tr,repr(s.dir));
 cell(tr,pct(s.p),s.p<=.05?"strong num":"num");cell(tr,pct(s.holm),"num");
 const b=el("button",expanded.has(s.id)?"收起":"展开");b.className="exp";b.setAttribute("aria-expanded",expanded.has(s.id));b.onclick=()=>{expanded.has(s.id)?expanded.delete(s.id):expanded.add(s.id);render()};cell(tr,b);$("rows").append(tr);if(expanded.has(s.id))$("rows").append(detail(s))}
}
for(const id of ["order","family","direction","strict"])$(id).addEventListener("change",render);$("query").addEventListener("input",render);
$("reset").onclick=()=>{for(const k of ["family","direction","query"])$(k).value="";$("order").value="any";$("strict").checked=false;expanded.clear();render()};render();
</script></body></html>'''

FAMILIES = {"block_seam":"块边界与接缝","flat_steps":"平台与台阶","banding":"亮度色带",
            "local_error":"局部误差","overall":"整体结构与感知"}


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def numeric(value: str) -> float | None:
    return float(value) if value else None


def main() -> None:
    compare = json.loads((HERE.parent/"gradient-screen-50/comparisons.json").read_bytes())
    labels = {m["key"]:m["label"] for m in compare["metrics"]}
    images = {s["id"]:s for s in compare["samples"]}
    stats = read(HERE/"statistical-screen.csv")
    family = read(HERE/"family-tail.csv")
    metric = {(r["id"],r["metric"]):r for r in read(HERE/"metric-tail.csv")}
    assert {int(r["id"]) for r in stats} == set(images)
    gradient = {int(r["id"]):(rank,r) for rank,r in enumerate(read(HERE/"gradient-candidates.csv"),1)}
    assert set(gradient)==set(images)
    rows = []
    for s in stats:
        i = images[int(s["id"])]
        position,component = gradient[i["id"]]
        groups = []
        for f in (r for r in family if r["id"]==s["id"]):
            k = f["strongest_metric"]
            hit = metric.get((s["id"],k),{})
            groups.append(dict(f=f["family"],k=k,label=labels.get(k,"缺测"),a=i["values"]["a"].get(k),
                               b=i["values"]["b"].get(k),delta=numeric(hit.get("signed_delta_B_minus_A","")),
                               d=f["direction"],p=numeric(f["family_tail"]),n=int(f["n_cal"] or 0)))
        rows.append(dict(id=i["id"],asset=i["asset"],a=i["preset_a"],b=i["preset_b"],points=i["points"],
                         family=s["strongest_family"],metric=s["strongest_metric"],label=labels[s["strongest_metric"]],
                         component=float(component["original_largest_gradient_component_pct"]),gradient_rank=position,
                         component_pct=float(component["pct_reference_with_strictly_smaller_component"]),
                         component_n=int(component["same_size_reference_n"]),
                         dir=s["direction"],p=float(s["p_any"]),holm=float(s["p_any_holm50"]),n=int(s["n_cal"]),
                         du=float(s["native_psnr_delta"]),dv=float(s["display_psnr_delta"]),
                         nsize=int(s["n_cal_same_size"]),psize=numeric(s["p_any_same_size"]),
                         npattern=int(s["n_cal_same_metric_pattern"]),ppattern=numeric(s["p_any_same_metric_pattern"]),
                         strict=s["qualifies_both_0p1"]=="1",nstrict=int(s["n_cal_within_0p1"] or 0),
                         pstrict=numeric(s["p_any_within_0p1"]),small=s["small_boundary_support"]=="1",
                         pairs=int(s["boundary_pairs"]),fams=groups))
    directions=dict(A_worse="A 失真较重",B_worse="B 失真较重",A_longer="A 平台较长",B_longer="B 平台较长",
                    tie="两档相同",unchanged="两档相同",same="两档相同",missing="缺测")
    payload=json.dumps(dict(rows=rows,families=FAMILIES,directions=directions),ensure_ascii=False,
                       separators=(",",":"),allow_nan=False).replace("<","\\u003c")
    (HERE/"review.html").write_text(TEMPLATE.replace("__DATA__",payload),encoding="utf-8")
    print("Statistical index:",len(rows),"assets,",sum(len(r["fams"]) for r in rows),"family rows")


if __name__=="__main__":
    main()
