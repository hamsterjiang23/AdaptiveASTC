"""Upload existing aggregate results with explicit historical provenance."""

import argparse
from dataclasses import replace
from pathlib import Path

from adaptive_astc.config import JsonDict, SwanLabConfig, TrainConfig
from adaptive_astc.tracking.swanlab import SwanLabTracker
from adaptive_astc.utils.artifacts import ArtifactStore


class MetricsUploader:
    """Replay recorded metrics after validating dataset and checkpoint identities."""

    def __init__(self, run_dir: Path, report_dir: Path, config: SwanLabConfig) -> None:
        self.run_dir = run_dir
        self.report_dir = report_dir
        self.config = config

    def upload(self) -> JsonDict:
        manifest = ArtifactStore.read_json(self.run_dir / "manifest.json")
        metrics = ArtifactStore.read_json(self.report_dir / "metrics.json")
        if metrics["data_fingerprint"] != manifest["fingerprint"]:
            raise ValueError("Imported metrics and manifest fingerprints differ")
        packets: JsonDict = {}
        for arm in ("pretrained", "scratch"):
            training = ArtifactStore.read_json(self.report_dir / f"{arm}_training.json")
            calibration = ArtifactStore.read_json(self.run_dir / arm / "temperature.json")
            checkpoint_sha = ArtifactStore.sha256_file(self.run_dir / arm / "best.pt")
            if (
                training["config"]["data_fingerprint"] != manifest["fingerprint"]
                or calibration["data_fingerprint"] != manifest["fingerprint"]
                or calibration["checkpoint_sha256"] != checkpoint_sha
                or metrics["arms"][arm]["inference"]["checkpoint_sha256"] != checkpoint_sha
            ):
                raise ValueError(f"Historical source identity mismatch for {arm}")
            packets[arm] = {"training": training, "calibration": calibration}
        sources = [self.report_dir / "metrics.json", self.run_dir / "manifest.json"]
        sources += [self.report_dir / f"{arm}_training.json" for arm in packets]
        sources += [self.run_dir / arm / "temperature.json" for arm in packets]
        hashes = {str(path.resolve()): ArtifactStore.sha256_file(path) for path in sources}
        uploaded: JsonDict = {}
        for arm, packet in packets.items():
            config = self.config
            if config.name:
                config = replace(config, name=f"{config.name}-{arm}")
            metadata = {
                **packet["training"]["config"],
                "historical_import": True,
                "source_artifact_sha256": hashes,
                "scope": "replay_of_recorded_results",
            }
            with SwanLabTracker(
                config, self.run_dir, "historical-import", metadata, arm
            ) as tracker:
                for epoch in packet["training"]["epochs"]:
                    tracker.log_epoch(epoch)
                step = int(packet["training"]["epochs"][-1]["epoch"])
                tracker.log_metrics("calibration", packet["calibration"], step)
                tracker.log_metrics("test", metrics["arms"][arm], step)
                tracker.log_metrics("majority_baseline", metrics["majority_baseline"], step)
                tracker.log_payload("test/result", metrics["arms"][arm], step)
                tracker.log_payload("calibration/result", packet["calibration"], step)
                tracker.log_report(self.report_dir, step)
                uploaded[arm] = dict(tracker.identity)
            uploaded[arm]["state"] = tracker.identity.get("state")
        ArtifactStore.write_json(self.run_dir / "tracking/import_receipt.json", uploaded)
        return uploaded

    @staticmethod
    def main(arguments: list[str] | None = None) -> None:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--config", type=Path)
        parser.add_argument("--run-dir", type=Path)
        parser.add_argument("--report-dir", type=Path)
        parser.add_argument("--swanlab-mode", choices=("online", "offline", "disabled"))
        parser.add_argument("--swanlab-project")
        parser.add_argument("--swanlab-workspace")
        parser.add_argument("--swanlab-name")
        args = parser.parse_args(arguments)
        paths = TrainConfig.load(
            args.config,
            {
                "run_dir": args.run_dir,
                "report_dir": args.report_dir,
            },
        )
        tracking = SwanLabConfig.load(
            args.config,
            {
                name: getattr(args, f"swanlab_{name}")
                for name in ("mode", "project", "workspace", "name")
            },
        )
        if args.config is None and args.swanlab_mode is None:
            tracking = replace(tracking, mode="online")
        result = MetricsUploader(
            paths.run_dir,
            paths.report_dir,
            tracking,
        ).upload()
        for arm, identity in result.items():
            print(f"{arm}: {identity.get('url')}", flush=True)
