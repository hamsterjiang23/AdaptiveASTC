"""Image-level decision and regression diagnostics from normalized candidate MSE."""

import numpy as np
import torch

from adaptive_astc.config import CLASSES, JsonDict
from adaptive_astc.data.patch_targets import PatchErrorGrid
from adaptive_astc.evaluation.metrics import ClassificationMetrics


class PatchRegressionMetrics:
    @staticmethod
    def compute(mse: np.ndarray, rows: list[JsonDict]) -> tuple[JsonDict, np.ndarray]:
        if mse.shape != (len(rows), 4) or not np.isfinite(mse).all() or (mse < 0).any():
            raise ValueError("Four finite nonnegative image MSE predictions required")
        psnr = PatchErrorGrid.psnr(mse)
        diagnostic_psnr = np.where(mse == 0, 300.0, psnr)
        truth_mse = np.array([row["full_squared_errors"] for row in rows], dtype=np.float64)
        truth_mse /= np.array([row["pixel_count"] for row in rows])[:, None] * 3 * 255**2
        truth_psnr = PatchErrorGrid.psnr(truth_mse)
        labels = np.array([row["class_id"] for row in rows])
        chosen = PatchErrorGrid.choose(psnr)
        # Hard decisions have no classification NLL. Reuse only confusion/recall metrics.
        logits = torch.nn.functional.one_hot(torch.from_numpy(chosen), 4).float()
        all_metrics = ClassificationMetrics.compute(logits, torch.from_numpy(labels))
        metrics = {
            key: all_metrics[key]
            for key in [
                "count",
                "accuracy",
                "macro_f1",
                "balanced_accuracy",
                "confusion_matrix",
                "per_class",
            ]
        }
        near = np.abs(truth_psnr - 35) <= 3
        near_rmse = (
            float(np.sqrt(np.square(diagnostic_psnr[near] - truth_psnr[near]).mean()))
            if near.any()
            else None
        )
        quality_pass = truth_psnr[np.arange(len(chosen)), chosen] > 35
        payload = np.array([row["payload_bytes"] for row in rows])
        finite = np.isfinite(truth_psnr)
        margins = []
        for margin in [0.0, 0.25, 0.5, 0.75, 1.0]:
            selected = PatchErrorGrid.choose(psnr, margin)
            margins.append(
                {
                    "margin_db": margin,
                    "accuracy": float((selected == labels).mean()),
                    "quality_pass_rate": float(
                        (truth_psnr[np.arange(len(selected)), selected] > 35).mean()
                    ),
                    "payload_bytes": int(payload[np.arange(len(selected)), selected].sum()),
                }
            )
        groups = np.array([row["group"] for row in rows])
        group_metrics = {
            str(group): {
                "count": int((groups == group).sum()),
                "accuracy": float((chosen[groups == group] == labels[groups == group]).mean()),
            }
            for group in np.unique(groups)
        }
        long_sides = np.array([max(row["width"], row["height"]) for row in rows])
        size_metrics = {}
        for name, mask in [
            ("at_most256", long_sides <= 256),
            ("257_to1023", (long_sides > 256) & (long_sides < 1024)),
            ("at_least1024", long_sides >= 1024),
        ]:
            size_metrics[name] = {
                "count": int(mask.sum()),
                "accuracy": float((chosen[mask] == labels[mask]).mean()) if mask.any() else None,
            }
        metrics.update(
            {
                "near_threshold_rmse_db": near_rmse,
                "near_threshold_evaluable": bool(near.any()),
                "zero_predicted_mse_candidates": int((mse == 0).sum()),
                "zero_mse_diagnostic_psnr_db": 300.0,
                "near_threshold_candidate_count": int(near.sum()),
                "finite_candidate_rmse_db": float(
                    np.sqrt(np.square(diagnostic_psnr[finite] - truth_psnr[finite]).mean())
                )
                if finite.any()
                else None,
                "lossless_candidate_count": int((~finite).sum()),
                "quality_pass_rate": float(quality_pass.mean()),
                "payload_bytes": int(payload[np.arange(len(chosen)), chosen].sum()),
                "fixed8_payload_bytes": int(payload[:, 1].sum()),
                "label_payload_bytes": int(payload[np.arange(len(labels)), labels].sum()),
                "margins": margins,
                "by_asset_group": group_metrics,
                "group_macro_accuracy": float(
                    np.mean([row["accuracy"] for row in group_metrics.values()])
                ),
                "by_long_side": size_metrics,
                "classes": list(CLASSES),
            }
        )
        return metrics, psnr
