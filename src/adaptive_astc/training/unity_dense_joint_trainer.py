"""Fine-tune the shared V3 trunk on dense tiles and the original Unity quality task."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_dense_tile_dataset import UnityDenseImageSampler
from adaptive_astc.data.unity_image_bags import UnityImageBags
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_dense_native_regression import UnityDenseNativeRegression
from adaptive_astc.models.unity_dense_tile import UnityDenseTileRegressor
from adaptive_astc.training.unity_dense_tile_trainer import (
    UnityDenseTileTrainer,
    UnityDenseTrainConfig,
)
from adaptive_astc.training.unity_quality_loss import UnityQualityLoss
from adaptive_astc.utils.artifacts import ArtifactStore as A


@dataclass(frozen=True)
class UnityDenseJointConfig:
    frozen_run: Path
    frozen_report_sha256: str
    encoder_learning_rate: float = 1e-5
    native_learning_rate: float = 3e-5
    native_batch_size: int = 4
    native_views: int = 2


class UnityDenseJointTrainer(UnityDenseTileTrainer):
    SOURCES = UnityDenseTileTrainer.SOURCES + (
        "script/train_unity_dense_joint.py",
        "src/adaptive_astc/data/unity_patch_dataset.py",
        "src/adaptive_astc/data/unity_image_bags.py",
        "src/adaptive_astc/training/unity_quality_loss.py",
        "src/adaptive_astc/training/unity_dense_joint_trainer.py",
        "src/adaptive_astc/evaluation/unity_dense_native_regression.py",
        "src/adaptive_astc/data/unity_inference.py",
        "src/adaptive_astc/evaluation/unity_inference.py",
        "reproductions/unity_search_baseline/v3_policy.py",
        "script/diagnose_unity_rules.py",
    )

    def __init__(
        self,
        root: Path,
        archive: UnityTileArchive,
        config: UnityDenseTrainConfig,
        joint: UnityDenseJointConfig,
    ) -> None:
        if (
            config.stage not in ("full", "aligned-smoke")
            or not 0 < joint.encoder_learning_rate < 1
            or not 0 < joint.native_learning_rate < 1
            or joint.native_batch_size < 1
            or joint.native_views < 1
        ):
            raise ValueError("Require a bound V5 joint configuration and native image batch")
        super().__init__(archive, config)
        self.root = root
        self.archive = archive
        self.joint = joint
        self.frozen = archive.read_bound_json(
            joint.frozen_run / "report.json", joint.frozen_report_sha256, dict
        )
        if (
            self.frozen["status"] != "passed"
            or not self.frozen["checkpoint_reloaded"]
            or not self.frozen["frozen_native_parameters_and_buffers_unchanged"]
            or self.frozen["test_opened"] is not False
            or self.frozen["stage"] != config.stage
            or self.frozen["corpus_sha256"] != config.corpus_sha256
            or self.frozen["parent_sha256"] != config.parent_sha256
        ):
            raise ValueError(
                "Joint init requires a verified frozen run on the same development inputs"
            )
        validation = archive.read_bound_json(
            joint.frozen_run / "best-validation.json", self.frozen["best_validation_sha256"], dict
        )
        self.frozen_key = self.validation_key(validation["summary"])

    def load_joint_model(self, device: torch.device) -> UnityDenseTileRegressor:
        path = self.joint.frozen_run / "best-head.pt"
        if A.sha256_file(path) != self.frozen["best_checkpoint_sha256"]:
            raise ValueError("Verified frozen V5 head checkpoint has changed")
        base = self.build_model(device)
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        if (
            checkpoint["parent_sha256"] != self.config.parent_sha256
            or checkpoint["corpus_sha256"] != self.config.corpus_sha256
        ):
            raise ValueError("Frozen V5 checkpoint provenance has changed")
        base.load_state_dict(checkpoint["model"], strict=True)
        base.set_frozen(False)
        return base

    def native_bags(self) -> UnityImageBags:
        path, sha = self.archive.path, self.archive.sha256
        if self.config.stage == "aligned-smoke":
            corpus = self.archive.read_bound_json(path, sha, dict)
            corpus["splits"] = {
                "train": self.train_dataset.rows,
                "validation": self.validation_dataset.rows,
            }
            corpus["counts"] = {split: len(rows) for split, rows in corpus["splits"].items()}
            corpus.update(coverage="partial", candidate_count=20 * sum(corpus["counts"].values()))
            corpus["patch_counts"] = {
                split: sum(row["patch_count"] for row in rows)
                for split, rows in corpus["splits"].items()
            }
            corpus["fingerprint"] = A.fingerprint(
                {"binding": corpus["binding"], "splits": corpus["splits"]}
            )
            path = self.config.output / "native-smoke-corpus/corpus.json"
            A.write_json(path, corpus)
            sha = A.sha256_file(path)
        native = UnityPatchDataset(path.parent, "train", expected_sha256=sha)
        if [row["path"] for row in native.rows] != [row["path"] for row in self.train_dataset.rows]:
            raise ValueError("Native joint supervision must cover the same ordered training images")
        return UnityImageBags(native, list(range(len(native.rows))), self.joint.native_views)

    @staticmethod
    def native_loss(
        model: UnityDenseTileRegressor,
        criterion: UnityQualityLoss,
        batch: dict[str, Tensor],
        targets: dict[str, Tensor],
        device: torch.device,
    ) -> Tensor:
        batch = {key: value.to(device) for key, value in batch.items()}
        count, views = batch["rgba"].shape[:2]
        ids = torch.arange(count, device=device).repeat_interleave(views)
        output = model.native(
            batch["rgba"].flatten(0, 1), batch["valid_mask"].flatten(0, 1), ids, batch["metadata"]
        )
        return criterion(
            output,
            batch["channel_log_mse"].flatten(0, 1),
            ids,
            {key: value.to(device) for key, value in targets.items()},
        )["total"]

    def fit(self, state: JsonDict, report: Path) -> None:
        if not torch.cuda.is_available():
            raise RuntimeError("V5 joint fine-tuning requires CUDA")
        config, joint = self.config, self.joint
        device = torch.device("cuda")
        torch.manual_seed(config.seed)
        torch.backends.cudnn.benchmark = False
        torch.cuda.reset_peak_memory_stats()
        model = self.load_joint_model(device)
        trunk_before = self.model_hash(model.native.backbone)
        buffers_before = {name: value.cpu().clone() for name, value in model.native.named_buffers()}
        native_heads = (
            model.native.metadata_conditioner,
            model.native.channel_head,
            model.native.image_head,
        )
        optimizer = torch.optim.AdamW(
            [
                {"params": model.native.backbone.parameters(), "lr": joint.encoder_learning_rate},
                {
                    "params": [param for layer in native_heads for param in layer.parameters()],
                    "lr": joint.native_learning_rate,
                },
                {"params": model.tile_head.parameters(), "lr": config.learning_rate},
            ]
        )
        criterion = UnityQualityLoss()
        dense_loader = DataLoader(
            self.train_dataset,
            batch_size=config.batch_size,
            sampler=UnityDenseImageSampler(self.train_dataset, config.seed),
        )
        native_bags = self.native_bags()
        native_loader = DataLoader(
            native_bags,
            batch_size=joint.native_batch_size,
            shuffle=True,
            generator=torch.Generator().manual_seed(config.seed),
        )
        validation = DataLoader(self.validation_dataset, batch_size=config.batch_size)
        if len(native_loader) > len(dense_loader):
            raise ValueError(
                "Native batches must fit a dense epoch without replaying either loader"
            )
        regression = UnityDenseNativeRegression(
            self.root, self.archive, [row["index"] for row in self.validation_dataset.rows]
        )
        frozen_replay = regression.run(model.native, device)
        A.write_json(config.output / "frozen-native-control.json", frozen_replay)
        if config.stage == "full" and any(frozen_replay["changes_from_v3"].values()):
            raise ValueError("Frozen native baseline must reproduce the actual V3 traces")
        state.update(
            status="training",
            mode="joint",
            native_batches=0,
            loss_cap_db=config.loss_cap_db,
            frozen_report_sha256=joint.frozen_report_sha256,
            frozen_dense_key=list(self.frozen_key),
            counts={"train": len(native_bags), "validation": len(self.validation_dataset.rows)},
            batch_size=config.batch_size,
            native_batch_size=joint.native_batch_size,
            native_views=joint.native_views,
            encoder_learning_rate=joint.encoder_learning_rate,
            native_learning_rate=joint.native_learning_rate,
            tile_learning_rate=config.learning_rate,
            batchnorm_buffers_frozen=True,
        )
        best = (2, float("inf"), float("inf"))
        for epoch in range(1, config.epochs + 1):
            model.train()
            for module in model.native.backbone.modules():
                if isinstance(module, nn.BatchNorm2d):
                    module.eval()
            dense_losses, native_losses = [], []
            native_iterator = iter(native_loader)
            for step, batch in enumerate(dense_loader, 1):
                optimizer.zero_grad(set_to_none=True)
                outputs = model(
                    *(batch[key].to(device) for key in ("rgba", "valid_mask", "metadata"))
                )
                dense_loss = self.loss(
                    outputs,
                    batch["log_mse"].to(device),
                    batch["pixels"].to(device),
                    config.loss_cap_db,
                )
                dense_loss.backward()
                dense_losses.append(float(dense_loss.detach()))
                if step * len(native_loader) // len(dense_loader) > len(native_losses):
                    native, native_targets = next(native_iterator)
                    native_loss = self.native_loss(model, criterion, native, native_targets, device)
                    native_loss.backward()
                    native_losses.append(float(native_loss.detach()))
                    state["native_batches"] += 1
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
                optimizer.step()
                state["training_updates"] += 1
            if len(native_losses) != len(native_loader):
                raise ValueError("Joint supervision did not cover all native batches")
            measured = self.evaluate(model, validation, self.validation_dataset, device)
            dense_metrics = measured.summarize()
            outcome = regression.run(model.native, device)
            A.write_json(config.output / f"epoch-{epoch:03d}-native-replay.json", outcome)
            key = (int(not outcome["no_aggregate_regression"]), *self.validation_key(dense_metrics))
            state["history"].append(
                {
                    "epoch": epoch,
                    "dense_huber": float(np.mean(dense_losses)),
                    "native_loss": float(np.mean(native_losses)),
                    "dense": dense_metrics,
                    "native_metrics": outcome["metrics"],
                    "no_aggregate_regression": outcome["no_aggregate_regression"],
                    "new_strict_regressions": outcome["new_strict_regressions"],
                }
            )
            if key < best:
                best = key
                self.save_best(model, epoch, measured, state)
            A.write_json(report, state)
            print(
                f"joint epoch {epoch}; {len(native_losses)} native batches; "
                f"regression gate {not key[0]}",
                flush=True,
            )
        buffers_after = dict(model.native.named_buffers())
        if not all(
            torch.equal(before, buffers_after[name].cpu())
            for name, before in buffers_before.items()
        ):
            raise ValueError("Joint training changed frozen native BatchNorm buffers")
        del model, optimizer
        self.audit_joint(state, validation, regression, trunk_before, buffers_before, device)

    def audit_joint(
        self,
        state: JsonDict,
        validation: DataLoader[dict[str, Tensor]],
        regression: UnityDenseNativeRegression,
        trunk_before: str,
        buffers_before: dict[str, Tensor],
        device: torch.device,
    ) -> None:
        config = self.config
        path = config.output / "best-head.pt"
        if A.sha256_file(path) != state["best_checkpoint_sha256"]:
            raise ValueError("Joint checkpoint changed before reload")
        model = self.build_model(device)
        model.load_state_dict(
            torch.load(path, map_location="cpu", weights_only=True)["model"], strict=True
        )
        fresh = self.evaluate(model, validation, self.validation_dataset, device)
        expected = self.archive.read_bound_json(
            config.output / "best-validation.json", state["best_validation_sha256"], dict
        )
        if fresh.values != expected["images"] or fresh.summarize() != expected["summary"]:
            raise ValueError("Joint dense output did not reproduce after reload")
        outcome = regression.run(model.native, device)
        original = A.read_json(
            config.output / f"epoch-{state['best_epoch']:03d}-native-replay.json"
        )
        if outcome["choices"] != original["choices"] or outcome["metrics"] != original["metrics"]:
            raise ValueError("Joint native policy traces did not reproduce after reload")
        if self.model_hash(model.native.backbone) == trunk_before:
            raise ValueError("Joint fine-tuning produced no backbone updates")
        if not all(
            torch.equal(buffers_before[name], current.cpu())
            for name, current in model.native.named_buffers()
        ):
            raise ValueError("Reloaded joint checkpoint changed native BatchNorm buffers")
        if (
            self.source_hashes() != state["source_sha256"]
            or A.sha256_file(config.corpus) != config.corpus_sha256
        ):
            raise ValueError("Joint source or input identity changed")
        native = config.output / "best-native.pt"
        torch.save(
            {
                "config": {
                    "backbone_name": "resnet34",
                    "image_pooling": model.native.image_pooling,
                },
                "model": model.native.state_dict(),
            },
            native,
        )
        better = self.validation_key(expected["summary"]) < self.frozen_key
        state.update(
            status="passed",
            checkpoint_reloaded=True,
            backbone_updated=True,
            best_native_checkpoint_sha256=A.sha256_file(native),
            no_aggregate_regression=outcome["no_aggregate_regression"],
            improved_dense_vs_frozen=better,
            provisional_training_preference=(
                "joint" if outcome["no_aggregate_regression"] and better else "frozen"
            ),
            peak_cuda_memory_bytes=torch.cuda.max_memory_allocated(),
        )
