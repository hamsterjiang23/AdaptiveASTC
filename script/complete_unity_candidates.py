"""Measure mip0 candidate grids using the captured color or normal quality scope."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.candidate_completion import UnityCandidateCompletion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityCandidateCompletion(args.config).run()
    print(
        {
            "status": result["status"],
            "images": len(result["rows"]),
            "report": result["config"]["report"],
        }
    )


if __name__ == "__main__":
    main()
