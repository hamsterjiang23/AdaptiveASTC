"""Gate measured-label manifests and time the existing ResNet trainer."""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from adaptive_astc.config import CLASSES, TrainConfig
from adaptive_astc.training.trainer import Trainer
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.upstream import BaselineGate


class GDCTraining:
    def __init__(self, root: Path, run: Path, report: Path) -> None:
        self.root, self.run, self.report = root.resolve(), run.resolve(), report.resolve()

    def validate_data(self) -> dict[str, Any]:
        BaselineGate.require(
            self.root
            / "experiment report/.local/unity-search-baseline-lite-rdo-off/full-receipt.json"
        )
        manifest = ArtifactStore.read_json(self.run / "manifest.json")
        content = dict(manifest)
        fingerprint = content.pop("fingerprint")
        if ArtifactStore.fingerprint(content) != fingerprint or manifest["classes"] != list(
            CLASSES
        ):
            raise ValueError("GDC training manifest changed or has incompatible classes")
        if manifest["label_protocol_sha256"] != ArtifactStore.sha256_file(
            self.run / "protocol.json"
        ) or manifest["label_collection_sha256"] != ArtifactStore.sha256_file(
            self.run / "collection.json"
        ):
            raise ValueError("GDC label collection changed before training")
        protocol = ArtifactStore.read_json(self.run / "protocol.json")
        indices = {
            (row["split"], row["path"]): index for index, row in enumerate(protocol["inputs"])
        }
        for split, rows in manifest["splits"].items():
            for row in rows:
                cache = (self.run / row["cache"]).resolve()
                if (
                    not cache.is_relative_to(self.run)
                    or ArtifactStore.sha256_file(cache) != row["cache_sha256"]
                ):
                    raise ValueError("GDC RGB224 classifier cache changed before training")
                index = indices[(split, row["path"])]
                receipt_path = self.run / "labels" / f"{index:05d}" / "receipt.json"
                if ArtifactStore.sha256_file(receipt_path) != row["label_receipt_sha256"]:
                    raise ValueError("GDC measured training label receipt changed")
                label = ArtifactStore.read_json(receipt_path)
                if (
                    label["path"] != row["path"]
                    or label["split"] != split
                    or label["fileHash"] != row["fileHash"]
                    or CLASSES.index(label["selected"]["name"]) != row["class_id"]
                    or label["target_met"] != row["label_target_met"]
                ):
                    raise ValueError("GDC classifier target differs from its measured label")
        return manifest

    def train(
        self,
        initialization: Literal["pretrained", "scratch"] = "pretrained",
        *,
        epochs: int = 30,
        micro_batch: int = 64,
        workers: int = 2,
        resume: bool = False,
    ) -> dict[str, Any]:
        gate_started = time.perf_counter()
        if initialization not in {"pretrained", "scratch"}:
            raise ValueError("Invalid GDC initialization")
        if (self.run / "test_seal.json").exists():
            raise ValueError("GDC test already opened; train a new experiment identity")
        manifest = self.validate_data()
        config = TrainConfig(
            run_dir=self.run,
            report_dir=self.report,
            initialization=initialization,
            epochs=epochs,
            micro_batch=micro_batch,
            workers=workers,
            resume=resume,
            seed=manifest["seed"],
        )
        directory = self.run / initialization
        if resume and directory.exists():
            previous = {
                path.name: ArtifactStore.sha256_file(path)
                for path in directory.iterdir()
                if path.name
                in {
                    "best.pt",
                    "last.pt",
                    "config.json",
                    "history.json",
                    "training_complete.json",
                    "wall-clock.json",
                }
            }
            archive = directory / "history" / ArtifactStore.fingerprint(previous)
            archive.mkdir(parents=True, exist_ok=True)
            for name, digest in previous.items():
                target = archive / name
                if not target.exists():
                    shutil.copy2(directory / name, target)
                if ArtifactStore.sha256_file(target) != digest:
                    raise ValueError("Prior GDC training archive differs from its checkpoint")
        gate_seconds = time.perf_counter() - gate_started
        started = time.perf_counter()
        attempt: dict[str, Any] = {
            "status": "running",
            "config": config.to_dict(),
            "data_fingerprint": manifest["fingerprint"],
            "gate_seconds": gate_seconds,
            "started_unix": time.time(),
            "wall_seconds": None,
        }
        attempts = self.run / "training-attempts"
        attempts.mkdir(exist_ok=True)
        prior_checkpoint = directory / "last.pt"
        prior_hash = (
            ArtifactStore.sha256_file(prior_checkpoint) if prior_checkpoint.exists() else None
        )
        prior_records = [
            ArtifactStore.read_json(path) for path in attempts.glob(f"{initialization}-*.json")
        ]
        covered = prior_hash is not None and any(
            row.get("checkpoint_last_sha256") == prior_hash and row["wall_seconds"] is not None
            for row in prior_records
        )
        attempt["initialization"] = initialization
        attempt["start_checkpoint_sha256"] = prior_hash
        attempt["unaccounted_prior_training"] = resume and prior_hash is not None and not covered
        attempt_path = attempts / f"{initialization}-{uuid.uuid4().hex}.json"
        ArtifactStore.write_json(attempt_path, attempt)
        try:
            result = Trainer.from_config(config).fit()
            attempt["status"] = "passed"
            attempt["completed_epochs"] = result["completed_epochs"]
            attempt["best_epoch"] = result["best_epoch"]
        except BaseException as error:
            attempt["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
            attempt["error"] = repr(error)
            raise
        finally:
            attempt["wall_seconds"] = time.perf_counter() - started
            if (directory / "last.pt").exists():
                attempt["checkpoint_last_sha256"] = ArtifactStore.sha256_file(directory / "last.pt")
            if attempt["status"] == "passed":
                attempt["model_sha256"] = ArtifactStore.sha256_file(directory / "best.pt")
                attempt["training_complete_sha256"] = ArtifactStore.sha256_file(
                    directory / "training_complete.json"
                )
            ArtifactStore.write_json(attempt_path, attempt)
            if attempt["status"] == "passed":
                all_attempts = [
                    ArtifactStore.read_json(path)
                    for path in attempts.glob(f"{initialization}-*.json")
                ]
                known_seconds = sum(
                    row["wall_seconds"] for row in all_attempts if row["wall_seconds"] is not None
                )
                unknown = sum(row["wall_seconds"] is None for row in all_attempts)
                attempt["all_attempts_known_wall_seconds"] = known_seconds
                attempt["unknown_duration_attempts"] = unknown
                unaccounted = any(
                    row.get("unaccounted_prior_training", False) for row in all_attempts
                )
                attempt["unaccounted_prior_training"] = unaccounted
                attempt["all_attempts_wall_seconds"] = (
                    None if unknown or unaccounted else known_seconds
                )
                attempt["prior_partial_attempts"] = sum(
                    row["status"] != "passed" for row in all_attempts
                )
                ArtifactStore.write_json(directory / "wall-clock.json", attempt)
        return attempt
