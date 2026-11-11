"""Complete ready reference batches, optionally following the live reference collector."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.candidate_queue import UnityCandidateQueue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--follow", action="store_true")
    args = parser.parse_args()
    result = UnityCandidateQueue(Path.cwd(), args.config).run(follow=args.follow)
    print({key: result[key] for key in ["status", "counts", "expected_counts"]})


if __name__ == "__main__":
    main()
