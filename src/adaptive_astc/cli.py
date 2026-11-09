"""Command-line entry points for the fixed reproduction protocol."""

import argparse
import gc
import json
import sys
import time
from pathlib import Path

from adaptive_astc.common import DEFAULT_REPORT, DEFAULT_RUN, JsonDict, write_json
from adaptive_astc.data import prepare


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("prepare", "train", "calibrate", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
        command.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT)
        if name == "prepare":
            command.add_argument(
                "--snapshot",
                type=Path,
                default=Path(r"C:\Users\admin\Downloads\parameter_cache_detail.json"),
            )
            command.add_argument(
                "--image-root", type=Path, default=Path(r"F:\MLBB_Test\haijiangli1_HAMSTERMLBB")
            )
            command.add_argument("--smoke", action="store_true")
            command.add_argument("--exclude-manifest", action="append", type=Path, default=[])
        else:
            command.add_argument("--workers", type=int, default=2)
        if name in {"train", "calibrate"}:
            command.add_argument(
                "--initialization", choices=("pretrained", "scratch"), required=True
            )
        if name == "train":
            command.add_argument("--epochs", type=int, default=30)
            command.add_argument("--micro-batch", type=int, choices=(16, 32, 64), default=64)
            command.add_argument("--resume", action="store_true")
            command.add_argument("--max-steps", type=int, default=0)
    return root


def main() -> None:
    args = parser().parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    result: JsonDict = {}
    try:
        if args.command == "prepare":
            result = prepare(
                args.snapshot,
                args.image_root,
                args.run_dir,
                args.report_dir,
                args.smoke,
                args.exclude_manifest,
            )
        elif args.command == "train":
            import torch

            from adaptive_astc.training import train

            batch = args.micro_batch
            while True:
                try:
                    result = train(
                        args.run_dir,
                        args.report_dir,
                        args.initialization,
                        args.epochs,
                        batch,
                        args.workers,
                        args.resume,
                        args.max_steps,
                    )
                    break
                except torch.cuda.OutOfMemoryError:
                    if batch == 16:
                        raise
                    batch //= 2
                    gc.collect()
                    torch.cuda.empty_cache()
                    args.resume = (args.run_dir / args.initialization / "last.pt").exists()
                    print(f"CUDA OOM: retry epoch with micro_batch={batch}", flush=True)
        elif args.command == "calibrate":
            from adaptive_astc.training import calibrate

            result = calibrate(args.run_dir, args.report_dir, args.initialization, args.workers)
        else:
            from adaptive_astc.reports import render_report
            from adaptive_astc.training import evaluate

            result = evaluate(args.run_dir, args.report_dir, args.workers)
            render_report(args.run_dir, args.report_dir)
    except Exception as error:
        write_json(
            args.report_dir / f"{args.command}_failure.json",
            {
                "error_type": type(error).__name__,
                "message": str(error),
                "argv": sys.argv,
                "elapsed_seconds": time.perf_counter() - started,
            },
        )
        raise
    write_json(
        args.run_dir / f"{args.command}_receipt.json",
        {
            "command": sys.argv,
            "elapsed_seconds": time.perf_counter() - started,
            "status": "success",
            "result_keys": list(result),
        },
    )
    print(
        json.dumps(
            {"command": args.command, "status": "success", "seconds": time.perf_counter() - started}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
