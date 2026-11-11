"""Prepare native RGBA patch targets from a frozen Unity candidate manifest."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.patch_targets import UnityPatchCorpus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    result = UnityPatchCorpus(parser.parse_args().config).prepare()
    print({key: result[key] for key in ["status", "counts", "patch_counts", "wall_seconds"]})


if __name__ == "__main__":
    main()
