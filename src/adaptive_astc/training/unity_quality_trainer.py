"""CUDA-only native quality training with original-policy validation and checkpoint replay."""

from __future__ import annotations

import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_image_bags import UnityImageBags
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_quality_loss import UnityQualityLoss, UnityQualityLossConfig
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.runtime import ExperimentRuntime
from reproductions.unity_search_baseline.prediction_audit import UnityPredictionAudit


@dataclass(frozen=True)
class UnityTrainConfig:
    corpus: Path
    corpus_sha256: str
    output: Path
    report: Path
    smoke: bool = False
    train_image_indices: tuple[int, ...] = ()
    epochs: int = 30
    image_batch_size: int = 16
    patches_per_image: int = 4
    validation_batch_size: int = 64
    learning_rate: float = 0.0003
    weight_decay: float = 0.05
    warmup_epochs: int = 1
    patience: int = 5
    workers: int = 2
    seed: int = 20261112
    zero_probability_threshold: float = 0.5
    zero_weight: float = 0.1
    ssim_weight: float = 0.1
    angle_weight: float = 0.1
    image_pooling: str = "mean_max"

    def validate(self) -> None:
        for name in ["epochs", "image_batch_size", "patches_per_image", "validation_batch_size"]:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError("Positive integer epoch, batch and sampling sizes required")
        for name in ["workers", "patience", "warmup_epochs"]:
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError("Worker, patience and warmup counts must be nonnegative")
        if (
            type(self.smoke) is not bool
            or not math.isfinite(self.learning_rate)
            or self.learning_rate <= 0
            or not math.isfinite(self.weight_decay)
            or self.weight_decay < 0
            or not 0 < self.zero_probability_threshold < 1
            or self.image_pooling not in ("mean_max", "mean")
        ):
            raise ValueError("Invalid native training configuration")
        if not self.smoke and self.train_image_indices:
            raise ValueError("Formal native training cannot silently select a source subset")
        if (
            type(self.seed) is not int
            or not 0 <= self.seed < 2**32
            or any(type(index) is not int or index < 0 for index in self.train_image_indices)
            or len(set(self.train_image_indices)) != len(self.train_image_indices)
        ):
            raise ValueError("Require a valid seed and unique nonnegative train image indices")
        UnityQualityLossConfig(self.zero_weight, self.ssim_weight, self.angle_weight).validate()


class UnityQualityTrainer:
    def __init__(self, config_path: Path, root: Path) -> None:
        self.root = root.resolve()
        self.config_path = config_path.resolve()
        values = ArtifactStore.read_json(config_path)
        for name in ["corpus", "output", "report"]:
            values[name] = Path(values[name]).resolve()
        if "train_image_indices" in values:
            values["train_image_indices"] = tuple(values["train_image_indices"])
        self.config = UnityTrainConfig(**values)
        self.config.validate()
        self.resolver = UnityPredictionAudit(self.root, self.config_path)

    @staticmethod
    def validate_coverage(document: JsonDict, config: UnityTrainConfig) -> None:
        if not config.smoke and (
            document.get("coverage") != "complete"
            or document["counts"] != {"train": 10000, "validation": 1000}
            or document["counts"] != document.get("expected_full_counts")
        ):
            raise ValueError(
                "Formal native training requires complete frozen train10000/validation1000"
            )

    def run(self) -> JsonDict:
        config = self.config
        if not config.output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Native checkpoints belong under experiment report/.local")
        if config.report.exists() or config.report.is_relative_to(config.output):
            raise FileExistsError("Use a new independent native training report")
        config.output.mkdir(parents=True, exist_ok=False)
        state: JsonDict = {"status": "preparing", "test_opened": False, "training_updates": 0}
        initial_report = config.output / "initial-report.json"
        ArtifactStore.write_json(initial_report, state)
        config.report.parent.mkdir(parents=True, exist_ok=True)
        os.link(initial_report, config.report)
        initial_report.unlink()
        started = time.perf_counter()
        try:
            state = self.fit(state, started)
        except BaseException as error:
            state.update(
                status="failed", error=repr(error), wall_seconds=time.perf_counter() - started
            )
            ArtifactStore.write_json(config.report, state)
            raise
        return state

    def fit(self, state: JsonDict, started: float) -> JsonDict:
        config = self.config
        device = ExperimentRuntime.configure(config.seed)
        if device.type != "cuda":
            raise RuntimeError("Native model training requires CUDA")
        document = ArtifactStore.read_json(config.corpus / "corpus.json")
        self.validate_coverage(document, config)
        train = UnityPatchDataset(config.corpus, "train", expected_sha256=config.corpus_sha256)
        validation = UnityPatchDataset(
            config.corpus, "validation", expected_sha256=config.corpus_sha256
        )
        indices = list(config.train_image_indices) or list(range(len(train.rows)))
        bags = UnityImageBags(train, indices, config.patches_per_image)
        loader = DataLoader(
            bags,
            batch_size=config.image_batch_size,
            shuffle=True,
            generator=torch.Generator().manual_seed(config.seed),
            num_workers=config.workers,
            pin_memory=True,
            persistent_workers=config.workers > 0,
        )
        # Verify native policy provenance before optimizing any parameter.
        for row in validation.rows:
            self.resolver.policy_for(row)
        model = UnityQualityRegressor(image_pooling=config.image_pooling).to(device)
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
            validation_images=len(validation.rows),
            sampling=(
                "Each selected train image once per epoch, shuffled; "
                "within-image patches with replacement"
            ),
            image_target_scope=(
                "Full-image quality and zero-channel supervision, sampled patch inputs at training"
            ),
            selection=(
                "Validation footprint accuracy, then color near-threshold RMSE; "
                "margin and zero threshold fixed"
            ),
            augmentations=[],
            initialization="scratch",
            policy_origins=self.resolver.origins,
        )
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
                for batch, targets in loader:
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
                    "learning_rate": optimizer.param_groups[0]["lr"],
                }
                state["history"].append(row)
                rmse = metrics["color_near_threshold_rmse_db"]
                rmse_key = math.inf if rmse is None else float(rmse)
                key = (-metrics["accuracy"], rmse_key)
                checkpoint = {
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "scaler": scaler.state_dict(),
                    "config": settings,
                    "epoch": epoch + 1,
                    "history": state["history"],
                }
                temporary = config.output / "last.tmp"
                torch.save(checkpoint, temporary)
                temporary.replace(config.output / "last.pt")
                if key < best_key:
                    best_key = key
                    torch.save(checkpoint, config.output / "best.pt")
                    np.savez_compressed(
                        config.output / "best-validation.npz",
                        channel_mse=predictions["channel_mse"],
                        channel_zero=predictions["channel_zero"],
                        zero_probability=predictions["zero_probability"],
                        image_quality=predictions["image_quality"],
                    )
                    ArtifactStore.write_json(
                        config.output / "best-decisions.json",
                        {"rows": decisions, "metrics": metrics},
                    )
                    state["best_artifacts_sha256"] = {
                        name: ArtifactStore.sha256_file(config.output / name)
                        for name in ["best.pt", "best-validation.npz", "best-decisions.json"]
                    }
                if rmse_key < best_rmse:
                    best_rmse, stale = rmse_key, 0
                elif math.isfinite(rmse_key):
                    stale += 1
                state.update(
                    training_updates=updates,
                    best_validation_accuracy=-best_key[0],
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
                        "accuracy": metrics["accuracy"],
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
        audit = self.audit_best(validation, device, state["best_artifacts_sha256"])
        state.update(
            status="passed_smoke" if config.smoke else "completed",
            checkpoint_audit=audit,
            wall_seconds=time.perf_counter() - started,
        )
        ArtifactStore.write_json(config.output / "history.json", state)
        ArtifactStore.write_json(config.report, state)
        return state

    def evaluate(
        self, model: UnityQualityRegressor, dataset: UnityPatchDataset, device: torch.device
    ) -> tuple[JsonDict, dict[str, np.ndarray], list[JsonDict]]:
        started = time.perf_counter()
        model.eval()
        features = np.empty((len(dataset), 512), dtype=np.float32)
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
        metrics, rows = UnityQualityPrediction.score(
            dataset.rows,
            [self.resolver.policy_for(row) for row in dataset.rows],
            mse,
            zero,
            quality,
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

    @staticmethod
    def verify_input_files(rows: list[JsonDict]) -> None:
        checked: dict[Path, str] = {}
        for row in rows:
            for field, hash_field in [
                ("reference", "reference_sha256"),
                ("targets", "target_sha256"),
            ]:
                path = Path(row[field])
                if path not in checked:
                    checked[path] = ArtifactStore.sha256_file(path)
                if checked[path] != row[hash_field]:
                    raise ValueError(f"Native training input changed: {path}")

    @staticmethod
    def verify_artifacts(output: Path, expected: dict[str, str]) -> None:
        if set(expected) != {"best.pt", "best-validation.npz", "best-decisions.json"}:
            raise ValueError("Require saved checkpoint, prediction and decision hashes")
        for name, sha256 in expected.items():
            if ArtifactStore.sha256_file(output / name) != sha256:
                raise ValueError(f"Selected native artifact changed: {name}")

    def audit_best(
        self,
        validation: UnityPatchDataset,
        device: torch.device,
        expected_artifacts: dict[str, str],
    ) -> JsonDict:
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
        fresh_validation = UnityPatchDataset(
            config.corpus, "validation", expected_sha256=config.corpus_sha256
        )
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
        result = {
            "status": "passed",
            "epoch": checkpoint["epoch"],
            "metrics": metrics,
            "checkpoint_sha256": ArtifactStore.sha256_file(config.output / "best.pt"),
            "predictions_sha256": ArtifactStore.sha256_file(config.output / "best-validation.npz"),
            "selected_artifacts_sha256": expected_artifacts,
            "test_opened": False,
            "wall_seconds": time.perf_counter() - started,
        }
        ArtifactStore.write_json(config.output / "checkpoint-audit.json", result)
        return result
