"""Scalar temperature fitting and checkpoint-bound calibration."""

import math
from pathlib import Path

import torch
from torch import Tensor

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.inference import Predictor
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.checkpoints import CheckpointStore


class TemperatureCalibrator:
    """Fit positive scalar temperature on the independent calibration split."""

    def __init__(
        self, run_dir: Path, report_dir: Path, initialization: str, workers: int = 2
    ) -> None:
        self.run_dir = run_dir
        self.report_dir = report_dir
        self.initialization = initialization
        self.predictor = Predictor(run_dir, workers)

    @staticmethod
    def fit(logits: Tensor, labels: Tensor) -> JsonDict:
        # Inference-mode tensors must be cloned before the autograd-based temperature fit.
        scores = logits.detach().cpu().double().clone()
        truth = labels.detach().cpu().long().clone()
        initial = float(torch.nn.functional.cross_entropy(scores, truth))
        log_temperature = torch.zeros((), dtype=torch.float64, requires_grad=True)
        optimizer = torch.optim.LBFGS(
            [log_temperature],
            lr=1.0,
            max_iter=100,
            tolerance_grad=1e-9,
            tolerance_change=1e-12,
            line_search_fn="strong_wolfe",
        )
        history: list[JsonDict] = []

        def closure() -> Tensor:
            optimizer.zero_grad()
            temperature = log_temperature.exp()
            loss = torch.nn.functional.cross_entropy(scores / temperature, truth)
            if not torch.isfinite(loss) or not torch.isfinite(temperature) or temperature <= 0:
                raise ValueError("Non-finite temperature fit")
            loss.backward()
            history.append(
                {"temperature": float(temperature.detach()), "nll": float(loss.detach())}
            )
            return loss

        status = "fitted"
        error_text: str | None = None
        try:
            optimizer.step(closure)
            temperature = float(log_temperature.detach().exp())
            fitted = float(torch.nn.functional.cross_entropy(scores / temperature, truth))
            if not math.isfinite(temperature) or temperature <= 0 or not math.isfinite(fitted):
                raise ValueError("Invalid fitted value")
            if fitted >= initial:
                temperature, fitted, status = 1.0, initial, "no_improvement"
        except (ValueError, RuntimeError) as error:
            temperature, fitted, status = 1.0, initial, "failed"
            error_text = str(error)
        state = optimizer.state.get(log_temperature, {})
        return {
            "temperature": temperature,
            "status": status,
            "error": error_text,
            "initial_nll": initial,
            "fitted_nll": fitted,
            "history": history,
            "optimizer_iterations": int(state.get("n_iter", 0)),
            "gradient_abs": float(log_temperature.grad.abs())
            if log_temperature.grad is not None
            else None,
            "max_iterations": 100,
        }

    def run(self) -> JsonDict:
        if (self.run_dir / "test_seal.json").exists():
            raise ValueError("Test already opened; calibration is frozen")
        CheckpointStore.require_completed(
            self.run_dir,
            self.initialization,
            ArtifactStore.read_json(self.run_dir / "manifest.json"),
        )
        logits, labels, information = self.predictor.from_checkpoint(
            self.initialization, "calibration"
        )
        fitted = self.fit(logits, labels)
        result = {
            **fitted,
            **information,
            "initialization": self.initialization,
            "scope": "calibration_fit_metrics_only",
        }
        ArtifactStore.write_json(self.run_dir / self.initialization / "temperature.json", result)
        ArtifactStore.write_json(
            self.report_dir / f"{self.initialization}_calibration.json", result
        )
        print(
            f"calibrated {self.initialization} T={result['temperature']:.6f} "
            f"status={result['status']}",
            flush=True,
        )
        return result
