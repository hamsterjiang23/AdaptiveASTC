"""Create a new V2 development cohort with approved input-scope replacements."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.development_revision import UnityDevelopmentRevision


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    arguments = parser.parse_args()
    result = UnityDevelopmentRevision(Path.cwd(), arguments.config).reserve()
    print({key: result[key] for key in ["status", "counts", "replacement_counts"]})


if __name__ == "__main__":
    main()
