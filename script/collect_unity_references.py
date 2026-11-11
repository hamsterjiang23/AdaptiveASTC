"""Run a frozen serial reference collection plan or revalidate its completed corpus."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.collection import UnityReferenceSeries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate", "collect", "assemble"])
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    series = UnityReferenceSeries(Path(__file__).resolve().parents[1], args.config)
    if args.action == "validate":
        _, batches = series.validate()
        print(
            {
                "status": "passed",
                "batches": len(batches),
                "scope": "plan identity and coverage only",
            }
        )
    else:
        result = series.run(collect=args.action == "collect")
        print({key: result[key] for key in ["status", "counts", "manifest", "manifest_sha256"]})


if __name__ == "__main__":
    main()
