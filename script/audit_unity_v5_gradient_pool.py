"""Recompute the original 560-image fixed8 gradient observation from archived pixels."""

import argparse
import time
from collections.abc import Iterator
from pathlib import Path

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_tile_oracle import TileObservation, UnityTileOracle
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "experiment report/.local/unity-v5-20261119"


def progress(observations: Iterator[TileObservation]) -> Iterator[TileObservation]:
    for i, observation in enumerate(observations, 1):
        if i % 32 == 0:
            print(f"Recomputed {i} archived gradient comparisons", flush=True)
        yield observation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(RAW) or output.exists():
        parser.error("Use a new V5 local audit path")
    started = time.perf_counter()
    public = ROOT / "experiment report/unity-v5-20261119/progress.json"
    step = A.read_json(public)["step_baseline"]
    source = UnityTileArchive.read_bound_json(ROOT / step["path"], step["sha256"], dict)
    handoff = ROOT / "experiment report/unity-accuracy90-20261111/unity-v2-data-inputs.json"
    archive = UnityTileArchive(handoff)
    if (
        source["status"] != "passed"
        or source["test_opened"] is not False
        or source["color_coverage"] != "complete"
        or source["candidate"] != [8, "fastest"]
        or source["development_corpus_sha256"] != archive.sha256
    ):
        raise ValueError("Historical gradient pool requires the validated V5 native step cohort")
    rows = [row for row in source["rows"] if row["native_psnr"] >= 35]
    if len(rows) != 560:
        raise ValueError("Historical 560-image comparison scope changed")
    if args.smoke:

        def pixels(row: dict[str, object]) -> int:
            index = row["index"]
            assert isinstance(index, int)
            image = archive.splits["validation"][index]
            return int(image["width"] * image["height"])

        largest = max(rows, key=pixels)["index"]
        rows = [row for row in rows if row["index"] in {615, 616, 617, largest}]
    names = (
        "script/audit_unity_v5_gradient_pool.py",
        "src/adaptive_astc/evaluation/unity_tile_oracle.py",
        "src/adaptive_astc/data/unity_tile_archive.py",
        "src/adaptive_astc/data/unity_tile_errors.py",
    )
    hashes = {name: A.sha256_file(ROOT / name) for name in names}
    result = UnityTileOracle.summarize(progress(UnityTileOracle.decode_observations(archive, rows)))
    if hashes != {name: A.sha256_file(ROOT / name) for name in names}:
        raise ValueError("Pixel audit sources changed during execution")
    A.write_json(
        output,
        {
            "status": "passed",
            "smoke": args.smoke,
            "scope": "Exact display RGB SSE from archived PNGs",
            "source_sha256": hashes,
            "step_report_sha256": step["sha256"],
            "development_corpus_sha256": archive.sha256,
            "test_opened": False,
            "actual_encode_calls": 0,
            "wall_seconds": time.perf_counter() - started,
            **result,
        },
    )
    print(f"Recomputed {result['images']} exact gradient comparisons")


if __name__ == "__main__":
    main()
