"""Evaluate the original-only prescreen against gradient-new-step-v2 (full reference) on the 657 holdout images."""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

from harness import KNOWN, spearman

HERE = Path(__file__).resolve().parent
CONTROLS = (790, 602, 207)
TARGETS = ("S@8", "E_p95@8", "L_p95_primary@8")


def num(v: object) -> float:
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return math.nan
    return x


def auc(score: np.ndarray, label: np.ndarray) -> float | None:
    keep = np.isfinite(score)
    s, y = score[keep], label[keep]
    pos, neg = s[y], s[~y]
    if not len(pos) or not len(neg):
        return None
    greater = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(greater / (len(pos) * len(neg)))


def main() -> None:
    pre = {int(r["id"]): r for r in csv.DictReader((HERE / "prescreen.csv").open(encoding="utf-8-sig"))}
    full = {int(r["id"]): r for r in csv.DictReader((HERE / "new-step-v2.csv").open(encoding="utf-8-sig"))}
    cal = json.loads((HERE / "prescreen-calibration.json").read_text(encoding="utf-8"))
    cal_ids, hold_ids = set(cal["calibration_ids"]), set(cal["holdout_ids"])
    out: dict[str, object] = {}
    for target in TARGETS:
        res: dict[str, object] = {}
        valid = [i for i in full if np.isfinite(num(full[i][target]))]
        ranked = sorted(valid, key=lambda i: -num(full[i][target]))
        top10 = set(ranked[:math.ceil(0.10 * len(ranked))])
        top5 = set(ranked[:math.ceil(0.05 * len(ranked))])
        # threshold R* chosen on calibration ids only: largest R_cc keeping >= 90% of their full-reference top 10%
        cal_top = [i for i in top10 if i in cal_ids]
        r_star = 0
        for t in range(0, 200):
            kept = sum(num(pre[i]["R_cc@8"]) >= t for i in cal_top)
            if cal_top and kept / len(cal_top) >= 0.9:
                r_star = t
            else:
                break
        hold = [i for i in hold_ids if i in pre]
        flagged = {i for i in hold if num(pre[i]["R_cc@8"]) >= r_star}
        hold_top10 = [i for i in top10 if i in hold_ids]
        hold_top5 = [i for i in top5 if i in hold_ids]
        res["r_star_from_calibration"] = r_star
        res["calibration_top10"] = len(cal_top)
        res["holdout_n"] = len(hold)
        res["holdout_flagged_share"] = len(flagged) / len(hold)
        res["holdout_recall_top10"] = (sum(i in flagged for i in hold_top10), len(hold_top10))
        res["holdout_recall_top5"] = (sum(i in flagged for i in hold_top5), len(hold_top5))
        res["known_R_cc"] = {k: num(pre[k]["R_cc@8"]) for k in KNOWN}
        res["known_flagged"] = sum(num(pre[k]["R_cc@8"]) >= r_star for k in KNOWN)
        res["controls_R_cc"] = {k: (num(pre[k]["R_cc@8"]), num(pre[k]["R_cc@8"]) >= r_star) for k in CONTROLS}
        both = [i for i in hold if i in full]
        res["spearman_R_cc_vs_target"] = spearman([num(pre[i]["R_cc@8"]) for i in both], [num(full[i][target]) for i in both])
        res["spearman_R_n_vs_target"] = spearman([num(pre[i]["R_n@8"]) for i in both], [num(full[i][target]) for i in both])
        label = np.array([i in top10 for i in both])
        res["auc_holdout"] = {
            "R_cc": auc(np.array([num(pre[i]["R_cc@8"]) for i in both]), label),
            "R_n": auc(np.array([num(pre[i]["R_n@8"]) for i in both]), label),
            "R_frac": auc(np.array([num(pre[i]["R_frac@8"]) for i in both]), label),
            "h_p90": auc(np.array([num(pre[i]["h_p90@8"]) for i in both]), label),
            "R_cc_L": auc(np.array([num(pre[i]["R_cc_L@8"]) for i in both]), label),
            "baseline_mask_frac": auc(np.array([num(pre[i]["mask_frac"]) for i in both]), label),
            "baseline_mask_px": auc(np.array([num(full[i]["mask_px@8"]) for i in both]), label),
        }
        out[target] = res
    blocks = (6, 8, 10, 12)
    mono = [all(num(r[f"R_n@{a}"]) <= num(r[f"R_n@{b}"]) for a, b in zip(blocks, blocks[1:])) for r in pre.values()]
    out["R_n_nondecreasing_with_block"] = sum(mono) / len(mono)
    out["no_gradient_share"] = float(np.mean([num(r["no_gradient@8"]) == 1 for r in pre.values()]))
    out["seconds_total"] = sum(num(r["seconds"]) for r in pre.values())
    (HERE / "prescreen-analysis.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
