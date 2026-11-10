"""Launch isolated literature reproductions and their Unity timing prerequisite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reproductions.common.nah_experiment import NahExperiment  # noqa: E402
from reproductions.common.upstream import EncoderSource  # noqa: E402
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline  # noqa: E402
from reproductions.unity_search_baseline.engine_patch import EngineTimingPatch  # noqa: E402
from reproductions.unity_search_baseline.recovery import BaselineRecovery  # noqa: E402
from reproductions.unity_search_baseline.reporting import write_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "prepare",
            "instrument",
            "fetch",
            "build",
            "run",
            "summarize",
            "recover",
            "report",
            "repair",
            "assemble",
        ],
    )
    parser.add_argument(
        "--method",
        choices=["unity_search_baseline", "nah2022_psnr_search", "nah2023_adaptive_astcenc"],
        default="unity_search_baseline",
    )
    parser.add_argument("--engine", type=Path, default=Path("E:/hamster_unity/unity20190433"))
    parser.add_argument("--no-upm", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--input-set", choices=["probe", "smoke"], default="probe")
    parser.add_argument("--target", type=float)
    parser.add_argument("--initial", default="6x6")
    parser.add_argument(
        "--category", choices=["photos", "game", "gis", "synthesized", "captured"], default="game"
    )
    parser.add_argument("--encoder-threads", type=int, default=1)
    parser.add_argument(
        "--phase", choices=["probe", "smoke1", "smoke2", "smoke3", "full"], default="probe"
    )
    parser.add_argument(
        "--project", type=Path, default=Path("F:/MLBB_Test/haijiangli1_HAMSTERMLBB")
    )
    parser.add_argument(
        "--editor",
        type=Path,
        default=Path("E:/hamster_unity/unity20190433/build/WindowsEditor/Unity.exe"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT
        / "experiment report/.local/gdc-lite-rgb-resnet18-seed20261109/coverage-v2/manifest.json",
    )
    args = parser.parse_args()
    if args.method != "unity_search_baseline":
        if args.action == "run":
            if args.run_id is None:
                parser.error("A literature run requires an explicit --run-id")
            initial = tuple(int(part) for part in args.initial.split("x"))
            if len(initial) != 2:
                parser.error("--initial must have the form 6x6")
            result = NahExperiment(
                ROOT,
                args.method,
                args.project,
                args.manifest,
                args.run_id,
                input_set=args.input_set,
                target=args.target,
                initial=(initial[0], initial[1]),
                category=args.category,
                threads=args.encoder_threads,
            ).run()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result["status"] == "failed":
                raise SystemExit(1)
            return
        if args.action not in ["fetch", "build"]:
            parser.error("Literature encoders support fetch, build and run actions")
        source = EncoderSource(
            ROOT / "reproductions" / args.method,
            ROOT / "experiment report/.local/reproduction-binaries" / args.method,
        )
        result = (
            {"commit": source.fetch()}
            if args.action == "fetch"
            else {"executable": str(source.build())}
        )
        print(json.dumps(result, indent=2))
        return
    baseline = UnitySearchBaseline(
        ROOT,
        args.project,
        args.editor,
        args.manifest,
        run_id=args.run_id or "unity-search-baseline-lite-rdo-off",
    )
    if args.action == "instrument":
        result = EngineTimingPatch(args.engine, baseline.run_dir / "engine-originals").apply()
    elif args.action == "prepare":
        result = baseline.prepare()
    elif args.action == "run":
        result = baseline.run(args.phase, no_upm=args.no_upm)
    elif args.action == "recover":
        config = json.loads(
            (baseline.run_dir / f"{args.phase}-config.json").read_text(encoding="utf-8")
        )
        conflicts = baseline.restore_metadata(Path(config["backupDirectory"]))
        result = {"status": "failed" if conflicts else "passed", "conflicts": conflicts}
    elif args.action == "report":
        result = write_report(baseline)
    elif args.action == "repair":
        result = BaselineRecovery(baseline).run()
    elif args.action == "assemble":
        result = BaselineRecovery(baseline).assemble()
    else:
        result = baseline.summarize(args.phase)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
