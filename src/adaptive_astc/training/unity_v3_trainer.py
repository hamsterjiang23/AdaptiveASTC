"""Paired V3 training with source inputs and unchanged Unity quality supervision.

The optimization loop is a static adaptation of UnityQualityTrainer.fit. V2
source files stay frozen; only dataset construction and evaluation context differ.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict
from pathlib import Path
from typing import cast

import numpy as np
import torch
from numpy.typing import NDArray
from PIL import __version__ as pillow_version
from torch.amp.grad_scaler import GradScaler
from torch.optim.swa_utils import AveragedModel, get_ema_multi_avg_fn
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_image_bags import UnityImageBags
from adaptive_astc.data.unity_image_sampling import UnityImageSampler
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.data.unity_v3_dataset import UnityV3PatchDataset
from adaptive_astc.data.unity_v3_input import SourceTextureSpec
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_quality_loss import UnityQualityLoss, UnityQualityLossConfig
from adaptive_astc.training.unity_quality_trainer import UnityQualityTrainer, UnityTrainConfig
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.prediction_audit import UnityPredictionAudit

V3Dataset = UnityPatchDataset | UnityV3PatchDataset


class UnityV3Prediction(UnityQualityPrediction):
    """Select from input-only properties; score against the original Unity rows."""

    @classmethod
    def score(
        cls,
        rows: list[JsonDict],
        policies: list[UnitySearchPolicy],
        channel_mse: NDArray[np.float64],
        channel_zero: NDArray[np.bool_],
        image_quality: NDArray[np.float64],
        decision_inputs: list[UnityTextureInput],
    ) -> tuple[JsonDict, list[JsonDict]]:
        count = len(rows)
        if (
            not count
            or len(policies) != count
            or len(decision_inputs) != count
            or channel_mse.shape != (count, 20, 4)
            or channel_zero.shape != channel_mse.shape
            or image_quality.shape != (count, 20, 3)
        ):
            raise ValueError(
                "Native predictions and bound policies must cover each evaluation image"
            )
        observations = []
        confusion = np.zeros((4, 4), dtype=np.int64)
        classes = ["6x6", "8x8", "10x10", "12x12"]
        errors: list[float] = []
        for i, (row, policy) in enumerate(zip(rows, policies, strict=True)):
            texture = UnityTextureInput.from_row(row)
            if row["candidate_grid"] != [list(item) for item in cls.GRID]:
                raise ValueError("Truth candidate ordering differs from model output contract")
            truth = [
                {"block": b, "preset": p, "metrics": quality}
                for (b, p), quality in zip(cls.GRID, row["image_quality"], strict=True)
            ]
            original = row["original_selection"]
            measured = policy.select(
                truth,
                width=texture.width,
                height=texture.height,
                srgb=texture.srgb,
                normal=texture.normal,
            )
            if any(
                getattr(measured, key) != original[key]
                for key in ["block_size", "preset", "selection_reason", "candidates_measured"]
            ):
                raise ValueError("Bound native quality policy does not reproduce original search")
            prediction = cls.select(
                policy, decision_inputs[i], channel_mse[i], channel_zero[i], image_quality[i]
            )
            confusion[
                classes.index(original["block_size"]), classes.index(prediction.block_size)
            ] += 1
            payload = [
                16 * ((texture.width + b - 1) // b) * ((texture.height + b - 1) // b)
                for b, _ in cls.GRID
            ]
            if payload != row["payload_bytes"]:
                raise ValueError("Recorded RDO-off payload differs from native block geometry")
            psnr = cls.psnr(channel_mse[i], channel_zero[i], decision_inputs[i])
            if not texture.normal:
                for index, value in enumerate(row["image_quality"]):
                    if abs(value["psnr"] - measured.effective_psnr_threshold) <= 3:
                        errors.append((float(psnr[index]) - value["psnr"]) ** 2)
            strict = cls.strict_quality(
                policy,
                texture,
                row["image_quality"][prediction.selected_index],
                measured.effective_psnr_threshold,
            )
            feasible = any(
                cls.strict_quality(policy, texture, value, measured.effective_psnr_threshold)
                for value in row["image_quality"]
            )
            observations.append(
                {
                    "path": row["path"],
                    "prediction_input": asdict(decision_inputs[i]),
                    "quality_reference_input": asdict(texture),
                    "predicted_decision": asdict(prediction),
                    "original_decision": asdict(measured),
                    "footprint_match": prediction.block_size == original["block_size"],
                    "full_choice_match": prediction.selected_index == measured.selected_index,
                    "actual_strict_quality_met": strict,
                    "any_strict_feasible_candidate": feasible,
                    "selected_payload_bytes": payload[prediction.selected_index],
                    "original_payload_bytes": payload[measured.selected_index],
                    "fixed8_payload_bytes": payload[cls.GRID.index((8, "medium"))],
                }
            )
        support = confusion.sum(axis=1)
        per_class = {
            name: {
                "support": int(support[i]),
                "recall": float(confusion[i, i] / support[i]) if support[i] else None,
            }
            for i, name in enumerate(classes)
        }
        result = {
            "count": count,
            "accuracy": float(np.trace(confusion) / count),
            "balanced_accuracy": float(
                np.mean(np.diag(confusion)[support > 0] / support[support > 0])
            ),
            "full_choice_accuracy": sum(r["full_choice_match"] for r in observations) / count,
            "confusion_matrix": confusion.tolist(),
            "per_class": per_class,
            "actual_quality_pass_rate": sum(r["actual_strict_quality_met"] for r in observations)
            / count,
            "no_strict_feasible_images": sum(
                not r["any_strict_feasible_candidate"] for r in observations
            ),
            "color_near_threshold_candidate_count": len(errors),
            "color_near_threshold_rmse_db": float(np.sqrt(np.mean(errors))) if errors else None,
            **{
                key: sum(row[key] for row in observations)
                for key in [
                    "selected_payload_bytes",
                    "original_payload_bytes",
                    "fixed8_payload_bytes",
                ]
            },
            "scope": (
                "V3 source-aware prediction vs original Unity labels; "
                "true-reference quality/payload; "
                "no encoding timing"
            ),
        }
        return result, observations


class UnityV3Trainer(UnityQualityTrainer):
    def __init__(self, config_path: Path, root: Path) -> None:
        self.root = root.resolve()
        self.config_path = config_path.resolve()
        self.config_sha256 = ArtifactStore.sha256_file(self.config_path)
        self.options = ArtifactStore.read_json(self.config_path)
        allowed = {
            "schema",
            "base_training_config",
            "source_manifest",
            "input_mode",
            "output",
            "report",
            "smoke",
            "corpus",
            "corpus_sha256",
            "epochs",
            "training_report",
        }
        if (
            self.options.get("schema") != "unity-v3-training-v1"
            or set(self.options) - allowed
            or self.options.get("input_mode") not in {"unity", "source_aligned"}
            or type(self.options.get("smoke")) is not bool
            or ("corpus" in self.options) != ("corpus_sha256" in self.options)
        ):
            raise ValueError("Require an explicit V3 training contract and supported input mode")
        self.base_config_path = self.bound_path(self.options["base_training_config"])
        self.manifest_path = self.bound_path(self.options["source_manifest"])
        self.manifest = ArtifactStore.read_json(self.manifest_path)
        if (
            self.manifest.get("status") != "passed"
            or self.manifest.get("test_opened") is not False
            or self.manifest.get("failures")
            or set(self.manifest.get("splits", {})) != {"train", "validation"}
            or self.manifest.get("smoke") != self.options["smoke"]
            or self.manifest.get("pillow") != pillow_version
        ):
            raise ValueError(
                "Require a complete development-only source manifest and pinned Pillow"
            )
        values = ArtifactStore.read_json(self.base_config_path)
        for name in ("output", "report", "smoke", "corpus", "corpus_sha256", "epochs"):
            if name in self.options:
                values[name] = self.options[name]
        for name in ("output", "report", "corpus"):
            values[name] = Path(values[name]).resolve()
        if values.get("pretrained_weights") is not None:
            values["pretrained_weights"] = Path(values["pretrained_weights"]).resolve()
        values["train_image_indices"] = tuple(values.get("train_image_indices", []))
        self.config = UnityTrainConfig(**values)
        self.config.validate()
        if (
            self.config.backbone_name != "resnet34"
            or self.config.initialization != "pretrained"
            or self.config.image_pooling != "mean"
            or self.config.patches_per_image != 4
            or self.config.train_image_indices
            or self.config.ema_decay != 0
            or self.config.group_image_cap != 0
            or self.config.normal_image_repeats != 1
            or self.config.selection_metric != "accuracy"
            or (not self.config.smoke and self.config.epochs != 30)
        ):
            raise ValueError("V3 requires the paired ResNet34 ImageNet/mean/four-patch recipe")
        self.resolver = UnityPredictionAudit(self.root, self.config_path)
        self.verify_bindings()

    @staticmethod
    def bound_path(binding: JsonDict) -> Path:
        if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
            raise ValueError("A bound file needs exactly path and SHA256")
        path = Path(binding["path"]).resolve()
        if ArtifactStore.sha256_file(path) != binding["sha256"]:
            raise ValueError(f"Bound V3 source changed: {path}")
        return path

    def verify_bindings(self) -> None:
        if ArtifactStore.sha256_file(self.config_path) != self.config_sha256:
            raise ValueError("V3 training configuration changed")
        self.bound_path(self.options["base_training_config"])
        self.bound_path(self.options["source_manifest"])
        seen: set[str] = set()
        for split, records in self.manifest["splits"].items():
            if not records:
                raise ValueError("Source manifest splits cannot be empty")
            for record in records:
                asset = record["asset"].replace("\\", "/").casefold()
                if record["split"] != split or asset in seen:
                    raise ValueError("Source identity is duplicated or crosses declared splits")
                seen.add(asset)
                if ArtifactStore.sha256_file(Path(record["source"])) != record["source_sha256"]:
                    raise ValueError(f"Frozen source image changed: {record['source']}")
        for name, digest in self.manifest.get("binding_sources_sha256", {}).items():
            if ArtifactStore.sha256_file(Path(name)) != digest:
                raise ValueError(f"Source manifest provenance changed: {name}")

    def build_dataset(self, split: str) -> V3Dataset:
        if split not in {"train", "validation"}:
            raise ValueError("V3 training cannot open a confirmation dataset")
        native = UnityPatchDataset(
            self.config.corpus, split, expected_sha256=self.config.corpus_sha256
        )
        records = self.manifest["splits"][split]
        lookup = {record["asset"].replace("\\", "/").casefold(): record for record in records}
        expected = [row["path"].replace("\\", "/").casefold() for row in native.rows]
        if len(lookup) != len(records) or set(lookup) != set(expected):
            raise ValueError("Source manifest must cover exactly the selected native split")
        specs = []
        for row, asset in zip(native.rows, expected, strict=True):
            record = lookup[asset]
            spec = SourceTextureSpec(
                source=Path(record["source"]),
                source_width=record["source_width"],
                source_height=record["source_height"],
                target_width=record["target_width"],
                target_height=record["target_height"],
                srgb=record["srgb"],
                normal=record["normal"],
                need_alpha=record["need_alpha"],
                normal_metric_mips=record["normal_metric_mips"],
                asset=record["asset"],
                file_sha256=record["source_sha256"],
            )
            if (
                (spec.target_width, spec.target_height) != (row["width"], row["height"])
                or spec.srgb != row["import_metadata"]["srgb"]
                or spec.normal != row["metadata"]["is_normal"]
                or spec.need_alpha != row["metadata"]["need_alpha"]
                or spec.normal_metric_mips
                != (row["metadata"]["mip_count"] if row["metadata"]["is_normal"] else 1)
            ):
                raise ValueError("Source import settings do not match native supervision")
            specs.append(spec)
        return (
            native
            if self.options["input_mode"] == "unity"
            else UnityV3PatchDataset(native, specs, "source_aligned")
        )

    @staticmethod
    def decision_inputs(dataset: V3Dataset) -> list[UnityTextureInput]:
        if isinstance(dataset, UnityV3PatchDataset):
            return dataset.decision_inputs
        return [UnityTextureInput.from_row(row) for row in dataset.rows]

    def enrich_settings(self, settings: JsonDict) -> None:
        settings.update(
            v3_schema="unity-v3-training-v1",
            input_mode=self.options["input_mode"],
            source_manifest=self.options["source_manifest"],
            base_training_config=self.options["base_training_config"],
            training_config_path=str(self.config_path),
            prediction_context="Model-input pixels and explicit importer settings only",
            supervision_context="Original Unity reference patch SSE and full-image quality",
        )
        paths = [
            self.base_config_path,
            self.manifest_path,
            self.root / "src/adaptive_astc/data/unity_v3_input.py",
            self.root / "src/adaptive_astc/data/unity_v3_dataset.py",
            self.root / "src/adaptive_astc/training/unity_v3_trainer.py",
            self.root / "src/adaptive_astc/training/unity_v3_head.py",
            self.root / "src/adaptive_astc/training/unity_quality_trainer.py",
            self.root / "script/train_unity_v3.py",
            self.root / "script/refit_unity_image_head.py",
        ]
        settings["source_sha256"].update(
            {str(path): ArtifactStore.sha256_file(path) for path in paths}
        )

    def fit(self, state: JsonDict, started: float) -> JsonDict:
        config = self.config
        device = ExperimentRuntime.configure(config.seed)
        if device.type != "cuda":
            raise RuntimeError("Native model training requires CUDA")
        document = ArtifactStore.read_json(config.corpus / "corpus.json")
        self.validate_coverage(document, config)
        self.verify_bindings()
        train = self.build_dataset("train")
        validation = self.build_dataset("validation")
        indices = list(config.train_image_indices) or list(range(len(train.rows)))
        bags = UnityImageBags(cast(UnityPatchDataset, train), indices, config.patches_per_image)
        generator = torch.Generator().manual_seed(config.seed)
        sampler = (
            UnityImageSampler(
                [train.rows[i] for i in indices],
                generator,
                group_image_cap=config.group_image_cap,
                normal_image_repeats=config.normal_image_repeats,
            )
            if config.group_image_cap or config.normal_image_repeats != 1
            else None
        )
        loader = DataLoader(
            bags,
            batch_size=config.image_batch_size,
            shuffle=sampler is None,
            sampler=sampler,
            generator=generator,
            num_workers=config.workers,
            pin_memory=True,
            persistent_workers=config.workers > 0,
        )
        # Verify native policy provenance before optimizing any parameter.
        for row in validation.rows:
            self.resolver.policy_for(row)
        backbone_weights: dict[str, torch.Tensor] | None = None
        self.verify_pretrained_weights(config)
        if config.pretrained_weights is not None:
            backbone_weights = torch.load(
                config.pretrained_weights, map_location="cpu", weights_only=True
            )
            self.verify_pretrained_weights(config)
        model = UnityQualityRegressor(
            image_pooling=config.image_pooling,
            backbone_name=config.backbone_name,
            backbone_weights=backbone_weights,
        ).to(device)
        ema = (
            AveragedModel(
                model,
                device=device,
                multi_avg_fn=get_ema_multi_avg_fn(config.ema_decay),
                use_buffers=True,
            )
            if config.ema_decay
            else None
        )
        criterion = UnityQualityLoss(
            UnityQualityLossConfig(config.zero_weight, config.ssim_weight, config.angle_weight)
        )
        optimizer = torch.optim.AdamW(
            model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
        )
        scaler = GradScaler("cuda")
        source_files = [
            Path(__file__),
            self.config_path,
            self.root / "src/adaptive_astc/data/unity_image_bags.py",
            self.root / "src/adaptive_astc/data/unity_image_sampling.py",
            self.root / "src/adaptive_astc/data/splitting.py",
            self.root / "src/adaptive_astc/data/unity_patch_dataset.py",
            self.root / "src/adaptive_astc/models/unity_quality.py",
            self.root / "src/adaptive_astc/training/unity_quality_loss.py",
            self.root / "src/adaptive_astc/evaluation/unity_quality.py",
            self.root / "reproductions/unity_search_baseline/prediction_audit.py",
            self.root / "reproductions/unity_search_baseline/policy.py",
            self.root / "reproductions/unity_search_baseline/policy_audit.py",
            self.root / "src/adaptive_astc/utils/runtime.py",
        ]
        settings = {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        }
        settings.update(
            parameters=sum(p.numel() for p in model.parameters()),
            fp32_parameter_bytes=sum(p.numel() * p.element_size() for p in model.parameters()),
            gpu=torch.cuda.get_device_name(),
            torch=torch.__version__,
            source_sha256={str(path): ArtifactStore.sha256_file(path) for path in source_files},
            corpus_fingerprint=train.fingerprint,
            train_images=len(bags),
            train_epoch_image_draws=len(sampler) if sampler is not None else len(bags),
            validation_images=len(validation.rows),
            sampling=(
                "Shuffled per-epoch asset-group cap or explicit normal repeats; "
                "within-image patches with replacement, observed image order recorded"
                if sampler is not None
                else "Each selected train image once per epoch, shuffled; "
                "within-image patches with replacement"
            ),
            image_target_scope=(
                "Full-image quality and zero-channel supervision, sampled patch inputs at training"
            ),
            selection=(
                "Validation footprint accuracy, then color near-threshold RMSE; "
                "margin and zero threshold fixed"
                if config.selection_metric == "accuracy"
                else "Validation color near-threshold RMSE, then footprint accuracy; "
                "margin and zero threshold fixed"
            ),
            augmentations=[],
            ema="Parameters and buffers after each applied optimizer update" if ema else False,
            policy_origins=self.resolver.origins,
        )
        self.enrich_settings(settings)
        ArtifactStore.write_json(config.output / "config.json", settings)
        state.update(
            status="running",
            config=settings,
            history=[],
            preparation_seconds=time.perf_counter() - started,
        )
        updates = 0

        def track_update(
            optimizer: torch.optim.Optimizer, args: tuple[object, ...], kwargs: dict[str, object]
        ) -> None:
            nonlocal updates
            updates += 1
            state["training_updates"] = updates
            if ema is not None:
                ema.update_parameters(model)
                state["ema_updates"] = int(ema.n_averaged.item())

        hook = optimizer.register_step_post_hook(track_update)
        best_key = (math.inf, math.inf)
        best_rmse, stale = math.inf, 0
        stop = "epoch_budget"
        torch.cuda.reset_peak_memory_stats()
        try:
            for epoch in range(config.epochs):
                epoch_start = time.perf_counter()
                warmup = min(config.epochs, config.warmup_epochs)
                factor = (
                    (epoch + 1) / warmup
                    if epoch < warmup
                    else 0.5
                    * (1 + math.cos(math.pi * (epoch - warmup) / max(1, config.epochs - warmup)))
                )
                for group in optimizer.param_groups:
                    group["lr"] = config.learning_rate * factor
                model.train()
                totals = dict.fromkeys(["total", "patch", "zero", "ssim", "angle"], 0.0)
                images_seen, attempts, before = 0, 0, updates
                observed_images: list[int] = []
                for batch, targets in loader:
                    if sampler is not None:
                        observed_images.extend(batch["original_image_index"].tolist())
                    batch = {k: v.to(device) for k, v in batch.items()}
                    targets = {k: v.to(device) for k, v in targets.items()}
                    count, views = batch["rgba"].shape[:2]
                    ids = torch.arange(count, device=device).repeat_interleave(views)
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast("cuda", dtype=torch.float16):
                        outputs = model(
                            batch["rgba"].flatten(0, 1),
                            batch["valid_mask"].flatten(0, 1),
                            ids,
                            batch["metadata"],
                        )
                    losses = criterion(
                        outputs, batch["channel_log_mse"].flatten(0, 1), ids, targets
                    )
                    scaler.scale(losses["total"]).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                    scaler.step(optimizer)
                    scaler.update()
                    for key in totals:
                        totals[key] += float(losses[key].detach()) * count
                    images_seen += count
                    attempts += 1
                    if attempts % 25 == 0:
                        ArtifactStore.write_json(
                            config.output / "progress.json",
                            {
                                "status": "training",
                                "epoch": epoch + 1,
                                "batches": attempts,
                                "images": images_seen,
                                "optimizer_updates": updates,
                                "wall_seconds": time.perf_counter() - started,
                            },
                        )
                torch.cuda.synchronize()
                training_seconds = time.perf_counter() - epoch_start
                if updates == before:
                    raise RuntimeError("Native epoch applied no optimizer updates")
                metrics, predictions, decisions = self.evaluate(model, validation, device)
                variants = {"raw": (model, metrics, predictions, decisions)}
                if ema is not None:
                    ema_model = cast(UnityQualityRegressor, ema.module)
                    ema_metrics, ema_predictions, ema_decisions = self.evaluate(
                        ema_model, validation, device
                    )
                    variants["ema"] = (
                        ema_model,
                        ema_metrics,
                        ema_predictions,
                        ema_decisions,
                    )
                winner = min(
                    variants,
                    key=lambda name: self.selection_key(variants[name][1], config.selection_metric),
                )
                selected_model, selected_metrics, selected_predictions, selected_decisions = (
                    variants[winner]
                )
                row = {
                    "epoch": epoch + 1,
                    "loss": {k: v / images_seen for k, v in totals.items()},
                    "images_seen": images_seen,
                    "patch_draws": images_seen * config.patches_per_image,
                    "step_attempts": attempts,
                    "optimizer_updates": updates - before,
                    "amp_skipped_steps": attempts - (updates - before),
                    "training_seconds": training_seconds,
                    "validation": metrics,
                    "validation_variants": {name: value[1] for name, value in variants.items()},
                    "selected_validation_variant": winner,
                    "ema_updates": int(ema.n_averaged.item()) if ema is not None else 0,
                    "learning_rate": optimizer.param_groups[0]["lr"],
                }
                if sampler is not None:
                    receipt = sampler.receipt(indices, observed_images)
                    path = config.output / f"epoch-{epoch + 1:02d}-image-draws.json"
                    ArtifactStore.write_json(path, receipt)
                    row["image_sampling"] = {
                        "path": str(path),
                        "sha256": ArtifactStore.sha256_file(path),
                        **{key: value for key, value in receipt.items() if key != "image_indices"},
                    }
                state["history"].append(row)
                rmse = selected_metrics["color_near_threshold_rmse_db"]
                rmse_key = min(self.selection_key(value[1])[1] for value in variants.values())
                key = self.selection_key(selected_metrics, config.selection_metric)
                checkpoint = {
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "scaler": scaler.state_dict(),
                    "config": settings,
                    "epoch": epoch + 1,
                    "history": state["history"],
                    "ema": ema.state_dict() if ema is not None else None,
                }
                temporary = config.output / "last.tmp"
                torch.save(checkpoint, temporary)
                temporary.replace(config.output / "last.pt")
                if key < best_key:
                    best_key = key
                    torch.save(
                        {
                            **checkpoint,
                            "model": selected_model.state_dict(),
                            "selected_variant": winner,
                        },
                        config.output / "best.pt",
                    )
                    np.savez_compressed(
                        config.output / "best-validation.npz",
                        channel_mse=selected_predictions["channel_mse"],
                        channel_zero=selected_predictions["channel_zero"],
                        zero_probability=selected_predictions["zero_probability"],
                        image_quality=selected_predictions["image_quality"],
                    )
                    ArtifactStore.write_json(
                        config.output / "best-decisions.json",
                        {"rows": selected_decisions, "metrics": selected_metrics},
                    )
                    state["best_artifacts_sha256"] = {
                        name: ArtifactStore.sha256_file(config.output / name)
                        for name in ["best.pt", "best-validation.npz", "best-decisions.json"]
                    }
                    state["best_validation_variant"] = winner
                    state["best_validation_accuracy"] = selected_metrics["accuracy"]
                if rmse_key < best_rmse:
                    best_rmse, stale = rmse_key, 0
                elif math.isfinite(rmse_key):
                    stale += 1
                state.update(
                    training_updates=updates,
                    best_color_near_threshold_rmse_db=best_rmse
                    if math.isfinite(best_rmse)
                    else None,
                    wall_seconds=time.perf_counter() - started,
                    peak_vram_bytes=torch.cuda.max_memory_allocated(),
                )
                ArtifactStore.write_json(config.output / "history.json", state)
                ArtifactStore.write_json(config.report, state)
                print(
                    {
                        "epoch": epoch + 1,
                        "updates": updates,
                        "loss": row["loss"],
                        "accuracy": selected_metrics["accuracy"],
                        "selected_variant": winner,
                        "near_rmse": rmse,
                    },
                    flush=True,
                )
                if config.patience and epoch >= warmup and stale >= config.patience:
                    stop = "color_near_threshold_rmse_patience"
                    break
        finally:
            hook.remove()
        state.update(
            status="trained_smoke" if config.smoke else "trained",
            stop_reason=stop,
            checkpoint_sha256=state["best_artifacts_sha256"]["best.pt"],
        )
        ArtifactStore.write_json(config.output / "history.json", state)
        self.verify_input_files([train.rows[i] for i in indices])
        self.verify_bindings()
        audit = self.audit_best(validation, device, state["best_artifacts_sha256"])
        self.verify_pretrained_weights(config)
        self.verify_bindings()
        if sampler is not None:
            for epoch in state["history"]:
                receipt = epoch["image_sampling"]
                if ArtifactStore.sha256_file(Path(receipt["path"])) != receipt["sha256"]:
                    raise ValueError("Native training image sampling receipt changed")
        state.update(
            status="passed_smoke" if config.smoke else "completed",
            checkpoint_audit=audit,
            wall_seconds=time.perf_counter() - started,
        )
        ArtifactStore.write_json(config.output / "history.json", state)
        ArtifactStore.write_json(config.report, state)
        return state

    def evaluate(
        self, model: UnityQualityRegressor, dataset: V3Dataset, device: torch.device
    ) -> tuple[JsonDict, dict[str, np.ndarray], list[JsonDict]]:
        started = time.perf_counter()
        model.eval()
        features = np.empty((len(dataset), model.channel_head.in_features), dtype=np.float32)
        logs = np.empty((len(dataset), 20, 4), dtype=np.float64)
        loader = DataLoader(dataset, batch_size=self.config.validation_batch_size, num_workers=0)
        with torch.inference_mode():
            for batch in loader:
                with torch.autocast("cuda", dtype=torch.float16):
                    output = model.encode(
                        batch["rgba"].to(device),
                        batch["valid_mask"].to(device),
                        batch["metadata"].to(device),
                    )
                indexes = batch["patch_index"].numpy()
                features[indexes] = output["features"].float().cpu().numpy()
                logs[indexes] = output["channel_log_mse"].float().cpu().numpy()
            with torch.autocast("cuda", dtype=torch.float16):
                image = model.predict_images(
                    torch.from_numpy(features).to(device),
                    torch.from_numpy(dataset.pixel_counts).to(device),
                    torch.from_numpy(dataset.image_ids).to(device),
                    torch.from_numpy(dataset.input_metadata).to(device),
                )
            quality = image["image_quality"].cpu().numpy().astype(np.float64)
            probability = (
                torch.sigmoid(image["channel_zero_logits"]).cpu().numpy().astype(np.float64)
            )
        mse = UnityQualityPrediction.aggregate_mse(
            logs, dataset.pixel_counts, dataset.image_ids, len(dataset.rows)
        )
        zero = probability >= self.config.zero_probability_threshold
        metrics, rows = UnityV3Prediction.score(
            dataset.rows,
            [self.resolver.policy_for(row) for row in dataset.rows],
            mse,
            zero,
            quality,
            self.decision_inputs(dataset),
        )
        metrics["seconds"] = time.perf_counter() - started
        return (
            metrics,
            {
                "channel_mse": mse,
                "channel_zero": zero,
                "zero_probability": probability,
                "image_quality": quality,
            },
            rows,
        )

    def audit_best(
        self,
        validation: V3Dataset,
        device: torch.device,
        expected_artifacts: dict[str, str],
    ) -> JsonDict:
        self.verify_bindings()
        started = time.perf_counter()
        config = self.config
        self.verify_artifacts(config.output, expected_artifacts)
        checkpoint = torch.load(config.output / "best.pt", map_location="cpu", weights_only=False)
        settings = ArtifactStore.read_json(config.output / "config.json")
        if ArtifactStore.fingerprint(checkpoint["config"]) != ArtifactStore.fingerprint(settings):
            raise ValueError("Native checkpoint configuration differs from its run")
        for path, expected_sha256 in settings["source_sha256"].items():
            if ArtifactStore.sha256_file(Path(path)) != expected_sha256:
                raise ValueError(f"Native run source changed: {path}")
        fresh_validation = self.build_dataset("validation")
        if fresh_validation.fingerprint != validation.fingerprint:
            raise ValueError("Native validation corpus changed during training")
        self.resolver = UnityPredictionAudit(self.root, self.config_path)
        for row in fresh_validation.rows:
            self.resolver.policy_for(row)
        model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
        metrics, predictions, rows = self.evaluate(model, fresh_validation, device)
        with np.load(config.output / "best-validation.npz", allow_pickle=False) as saved:
            for key, value in predictions.items():
                if value.dtype == np.bool_:
                    np.testing.assert_array_equal(value, saved[key])
                else:
                    np.testing.assert_allclose(value, saved[key], rtol=0, atol=1e-5)
        expected = ArtifactStore.read_json(config.output / "best-decisions.json")
        if expected["rows"] != rows:
            raise ValueError("Reloaded native decisions differ from selected predictions")
        self.verify_artifacts(config.output, expected_artifacts)
        self.verify_bindings()
        self.verify_input_files(fresh_validation.rows)
        result = {
            "status": "passed",
            "epoch": checkpoint["epoch"],
            "selected_variant": checkpoint.get("selected_variant", "raw"),
            "metrics": metrics,
            "checkpoint_sha256": ArtifactStore.sha256_file(config.output / "best.pt"),
            "predictions_sha256": ArtifactStore.sha256_file(config.output / "best-validation.npz"),
            "selected_artifacts_sha256": expected_artifacts,
            "test_opened": False,
            "wall_seconds": time.perf_counter() - started,
        }
        ArtifactStore.write_json(config.output / "checkpoint-audit.json", result)
        return result
