"""Measure full candidate grids from frozen imported color and mip0 normal references."""

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
