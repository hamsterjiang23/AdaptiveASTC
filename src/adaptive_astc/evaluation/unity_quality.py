"""Convert predicted native quality into the original Unity decision and measured outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from numpy.typing import NDArray

from adaptive_astc.config import JsonDict
from reproductions.unity_search_baseline.policy import UnitySearchDecision, UnitySearchPolicy
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


@dataclass(frozen=True)
class UnityTextureInput:
    width: int
    height: int
    srgb: bool
    normal: bool
    need_alpha: bool
    alpha_constant: bool
    black_pixel_ratio: float

    @classmethod
    def from_row(cls, row: JsonDict) -> UnityTextureInput:
        if row["metadata"]["is_hdr"]:
            raise ValueError("Current native model protocol covers LDR references")
        result = cls(
            row["width"],
            row["height"],
            row["import_metadata"]["srgb"],
            row["metadata"]["is_normal"],
            row["metadata"]["need_alpha"],
            row["alpha_constant"],
            row["black_pixel_ratio"],
        )
        if (
            type(result.width) is not int
            or type(result.height) is not int
            or min(result.width, result.height) < 1
            or any(
                type(v) is not bool
                for v in [result.srgb, result.normal, result.need_alpha, result.alpha_constant]
            )
            or not np.isfinite(result.black_pixel_ratio)
            or not 0 <= result.black_pixel_ratio <= 1
        ):
            raise ValueError("Invalid native input metadata")
        return result


class UnityQualityPrediction:
    GRID = [(b, p) for b in UnityASTCBackend.BLOCKS for p in UnityASTCBackend.PRESETS]
    QUALITY_NAMES = ("ms_ssim_db", "normal_mean_deg", "normal_p95_deg")

    @staticmethod
    def aggregate_mse(
        log_mse: NDArray[np.float64],
        pixels: NDArray[np.int64],
        image_ids: NDArray[np.int64],
        image_count: int,
    ) -> NDArray[np.float64]:
        if (
            log_mse.shape != (len(pixels), 20, 4)
            or image_ids.shape != pixels.shape
            or pixels.ndim != 1
            or len(pixels) == 0
            or not np.issubdtype(pixels.dtype, np.integer)
            or not np.issubdtype(image_ids.dtype, np.integer)
            or type(image_count) is not int
            or image_count < 1
            or np.any(pixels <= 0)
            or np.any(image_ids < 0)
            or np.any(image_ids >= image_count)
            or not np.isfinite(log_mse).all()
        ):
            raise ValueError("Require finite20x4 patch predictions and valid image/pixel indexes")
        mse = np.clip(10.0 ** np.clip(log_mse, -10, np.log10(1 + 1e-10)) - 1e-10, 0, 1)
        sums = np.zeros((image_count, 20, 4), dtype=np.float64)
        np.add.at(sums, image_ids, mse * pixels[:, None, None])
        totals = np.bincount(image_ids, weights=pixels, minlength=image_count)
        if np.any(totals <= 0):
            raise ValueError("Every evaluated image requires complete predicted patch coverage")
        return sums / totals[:, None, None]

    @staticmethod
    def psnr(
        channel_mse: NDArray[np.float64],
        channel_zero: NDArray[np.bool_],
        texture: UnityTextureInput,
    ) -> NDArray[np.float64]:
        if (
            channel_mse.shape != (20, 4)
            or channel_zero.shape != channel_mse.shape
            or channel_zero.dtype != np.bool_
            or not np.isfinite(channel_mse).all()
            or np.any(channel_mse < 0)
            or np.any(channel_mse > 1)
        ):
            raise ValueError("Require normalized finite20x4 MSE and explicit predicted zero mask")
        # Unity applies 1e-10 in BYTE MSE units, then averages participating channels.
        mask = (~channel_zero) & (channel_mse * 255**2 > 1e-10)
        mask[:, 3] &= texture.need_alpha and not texture.alpha_constant
        count = mask.sum(axis=1)
        average = (channel_mse * mask).sum(axis=1) / np.maximum(count, 1)
        psnr = np.full(20, 100.0, dtype=np.float64)
        valid = count > 0
        psnr[valid] = -10 * np.log10(average[valid])
        return psnr

    @classmethod
    def candidates(
        cls,
        texture: UnityTextureInput,
        channel_mse: NDArray[np.float64],
        channel_zero: NDArray[np.bool_],
        image_quality: NDArray[np.float64],
    ) -> list[JsonDict]:
        if image_quality.shape != (20, 3):
            raise ValueError("Require20 image-level SSIM/mean-angle/p95-angle predictions")
        active = [1, 2] if texture.normal else ([0] if texture.srgb else [])
        if not np.isfinite(image_quality[:, active]).all():
            raise ValueError("Missing applicable image-level quality prediction")
        psnr = cls.psnr(channel_mse, channel_zero, texture)
        return [
            {
                "block": block,
                "preset": preset,
                "metrics": {
                    "psnr": float(psnr[index]),
                    "black_pixel_ratio": texture.black_pixel_ratio,
                    **{
                        name: float(image_quality[index, column]) if column in active else None
                        for column, name in enumerate(cls.QUALITY_NAMES)
                    },
                },
            }
            for index, (block, preset) in enumerate(cls.GRID)
        ]

    @classmethod
    def select(
        cls,
        policy: UnitySearchPolicy,
        texture: UnityTextureInput,
        channel_mse: NDArray[np.float64],
        channel_zero: NDArray[np.bool_],
        image_quality: NDArray[np.float64],
    ) -> UnitySearchDecision:
        return policy.select(
            cls.candidates(texture, channel_mse, channel_zero, image_quality),
            width=texture.width,
            height=texture.height,
            srgb=texture.srgb,
            normal=texture.normal,
        )

    @staticmethod
    def strict_quality(
        policy: UnitySearchPolicy,
        texture: UnityTextureInput,
        quality: JsonDict,
        threshold: float,
    ) -> bool:
        if texture.normal:
            return bool(
                np.float32(quality["normal_mean_deg"]) <= policy.table["targetNormalMeanDeg"]
                and np.float32(quality["normal_p95_deg"]) <= policy.table["targetNormalP95Deg"]
            )
        return bool(
            np.float32(quality["psnr"]) >= threshold
            and (
                not texture.srgb
                or np.float32(quality["ms_ssim_db"]) >= policy.table["targetMsSsimDb"]
            )
        )

    @classmethod
    def score(
        cls,
        rows: list[JsonDict],
        policies: list[UnitySearchPolicy],
        channel_mse: NDArray[np.float64],
        channel_zero: NDArray[np.bool_],
        image_quality: NDArray[np.float64],
    ) -> tuple[JsonDict, list[JsonDict]]:
        count = len(rows)
        if (
            not count
            or len(policies) != count
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
                policy, texture, channel_mse[i], channel_zero[i], image_quality[i]
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
            psnr = cls.psnr(channel_mse[i], channel_zero[i], texture)
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
                "Original Unity decision agreement; measured selected quality and actual payload; "
                "no encoding timing"
            ),
        }
        return result, observations
