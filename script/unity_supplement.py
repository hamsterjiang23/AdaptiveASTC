"""Build exact-source Unity metrics or collect separately timed offline candidates."""

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.quality import UnityQualityBuild
from reproductions.unity_search_baseline.supplement import UnitySupplementalCapture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build-metrics")
    build.add_argument("--engine-source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    collect = subcommands.add_parser("collect")
    collect.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build-metrics":
        result = UnityQualityBuild.build(args.engine_source, args.output)
    else:
        result = UnitySupplementalCapture(args.config).run()
    print(result, flush=True)


if __name__ == "__main__":
    main()
