"""Exact binomial power for paired 2AFC, CI half-widths, rule of three, Fisher-z CI for Spearman."""
from __future__ import annotations

import math

from scipy.stats import binom, norm


def exact_power(n: int, p1: float, alpha: float = 0.05) -> float:
    # two-sided exact binomial test vs p0=0.5: reject if k >= c_hi or k <= c_lo
    c_hi = next(k for k in range(n + 1) if binom.sf(k - 1, n, 0.5) <= alpha / 2)
    c_lo = n - c_hi
    return float(binom.sf(c_hi - 1, n, p1) + binom.cdf(c_lo, n, p1))


def min_n(p1: float, power: float = 0.8) -> int:
    for n in range(10, 2000):
        # require power for n and the next 4 n (exact power saw-tooths)
        if all(exact_power(m, p1) >= power for m in range(n, n + 5)):
            return n
    return -1


def main() -> None:
    za, zb = norm.ppf(0.975), norm.ppf(0.8)
    for p1 in (0.6, 0.65, 0.7, 0.75, 0.8):
        approx = ((za * 0.5 + zb * math.sqrt(p1 * (1 - p1))) / (p1 - 0.5)) ** 2
        print(f"2AFC p1={p1}: normal-approx n={math.ceil(approx)}, exact stable n={min_n(p1)}")
    for n in (30, 50, 100, 150):
        print(f"precision 95% half-width at p=0.5, n={n}: +-{1.96 * math.sqrt(0.25 / n):.3f}; at p=0.8: +-{1.96 * math.sqrt(0.16 / n):.3f}")
    for n in (30, 60, 100):
        exact = 1 - 0.05 ** (1 / n)
        print(f"0 events in n={n}: rule-of-3 upper {3 / n:.3f}, exact 95% upper {exact:.3f}")
    for n, rho in ((40, 0.5), (80, 0.5), (150, 0.5), (80, 0.3)):
        z, se = math.atanh(rho), math.sqrt((1 + rho * rho / 2) / (n - 3))
        print(f"Spearman n={n} rho={rho}: Bonett-Wright 95% CI [{math.tanh(z - 1.96 * se):.2f}, {math.tanh(z + 1.96 * se):.2f}]")
    # kappa SE approx for two raters, n items, prevalence 0.3, kappa 0.6 (Fleiss large-sample, rough)
    for n in (100, 150, 200):
        po, pe = 0.6 * (1 - 0.58) + 0.58, 0.58
        se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
        print(f"kappa~0.6 (pe=0.58) n={n}: approx SE {se:.3f}, 95% half-width {1.96 * se:.3f}")
    # recall: to estimate miss rate among unflagged images when prevalence there is ~5%
    for prev in (0.02, 0.05, 0.1):
        n = math.ceil(20 / prev)
        print(f"unflagged prevalence {prev}: random images needed to observe ~20 positives = {n}")
    # chance that all 3 known land in top-t by luck
    for n, t in ((138, 20), (61, 20), (442, 45), (115, 23)):
        print(f"P(all 3 in top {t} of {n}) = {math.comb(t, 3) / math.comb(n, 3):.4g}")


if __name__ == "__main__":
    main()
