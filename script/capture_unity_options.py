"""Capture actual Unity encoder arguments or restore a journaled source hook."""

import argparse
from pathlib import Path

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.metadata import ManagedCaptureHook, UnityOptionCapture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    audit = subcommands.add_parser("audit")
    audit.add_argument("--config", type=Path, required=True)
    audit.add_argument("--report", type=Path, required=True)
    restore = subcommands.add_parser("restore")
    restore.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "restore":
        receipt = ArtifactStore.read_json(args.journal / "receipt.json")
        source = Path(receipt["source"])
        if [part.casefold() for part in source.parts[-4:]] != [
            "assets",
            "editor",
            "astc",
            "astccustom.cs",
        ]:
            raise ValueError("Recovery source is not the expected project callback")
        project = source.parents[3]
        UnitySearchBaseline(project, project, project, project).require_project_closed()
        result = ManagedCaptureHook(args.journal).restore()
    elif args.command == "audit":
        result = UnityOptionCapture(Path(__file__).resolve().parents[1], args.config).reaudit(
            args.report
        )
    else:
        result = UnityOptionCapture(Path(__file__).resolve().parents[1], args.config).run()
    print(result, flush=True)


if __name__ == "__main__":
    main()
