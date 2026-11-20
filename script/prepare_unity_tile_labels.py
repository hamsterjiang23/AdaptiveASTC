"""Generate and verify V5 tile labels from the frozen development archive."""

import argparse
from pathlib import Path

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.data.unity_tile_corpus import UnityTileCorpus

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train", type=int, nargs="+", default=[])
    parser.add_argument("--validation", type=int, nargs="+", default=[])
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if args.full == bool(args.train or args.validation):
        parser.error("Specify --full or explicit development indices")
    handoff = ROOT / "experiment report/unity-accuracy90-20261111/unity-v2-data-inputs.json"
    archive = UnityTileArchive(handoff)
    selection: dict[str, list[int]] = {"train": args.train, "validation": args.validation}
    if args.full:
        selection = {split: list(range(len(rows))) for split, rows in archive.splits.items()}
    report = UnityTileCorpus(archive, args.output).run(selection)
    summary = {key: value for key, value in report.items() if key != "splits"}
    print(summary, flush=True)


if __name__ == "__main__":
    main()
