"""Measure Unity rule baselines and train-only Gaussian quality perturbations."""

from __future__ import annotations

import argparse
import math
import random
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.prediction_audit import UnityPredictionAudit


class UnityRuleDiagnostics:
    def __init__(self, config_path: Path) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.config_path = config_path.resolve()
        self.config = ArtifactStore.read_json(config_path)
        self.resolver = UnityPredictionAudit(self.root, self.config_path)

    def prepare(self, rows: list[JsonDict]) -> list[JsonDict]:
        entries = []
        for row in rows:
            policy = self.resolver.policy_for(row)
            texture = UnityTextureInput.from_row(row)
            candidates = [
                {"block": block, "preset": preset, "metrics": dict(quality)}
                for (block, preset), quality in zip(
                    UnityQualityPrediction.GRID, row["image_quality"], strict=True
                )
            ]
            decision = policy.select(
                candidates,
                width=texture.width,
                height=texture.height,
                srgb=texture.srgb,
                normal=texture.normal,
            )
            for field in ["block_size", "preset", "selection_reason", "candidates_measured"]:
                if asdict(decision)[field] != row["original_selection"][field]:
                    raise ValueError(f"Measured native rule differs at {row['path']}: {field}")
            entries.append(
                {
                    "row": row,
                    "policy": policy,
                    "texture": texture,
                    "candidates": candidates,
                    "decision": decision,
                    "strict": [
                        UnityQualityPrediction.strict_quality(
                            policy, texture, quality, decision.effective_psnr_threshold
                        )
                        for quality in row["image_quality"]
                    ],
                }
            )
        return entries

    @staticmethod
    def summarize(entries: list[JsonDict], selections: list[int]) -> JsonDict:
        count = len(entries)
        matches = full = passed = regressions = larger = smaller = 0
        selected_bytes = original_bytes = fixed8_bytes = 0
        for entry, index in zip(entries, selections, strict=True):
            row, original = entry["row"], entry["decision"].selected_index
            block = UnityQualityPrediction.GRID[index][0]
            original_block = UnityQualityPrediction.GRID[original][0]
            matches += block == original_block
            full += index == original
            passed += entry["strict"][index]
            regressions += entry["strict"][original] and not entry["strict"][index]
            larger += block > original_block
            smaller += block < original_block
            selected_bytes += row["payload_bytes"][index]
            original_bytes += row["payload_bytes"][original]
            fixed8_bytes += row["payload_bytes"][12]
        return {
            "images": count,
            "accuracy": matches / count,
            "full_choice_accuracy": full / count,
            "actual_strict_quality_pass_rate": passed / count,
            "quality_regression_images": regressions,
            "larger_block_images": larger,
            "smaller_block_images": smaller,
            "payload_bytes": selected_bytes,
            "original_payload_bytes": original_bytes,
            "fixed8_medium_payload_bytes": fixed8_bytes,
            "payload_ratio_to_original": selected_bytes / original_bytes,
            "payload_ratio_to_fixed8": selected_bytes / fixed8_bytes,
        }

    def baselines(self, entries: list[JsonDict]) -> JsonDict:
        choices = {
            f"fixed{block}_medium": [UnityQualityPrediction.GRID.index((block, "medium"))]
            * len(entries)
            for block in [6, 8, 10, 12]
        }
        choices["always12_fastest"] = [0] * len(entries)
        choices["original_rule_measured"] = [e["decision"].selected_index for e in entries]
        psnr_only = []
        for entry in entries:
            texture = entry["texture"]
            # Keep native ordering and fallback while disabling the non-PSNR branches.
            decision = entry["policy"].select(
                entry["candidates"],
                width=texture.width,
                height=texture.height,
                srgb=False,
                normal=False,
            )
            psnr_only.append(decision.selected_index)
        choices["psnr_only"] = psnr_only
        return {name: self.summarize(entries, indices) for name, indices in choices.items()}

    @staticmethod
    def applicable(entry: JsonDict, mode: str) -> bool:
        texture = entry["texture"]
        return (
            mode in {"psnr", "all"}
            or (mode == "angles" and texture.normal)
            or (mode == "ms_ssim" and texture.srgb and not texture.normal)
        )

    def perturb(self, entries: list[JsonDict], mode: str, sigma: float, seed: int) -> JsonDict:
        rng = random.Random(seed)
        selections = []
        active_entries, active_selections = [], []
        squared = dict.fromkeys(UnityQualityPrediction.QUALITY_NAMES + ("psnr",), 0.0)
        samples = dict.fromkeys(squared, 0)
        for entry in entries:
            texture = entry["texture"]
            keys = []
            if mode in {"psnr", "all"}:
                keys.append("psnr")
            if mode in {"ms_ssim", "all"} and texture.srgb and not texture.normal:
                keys.append("ms_ssim_db")
            if mode in {"angles", "all"} and texture.normal:
                keys.extend(["normal_mean_deg", "normal_p95_deg"])
            candidates = []
            for candidate in entry["candidates"]:
                metrics = dict(candidate["metrics"])
                for key in keys:
                    error = sigma * rng.gauss(0.0, 1.0)
                    metrics[key] += error
                    squared[key] += error**2
                    samples[key] += 1
                candidates.append({**candidate, "metrics": metrics})
            selected = (
                entry["policy"]
                .select(
                    candidates,
                    width=texture.width,
                    height=texture.height,
                    srgb=texture.srgb,
                    normal=texture.normal,
                )
                .selected_index
            )
            if sigma == 0 and selected != entry["decision"].selected_index:
                raise ValueError("Zero-noise control changed the original native choice")
            selections.append(selected)
            if self.applicable(entry, mode):
                active_entries.append(entry)
                active_selections.append(selected)
        return {
            "seed": seed,
            "all_images": self.summarize(entries, selections),
            "applicable_images": self.summarize(active_entries, active_selections)
            if active_entries
            else None,
            "injected_rmse": {
                key: math.sqrt(squared[key] / count) if count else None
                for key, count in samples.items()
            },
        }

    def run(self) -> JsonDict:
        started = time.perf_counter()
        config = self.config
        corpus = Path(config["corpus"])
        corpus_path = corpus / "corpus.json"
        if ArtifactStore.sha256_file(corpus_path) != config["corpus_sha256"]:
            raise ValueError("V2 development corpus changed")
        document = ArtifactStore.read_json(corpus_path)
        if set(document["splits"]) != {"train", "validation"} or document["test_opened"]:
            raise ValueError("Diagnostics require development splits only")
        if not config["smoke"] and (
            document["coverage"] != "complete"
            or document["counts"] != {"train": 10000, "validation": 1000}
        ):
            raise ValueError("Full diagnostics require train10000/validation1000")
        sigmas, seeds = config["sigmas"], config["seeds"]
        if (
            not sigmas
            or sigmas[0] != 0
            or any(not math.isfinite(sigma) or sigma < 0 for sigma in sigmas)
            or sigmas != sorted(set(sigmas))
            or not seeds
            or any(type(seed) is not int for seed in seeds)
        ):
            raise ValueError("Require increasing finite noise levels beginning at zero and seeds")
        output, report = Path(config["output"]), Path(config["report"])
        if not output.resolve().is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Raw diagnostics belong under experiment report/.local")
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as handle:
            handle.write('{"status":"preparing"}\n')
        source_paths = [
            Path(__file__),
            self.root / "reproductions/unity_search_baseline/prediction_audit.py",
            self.root / "reproductions/unity_search_baseline/policy.py",
            self.root / "reproductions/unity_search_baseline/policy_audit.py",
            self.root / "src/adaptive_astc/evaluation/unity_quality.py",
            self.config_path,
            corpus_path,
        ]
        sources = {str(path.resolve()): ArtifactStore.sha256_file(path) for path in source_paths}
        state: JsonDict = {
            "status": "running",
            "config": config,
            "sources_sha256": sources,
            "training_updates": 0,
            "model_forward_calls": 0,
            "test_opened": False,
            "noise_scope": (
                "Independent zero-mean Gaussian candidate errors in native dB/degrees, "
                "unclipped; all mode uses the same numerical sigma for each applicable metric. "
                "Common random numbers across sigma levels within each mode/seed. "
                "Simulation precision references are conditional on this noise model."
            ),
            "noise_split": "train",
            "baselines_split": "validation",
            "curves": {},
        }
        try:
            validation = self.prepare(document["splits"]["validation"])
            state["validation_baselines"] = self.baselines(validation)
            train = self.prepare(document["splits"]["train"])
            state["counts"] = {"train": len(train), "validation": len(validation)}
            state["exact_four_field_replay_mismatches"] = 0
            for mode in ["psnr", "ms_ssim", "angles", "all"]:
                curve = []
                for sigma in sigmas:
                    trials = [self.perturb(train, mode, sigma, seed) for seed in seeds]
                    curve.append(
                        {
                            "sigma": sigma,
                            "mean_accuracy": statistics.mean(
                                trial["all_images"]["accuracy"] for trial in trials
                            ),
                            "trials": trials,
                        }
                    )
                    state["curves"][mode] = curve
                    state["wall_seconds"] = time.perf_counter() - started
                    ArtifactStore.write_json(report, state)
                    print(
                        {"mode": mode, "sigma": sigma, "accuracy": curve[-1]["mean_accuracy"]},
                        flush=True,
                    )
            state["policy_origins"] = self.resolver.origins
            for path, expected in sources.items():
                if ArtifactStore.sha256_file(Path(path)) != expected:
                    raise ValueError(f"Diagnostic source changed during execution: {path}")
            state["status"] = "passed_smoke" if config["smoke"] else "completed"
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            receipt = output / "receipt.json"
            ArtifactStore.write_json(receipt, state)
            state.update(
                raw_receipt=str(receipt), raw_receipt_sha256=ArtifactStore.sha256_file(receipt)
            )
            ArtifactStore.write_json(report, state)
        return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityRuleDiagnostics(args.config).run()
    print({key: result[key] for key in ["status", "counts", "wall_seconds"]}, flush=True)


if __name__ == "__main__":
    main()
