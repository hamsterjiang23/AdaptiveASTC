"""Attribute frozen Unity validation decisions by replacing quality components with truth."""

from __future__ import annotations

import argparse
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.patch_normalization import PatchNormalizationAudit
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.prediction_audit import UnityPredictionAudit


def grouped_metrics(rows: list[JsonDict], decisions: list[JsonDict]) -> JsonDict:
    groups: dict[str, list[JsonDict]] = defaultdict(list)
    assets: dict[str, list[bool]] = defaultdict(list)
    for row, decision in zip(rows, decisions, strict=True):
        texture = UnityTextureInput.from_row(row)
        kind = "normal" if texture.normal else "linear"
        if not texture.normal and texture.srgb:
            kind = "srgb_large" if decision["original_decision"]["size_first"] else "srgb_small"
        side = max(texture.width, texture.height)
        side_range = next(
            (f"max_side_le{limit}" for limit in [128, 256, 512, 1024] if side <= limit),
            "max_side_gt1024",
        )
        for name in [
            kind,
            side_range,
            "original_" + row["original_selection"]["selection_reason"],
        ]:
            groups[name].append(decision)
        assets[row["group"]].append(decision["footprint_match"])
    result = {
        name: {
            "images": len(items),
            "accuracy": sum(item["footprint_match"] for item in items) / len(items),
            "full_choice_accuracy": sum(item["full_choice_match"] for item in items) / len(items),
            "actual_quality_pass_rate": sum(item["actual_strict_quality_met"] for item in items)
            / len(items),
        }
        for name, items in groups.items()
    }
    result["asset_group_macro"] = {
        "groups": len(assets),
        "accuracy": sum(sum(items) / len(items) for items in assets.values()) / len(assets),
    }
    return result


def error_summary(values: list[float]) -> JsonDict:
    return {
        "count": len(values),
        "rmse": math.sqrt(sum(value**2 for value in values) / len(values)) if values else None,
        "bias": sum(values) / len(values) if values else None,
    }


def residual_metrics(
    rows: list[JsonDict],
    baseline_decisions: list[JsonDict],
    mse: NDArray[np.float64],
    zero: NDArray[np.bool_],
    quality: NDArray[np.float64],
    true_zero: NDArray[np.bool_],
) -> JsonDict:
    errors: dict[str, list[float]] = defaultdict(list)
    for index, (row, decision) in enumerate(zip(rows, baseline_decisions, strict=True)):
        texture = UnityTextureInput.from_row(row)
        psnr = UnityQualityPrediction.psnr(mse[index], zero[index], texture)
        for candidate, truth in enumerate(row["image_quality"]):
            if not texture.normal:
                delta = float(psnr[candidate]) - truth["psnr"]
                errors["color_psnr_db"].append(delta)
                threshold = decision["original_decision"]["effective_psnr_threshold"]
                if abs(truth["psnr"] - threshold) <= 3:
                    errors["color_psnr_near_threshold_3db"].append(delta)
            for column, name in enumerate(UnityQualityPrediction.QUALITY_NAMES):
                active = texture.normal if column else texture.srgb and not texture.normal
                if active:
                    errors[name].append(float(quality[index, candidate, column]) - truth[name])
    result = {name: error_summary(values) for name, values in errors.items()}
    result["zero_channel_confusion"] = {
        "true_zero_predicted_zero": int(np.sum(true_zero & zero)),
        "true_zero_predicted_nonzero": int(np.sum(true_zero & ~zero)),
        "true_nonzero_predicted_zero": int(np.sum(~true_zero & zero)),
        "true_nonzero_predicted_nonzero": int(np.sum(~true_zero & ~zero)),
        "scope": "All validation images x20 candidates x4 supervised channels",
    }
    return result


def run(config_path: Path) -> JsonDict:
    started = time.perf_counter()
    root = Path(__file__).resolve().parents[1]
    config = ArtifactStore.read_json(config_path)
    training_path = Path(config["training_report"])
    if ArtifactStore.sha256_file(training_path) != config["training_report_sha256"]:
        raise ValueError("Completed training report changed")
    training = ArtifactStore.read_json(training_path)
    smoke = config["smoke"]
    if training["status"] != ("passed_smoke" if smoke else "completed"):
        raise ValueError("Attribution requires a terminal successful training identity")
    if training["checkpoint_audit"]["status"] != "passed":
        raise ValueError("Selected checkpoint replay audit must pass first")
    settings = training["config"]
    corpus = Path(settings["corpus"]) / "corpus.json"
    if ArtifactStore.sha256_file(corpus) != settings["corpus_sha256"]:
        raise ValueError("Original training corpus changed")
    document = ArtifactStore.read_json(corpus)
    if set(document["splits"]) != {"train", "validation"} or document["test_opened"]:
        raise ValueError("Require the bound development corpus")
    rows = document["splits"]["validation"]
    if not smoke and (
        document["coverage"] != "complete"
        or document["counts"] != {"train": 10000, "validation": 1000}
    ):
        raise ValueError("Formal attribution requires the full development split")
    model_output = Path(settings["output"])
    archive = config.get("training_source_archive")
    source_binding = PatchNormalizationAudit.bind_training_sources(
        {"source_files_sha256": settings["source_sha256"]},
        root,
        Path(archive) if archive else None,
    )
    sources = {
        str(training_path.resolve()): config["training_report_sha256"],
        str(config_path.resolve()): ArtifactStore.sha256_file(config_path),
        str(corpus.resolve()): settings["corpus_sha256"],
        str(Path(__file__).resolve()): ArtifactStore.sha256_file(Path(__file__)),
        **{row["verified_source"]: row["training_sha256"] for row in source_binding["sources"]},
    }
    for relative in [
        "src/adaptive_astc/evaluation/patch_normalization.py",
        "src/adaptive_astc/evaluation/unity_quality.py",
        "src/adaptive_astc/utils/artifacts.py",
        "reproductions/unity_search_baseline/prediction_audit.py",
        "reproductions/unity_search_baseline/policy.py",
        "reproductions/unity_search_baseline/policy_audit.py",
    ]:
        path = root / relative
        sources[str(path)] = ArtifactStore.sha256_file(path)
    for name, expected in training["best_artifacts_sha256"].items():
        sources[str(model_output / name)] = expected
    for path, expected in sources.items():
        if ArtifactStore.sha256_file(Path(path)) != expected:
            raise ValueError(f"Frozen training source or selected artifact changed: {path}")
    with np.load(model_output / "best-validation.npz", allow_pickle=False) as archive:
        mse = archive["channel_mse"].astype(np.float64)
        zero = archive["channel_zero"].copy()
        quality = archive["image_quality"].astype(np.float64)
        np.testing.assert_array_equal(
            zero, archive["zero_probability"] >= settings["zero_probability_threshold"]
        )
    true_mse = np.array([row["full_channel_squared_errors"] for row in rows], dtype=np.float64)
    true_mse /= np.array([row["pixel_count"] for row in rows])[:, None, None] * 255**2
    true_zero = true_mse == 0
    true_quality = np.array(
        [
            [
                [
                    value[name] if value[name] is not None else np.nan
                    for name in UnityQualityPrediction.QUALITY_NAMES
                ]
                for value in row["image_quality"]
            ]
            for row in rows
        ],
        dtype=np.float64,
    )
    resolver = UnityPredictionAudit(root, config_path)
    policies = [resolver.policy_for(row) for row in rows]
    output, report = Path(config["output"]), Path(config["report"])
    if not output.resolve().is_relative_to(root / "experiment report/.local"):
        raise ValueError("Raw validation decisions belong under experiment report/.local")
    output.mkdir(parents=True, exist_ok=False)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x", encoding="utf-8") as handle:
        handle.write('{"status":"running"}\n')
    variants = {
        "frozen_predictions": (mse, zero, quality),
        "true_channel_mse": (true_mse, zero, quality),
        "true_zero_mask": (mse, true_zero, quality),
        "true_channel_mse_and_zero": (true_mse, true_zero, quality),
        "true_ms_ssim": (
            mse,
            zero,
            np.concatenate([true_quality[:, :, :1], quality[:, :, 1:]], axis=2),
        ),
        "true_angles": (
            mse,
            zero,
            np.concatenate([quality[:, :, :1], true_quality[:, :, 1:]], axis=2),
        ),
        "all_true_metrics": (true_mse, true_zero, true_quality),
    }
    result: JsonDict = {
        "status": "running",
        "config": config,
        "sources_sha256": sources,
        "training_source_binding": source_binding,
        "validation_images": len(rows),
        "training_updates": 0,
        "model_forward_calls": 0,
        "test_opened": False,
        "variants": {},
        "scope": (
            "Frozen validation predictions with one or combined true-quality replacements; "
            "diagnostic conditional effects, no retraining or held-out evaluation"
        ),
    }
    raw = {}
    baseline_decisions: list[JsonDict] = []
    try:
        for name, (variant_mse, variant_zero, variant_quality) in variants.items():
            metrics, decisions = UnityQualityPrediction.score(
                rows, policies, variant_mse, variant_zero, variant_quality
            )
            if name == "frozen_predictions":
                saved = ArtifactStore.read_json(model_output / "best-decisions.json")
                if saved["rows"] != decisions:
                    raise ValueError("Frozen prediction replay differs from saved best decisions")
                baseline_decisions = decisions
                result["residuals"] = residual_metrics(
                    rows, decisions, mse, zero, quality, true_zero
                )
            metrics["groups"] = grouped_metrics(rows, decisions)
            metrics["fixed_error_images"] = sum(
                not old["footprint_match"] and new["footprint_match"]
                for old, new in zip(baseline_decisions, decisions, strict=True)
            )
            metrics["lost_correct_images"] = sum(
                old["footprint_match"] and not new["footprint_match"]
                for old, new in zip(baseline_decisions, decisions, strict=True)
            )
            confusion = metrics["confusion_matrix"]
            for index, label in enumerate(["6x6", "8x8", "10x10", "12x12"]):
                predicted = sum(row[index] for row in confusion)
                metrics["per_class"][label]["precision"] = (
                    confusion[index][index] / predicted if predicted else None
                )
            result["variants"][name] = metrics
            raw[name] = decisions
            print(
                {
                    "variant": name,
                    "accuracy": metrics["accuracy"],
                    "fixed": metrics["fixed_error_images"],
                    "lost": metrics["lost_correct_images"],
                },
                flush=True,
            )
        oracle = result["variants"]["all_true_metrics"]
        if oracle["accuracy"] != 1.0 or oracle["full_choice_accuracy"] != 1.0:
            raise ValueError("Complete true metrics did not reconstruct original choices")
        for path, expected in sources.items():
            if ArtifactStore.sha256_file(Path(path)) != expected:
                raise ValueError(f"Frozen source changed during attribution: {path}")
        decisions_path = output / "decisions.json"
        ArtifactStore.write_json(decisions_path, raw)
        result.update(
            status="passed_smoke" if smoke else "completed",
            policy_origins=resolver.origins,
            decisions=str(decisions_path),
            decisions_sha256=ArtifactStore.sha256_file(decisions_path),
        )
    except BaseException as error:
        result.update(status="failed", error=repr(error))
        raise
    finally:
        result["wall_seconds"] = time.perf_counter() - started
        ArtifactStore.write_json(report, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
