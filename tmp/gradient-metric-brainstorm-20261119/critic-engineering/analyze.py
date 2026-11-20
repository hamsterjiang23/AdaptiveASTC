"""Replay the first-valid label rule on archived candidates, add a metric gate, and summarise
monotonicity across presets / block sizes. Input: candidates-pop128.csv from check_candidates.py."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PRESETS = ("fastest", "fast", "medium", "thorough", "exhaustive")
ORDER = [(b, p) for b in (12, 10, 8, 6) for p in PRESETS]
METRICS = ("seam", "grid_p95", "change_p95", "b3", "e1_p90")
KNOWN = (615, 616, 617)


def num(v: str) -> float | None:
    return None if v in ("", "None") else float(v)


def load(tag: str) -> dict[int, dict[tuple[int, str], dict]]:
    imgs: dict[int, dict[tuple[int, str], dict]] = defaultdict(dict)
    for r in csv.DictReader((HERE / f"candidates-{tag}.csv").open(encoding="utf-8-sig")):
        for k in ("psnr", "ms", "t_psnr", "t_ms", *METRICS):
            r[k] = num(r[k])
        r["payload"] = int(r["payload"])
        imgs[int(r["id"])][(int(r["block"]), r["preset"])] = r
    return imgs


def pick(c: dict[tuple[int, str], dict], gate: str | None = None, tau: float = 0.) -> tuple[tuple[int, str], str]:
    def ok(r: dict) -> bool:
        return r["psnr"] >= r["t_psnr"] and r["ms"] >= r["t_ms"]
    def gated(r: dict) -> bool:
        return gate is None or r[gate] is None or r[gate] <= tau
    for key in ORDER:
        if ok(c[key]) and gated(c[key]):
            return key, "valid"
    valid = [k for k in ORDER if ok(c[k])]
    if gate is not None and valid:  # gate unsatisfiable: least-bad valid candidate by the gate metric
        return min(valid, key=lambda k: (c[k][gate] if c[k][gate] is not None else -1, ORDER.index(k))), "gate_fallback"
    best = max(ORDER, key=lambda k: (c[k]["psnr"], -ORDER.index(k)))
    return best, "psnr_fallback"


def monotone(seq: list[float | None], increasing: bool) -> bool | None:
    vals = [v for v in seq if v is not None]
    if len(vals) < 2 or max(vals) < 3:
        return None
    for a, b in zip(vals, vals[1:]):
        if increasing and b < a - max(.5, .1 * a):
            return False
        if not increasing and b > a + max(.5, .1 * a):
            return False
    return True


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "pop128"
    imgs = load(tag)
    out: dict[str, object] = {"images": len(imgs)}
    # 1. rule replay sanity
    mism = [i for i, c in imgs.items() if f"{pick(c)[0][0]}x{pick(c)[0][0]}_{pick(c)[0][1]}" != next(iter(c.values()))["gt"]]
    out["replay_mismatch"] = mism
    labels = {i: pick(c)[0] for i, c in imgs.items()}
    out["label_blocks"] = Counter(f"{b}x{b}" for b, _ in labels.values())
    # 2. monotonicity
    mono: dict[str, dict[str, object]] = {}
    for m in METRICS:
        pres, blk = [], []
        for c in imgs.values():
            for b in (12, 10, 8, 6):
                pres.append(monotone([c[(b, p)][m] for p in PRESETS], increasing=False))
            for p in PRESETS:
                blk.append(monotone([c[(b, p)][m] for b in (6, 8, 10, 12)], increasing=True))
        pv, bv = [x for x in pres if x is not None], [x for x in blk if x is not None]
        mono[m] = {"preset_seq_monotone": f"{sum(pv)}/{len(pv)}", "block_seq_monotone": f"{sum(bv)}/{len(bv)}"}
    out["monotonicity_tol_max(0.5,10pct)_floor3"] = mono
    # 3. shipped label and fixed 8x8 medium: rank of known positives within the 196
    ranks: dict[str, dict[str, object]] = {}
    for m in METRICS:
        for name, key_of in (("label", lambda i: labels[i]), ("fixed8_medium", lambda i: (8, "medium")),
                             ("fixed8_fastest", lambda i: (8, "fastest"))):
            vals = sorted(((imgs[i][key_of(i)][m] or 0., i) for i in imgs), reverse=True)
            order = [i for _, i in vals]
            ranks.setdefault(m, {})[name] = {str(k): {"rank": order.index(k) + 1, "value": round(imgs[k][key_of(k)][m] or 0., 2)}
                                            for k in KNOWN if k in imgs}
    out["known_ranks_among_196"] = ranks
    # 4. gate simulation: tau = smallest value of the metric over the three positives at 8x8 fastest
    sims = {}
    base_bytes = sum(imgs[i][labels[i]]["payload"] for i in imgs)
    for m in METRICS:
        taus = sorted({round(imgs[k][(8, 'fastest')][m], 2) for k in KNOWN if k in imgs})
        for tau in [min(taus) * f for f in (1.0, .75, .5)]:
            moved, kinds, new_bytes, known = 0, Counter(), 0, {}
            shift = Counter()
            for i, c in imgs.items():
                key, kind = pick(c, m, tau)
                kinds[kind] += 1
                new_bytes += c[key]["payload"]
                if key != labels[i]:
                    moved += 1
                    shift[f"{labels[i][0]}->{key[0]}" + ("" if key[0] != labels[i][0] else " preset")] += 1
                if i in KNOWN:
                    known[str(i)] = f"{labels[i][0]}x{labels[i][0]}_{labels[i][1]} -> {key[0]}x{key[0]}_{key[1]} ({kind})"
            sims[f"{m}<= {tau:.2f}"] = {"moved": moved, "kinds": dict(kinds), "bytes_ratio": round(new_bytes / base_bytes, 3),
                                        "shift": dict(shift.most_common(8)), "known": known}
    out["gate_sim"] = sims
    # 5. preset-only escalation (no byte change): same block, first preset passing gate
    text = json.dumps(out, indent=1, ensure_ascii=False, default=dict)
    (HERE / f"analysis-{tag}.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
