"""Recompute the V5 luminance step baseline on archived ASTC 8x8 fastest decodes."""

import argparse
import time
from pathlib import Path

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.data.unity_tile_errors import UnityTileViews
from adaptive_astc.evaluation.unity_gradient_step import UnityGradientStep
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", type=int, nargs="+")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "experiment report/.local/unity-v5-20261119"):
        parser.error("Keep V5 raw results in its local experiment directory")
    handoff = ROOT / "experiment report/unity-accuracy90-20261111/unity-v2-data-inputs.json"
    archive = UnityTileArchive(handoff)
    eligible = {
        row["index"]
        for row in archive.splits["validation"]
        if row["import_metadata"]["srgb"] and not row["metadata"]["is_normal"]
    }
    indices: list[int] = sorted(eligible) if args.indices is None else args.indices
    if len(set(indices)) != len(indices) or not set(indices).issubset(eligible):
        parser.error("Use unique native sRGB color validation indices")
    output.mkdir(parents=True, exist_ok=False)
    source_paths = [
        Path(__file__),
        ROOT / "src/adaptive_astc/evaluation/unity_gradient_step.py",
        ROOT / "src/adaptive_astc/data/unity_tile_errors.py",
        ROOT / "src/adaptive_astc/data/unity_tile_archive.py",
    ]
    sources = {p.relative_to(ROOT).as_posix(): A.sha256_file(p) for p in source_paths}
    start = time.perf_counter()
    details = []
    index = None
    try:
        for index in indices:
            image = archive.image("validation", index)
            candidate = image.candidates[archive.GRID.index((8, "fastest"))]
            need_alpha = image.row["actual_options"]["need_alpha"]
            reference = UnityTileViews.display(image.reference(), need_alpha)
            decoded = UnityTileViews.display(image.decode(candidate), need_alpha)
            l_p95, count = UnityGradientStep.score(reference, decoded)
            details.append(
                {
                    "index": index,
                    "asset": image.row["path"],
                    "reference_sha256": image.row["reference_sha256"],
                    "decoded_sha256": candidate["decoded_png_sha256"],
                    "native_psnr": candidate["metrics"]["psnr"],
                    "window_count": count,
                    "l_p95_primary": l_p95,
                }
            )
            if len(details) % 32 == 0:
                print(f"{len(details)}/{len(indices)} validation step scores computed", flush=True)
        if sources != {p.relative_to(ROOT).as_posix(): A.sha256_file(p) for p in source_paths}:
            raise ValueError("Step baseline source changed during computation")
    except Exception as error:
        A.write_json(
            output / "failure.json", {"index": index, "error": str(error), "rows": details}
        )
        raise
    A.write_json(
        output / "report.json",
        {
            "status": "passed",
            "split": "validation",
            "candidate": [8, "fastest"],
            "color_coverage": "complete" if set(indices) == eligible else "partial",
            "images": len(details),
            "scored": sum(row["l_p95_primary"] is not None for row in details),
            "development_corpus_sha256": archive.sha256,
            "source_sha256": sources,
            "wall_seconds": time.perf_counter() - start,
            "test_opened": False,
            "rows": details,
        },
    )
    print(f"Computed {len(details)} validation step scores", flush=True)


if __name__ == "__main__":
    main()
