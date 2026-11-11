"""Launch isolated literature reproductions and their Unity timing prerequisite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reproductions.common.nah_experiment import NahExperiment  # noqa: E402
from reproductions.common.reporting import NahReport  # noqa: E402
from reproductions.common.upstream import EncoderSource  # noqa: E402
from reproductions.texnn.corpus import TexNNBlockCorpus, TexNNCorpusBuilder  # noqa: E402
from reproductions.texnn.data import TexNNLabelCollector  # noqa: E402
from reproductions.texnn.reference import TexNNReference  # noqa: E402
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
            "collect",
            "dataset",
            "train",
            "evaluate",
            "benchmark",
        ],
    )
    parser.add_argument(
        "--method",
        choices=[
            "unity_search_baseline",
            "nah2022_psnr_search",
            "nah2023_adaptive_astcenc",
            "texnn",
            "gdc2023",
        ],
        default="unity_search_baseline",
    )
    parser.add_argument("--engine", type=Path, default=Path("E:/hamster_unity/unity20190433"))
    parser.add_argument("--no-upm", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--input-set", choices=["probe", "smoke", "full"], default="probe")
    parser.add_argument("--target", type=float)
    parser.add_argument("--initial", default="6x6")
    parser.add_argument(
        "--category", choices=["photos", "game", "gis", "synthesized", "captured"], default="game"
    )
    parser.add_argument("--encoder-threads", type=int, default=1)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--footprint", choices=["4x4", "6x6", "8x8"], default="4x4")
    parser.add_argument("--preset", default="exhaustive")
    parser.add_argument("--images", type=int, default=64)
    parser.add_argument("--patch-size", type=int, default=64)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--network", choices=["pnn", "demnn", "all"], default="all")
    parser.add_argument("--all-footprints", action="store_true")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--partition-topk", type=int, default=1)
    parser.add_argument("--joint-topk", type=int, default=1)
    parser.add_argument("--evaluation-id")
    parser.add_argument("--inference-device", default="cpu")
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
    if args.method == "gdc2023":
        from reproductions.gdc2023.dataset import GDCMeasuredDataset

        if not args.run_id or Path(args.run_id).name != args.run_id or args.run_id in {".", ".."}:
            parser.error("GDC preparation requires a single-directory --run-id")
        directory = ROOT / "experiment report/.local/reproduction-runs/gdc2023" / args.run_id
        dataset = GDCMeasuredDataset(ROOT, args.project, args.manifest, directory)
        if args.action == "dataset":
            counts = {
                "probe": {"train": 2, "validation": 2, "calibration": 2, "test": 2},
                "smoke": {"train": 32, "validation": 8, "calibration": 8, "test": 16},
                "full": {"train": 10000, "validation": 1000, "calibration": 1000, "test": 2000},
            }
            result = dataset.collect(
                counts[args.input_set],
                target=35.0 if args.target is None else args.target,
                workers=args.workers,
            )
            if result["status"] != "passed":
                print(json.dumps(result, ensure_ascii=False, indent=2))
                raise SystemExit(1)
            result = dataset.assemble()
        elif args.action == "assemble":
            result = dataset.assemble()
        else:
            parser.error("GDC preparation supports dataset and assemble actions")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.method == "texnn":
        if args.action == "report":
            from reproductions.texnn.reporting import TexNNReport

            if not args.run_id or not args.evaluation_id:
                parser.error("TexNN report requires --run-id and --evaluation-id")
            print(json.dumps(TexNNReport(ROOT, args.run_id, args.evaluation_id).write(), indent=2))
            return
        if args.action == "benchmark":
            from reproductions.texnn.evaluation import TexNNBatchEvaluation

            if not args.run_id or not args.evaluation_id:
                parser.error("TexNN benchmark requires --run-id and --evaluation-id")
            for name in [args.run_id, args.evaluation_id]:
                if Path(name).name != name or name in {".", ".."}:
                    parser.error("TexNN identifiers must be single directory names")
            directory = ROOT / "experiment report/.local/reproduction-runs/texnn" / args.run_id
            result = TexNNBatchEvaluation(ROOT, args.project, args.manifest, directory).run(
                directory / "evaluations" / args.evaluation_id,
                images=args.images,
                patch_size=args.patch_size,
                device=args.inference_device,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result["status"] != "passed":
                raise SystemExit(1)
            return
        if args.action == "evaluate":
            from reproductions.texnn.evaluation import TexNNEvaluation

            if args.source is None or not args.run_id or not args.evaluation_id:
                parser.error("TexNN evaluation requires --source, --run-id and --evaluation-id")
            for name in [args.run_id, args.evaluation_id]:
                if Path(name).name != name or name in {".", ".."}:
                    parser.error("TexNN run/evaluation identifiers must be single directory names")
            directory = ROOT / "experiment report/.local/reproduction-runs/texnn" / args.run_id
            sizes = [4, 6, 8] if args.all_footprints else [int(args.footprint.split("x")[0])]
            for size in sizes:
                result = TexNNEvaluation(
                    ROOT, directory, size, device=args.inference_device
                ).evaluate(
                    args.source,
                    directory / "evaluations" / args.evaluation_id / f"{size}x{size}",
                    partition_topk=args.partition_topk,
                    joint_topk=args.joint_topk,
                    preset=args.preset,
                )
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.action == "train":
            from reproductions.texnn.training import TexNNTrainer

            if (
                not args.run_id
                or Path(args.run_id).name != args.run_id
                or args.run_id in {".", ".."}
            ):
                parser.error("TexNN training requires a nonempty run directory name")
            directory = ROOT / "experiment report/.local/reproduction-runs/texnn" / args.run_id
            sizes = [4, 6, 8] if args.all_footprints else [int(args.footprint.split("x")[0])]
            networks: list[Literal["pnn", "demnn"]] = (
                ["pnn", "demnn"]
                if args.network == "all"
                else [cast(Literal["pnn", "demnn"], args.network)]
            )
            for size in sizes:
                for network in networks:
                    result = TexNNTrainer(
                        directory / "prepared" / f"{size}x{size}",
                        directory / "models" / f"{size}x{size}" / network,
                        network,
                        epochs=args.epochs,
                        batch_size=args.batch_size,
                        learning_rate=args.learning_rate,
                        patience=args.patience,
                        seed=args.seed,
                        device=args.device,
                        resume=args.resume,
                    ).train()
                    print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.action == "dataset":
            if (
                not args.run_id
                or Path(args.run_id).name != args.run_id
                or args.run_id in {".", ".."}
            ):
                parser.error("TexNN dataset requires a nonempty run directory name")
            directory = ROOT / "experiment report/.local/reproduction-runs/texnn" / args.run_id
            result = TexNNCorpusBuilder(ROOT, args.project, args.manifest, directory).collect(
                args.images, args.patch_size, args.workers, args.seed
            )
            if result["status"] == "failed":
                print(json.dumps(result, ensure_ascii=False, indent=2))
                raise SystemExit(1)
            prepared = {
                size: TexNNBlockCorpus.prepare(directory, size, args.seed) for size in [4, 6, 8]
            }
            print(
                json.dumps(
                    {
                        size: {
                            key: value[key]
                            for key in ["samples", "train_samples", "validation_samples"]
                        }
                        for size, value in prepared.items()
                    },
                    indent=2,
                )
            )
            return
        if args.action == "collect":
            if args.source is None or args.run_id is None:
                parser.error("TexNN collection requires --source and an explicit --run-id")
            if (
                not args.run_id
                or Path(args.run_id).name != args.run_id
                or args.run_id in {".", ".."}
            ):
                parser.error("--run-id must be one directory name")
            size = int(args.footprint.split("x")[0])
            result = TexNNLabelCollector(ROOT).collect(
                args.source,
                ROOT / "experiment report/.local/reproduction-runs/texnn" / args.run_id,
                (size, size),
                args.preset,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.action not in {"fetch", "build"}:
            parser.error("Unsupported TexNN action")
        reference = TexNNReference(ROOT)
        result = (
            {"commit": reference.fetch()}
            if args.action == "fetch"
            else {"executable": str(reference.build())}
        )
        print(json.dumps(result, indent=2))
        return
    if args.method != "unity_search_baseline":
        if args.input_set == "full":
            parser.error("--input-set full is currently supported only by the GDC label pipeline")
        if args.action == "report":
            if args.run_id is None:
                parser.error("A literature report requires an explicit --run-id")
            print(json.dumps(NahReport(ROOT, args.method, args.run_id).write(), indent=2))
            return
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
            parser.error("Literature encoders support fetch, build, run and report actions")
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
