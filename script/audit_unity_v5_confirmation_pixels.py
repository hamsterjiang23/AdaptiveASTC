"""Gate V5 model evaluation on native RGBA isolation of its complete new cohort."""

from __future__ import annotations

import argparse
import hashlib
import io
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from scipy.spatial import KDTree

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture
from reproductions.unity_search_baseline.confirmation_series import UnityConfirmationSeries
from reproductions.unity_search_baseline.near_duplicates import UnityAlignedPixelDistance
from script.prepare_unity_v5_confirmation_capture import (
    EXECUTION,
    HISTORICAL,
    PUBLIC,
    ROOT,
    checked,
    record,
)
from script.prepare_unity_v5_pixel_revision import PREFLIGHT as REVISED_PREFLIGHT
from script.prepare_unity_v5_pixel_revision import REVISED_AUDIT, REVISED_CAPTURE, REVISION
from script.recover_unity_v5_confirmation_capture import RECOVERED_BATCH, RECOVERED_SERIES
from script.run_unity_v5_pixel_revision import load_capture

REPORT = PUBLIC / "confirmation-pixel-isolation-v1.json"
THRESHOLD = 2.0
CELL_GRID = 8
V5_DEVELOPMENT_SHA256 = "560094e9d87b220b037ed37574e5941f0eff0675ffb43f34737f904e1f895c57"


@dataclass(frozen=True)
class NativeReference:
    asset: str
    path: Path
    sha256: str
    callback_sha256: str
    width: int
    height: int

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    @classmethod
    def from_row(cls, row: JsonDict, reference_key: str) -> NativeReference:
        return cls(
            row["path"],
            Path(row[reference_key]),
            row["reference_sha256"],
            row["actual_options"]["rgba_sha256"],
            row["width"],
            row["height"],
        )

    def pixels(self) -> NDArray[np.uint8]:
        raw = self.path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.sha256:
            raise ValueError(f"Native reference PNG changed: {self.path}")
        with Image.open(io.BytesIO(raw)) as image:
            if image.size != self.size:
                raise ValueError(f"Native PNG has incorrect dimensions: {self.path}")
            rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
        if hashlib.sha256(rgba[::-1].tobytes()).hexdigest() != self.callback_sha256:
            raise ValueError(f"Native pixel order differs from Unity's callback: {self.path}")
        return rgba


@dataclass
class PixelGroup:
    reference: NativeReference
    assets: list[str]
    descriptor: NDArray[np.float64]


def inspect_pixels(
    references: list[NativeReference],
) -> dict[tuple[int, int], dict[str, PixelGroup]]:
    groups: dict[tuple[int, int], dict[str, PixelGroup]] = defaultdict(dict)
    for ref in references:
        pixels = ref.pixels()
        key = ref.callback_sha256
        size_group = groups[ref.size]
        if key not in size_group:
            descriptor = UnityAlignedPixelDistance.descriptor(pixels, CELL_GRID)
            size_group[key] = PixelGroup(ref, [], descriptor)
        size_group[key].assets.append(ref.asset)
    return groups


def compare_pixels(
    development: list[NativeReference], confirmation: list[NativeReference]
) -> JsonDict:
    sizes = {row.size for row in development} & {row.size for row in confirmation}
    old = inspect_pixels(development)
    new = inspect_pixels(confirmation)
    exact, near = [], []
    examined = 0
    for size in sorted(sizes):
        a, b = old[size], new[size]
        for key in sorted(a.keys() & b.keys()):
            exact.append(
                {
                    "width": size[0],
                    "height": size[1],
                    "callback_sha256": key,
                    "development_assets": a[key].assets,
                    "confirmation_assets": b[key].assets,
                }
            )
        dev_groups = list(a.values())
        held_groups = list(b.values())
        tree = KDTree(np.stack([group.descriptor for group in dev_groups]))
        query = np.stack([group.descriptor for group in held_groups])
        neighbors = tree.query_ball_point(query, THRESHOLD + 1e-9, return_sorted=True)
        for held, candidates in zip(held_groups, neighbors, strict=True):
            candidates = [
                i
                for i in candidates
                if (held.reference.callback_sha256 != dev_groups[i].reference.callback_sha256)
            ]
            if not candidates:
                continue
            actual = held.reference.pixels()
            for i in candidates:
                other = dev_groups[i]
                metrics = UnityAlignedPixelDistance.measure(other.reference.pixels(), actual)
                examined += 1
                if metrics["rgba_rmse_8bit"] <= THRESHOLD:
                    near.append(
                        {
                            "development_assets": other.assets,
                            "confirmation_assets": held.assets,
                            "width": size[0],
                            "height": size[1],
                            **metrics,
                        }
                    )
    return {
        "exact_cross_cohort_groups": exact,
        "near_cross_cohort_groups": near,
        "full_resolution_near_comparisons": examined,
        "same_dimensions_groups_tested": len(sizes),
        "confirmation_unique_rgba_identities": sum(len(group) for group in new.values()),
        "within_confirmation_exact_groups": [
            entry.assets
            for group in new.values()
            for entry in group.values()
            if len(entry.assets) > 1
        ],
    }


def captured_rows(
    preflight: JsonDict, recovered_series_sha256: str | None = None
) -> tuple[list[JsonDict], JsonDict]:
    series = UnityConfirmationSeries(ROOT, checked(preflight["series_configuration"]))
    report_path = (
        checked({"path": str(RECOVERED_SERIES), "sha256": recovered_series_sha256})
        if recovered_series_sha256 is not None
        else series.report
    )
    report = A.read_json(report_path)
    if recovered_series_sha256 is not None and (
        checked(report["original_failed_series"]).resolve() != series.report.resolve()
        or checked(report["recovered_native_batch"]).resolve() != RECOVERED_BATCH.resolve()
        or report["unity_reimports"] != 0
    ):
        raise ValueError("Recovered series does not preserve the original capture scope")
    if (
        report["status"] != "passed"
        or report["coverage"] != "complete"
        or report["captured_images"] != 1000
        or report["test_opened"] is not False
        or report["config_sha256"] != series.config_sha
        or report["source_files_sha256"] != series.config["sources_sha256"]
    ):
        raise ValueError("The complete ordered V5 native capture is required")
    manifest = checked({"path": report["manifest"], "sha256": report["manifest_sha256"]})
    payload = A.read_json(manifest)
    fingerprint = payload.pop("fingerprint")
    if fingerprint != A.fingerprint(payload) or payload["status"] != "passed":
        raise ValueError("Native capture manifest differs from its completed fingerprint")
    rows = []
    for batch, (start, count) in zip(report["batches"], [(0, 2), *series.ranges()], strict=True):
        capture = UnityConfirmationCapture(
            ROOT,
            checked(
                {
                    "path": batch["config"],
                    "sha256": batch["config_sha256"],
                }
            ),
        )
        if recovered_series_sha256 is not None and start == 770:
            recovered = A.read_json(RECOVERED_BATCH)
            if checked(recovered["prior_failed_capture"]).resolve() != capture.report:
                raise ValueError("Recovered archive does not bind the original failed capture")
            capture.report = RECOVERED_BATCH
        receipt = capture.baseline.run_dir / "references/normalized-batch/receipt.json"
        if not receipt.is_file():
            raise ValueError("Pixel audit requires archived, completed Unity references")
        actual, binding = series.audit_batch(capture)
        if binding != batch or batch["start"] != start or len(actual) != count:
            raise ValueError("Unity batch cannot be re-audited in the approved cohort order")
        rows.extend(actual)
    reservation = A.read_json(checked(preflight["revised_reservation"]))
    if (
        rows != payload["splits"]["confirmation"]
        or len(rows) != 1000
        or [row["path"] for row in rows] != [row["path"] for row in series.rows]
        or payload["reservation_manifest_sha256"] != reservation["manifest_sha256"]
        or [row["source_sha256"] for row in rows] != [row["source_sha256"] for row in series.rows]
    ):
        raise ValueError("Native capture order or source identities changed")
    return rows, {"series_report": record(report_path), "capture_manifest": record(manifest)}


def revised_rows(capture_sha256: str, preflight: JsonDict) -> tuple[list[JsonDict], JsonDict]:
    capture_binding = {"path": str(REVISED_CAPTURE), "sha256": capture_sha256}
    capture, manifest = load_capture(capture_binding)
    if checked(capture["revision_preflight"]).resolve() != REVISED_PREFLIGHT.resolve():
        raise ValueError("The revised native capture lost its approved authorization binding")
    old, original = load_capture(preflight["prior_completed_capture"])
    fresh, replacements = load_capture(capture["six_replacement_capture"])
    expected = list(original["splits"]["confirmation"])
    changes = preflight["approved_pixel_replacements"]
    for change, new in zip(changes, replacements["splits"]["confirmation"], strict=True):
        index = change["primary_index"]
        if (
            expected[index]["path"] != change["excluded_path"]
            or new["path"] != change["replacement_path"]
        ):
            raise ValueError("The native replacement source moved outside its authorized slot")
        expected[index] = new
    rows = manifest["splits"]["confirmation"]
    revision = A.read_json(checked(preflight["revised_manifest"]))
    if (
        len(rows) != 1000
        or len(changes) != 6
        or rows != expected
        or capture["batches"] != old["batches"] + fresh["batches"]
        or manifest["reservation_manifest_sha256"] != preflight["revised_manifest"]["sha256"]
        or [row["path"] for row in rows] != [row["path"] for row in revision["primary"]]
    ):
        raise ValueError("The re-audit must use all 1,000 authorized native references")
    return rows, {
        "series_report": capture_binding,
        "capture_manifest": {"path": capture["manifest"], "sha256": capture["manifest_sha256"]},
    }


def main() -> None:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--recovered-series-sha256")
    mode.add_argument("--revised-capture-sha256")
    args = parser.parse_args()
    revised = args.revised_capture_sha256 is not None
    destination = REVISED_AUDIT if revised else REPORT
    if destination.exists():
        raise FileExistsError("Preserve the previous pixel isolation result")
    preflight_path = (
        REVISED_PREFLIGHT if revised else PUBLIC / "confirmation-execution-preflight-v1.json"
    )
    preflight = A.read_json(preflight_path)
    checked(preflight["protocol"])
    isolation = A.read_json(
        checked(preflight["source_isolation" if revised else "revised_source_isolation"])
    )
    if (
        preflight["confirmation_authorized_by_user"] is not True
        or isolation["path_group_and_source_md4_overlaps"] != 0
    ):
        raise ValueError("V5 pixel audit requires the approved, source-isolated cohort")
    if revised:
        captured, capture = revised_rows(args.revised_capture_sha256, preflight)
    else:
        captured, capture = captured_rows(preflight, args.recovered_series_sha256)
    adapter = UnityCaptureInputAdapter(captured, "confirmation")
    archive = UnityTileArchive(HISTORICAL / "unity-v2-data-inputs.json")
    if archive.sha256 != V5_DEVELOPMENT_SHA256:
        raise ValueError("Pixel isolation requires the development corpus used for V5 training")
    development = [
        NativeReference.from_row(row, "reference")
        for split in ("train", "validation")
        for row in archive.splits[split]
    ]
    confirmation = [NativeReference.from_row(row, "reference_png") for row in captured]
    measurements = compare_pixels(development, confirmation)
    passed = not (
        measurements["exact_cross_cohort_groups"] or measurements["near_cross_cohort_groups"]
    )
    inputs = (REVISION if revised else EXECUTION) / "pixel-audited-inputs.json"
    A.write_json(
        inputs, {"schema": "unity-v5-confirmation-pixel-inputs-v1", "rows": adapter.bindings}
    )
    A.write_json(
        destination,
        {
            "status": "passed" if passed else "failed_cross_cohort_overlap",
            "full_scoped_pixel_isolation_passed": passed,
            "revised_cohort": revised,
            "execution_preflight": record(preflight_path),
            **capture,
            "development_corpus": {"path": str(archive.path), "sha256": archive.sha256},
            "counts": {"train": 10000, "validation": 1000, "confirmation": 1000},
            "inputs": record(inputs),
            "input_fingerprint": adapter.fingerprint,
            "rgba_near_rmse_8bit": THRESHOLD,
            "cell_grid": CELL_GRID,
            "scope": "Cross-cohort exact native RGBA and aligned same-dimension native RGBA RMSE",
            "capture_types": sorted({row["texture_type"] for row in adapter.bindings}),
            "model_forward_calls": 0,
            "training_updates": 0,
            "test_opened": False,
            **measurements,
            "wall_seconds": time.perf_counter() - started,
        },
    )
    print(f"V5 native pixel isolation: {destination}, passed={passed}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
