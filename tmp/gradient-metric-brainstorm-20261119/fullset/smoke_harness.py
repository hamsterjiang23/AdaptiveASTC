"""Smoke checks for harness.py: inputs, grid anchoring and baseline rank reproduction."""
from __future__ import annotations

import json

import numpy as np

from harness import KNOWN, block_index, common_rows, grid_edges, load_items, rank_known, read


def anchoring(items: list) -> dict[str, float]:
    """Mean |decoded step - reference step| on block edges under bottom vs top anchoring (axis 0)."""
    sums = {"bottom": [0.0, 0], "top": [0.0, 0], "interior": [0.0, 0]}
    picked = [i for i in items if i.height % 8 not in (0,) and i.height >= 40 and i.native_psnr < 40][:12]
    for item in picked:
        ref = read(item.display(None)).astype(float)
        dec = read(item.display(8)).astype(float)
        d = np.abs(np.diff(dec, axis=0) - np.diff(ref, axis=0)).sum(axis=2).mean(axis=1)
        bottom = grid_edges(item.height, 8, 0)
        top = (np.arange(1, item.height) % 8) == 0
        for name, mask in (("bottom", bottom), ("top", top), ("interior", ~(bottom | top))):
            sums[name][0] += float(d[mask].sum())
            sums[name][1] += int(mask.sum())
    return {k: v[0] / max(v[1], 1) for k, v in sums.items()} | {"images": len(picked)}


def main() -> None:
    items = load_items()
    assert len({i.id for i in items}) == 938
    assert all(i.display(None).exists() and i.display(8).exists() for i in items[:50])
    known = [i for i in items if i.id in KNOWN]
    for item in known:
        native = read(item.native(None), "RGBA")
        assert native.shape[:2] == (item.height, item.width), item.id
        assert item.native(8).exists() and item.native(6).exists() and item.display(4).exists()
    assert list(block_index(10, 4, 0)) == [2, 2, 1, 1, 1, 1, 0, 0, 0, 0]
    common = [r for r in common_rows().values()
              if all(isinstance(r.get(k), (int, float)) for k in ("grid_excess_p95", "phase_adjusted", "flip_p99"))]
    print(json.dumps({"items": len(items), "views": {v: sum(i.view == v for i in items) for v in ("rgb", "dark")},
                      "common_valid": len(common),
                      "grid_excess_p95_common": rank_known(common, "grid_excess_p95"),
                      "anchoring_axis0": anchoring(items)}, indent=1))


if __name__ == "__main__":
    main()
