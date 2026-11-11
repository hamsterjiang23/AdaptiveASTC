"""Replay the RDO-off Unity search decision from measured or predicted quality."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from adaptive_astc.config import JsonDict
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


@dataclass(frozen=True)
class UnitySearchDecision:
    selected_index: int
    block_size: str
    preset: str
    selection_reason: str
    candidates_measured: int
    early_exit: bool
    strict_quality_met: bool
    effective_psnr_threshold: float
    size_first: bool


class UnitySearchPolicy:
    """Source order and early stops are part of the label, including relaxed winners."""

    def __init__(self, table: JsonDict) -> None:
        if (
            table["schemaVersion"] != 2
            or table["astcOptimizerEnabled"] is not True
            or table["rdoGlobalEnabled"] is not False
        ):
            raise ValueError("Replay requires optimizer schema2 with RDO disabled")
        keys = [
            "targetPsnrDb",
            "targetMsSsimDb",
            "targetNormalMeanDeg",
            "targetNormalP95Deg",
            "blackPixelRatioMild",
            "blackPixelRatioStrong",
            "blackElevatedPsnrMildDb",
            "blackElevatedPsnrStrongDb",
        ]
        if any(
            type(table[key]) not in {int, float} or not math.isfinite(table[key]) for key in keys
        ):
            raise ValueError("Native policy thresholds must be finite numbers")
        if not 0 <= table["blackPixelRatioMild"] <= table["blackPixelRatioStrong"] <= 1:
            raise ValueError("Invalid pure-black ratio thresholds")
        if type(table["sizeFirstMinSideLarge"]) is not int or table["sizeFirstMinSideLarge"] < 1:
            raise ValueError("Positive size-first side threshold required")
        self.table = {**table, **{key: float(np.float32(table[key])) for key in keys}}

    def select(
        self, candidates: list[JsonDict], *, width: int, height: int, srgb: bool, normal: bool
    ) -> UnitySearchDecision:
        if (
            type(width) is not int
            or type(height) is not int
            or min(width, height) < 1
            or type(srgb) is not bool
            or type(normal) is not bool
        ):
            raise ValueError("Positive integer dimensions and boolean texture flags required")
        expected = [
            (block, preset)
            for block in UnityASTCBackend.BLOCKS
            for preset in UnityASTCBackend.PRESETS
        ]
        if [(row["block"], row["preset"]) for row in candidates] != expected:
            raise ValueError("Require the full canonical20 candidate grid")
        values: list[JsonDict] = []
        for candidate in candidates:
            metrics = candidate["metrics"]
            keys = ["psnr", "black_pixel_ratio"]
            keys += (
                ["normal_mean_deg", "normal_p95_deg"]
                if normal
                else (["ms_ssim_db"] if srgb else [])
            )
            if any(
                type(metrics[key]) not in {int, float} or not math.isfinite(metrics[key])
                for key in keys
            ):
                raise ValueError("Missing or nonfinite native quality")
            values.append({key: float(np.float32(metrics[key])) for key in keys})
        black = values[0]["black_pixel_ratio"]
        if not 0 <= black <= 1 or any(row["black_pixel_ratio"] != black for row in values):
            raise ValueError("Pure-black ratio must be identical for the same reference")
        threshold = self.table["targetPsnrDb"]
        if black > self.table["blackPixelRatioStrong"]:
            threshold = self.table["blackElevatedPsnrStrongDb"]
        elif black > self.table["blackPixelRatioMild"]:
            threshold = self.table["blackElevatedPsnrMildDb"]
        large = not normal and srgb and width * height >= self.table["sizeFirstMinSideLarge"] ** 2
        locked: int | None = None
        fallback: int | None = None
        measured = 0

        def strict(index: int) -> bool:
            metrics = values[index]
            if normal:
                return (
                    metrics["normal_mean_deg"] <= self.table["targetNormalMeanDeg"]
                    and metrics["normal_p95_deg"] <= self.table["targetNormalP95Deg"]
                )
            return metrics["psnr"] >= threshold and (
                not srgb or metrics["ms_ssim_db"] >= self.table["targetMsSsimDb"]
            )

        def decision(index: int, reason: str, early: bool) -> UnitySearchDecision:
            return UnitySearchDecision(
                index,
                f"{candidates[index]['block']}x{candidates[index]['block']}",
                candidates[index]["preset"],
                reason,
                measured,
                early,
                strict(index),
                threshold,
                large,
            )

        for index, candidate in enumerate(candidates):
            # The C++ loop measures and appends the next block before checking the lock.
            measured = index + 1
            if large:
                psnr_pass = values[index]["psnr"] >= threshold
                if locked is None and psnr_pass:
                    locked = candidate["block"]
                if locked is not None:
                    if candidate["block"] != locked:
                        break
                    if psnr_pass:
                        fallback = index
                        if strict(index):
                            return decision(index, "size_first_strict", True)
                continue
            # bestResult starts invalid and the first accepted candidate immediately breaks.
            if strict(index):
                return decision(index, "first_valid", True)
        if fallback is not None:
            return decision(fallback, "size_first_relaxed", False)
        highest = max(range(measured), key=lambda index: values[index]["psnr"])
        return decision(highest, "highest_psnr_fallback", False)
