"""Prepare native patch error supervision and run CUDA regression experiments."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptive_astc.data.patch_targets import GDCPatchCorpus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--measured", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--train-limit", type=int, default=0)
    prepare.add_argument("--validation-limit", type=int, default=0)
    prepare.add_argument("--patch-size", type=int, default=240)
    probe = subcommands.add_parser("probe")
    probe.add_argument("--corpus", type=Path, required=True)
    probe.add_argument("--executable", type=Path, required=True)
    probe.add_argument("--output", type=Path, required=True)
    probe.add_argument("--report", type=Path, required=True)
    probe.add_argument("--image-count", type=int, default=20)
    suite = subcommands.add_parser("suite")
    suite.add_argument("--config", type=Path, required=True)
    audit = subcommands.add_parser("audit")
    audit.add_argument("--output", type=Path, required=True)
    audit.add_argument("--report", type=Path, required=True)
    train = subcommands.add_parser("train")
    train.add_argument("--corpus", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--report", type=Path, required=True)
    train.add_argument("--initialization", choices=["scratch", "pretrained"], default="scratch")
    train.add_argument("--epochs", type=int, default=15)
    train.add_argument("--batch-size", type=int, default=32)
    train.add_argument("--patches-per-image", type=int, default=4)
    train.add_argument("--group-image-cap", type=int, default=0)
    train.add_argument("--learning-rate", type=float, default=0.001)
    train.add_argument("--weight-decay", type=float, default=0.05)
    train.add_argument("--warmup-epochs", type=int, default=2)
    train.add_argument("--workers", type=int, default=2)
    train.add_argument("--seed", type=int, default=20261111)
    train.add_argument("--max-steps", type=int, default=0)
    train.add_argument("--keep-maxpool", action="store_true")
    train.add_argument("--monotone", action="store_true")
    train.add_argument("--ema-decay", type=float, default=0.0)
    train.add_argument("--patience", type=int, default=0)
    args = parser.parse_args()
    if args.command == "prepare":
        result = GDCPatchCorpus(args.measured, args.output, args.patch_size).prepare(
            args.train_limit, args.validation_limit
        )
    elif args.command == "probe":
        from reproductions.gdc2023.patch_probe import GDCPatchProbe

        result = GDCPatchProbe(args.corpus, args.executable, args.output, args.report).run(
            args.image_count
        )
    elif args.command == "suite":
        from adaptive_astc.training.patch_suite import PatchExperimentSuite

        result = PatchExperimentSuite(args.config).run()
    elif args.command == "audit":
        from adaptive_astc.training.patch_trainer import PatchTrainer

        result = PatchTrainer.audit_best(args.output, args.report)
    else:
        from adaptive_astc.training.patch_trainer import PatchTrainConfig, PatchTrainer

        options = vars(args).copy()
        options.pop("command")
        options["remove_maxpool"] = not options.pop("keep_maxpool")
        result = PatchTrainer(PatchTrainConfig(**options)).fit()
    print(
        {key: value for key, value in result.items() if key not in {"splits", "rows", "history"}},
        flush=True,
    )


if __name__ == "__main__":
    main()
