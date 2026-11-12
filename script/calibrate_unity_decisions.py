"""Fit validation-only decision margins on hash-bound frozen native predictions."""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.utils.artifacts import ArtifactStore
from script.diagnose_unity_rules import UnityRuleDiagnostics


class UnityDecisionCalibration:
    PARAMETERS = (
        "zero_probability_threshold",
        "psnr_margin_db",
        "ssim_margin_db",
        "mean_angle_margin_deg",
        "p95_angle_margin_deg",
    )

    def __init__(self, config_path: Path) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.config_path = config_path.resolve()
        self.config = ArtifactStore.read_json(config_path)
        self.candidate_cache: dict[float, list[list[JsonDict]]] = {}

    def select(self, parameters: dict[str, float]) -> list[JsonDict]:
        threshold = parameters["zero_probability_threshold"]
        if threshold not in self.candidate_cache:
            zero = self.probability >= threshold
            self.candidate_cache[threshold] = [
                UnityQualityPrediction.candidates(
                    entry["texture"], self.mse[index], zero[index], self.quality[index]
                )
                for index, entry in enumerate(self.entries)
            ]
        decisions = []
        for entry, original in zip(self.entries, self.candidate_cache[threshold], strict=True):
            texture = entry["texture"]
            candidates = []
            for candidate in original:
                metrics = dict(candidate["metrics"])
                metrics["psnr"] -= parameters["psnr_margin_db"]
                if texture.normal:
                    metrics["normal_mean_deg"] += parameters["mean_angle_margin_deg"]
                    metrics["normal_p95_deg"] += parameters["p95_angle_margin_deg"]
                elif texture.srgb:
                    metrics["ms_ssim_db"] -= parameters["ssim_margin_db"]
                candidates.append({**candidate, "metrics": metrics})
            decision = entry["policy"].select(
                candidates,
                width=texture.width,
                height=texture.height,
                srgb=texture.srgb,
                normal=texture.normal,
            )
            decisions.append(asdict(decision))
        return decisions

    def accuracy(self, decisions: list[JsonDict]) -> float:
        return sum(
            decision["block_size"] == entry["decision"].block_size
            for decision, entry in zip(decisions, self.entries, strict=True)
        ) / len(self.entries)

    def run(self) -> JsonDict:
        started = time.perf_counter()
        config = self.config
        grids = config["grids"]
        if (
            set(grids) != set(self.PARAMETERS)
            or type(config["passes"]) is not int
            or config["passes"] < 1
            or type(config["smoke"]) is not bool
        ):
            raise ValueError("Require all five finite parameter grids and a positive pass count")
        for name, values in grids.items():
            if not values or any(
                type(value) not in {int, float} or not math.isfinite(value) for value in values
            ):
                raise ValueError(f"Invalid finite parameter grid: {name}")
        if any(not 0 < value < 1 for value in grids["zero_probability_threshold"]):
            raise ValueError("Zero-channel probability thresholds must lie strictly inside (0,1)")
        attribution_path = Path(config["attribution_report"])
        if ArtifactStore.sha256_file(attribution_path) != config["attribution_report_sha256"]:
            raise ValueError("Frozen attribution report changed")
        attribution = ArtifactStore.read_json(attribution_path)
        if (
            attribution["status"] != ("passed_smoke" if config["smoke"] else "completed")
            or attribution["config"]["smoke"] != config["smoke"]
            or attribution["test_opened"] is not False
        ):
            raise ValueError("Require completed development-only attribution with matching scope")
        sources = {
            **attribution["sources_sha256"],
            str(attribution_path.resolve()): config["attribution_report_sha256"],
            str(self.config_path): ArtifactStore.sha256_file(self.config_path),
            str(Path(__file__).resolve()): ArtifactStore.sha256_file(Path(__file__)),
            str(
                (self.root / "script/diagnose_unity_rules.py").resolve()
            ): ArtifactStore.sha256_file(self.root / "script/diagnose_unity_rules.py"),
            attribution["decisions"]: attribution["decisions_sha256"],
        }
        for path, expected in sources.items():
            if ArtifactStore.sha256_file(Path(path)) != expected:
                raise ValueError(f"Frozen calibration input or source changed: {path}")
        training = ArtifactStore.read_json(Path(attribution["config"]["training_report"]))
        settings = training["config"]
        document = ArtifactStore.read_json(Path(settings["corpus"]) / "corpus.json")
        rows = document["splits"]["validation"]
        if not config["smoke"] and len(rows) != 1000:
            raise ValueError("Formal calibration requires all1000 frozen validation images")
        diagnostics = UnityRuleDiagnostics(self.config_path)
        self.entries = diagnostics.prepare(rows)
        with np.load(
            Path(settings["output"]) / "best-validation.npz", allow_pickle=False
        ) as archive:
            self.mse = archive["channel_mse"].copy()
            self.probability = archive["zero_probability"].copy()
            self.quality = archive["image_quality"].copy()
        parameters = {
            "zero_probability_threshold": settings["zero_probability_threshold"],
            **{name: 0.0 for name in self.PARAMETERS[1:]},
        }
        for name, value in parameters.items():
            if value not in grids[name]:
                raise ValueError("Each grid must include its initial parameter value")
        baseline_decisions = self.select(parameters)
        saved = ArtifactStore.read_json(Path(attribution["decisions"]))["frozen_predictions"]
        if baseline_decisions != [row["predicted_decision"] for row in saved]:
            raise ValueError("Zero-margin decision replay differs from frozen native predictions")
        output, report = Path(config["output"]), Path(config["report"])
        if not output.resolve().is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Raw calibration decisions belong under experiment report/.local")
        output.mkdir(parents=True, exist_ok=False)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as handle:
            handle.write('{"status":"running"}\n')
        best_decisions = baseline_decisions
        best_accuracy = self.accuracy(best_decisions)
        state: JsonDict = {
            "status": "running",
            "config": config,
            "sources_sha256": sources,
            "baseline_accuracy": best_accuracy,
            "validation_images": len(rows),
            "trace": [],
            "training_updates": 0,
            "model_forward_calls": 0,
            "test_opened": False,
            "scope": (
                "Coordinate search over explicit grids using the same validation data; "
                "first-encountered ties; no independent evaluation"
            ),
            "margin_convention": (
                "Positive PSNR/SSIM margins subtract from predicted dB; positive angle margins "
                "add to predicted degrees; candidates are passed to the original native policy"
            ),
        }
        try:
            for pass_index in range(config["passes"]):
                before = best_accuracy
                for name in self.PARAMETERS:
                    chosen = dict(parameters)
                    for value in grids[name]:
                        candidate = {**parameters, name: value}
                        decisions = self.select(candidate)
                        accuracy = self.accuracy(decisions)
                        state["trace"].append(
                            {
                                "pass": pass_index + 1,
                                "parameter": name,
                                "parameters": candidate,
                                "accuracy": accuracy,
                            }
                        )
                        if accuracy > best_accuracy:
                            best_accuracy, best_decisions = accuracy, decisions
                            chosen = candidate
                    parameters = chosen
                    state.update(
                        best_accuracy=best_accuracy,
                        best_parameters=parameters,
                        wall_seconds=time.perf_counter() - started,
                    )
                    ArtifactStore.write_json(report, state)
                    print(
                        {
                            "pass": pass_index + 1,
                            "parameter": name,
                            "best_accuracy": best_accuracy,
                            "parameters": parameters,
                        },
                        flush=True,
                    )
                if best_accuracy == before:
                    break
            for path, expected in sources.items():
                if ArtifactStore.sha256_file(Path(path)) != expected:
                    raise ValueError(f"Frozen source changed during calibration: {path}")
            indices = [decision["selected_index"] for decision in best_decisions]
            baseline_indices = [decision["selected_index"] for decision in baseline_decisions]
            raw_path = output / "decisions.json"
            ArtifactStore.write_json(
                raw_path,
                {
                    "rows": [
                        {"path": row["path"], "decision": decision}
                        for row, decision in zip(rows, best_decisions, strict=True)
                    ]
                },
            )
            state.update(
                status="passed_smoke" if config["smoke"] else "completed",
                baseline_metrics=diagnostics.summarize(self.entries, baseline_indices),
                selected_metrics=diagnostics.summarize(self.entries, indices),
                best_parameters=parameters,
                best_accuracy=best_accuracy,
                decisions=str(raw_path),
                decisions_sha256=ArtifactStore.sha256_file(raw_path),
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            ArtifactStore.write_json(report, state)
        return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    UnityDecisionCalibration(args.config).run()


if __name__ == "__main__":
    main()
