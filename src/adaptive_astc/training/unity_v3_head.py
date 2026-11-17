"""Refit paired V3 image heads, preserving the source-only prediction context.

The stage loop is a static adaptation of UnityImageHeadRefit.run; cache extraction
and loss functions remain shared with V2 while V3 input/target identities stay explicit.
"""

from __future__ import annotations

import math
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import torch
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader, TensorDataset

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_quality_trainer import UnityQualityTrainer
from adaptive_astc.training.unity_v3_trainer import UnityV3Prediction, UnityV3Trainer
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from script.audit_unity_normalization import UnityNormalizationAudit
from script.refit_unity_image_head import NativeFeatureCache, UnityImageHeadRefit


class UnityV3HeadTrainer(UnityV3Trainer):
    @staticmethod
    def evaluate_cache(
        cache: NativeFeatureCache,
        model: UnityQualityRegressor,
        trainer: UnityV3Trainer,
        decision_inputs: list[UnityTextureInput],
    ) -> tuple[JsonDict, dict[str, np.ndarray], list[JsonDict]]:
        started = time.perf_counter()
        model.eval()
        with torch.inference_mode():
            with torch.autocast("cuda", dtype=torch.float16):
                outputs = cache.predict(model, torch.arange(len(cache.rows)))
            quality = outputs["image_quality"].cpu().numpy().astype(np.float64)
            probability = (
                torch.sigmoid(outputs["channel_zero_logits"]).cpu().numpy().astype(np.float64)
            )
        zero = probability >= trainer.config.zero_probability_threshold
        metrics, decisions = UnityV3Prediction.score(
            cache.rows,
            [trainer.resolver.policy_for(row) for row in cache.rows],
            cache.channel_mse,
            zero,
            quality,
            decision_inputs,
        )
        metrics["seconds"] = time.perf_counter() - started
        return (
            metrics,
            {
                "channel_mse": cache.channel_mse,
                "channel_zero": zero,
                "zero_probability": probability,
                "image_quality": quality,
            },
            decisions,
        )

    def run(self) -> JsonDict:
        root = self.root
        config_path = self.config_path
        config_sha256 = self.config_sha256
        self.verify_bindings()
        if "training_report" not in self.options:
            raise ValueError("V3 head stage requires a bound completed full-stage report")
        training = self.options["training_report"]
        self.bound_path(training)
        config = {
            **self.options,
            "epochs": self.config.epochs,
            "patches_per_image": self.config.patches_per_image,
            "learning_rate": self.config.learning_rate,
            "training_report": training["path"],
            "training_report_sha256": training["sha256"],
        }
        if (
            type(config["smoke"]) is not bool
            or type(config["epochs"]) is not int
            or config["epochs"] < 1
            or type(config["patches_per_image"]) is not int
            or config["patches_per_image"] not in (0, 4)
            or not math.isfinite(config["learning_rate"])
            or config["learning_rate"] <= 0
        ):
            raise ValueError(
                "Require explicit smoke, epoch budget, 0/all or4 views, and positive lr"
            )
        output, report = Path(config["output"]).resolve(), Path(config["report"]).resolve()
        if not output.is_relative_to(root / "experiment report/.local") or report.is_relative_to(
            output
        ):
            raise ValueError("Require private head-stage artifacts and an external report")
        if output.exists() or report.exists():
            raise FileExistsError("Use a new native image-head refit identity")
        training_path = Path(config["training_report"]).resolve()
        if A.sha256_file(training_path) != config["training_report_sha256"]:
            raise ValueError("Initial native training report changed")
        initial = A.read_json(training_path)
        initial_settings = initial["config"]
        loss_config = UnityImageHeadRefit.loss_config(config, initial_settings)
        expected_status = "passed_smoke" if config["smoke"] else "completed"
        counts = {split: len(records) for split, records in self.manifest["splits"].items()}
        if (
            initial["status"] != expected_status
            or initial["test_opened"] is not False
            or initial_settings["smoke"] != config["smoke"]
            or initial_settings["input_mode"] != self.options["input_mode"]
            or initial_settings["source_manifest"] != self.options["source_manifest"]
            or initial_settings["train_image_indices"]
            or initial["training_updates"] <= 0
            or initial_settings["train_images"] != counts["train"]
            or initial_settings["validation_images"] != counts["validation"]
            or initial["checkpoint_audit"]["status"] != "passed"
            or initial["checkpoint_audit"]["test_opened"] is not False
            or initial["checkpoint_audit"]["metrics"]["count"] != counts["validation"]
            or initial["checkpoint_audit"]["selected_artifacts_sha256"]
            != initial["best_artifacts_sha256"]
            or initial["checkpoint_audit"]["checkpoint_sha256"] != initial["checkpoint_sha256"]
            or initial["best_artifacts_sha256"]["best.pt"] != initial["checkpoint_sha256"]
        ):
            raise ValueError("Require matching paired V3 full training and selected-weight replay")
        archive = (
            Path(config["training_source_archive"])
            if config.get("training_source_archive")
            else None
        )
        binding_settings = {"source_files_sha256": initial_settings["source_sha256"]}
        source_binding = PatchNormalizationAudit.bind_training_sources(
            binding_settings, root, archive
        )
        initial_output = Path(initial_settings["output"])
        UnityQualityTrainer.verify_artifacts(initial_output, initial["best_artifacts_sha256"])
        training_config_path = UnityNormalizationAudit.training_config_path(initial_settings)
        corpus = Path(initial_settings["corpus"])
        execution_paths = {Path(name) for name in initial_settings["source_sha256"]}
        execution_paths.update(
            {
                Path(__file__).resolve(),
                config_path,
                training_path,
                root / "script/audit_unity_normalization.py",
                root / "src/adaptive_astc/evaluation/patch_normalization.py",
                root / "src/adaptive_astc/utils/artifacts.py",
            }
        )
        sources = {str(path): A.sha256_file(path) for path in execution_paths}
        sources.update(
            {
                str(config_path): config_sha256,
                str(training_path): config["training_report_sha256"],
                str(corpus / "corpus.json"): initial_settings["corpus_sha256"],
            }
        )
        UnityNormalizationAudit.verify_sources(sources)
        trainer = self
        if (
            trainer.config.corpus != Path(initial_settings["corpus"]).resolve()
            or trainer.config.corpus_sha256 != initial_settings["corpus_sha256"]
            or trainer.config.zero_probability_threshold
            != initial_settings["zero_probability_threshold"]
        ):
            raise ValueError("Initial native trainer input configuration differs from the model")
        trainer.config = replace(
            trainer.config, output=output, report=report, smoke=config["smoke"]
        )
        device = ExperimentRuntime.configure(initial_settings["seed"])
        if device.type != "cuda":
            raise RuntimeError("Native image-head refitting requires CUDA")
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as handle:
            handle.write('{"status":"preparing"}\n')
        started = time.perf_counter()
        state: JsonDict = {"status": "preparing", "training_updates": 0, "test_opened": False}
        try:
            datasets = {split: self.build_dataset(split) for split in ("train", "validation")}
            if (
                len(datasets["train"].rows) != counts["train"]
                or len(datasets["validation"].rows) != counts["validation"]
            ):
                raise ValueError("Source manifest and V3 datasets changed")
            if datasets["train"].fingerprint != initial_settings["corpus_fingerprint"]:
                raise ValueError("Initial native corpus fingerprint changed")
            checkpoint = torch.load(
                initial_output / "best.pt", map_location="cpu", weights_only=False
            )
            if A.fingerprint(checkpoint["config"]) != A.fingerprint(initial_settings):
                raise ValueError("Initial checkpoint settings differ from its training report")
            model = UnityQualityRegressor.from_checkpoint(checkpoint, device)
            for parameter in model.parameters():
                parameter.requires_grad_(False)
            model.image_head.requires_grad_(True)
            train_images = list(range(counts["train"]))
            train, train_files = NativeFeatureCache.prepare(
                cast(UnityPatchDataset, datasets["train"]),
                train_images,
                model,
                trainer.config.validation_batch_size,
                device,
                output,
                "train",
            )
            validation, validation_files = NativeFeatureCache.prepare(
                cast(UnityPatchDataset, datasets["validation"]),
                list(range(counts["validation"])),
                model,
                trainer.config.validation_batch_size,
                device,
                output,
                "validation",
            )
            baseline, predictions, decisions = self.evaluate_cache(
                validation, model, trainer, self.decision_inputs(datasets["validation"])
            )
            UnityNormalizationAudit.verify_predictions(
                predictions, initial_output / "best-validation.npz"
            )
            if decisions != A.read_json(initial_output / "best-decisions.json")["rows"]:
                raise ValueError("Cached native baseline decisions did not replay")
            sources.update({**train_files, **validation_files})
            UnityNormalizationAudit.verify_sources(sources)
            settings = {
                **initial_settings,
                "output": str(output),
                "report": str(report),
                "smoke": config["smoke"],
                "train_image_indices": [],
                "epochs": config["epochs"],
                "learning_rate": config["learning_rate"],
                "warmup_epochs": 0,
                "patience": 0,
                "learning_rate_schedule": "Constant during the image-head stage",
                "ema_decay": 0.0,
                "ema": False,
                "selection_metric": "accuracy",
                "group_image_cap": 0,
                "normal_image_repeats": 1,
                "train_epoch_image_draws": len(train.rows),
                "zero_weight": loss_config.zero_weight,
                "ssim_weight": loss_config.ssim_weight,
                "angle_weight": loss_config.angle_weight,
                "source_sha256": sources,
                "training_config_path": str(training_config_path),
                "train_images": len(train.rows),
                "validation_images": counts["validation"],
                "stage": "Frozen encoder image-head refit",
                "head_patch_views": config["patches_per_image"],
                "patches_per_image": config["patches_per_image"],
                "image_target_scope": "Full-image targets with frozen native patch encodings",
                "initial_training_report": str(training_path),
                "initial_training_report_sha256": config["training_report_sha256"],
                "trainable_parameters": sum(
                    p.numel() for p in model.parameters() if p.requires_grad
                ),
                "sampling": (
                    "Each selected image once per epoch; independent fixed-seed patch generator"
                ),
                "selection": "Validation footprint Top1 then color near-threshold RMSE",
            }
            self.enrich_settings(settings)
            A.write_json(output / "config.json", settings)
            state.update(
                status="running",
                config=settings,
                baseline=baseline,
                initial_training_updates=initial["training_updates"],
                training_source_binding=source_binding,
                history=[],
                preparation_seconds=time.perf_counter() - started,
            )
            optimizer = torch.optim.AdamW(
                model.image_head.parameters(),
                lr=config["learning_rate"],
                weight_decay=initial_settings["weight_decay"],
            )
            scaler = GradScaler("cuda")
            updates = 0

            def track_update(
                optimizer: torch.optim.Optimizer,
                args: tuple[object, ...],
                kwargs: dict[str, object],
            ) -> None:
                nonlocal updates
                updates += 1
                state["training_updates"] = updates

            hook = optimizer.register_step_post_hook(track_update)
            loader = DataLoader(
                TensorDataset(torch.arange(len(train.rows))),
                batch_size=initial_settings["image_batch_size"],
                shuffle=True,
                generator=torch.Generator().manual_seed(initial_settings["seed"]),
            )
            patch_generator = torch.Generator().manual_seed(initial_settings["seed"] + 1)
            best_key = (math.inf, math.inf)
            torch.cuda.reset_peak_memory_stats()
            try:
                for epoch in range(config["epochs"]):
                    epoch_started = time.perf_counter()
                    model.eval()
                    totals = dict.fromkeys(["total", "zero", "ssim", "angle"], 0.0)
                    attempts, before = 0, updates
                    for (indexes,) in loader:
                        optimizer.zero_grad(set_to_none=True)
                        with torch.autocast("cuda", dtype=torch.float16):
                            outputs = train.predict(
                                model, indexes, config["patches_per_image"], patch_generator
                            )
                        targets = {
                            name: values[indexes.to(device)]
                            for name, values in train.targets.items()
                        }
                        losses = UnityImageHeadRefit.image_losses(outputs, targets, settings)
                        scaler.scale(losses["total"]).backward()
                        scaler.unscale_(optimizer)
                        torch.nn.utils.clip_grad_norm_(model.image_head.parameters(), 5.0)
                        scaler.step(optimizer)
                        scaler.update()
                        for name in totals:
                            totals[name] += float(losses[name].detach()) * len(indexes)
                        attempts += 1
                    torch.cuda.synchronize()
                    training_seconds = time.perf_counter() - epoch_started
                    if updates == before:
                        raise RuntimeError("Native head epoch applied no optimizer updates")
                    metrics, predictions, decisions = self.evaluate_cache(
                        validation, model, trainer, self.decision_inputs(datasets["validation"])
                    )
                    state["history"].append(
                        {
                            "epoch": epoch + 1,
                            "loss": {k: v / len(train.rows) for k, v in totals.items()},
                            "validation": metrics,
                            "images_seen": len(train.rows),
                            "step_attempts": attempts,
                            "optimizer_updates": updates - before,
                            "amp_skipped_steps": attempts - (updates - before),
                            "training_seconds": training_seconds,
                        }
                    )
                    saved = {
                        "model": model.state_dict(),
                        "optimizer": optimizer.state_dict(),
                        "scaler": scaler.state_dict(),
                        "config": settings,
                        "epoch": epoch + 1,
                        "history": state["history"],
                        "selected_variant": "image_head_refit",
                    }
                    torch.save(saved, output / "last.pt")
                    key = UnityQualityTrainer.selection_key(metrics)
                    if key < best_key:
                        best_key = key
                        torch.save(saved, output / "best.pt")
                        np.savez_compressed(
                            output / "best-validation.npz",
                            channel_mse=predictions["channel_mse"],
                            channel_zero=predictions["channel_zero"],
                            zero_probability=predictions["zero_probability"],
                            image_quality=predictions["image_quality"],
                        )
                        A.write_json(
                            output / "best-decisions.json", {"rows": decisions, "metrics": metrics}
                        )
                        state["best_artifacts_sha256"] = {
                            name: A.sha256_file(output / name)
                            for name in ("best.pt", "best-validation.npz", "best-decisions.json")
                        }
                    state.update(
                        best_validation_accuracy=-best_key[0],
                        wall_seconds=time.perf_counter() - started,
                        peak_vram_bytes=torch.cuda.max_memory_allocated(),
                    )
                    A.write_json(report, state)
                    print(
                        {"epoch": epoch + 1, "updates": updates, "accuracy": metrics["accuracy"]},
                        flush=True,
                    )
            finally:
                hook.remove()
            best = torch.load(output / "best.pt", map_location="cpu", weights_only=False)
            for name, tensor in best["model"].items():
                if not name.startswith("image_head.") and not torch.equal(
                    tensor, checkpoint["model"][name]
                ):
                    raise ValueError("Frozen encoder, channel head or buffers changed")
            UnityQualityTrainer.verify_input_files(
                datasets["train"].rows + datasets["validation"].rows
            )
            UnityQualityTrainer.verify_artifacts(initial_output, initial["best_artifacts_sha256"])
            UnityNormalizationAudit.verify_sources(sources)
            if source_binding != PatchNormalizationAudit.bind_training_sources(
                binding_settings, root, archive
            ):
                raise ValueError("Initial native training source archive changed")
            self.verify_bindings()
            audit = trainer.audit_best(
                datasets["validation"], device, state["best_artifacts_sha256"]
            )
            UnityNormalizationAudit.verify_sources(sources)
            self.verify_bindings()
            state.update(
                status="passed_smoke" if config["smoke"] else "completed",
                checkpoint_audit=audit,
                checkpoint_sha256=state["best_artifacts_sha256"]["best.pt"],
                encoder_and_channel_head_unchanged=True,
                stop_reason="epoch_budget",
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(report, state)
            A.write_json(output / "history.json", state)
        return state
