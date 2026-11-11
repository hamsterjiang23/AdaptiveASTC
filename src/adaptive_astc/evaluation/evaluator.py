"""Sealed test evaluation and probability artifact export."""

from pathlib import Path

import numpy as np
import torch

from adaptive_astc.config import CLASSES, JsonDict
from adaptive_astc.evaluation.inference import Predictor
from adaptive_astc.evaluation.metrics import ClassificationMetrics
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.checkpoints import CheckpointStore
from adaptive_astc.utils.evaluation_seal import EvaluationSeal


class Evaluator:
    """Freeze dataset/model/temperature identities before opening test data."""

    def __init__(self, run_dir: Path, report_dir: Path, workers: int = 2) -> None:
        self.run_dir = run_dir
        self.report_dir = report_dir
        self.predictor = Predictor(run_dir, workers)

    def run(self) -> JsonDict:
        manifest = ArtifactStore.read_json(self.run_dir / "manifest.json")
        arms = ("pretrained", "scratch")
        locked: JsonDict = {"data_fingerprint": manifest["fingerprint"], "arms": {}}
        for arm in arms:
            CheckpointStore.require_completed(self.run_dir, arm, manifest)
            temperature = ArtifactStore.read_json(self.run_dir / arm / "temperature.json")
            if temperature["data_fingerprint"] != manifest["fingerprint"]:
                raise ValueError("Temperature belongs to a different dataset")
            checkpoint_hash = ArtifactStore.sha256_file(self.run_dir / arm / "best.pt")
            if temperature["checkpoint_sha256"] != checkpoint_hash:
                raise ValueError("Calibration checkpoint changed")
            locked["arms"][arm] = {
                "checkpoint_sha256": checkpoint_hash,
                "temperature_sha256": ArtifactStore.sha256_file(
                    self.run_dir / arm / "temperature.json"
                ),
            }
        locked = EvaluationSeal.probabilities(self.run_dir, manifest["fingerprint"], locked["arms"])
        results: JsonDict = {"data_fingerprint": manifest["fingerprint"], "arms": {}}
        for arm in arms:
            logits_path = self.run_dir / arm / "test_logits.pt"
            if logits_path.exists():
                packet = torch.load(logits_path, map_location="cpu", weights_only=True)
                logits, labels, information = (
                    packet["logits"],
                    packet["labels"],
                    packet["information"],
                )
                if information["checkpoint_sha256"] != locked["arms"][arm]["checkpoint_sha256"]:
                    raise ValueError("Cached inference checkpoint mismatch")
            else:
                logits, labels, information = self.predictor.from_checkpoint(arm, "test")
            fitted = ArtifactStore.read_json(self.run_dir / arm / "temperature.json")
            temperature = float(fitted["temperature"])
            if not torch.equal(logits.argmax(dim=1), (logits.double() / temperature).argmax(dim=1)):
                raise ValueError("Temperature scaling changed argmax")
            results["arms"][arm] = {
                "raw": ClassificationMetrics.compute(logits, labels),
                "calibrated": ClassificationMetrics.compute(logits, labels, temperature),
                "temperature": temperature,
                "argmax_unchanged": True,
                "inference": information,
            }
            np.savez_compressed(
                self.run_dir / arm / "test_predictions.npz",
                logits=logits.numpy(),
                labels=labels.numpy(),
                raw_probabilities=logits.double().softmax(dim=1).numpy(),
                calibrated_probabilities=(logits.double() / temperature).softmax(dim=1).numpy(),
            )
        train_labels = [row["class_id"] for row in manifest["splits"]["train"]]
        majority = int(np.bincount(train_labels, minlength=4).argmax())
        test_labels = torch.tensor([row["class_id"] for row in manifest["splits"]["test"]])
        results["majority_baseline"] = {
            "class": CLASSES[majority],
            "accuracy": float((test_labels == majority).double().mean()),
        }
        ArtifactStore.write_json(self.report_dir / "metrics.json", results)
        return results
