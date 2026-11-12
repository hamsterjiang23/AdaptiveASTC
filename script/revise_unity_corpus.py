"""Build a new native development corpus from approved replacement measurements."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.development_corpus_revision import (
    UnityDevelopmentCorpusRevision,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityDevelopmentCorpusRevision(Path.cwd(), args.config).run()
    print({key: result[key] for key in ["status", "counts", "patch_counts", "corpus_sha256"]})


if __name__ == "__main__":
    main()
