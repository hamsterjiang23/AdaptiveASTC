"""Command-line entry points for the fixed reproduction protocol."""

import argparse
import gc
import json
import sys
import time
from dataclasses import fields, replace
from pathlib import Path

from adaptive_astc.config import JsonDict, SwanLabConfig, TrainConfig
from adaptive_astc.data import DataPreparer
from adaptive_astc.tracking.swanlab import SwanLabTracker
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
            command.add_argument("--config", type=Path)
            command.add_argument("--run-dir", type=Path)
            command.add_argument("--report-dir", type=Path)
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
                command.add_argument("--workers", type=int)
                command.add_argument("--swanlab-mode", choices=("online", "offline", "disabled"))
                command.add_argument("--swanlab-project")
                command.add_argument("--swanlab-workspace")
                command.add_argument("--swanlab-name")
            if name in {"train", "calibrate"}:
                command.add_argument(
                    "--initialization",
                    choices=("pretrained", "scratch"),
                )
            if name == "train":
                command.add_argument("--epochs", type=int)
                command.add_argument("--micro-batch", type=int, choices=(16, 32, 64))
                command.add_argument("--resume", action="store_true", default=None)
                command.add_argument("--max-steps", type=int)
                command.add_argument("--learning-rate", type=float)
                command.add_argument("--momentum", type=float)
                command.add_argument("--weight-decay", type=float)
                command.add_argument("--effective-batch", type=int)
                command.add_argument("--scheduler-t-max", type=int)
                command.add_argument("--seed", type=int)
        return root

    @staticmethod
    def train(config: TrainConfig, tracking: SwanLabConfig) -> JsonDict:
        import torch

        from adaptive_astc.training import Trainer
        from adaptive_astc.utils.checkpoints import CheckpointStore

        if (config.run_dir / "test_seal.json").exists():
            raise ValueError("Test already opened; train a new run instead")
        manifest = ArtifactStore.read_json(config.run_dir / "manifest.json")
        output = config.run_dir / config.initialization
        last_path = output / "last.pt"
        if last_path.exists() and not config.resume:
            raise ValueError("Existing training state requires --resume or a new run directory")
        if config.resume:
            state = torch.load(last_path, map_location="cpu", weights_only=False)
            CheckpointStore.validate_resume(
                state,
                manifest,
                config.initialization,
                output,
                config.optimization_signature(),
            )
            del state
        metadata = {
            **config.to_dict(),
            "data_fingerprint": manifest["fingerprint"],
            "dataset_smoke": manifest.get("smoke"),
            "dataset_sizes": manifest.get("sizes"),
        }
        with SwanLabTracker(
            tracking,
            config.run_dir,
            "train",
            metadata,
            config.initialization,
            config.resume,
        ) as tracker:
            while True:
                try:
                    result = Trainer.from_config(config, tracker).fit()
                    tracker.log_payload(
                        "training/effective_config",
                        ArtifactStore.read_json(
                            config.run_dir / config.initialization / "config.json"
                        ),
                        config.epochs,
                    )
                    return result
                except torch.cuda.OutOfMemoryError:
                    if config.micro_batch == 16:
                        raise
                    config = replace(
                        config,
                        micro_batch=config.micro_batch // 2,
                        resume=(config.run_dir / config.initialization / "last.pt").exists(),
                    )
                    gc.collect()
                    torch.cuda.empty_cache()
                    print(
                        f"CUDA OOM: retry epoch with micro_batch={config.micro_batch}", flush=True
                    )

    def run(self) -> None:
        args = self.args
        training = None
        tracking = SwanLabConfig()
        if args.command != "prepare":
            tracking = SwanLabConfig.load(
                args.config,
                {
                    name: getattr(args, f"swanlab_{name}")
                    for name in ("mode", "project", "workspace", "name")
                },
            )
        if args.command in {"train", "calibrate"}:
            if args.config is None and args.initialization is None:
                raise ValueError("--initialization is required without --config")
        if args.command == "train":
            training = TrainConfig.load(
                args.config,
                {field.name: getattr(args, field.name) for field in fields(TrainConfig)},
            )
            args.run_dir, args.report_dir = training.run_dir, training.report_dir
        else:
            names = ["run_dir", "report_dir"]
            if args.command != "prepare":
                names.append("workers")
            if args.command == "calibrate":
                names.append("initialization")
            resolved = TrainConfig.load(args.config, {name: getattr(args, name) for name in names})
            for name in names:
                setattr(args, name, getattr(resolved, name))
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
                assert training is not None
                result = self.train(training, tracking)
            elif args.command == "calibrate":
                from adaptive_astc.calibration import TemperatureCalibrator

                metadata = ArtifactStore.read_json(args.run_dir / "manifest.json")
                with SwanLabTracker(
                    tracking,
                    args.run_dir,
                    "calibration",
                    {"data_fingerprint": metadata["fingerprint"]},
                    args.initialization,
                ) as tracker:
                    result = TemperatureCalibrator(
                        args.run_dir, args.report_dir, args.initialization, args.workers
                    ).run()
                    tracker.log_metrics("calibration", result)
                    tracker.log_payload("calibration/result", result)
            else:
                from adaptive_astc.evaluation.evaluator import Evaluator
                from adaptive_astc.reporting import ReportGenerator

                metadata = ArtifactStore.read_json(args.run_dir / "manifest.json")
                with SwanLabTracker(
                    tracking,
                    args.run_dir,
                    "evaluation",
                    {"data_fingerprint": metadata["fingerprint"]},
                ) as tracker:
                    result = Evaluator(args.run_dir, args.report_dir, args.workers).run()
                    ReportGenerator(args.run_dir, args.report_dir).render()
                    tracker.log_metrics("test", result)
                    tracker.log_payload("test/result", result)
                    tracker.log_report(args.report_dir)
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
    def main(command: str | None = None, arguments: list[str] | None = None) -> None:
        values = sys.argv[1:] if arguments is None else arguments
        if command is not None:
            values = [command, *values]
        ExperimentCLI(ExperimentCLI.parser().parse_args(values)).run()


parser = ExperimentCLI.parser
main = ExperimentCLI.main

if __name__ == "__main__":
    main()
