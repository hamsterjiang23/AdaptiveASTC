"""Run the V5 development-only tile/label audit against frozen Unity PNGs."""

import argparse
from pathlib import Path

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_tile_audit import UnityTileAudit
from adaptive_astc.utils.artifacts import ArtifactStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", type=int, nargs="+")
    parser.add_argument(
        "--history",
        type=Path,
        default=ROOT / "experiment plan/V5/known-tile-history.csv",
    )
    args = parser.parse_args()
    handoff = ROOT / "experiment report/unity-accuracy90-20261111/unity-v2-data-inputs.json"
    indices: list[int] | None = args.indices
    if indices is None:
        v4_selection = ROOT / "experiment report/unity-v4-20261117/smoke-selection.json"
        baseline: list[int] = ArtifactStore.read_json(v4_selection)["indices"]
        indices = sorted((set(baseline) - {1, 2, 3}) | set(UnityTileAudit.KNOWN))
    result = UnityTileAudit(UnityTileArchive(handoff), args.history).run(indices, args.output)
    print(f"{result['status']}: {result['images']} images, {result['candidate_decodes']} decodes")
    return int(result["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
