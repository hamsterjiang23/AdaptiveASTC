"""Evaluate gradient detection on frozen Unity development assets and matched controls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from distortion import measure_distortion
from PIL import Image
from scipy.ndimage import label
from source_support import source_support

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tmp/multimetric-review-20261118/population/fixed8_manifest.json"
NATIVE_BUILD = (
    ROOT
    / "experiment report/.local/unity-accuracy90-20261111"
    / "unity-quality-native-retry1/build-receipt.json"
)
BASELINE = ROOT / "metric/gradient-screen/fixed8-validation.csv"
LEGACY_PHASE = ROOT / "metric/gradient-screen/phase-validation.csv"
KNOWN = (615, 616, 617, 544, 698)
PEERS = (407, 467, 474, 489)
EXTRA_PRESETS = {544: ("fast",), 698: ("thorough", "exhaustive")}
SCORES = (
    "tangential_p95",
    "tangential_smoothed_p95",
    "normal_step_p95",
    "normal_step_p99",
    "grid_excess",
)

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BASELINE.parent))
from seam_metric import gradient_mask, lab  # pyright: ignore[reportMissingImports]  # noqa: E402

from reproductions.unity_search_baseline.quality import UnityQuality  # noqa: E402

type Scalar = str | bool | int | float | None
type Row = dict[str, Scalar]
type Job = tuple[list[Row], Row, int]


def image(path: Path, sha256: str) -> np.ndarray:
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise ValueError(f"Mismatched archive identity: {path}")
    with Image.open(path) as handle:
        return np.asarray(handle.convert("RGBA"))


def linear_light(srgb: np.ndarray) -> np.ndarray:
    return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)


def composite(rgba: np.ndarray, background: int | None) -> np.ndarray:
    if background is None:
        return rgba[..., :3]
    alpha = rgba[..., 3:] / 255
    backdrop = float(linear_light(np.array(background / 255)))
    value = alpha * linear_light(rgba[..., :3] / 255) + (1 - alpha) * backdrop
    srgb = np.where(value <= 0.0031308, value * 12.92, 1.055 * value ** (1 / 2.4) - 0.055)
    return np.rint(srgb * 255).clip(0, 255).astype(np.uint8)


def source_field(rgba: np.ndarray) -> np.ndarray:
    alpha = rgba[..., 3:] / 255
    return np.concatenate((alpha * lab(rgba[..., :3]), 100 * alpha), axis=2)


def area_summary(support: dict[str, np.ndarray]) -> dict[str, float | int]:
    mask = support["quadratic"]
    components = np.empty(mask.shape, dtype=np.int32)
    label(mask, output=components)
    return {
        "linear_area_pct": float(support["linear"].mean() * 100),
        "quadratic_area_pct": float(mask.mean() * 100),
        "quadratic_pixels": int(mask.sum()),
        "largest_quadratic_pixels": int(np.bincount(components[mask]).max()) if mask.any() else 0,
    }


def sum_squared_channels(error: np.ndarray) -> np.ndarray:
    return np.square(error, dtype=np.int64).sum(axis=(0, 1))


def shuffled_decode(
    reference: np.ndarray, error: np.ndarray, groups: list[np.ndarray], seed: int
) -> np.ndarray:
    """Move complete residual vectors only where both resulting pixels remain legal."""
    rng = np.random.default_rng(seed)
    channels = reference.shape[-1]
    pixels = reference.reshape(-1, channels).astype(np.int16)
    residuals = error.reshape(-1, channels).copy()
    for _ in range(4):
        for group in groups:
            order = rng.permutation(group)[: 2 * (len(group) // 2)]
            left, right = order[::2], order[1::2]
            first = pixels[left] + residuals[right]
            second = pixels[right] + residuals[left]
            legal = ((first >= 0) & (first <= 255) & (second >= 0) & (second <= 255)).all(axis=1)
            left, right = left[legal], right[legal]
            residuals[left], residuals[right] = residuals[right], residuals[left]
    return (pixels + residuals).astype(np.uint8).reshape(reference.shape)


def groups_for_shuffle(reference: np.ndarray) -> list[np.ndarray]:
    luma = np.rint(reference[..., :3] @ np.array([0.2126, 0.7152, 0.0722])).astype(int)
    bins = (luma // 16 + 16 * (reference[..., 3] // 16)).ravel()
    return [np.flatnonzero(bins == key) for key in np.unique(bins)]


def display_sse(reference: np.ndarray, decoded: np.ndarray) -> int:
    return int(sum_squared_channels(decoded.astype(np.int16) - reference).sum())


def measure_asset(job: Job) -> list[Row]:
    items, baseline, seeds = job
    first = items[0]
    reference = image(Path(str(first["reference_path"])), str(first["reference_sha256"]))
    if reference.shape != (first["height"], first["width"], 4):
        raise ValueError(f"Unexpected native dimensions for asset {first['validation_index']}")
    raw = area_summary(source_support(source_field(reference)))
    alpha = bool(first["need_alpha"])
    backgrounds = {"dark": 64, "light": 192} if alpha else {"rgb": None}
    displays = {name: composite(reference, background) for name, background in backgrounds.items()}
    fields = {name: lab(display) for name, display in displays.items()}
    support = {name: source_support(field) for name, field in fields.items()}
    areas = {name: area_summary(region) for name, region in support.items()}
    legacy_areas = {
        name: float(gradient_mask(field).mean() * 100) for name, field in fields.items()
    }
    rows = []
    native = UnityQuality(NATIVE_BUILD) if seeds else None
    for item in items:
        if item["reference_sha256"] != first["reference_sha256"]:
            raise ValueError("Reference identity varies between presets of one asset")
        decoded = image(Path(str(item["decoded_path"])), str(item["decoded_sha256"]))
        error = decoded.astype(np.int16) - reference
        channel_sse = sum_squared_channels(error)
        groups = groups_for_shuffle(reference) if seeds else []
        test_seeds = range(seeds) if item["preset"] == "fastest" else range(0)
        for seed in [-1, *test_seeds]:
            candidate = decoded if seed < 0 else shuffled_decode(reference, error, groups, seed)
            if native is not None:
                if not np.array_equal(
                    sum_squared_channels(candidate.astype(np.int16) - reference), channel_sse
                ):
                    raise ValueError("Native residual rearrangement changed channel SSE")
                scored = native.measure(reference, candidate, need_alpha=alpha, compute_ssim=False)
                if scored["psnr"] != item["native_psnr_db"]:
                    raise ValueError(f"Native PSNR mismatch for asset {item['validation_index']}")
            for name, background in backgrounds.items():
                src = fields[name]
                test = composite(candidate, background)
                sse = display_sse(displays[name], test)
                primary = name == baseline["view"] and seed < 0 and item["preset"] == "fastest"
                rows.append(
                    {
                        "id": item["validation_index"],
                        "asset": baseline["asset"],
                        "width": item["width"],
                        "height": item["height"],
                        "preset": item["preset"],
                        "view": name,
                        "seed": None if seed < 0 else seed,
                        "native_psnr": item["native_psnr_db"],
                        "native_psnr_recomputed": native is not None,
                        "display_psnr": float(10 * np.log10(255**2 * test.size / sse))
                        if sse
                        else None,
                        "display_rgb_sse": sse,
                        "legacy_gradient_area_pct": legacy_areas[name],
                        "legacy_grid_p95": baseline["grid_excess_p95"] if primary else None,
                        "legacy_phase_adjusted": baseline["phase_adjusted"] if primary else None,
                        **{f"source_rgba_{key}": value for key, value in raw.items()},
                        **areas[name],
                        **measure_distortion(src, lab(test), support[name], block=8),
                    }
                )
    return rows


def load_jobs(cohort128: bool, seeds: int) -> tuple[list[Job], set[int]]:
    with BASELINE.open(encoding="utf-8-sig", newline="") as handle:
        baseline = {int(row["id"]): row for row in csv.DictReader(handle)}
    with LEGACY_PHASE.open(encoding="utf-8-sig", newline="") as handle:
        legacy_phase = {int(row["id"]): row["phase_adjusted"] for row in csv.DictReader(handle)}
    for id_, row in baseline.items():
        row["phase_adjusted"] = legacy_phase[id_]
    cohort = {
        id_
        for id_, row in baseline.items()
        if cohort128 and row["width"] == row["height"] == "128" and float(row["native_psnr"]) >= 35
    }
    selected = cohort | set(KNOWN) | set(PEERS)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items: dict[int, list[Row]] = {id_: [] for id_ in sorted(selected)}
    for candidate in manifest:
        id_ = int(candidate["validation_index"])
        preset = candidate["preset"]
        if id_ in selected and preset in ("fastest", *EXTRA_PRESETS.get(id_, ())):
            if not candidate["srgb"] or candidate["is_normal"]:
                raise ValueError(f"Asset {id_} is outside the SDR color protocol")
            items[id_].append(candidate)
            if preset == "fastest" and candidate["native_psnr_db"] != float(
                str(baseline[id_]["native_psnr"])
            ):
                raise ValueError(f"Archived native PSNR disagrees for asset {id_}")
    for id_, rows in items.items():
        if len(rows) != 1 + len(EXTRA_PRESETS.get(id_, ())):
            raise ValueError(f"Missing or duplicate compression candidates for asset {id_}")
    jobs = [(rows, baseline[id_], seeds if id_ in KNOWN else 0) for id_, rows in items.items()]
    return jobs, cohort


def describe(rows: list[Row], cohort: set[int]) -> dict[str, object]:
    fastest = [row for row in rows if row["seed"] is None and row["preset"] == "fastest"]
    controls = [row for row in rows if row["seed"] is not None]
    comparisons = []
    for row in fastest:
        matched = [
            control
            for control in controls
            if (control["id"], control["view"]) == (row["id"], row["view"])
        ]
        if not matched:
            continue
        distributions: dict[str, object] = {}
        for score in SCORES:
            matched_values = (entry[score] for entry in matched)
            values = [float(value) for value in matched_values if isinstance(value, (int, float))]
            truth = row[score]
            distributions[score] = {
                "real": truth,
                "controls_with_value": len(values),
                "control_median": float(np.median(values)) if values else None,
                "control_max": max(values, default=None),
                "controls_ge_real": sum(value >= truth for value in values)
                if isinstance(truth, (float, int))
                else None,
            }
        comparisons.append(
            {
                "id": row["id"],
                "view": row["view"],
                "controls": len(matched),
                "native_psnr": row["native_psnr"],
                "real_display_psnr": row["display_psnr"],
                "control_display_psnr_range": [
                    min(float(str(entry["display_psnr"])) for entry in matched),
                    max(float(str(entry["display_psnr"])) for entry in matched),
                ],
                "scores": distributions,
            }
        )
    base = [row for row in fastest if row["id"] in cohort and row["view"] != "light"]
    coverage = {
        key: sum(row[key] not in (None, "") for row in base)
        for key in (*SCORES, "legacy_grid_p95", "legacy_phase_adjusted")
    }
    rank = {}
    for score in (*SCORES, "legacy_grid_p95", "legacy_phase_adjusted"):
        valid = sorted(
            (row for row in base if row[score] not in (None, "")),
            key=lambda row: (-float(str(row[score])), int(str(row["id"]))),
        )
        rank[score] = {
            str(row["id"]): index for index, row in enumerate(valid, 1) if row["id"] in KNOWN
        }
    return {
        "cohort_rows": len(base),
        "coverage": coverage,
        "rank_among_valid_rows": rank,
        "matched_controls": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=0)
    parser.add_argument("--cohort128", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.seeds < 0 or args.workers < 1:
        parser.error("Expected nonnegative seed count and positive worker count")
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[key] = "1"
    jobs, cohort = load_jobs(args.cohort128, args.seeds)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [row for measured in pool.map(measure_asset, jobs) for row in measured]
    summary = describe(rows, cohort)
    summary.update(
        {
            "asset_count": len(jobs),
            "row_count": len(rows),
            "control_seeds_per_target": args.seeds,
            "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        }
    )
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "scores.csv").open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(f"{len(jobs)} assets, {len(rows)} rows, cohort={len(cohort)}, matched seeds={args.seeds}")
    print(summary["coverage"])


if __name__ == "__main__":
    main()
