"""Command-line entry points for the fixed reproduction protocol."""

import argparse
import gc
import json
import sys
import time
from pathlib import Path

from adaptive_astc.config import DEFAULT_REPORT, DEFAULT_RUN, JsonDict
from adaptive_astc.data import DataPreparer
from adaptive_astc.utils.artifacts import ArtifactStore


class ExperimentCLI:
    """Parse commands and dispatch to independent experiment components."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args

    @staticmethod
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

    def run(self) -> None:
        args = self.args
        args.report_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        result: JsonDict = {}
        try:
            if args.command == "prepare":
                result = DataPreparer(
                    args.snapshot,
                    args.image_root,
                    args.run_dir,
                    args.report_dir,
                    args.smoke,
                    args.exclude_manifest,
                ).run()
            elif args.command == "train":
                import torch

                from adaptive_astc.training import Trainer

                batch = args.micro_batch
                while True:
                    try:
                        result = Trainer(
                            args.run_dir,
                            args.report_dir,
                            args.initialization,
                            args.epochs,
                            batch,
                            args.workers,
                            args.resume,
                            args.max_steps,
                        ).fit()
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
                from adaptive_astc.calibration import TemperatureCalibrator

                result = TemperatureCalibrator(
                    args.run_dir, args.report_dir, args.initialization, args.workers
                ).run()
            else:
                from adaptive_astc.evaluation.evaluator import Evaluator
                from adaptive_astc.reporting import ReportGenerator

                result = Evaluator(args.run_dir, args.report_dir, args.workers).run()
                ReportGenerator(args.run_dir, args.report_dir).render()
        except Exception as error:
            ArtifactStore.write_json(
                args.report_dir / f"{args.command}_failure.json",
                {
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "argv": sys.argv,
                    "elapsed_seconds": time.perf_counter() - started,
                },
            )
            raise
        ArtifactStore.write_json(
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
                {
                    "command": args.command,
                    "status": "success",
                    "seconds": time.perf_counter() - started,
                }
            ),
            flush=True,
        )

    @staticmethod
    def main() -> None:
        ExperimentCLI(ExperimentCLI.parser().parse_args()).run()


parser = ExperimentCLI.parser
main = ExperimentCLI.main

if __name__ == "__main__":
    main()
