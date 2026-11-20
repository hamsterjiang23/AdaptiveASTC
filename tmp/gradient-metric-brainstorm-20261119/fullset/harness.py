"""Shared inputs, ASTC grid helpers, ranking and review sheets for full-set gradient-metric checks."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
REVIEW = ROOT / "outputs/01a1eca4-b759-74d2-82d5-2d27a4db8e18"
MANIFEST = ROOT / "tmp/multimetric-review-20261118/population/fixed8_manifest.json"
BASELINE = ROOT / "metric/gradient-screen/fixed8-validation.csv"
COMMON = ROOT / "metric/gradient-statistics/fixed8-absolute.csv"
KNOWN = (615, 616, 617)
PRESETS = ("fastest", "fast", "medium", "thorough", "exhaustive")
Row = dict[str, object]


@dataclass(frozen=True)
class Item:
    id: int
    asset: str
    group: str
    view: str
    width: int
    height: int
    need_alpha: bool
    native_psnr: float
    display_psnr: float
    flip_p99: float
    reference_native: Path
    decoded_dir: Path

    def display(self, block: int | None = 8, preset: str = "fastest") -> Path:
        """Display PNG: None gives the reference, 8 the archived 8x8 file, other sizes the prefixed files."""
        folder = REVIEW / "media" / f"{self.id:04d}"
        if block is None:
            return folder / f"ref-{self.view}.png"
        prefix = "" if block == 8 else f"{block}x{block}-"
        return folder / f"{prefix}{preset}-{self.view}.png"

    def native(self, block: int | None = 8, preset: str = "fastest") -> Path:
        """Native RGBA PNG in display row order; the Unity candidate queue holds 6/8/10/12 only."""
        if block is None:
            return self.reference_native
        if block not in (6, 8, 10, 12):
            raise ValueError(f"native decode not archived for {block}x{block}")
        return self.decoded_dir / f"{block}x{block}_{preset}.png"


def load_items() -> list[Item]:
    raw = (REVIEW / "data.js").read_text(encoding="utf-8")
    assets = json.loads(raw.removeprefix("window.REVIEW=").removesuffix(";"))["assets"]
    manifest = {(r["validation_index"], r["preset"]): r for r in json.loads(MANIFEST.read_bytes())}
    items = []
    for asset in assets:
        if asset["views"] == ["data"]:
            continue
        view = "dark" if "dark" in asset["views"] else "rgb"
        row = next(r for r in asset["rows"] if (r["view"], r["preset"]) == (view, "fastest"))
        native = manifest[asset["id"], "fastest"]
        assert native["block"] == 8 and native["asset"] == asset["asset"]
        items.append(Item(id=asset["id"], asset=asset["asset"], group=asset["group"], view=view,
                          width=asset["w"], height=asset["h"], need_alpha=bool(native["need_alpha"]),
                          native_psnr=_finite(row["psnr"]), display_psnr=_finite(row["viewpsnr"]),
                          flip_p99=_finite(row["fp99"]), reference_native=Path(native["reference_path"]),
                          decoded_dir=Path(native["decoded_path"]).parent))
    assert len(items) == 938
    return items


def _finite(value: object) -> float:
    """Archive values are numbers; identical images store a text infinity marker."""
    return float(value) if isinstance(value, (int, float)) else math.inf


def read(path: Path, mode: str = "RGB") -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert(mode))


def grid_edges(length: int, block: int, axis: int) -> np.ndarray:
    """Boolean mask over np.diff indices along an axis: True where the step crosses an ASTC block edge.

    Display rows are Unity rows flipped, so along axis 0 the grid is anchored at the bottom row.
    The step k joins pixels k and k+1; its edge position is p = k+1.
    """
    position = np.arange(1, length)
    native = length - position if axis == 0 else position
    return native % block == 0


def block_index(length: int, block: int, axis: int) -> np.ndarray:
    """Block id of every pixel along one axis, anchored the same way as grid_edges."""
    pixel = np.arange(length)
    return (length - 1 - pixel) // block if axis == 0 else pixel // block


def rank_known(rows: Sequence[Row], metric: str, descending: bool = True) -> dict[str, object]:
    """Strict rank (1 + count strictly worse) of each known image among rows with a finite value."""
    valid = [r for r in rows if isinstance(r.get(metric), (int, float)) and math.isfinite(r[metric])]
    values = np.array([r[metric] for r in valid], dtype=float)
    ranks = {}
    for r in valid:
        if r["id"] in KNOWN:
            v = r[metric]
            better = np.sum(values > v) if descending else np.sum(values < v)
            ties = np.sum(values == v) - 1
            ranks[str(r["id"])] = dict(rank=int(better) + 1, ties=int(ties))
    worst = max((v["rank"] + v["ties"] for v in ranks.values()), default=None)
    n = len(valid)
    budgets = {}
    for share in (0.05, 0.10, 0.15):
        cut = math.ceil(share * n)
        budgets[f"top{int(share * 100)}pct_n{cut}"] = sum(v["rank"] <= cut for v in ranks.values())
    return dict(n=n, known=ranks, budget_for_all=worst, recall=budgets,
                missing=[k for k in KNOWN if str(k) not in ranks])


def family_report(rows: Sequence[Row], metric: str, top: int, descending: bool = True) -> dict[str, object]:
    valid = [r for r in rows if isinstance(r.get(metric), (int, float)) and math.isfinite(r[metric])]
    ordered = sorted(valid, key=lambda r: ((-r[metric]) if descending else r[metric], r["id"]))[:top]
    groups = Counter(str(r["group"]) for r in ordered)
    return dict(top=len(ordered), distinct_groups=len(groups), groups=groups.most_common(12),
                effects=sum("/Effects/" in str(r["asset"]) for r in ordered),
                alpha=sum(r["view"] == "dark" for r in ordered),
                sizes=Counter(f"{r['width']}x{r['height']}" for r in ordered).most_common(6),
                ids=[r["id"] for r in ordered])


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    if keep.sum() < 3:
        return None
    rx = np.argsort(np.argsort(x[keep])).astype(float)
    ry = np.argsort(np.argsort(y[keep])).astype(float)
    return float(np.corrcoef(rx, ry)[0, 1])


def _number(value: str) -> object:
    if value in ("", "None"):
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() and "." not in value else number


def _csv_rows(path: Path) -> dict[int, Row]:
    with path.open(encoding="utf-8-sig") as handle:
        return {int(r["id"]): {k: _number(v) for k, v in r.items()} for r in csv.DictReader(handle)}


def baseline_rows() -> dict[int, Row]:
    """Earlier 938-image 8x8 fastest scores (continuous seam, grid excess, gradient change)."""
    return _csv_rows(BASELINE)


def common_rows() -> dict[int, Row]:
    """The 560 native-PSNR>=35 rows used by the earlier three-signal review queue."""
    return _csv_rows(COMMON)


def review_sheet(entries: Sequence[tuple[Item, int, int, str]], path: Path, block: int = 8,
                 preset: str = "fastest", window: int = 32, zoom: int = 6) -> None:
    """Rows of reference | decoded | 4x error crops around (x, y), nearest-neighbour zoom, ASTC grid ticks."""
    cell = window * zoom
    pad, text = 6, 16
    sheet = Image.new("RGB", (3 * cell + 4 * pad, len(entries) * (cell + text + pad) + pad), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for row, (item, x, y, title) in enumerate(entries):
        ref = read(item.display(None))
        dec = read(item.display(block, preset))
        h, w = ref.shape[:2]
        x0 = int(min(max(x - window // 2, 0), max(w - window, 0)))
        y0 = int(min(max(y - window // 2, 0), max(h - window, 0)))
        crops = [ref[y0:y0 + window, x0:x0 + window], dec[y0:y0 + window, x0:x0 + window]]
        err = np.abs(crops[1].astype(int) - crops[0].astype(int)).max(axis=2) * 4
        crops.append(np.repeat(np.clip(err, 0, 255).astype(np.uint8)[..., None], 3, axis=2))
        top = pad + row * (cell + text + pad)
        draw.text((pad, top), f"{item.id:04d} {title}", fill=(230, 230, 230))
        for col, crop in enumerate(crops):
            tile = Image.fromarray(np.ascontiguousarray(crop)).resize(
                (crop.shape[1] * zoom, crop.shape[0] * zoom), Image.NEAREST)
            left = pad + col * (cell + pad)
            sheet.paste(tile, (left, top + text))
            ys = np.flatnonzero(grid_edges(h, block, 0)[y0:y0 + crop.shape[0] - 1]) + 1
            xs = np.flatnonzero(grid_edges(w, block, 1)[x0:x0 + crop.shape[1] - 1]) + 1
            for gy in ys:
                draw.line([(left, top + text + gy * zoom), (left + 3, top + text + gy * zoom)], fill=(255, 80, 80))
            for gx in xs:
                draw.line([(left + gx * zoom, top + text), (left + gx * zoom, top + text + 3)], fill=(255, 80, 80))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
