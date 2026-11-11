"""Check RGBA Dataset inputs and exact native channel targets on frozen corpora."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.dataset_audit import UnityPatchDatasetAudit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    result = UnityPatchDatasetAudit(parser.parse_args().config).run()
    print(
        {
            key: result[key]
            for key in ["status", "unique_images", "wall_seconds", "training_updates"]
        }
    )


if __name__ == "__main__":
    main()
