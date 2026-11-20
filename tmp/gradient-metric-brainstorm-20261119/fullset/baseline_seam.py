"""Runner check: re-score the earlier continuous seam and grid-excess metrics at several block sizes."""
from __future__ import annotations

import sys

from harness import ROOT, Item, Row, read

sys.path.insert(0, str(ROOT / "metric/gradient-screen"))
from seam_metric import evaluate, gradient_mask, lab  # noqa: E402

from runner import main  # noqa: E402


def score(item: Item, block: int, preset: str) -> Row:
    source = lab(read(item.display(None)))
    result, _ = evaluate(source, lab(read(item.display(block, preset))), gradient_mask(source), block)
    return {"continuous_seam": result["continuous_seam"], "grid_excess_p95": result["grid_excess_p95"]}


if __name__ == "__main__":
    main(score, "baseline-seam", [("continuous_seam", True), ("grid_excess_p95", True)], blocks=(4, 6, 8))
