"""Unity search over explicit candidate sets without changing canonical20 identities."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from reproductions.unity_search_baseline.policy import UnitySearchDecision, UnitySearchPolicy
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


@dataclass(frozen=True)
class NativeCandidateSet:
    """A named ordered subset of the existing twenty prediction/measurement slots."""

    name: str = "full20"
    GRID: ClassVar[tuple[tuple[int, str], ...]] = tuple(
        (block, preset) for block in UnityASTCBackend.BLOCKS for preset in UnityASTCBackend.PRESETS
    )

    def __post_init__(self) -> None:
        if self.name not in {"full20", "no_exhaustive16"}:
            raise ValueError("Require full20 or no_exhaustive16 candidate set")
        if self.GRID != tuple(
            (block, preset)
            for block in (12, 10, 8, 6)
            for preset in ("fastest", "fast", "medium", "thorough", "exhaustive")
        ):
            raise ValueError("The V3 candidate identities require the original canonical20 grid")

    @property
    def active_ids(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, (_, preset) in enumerate(self.GRID)
            if self.name == "full20" or preset != "exhaustive"
        )

    @classmethod
    def full20(cls) -> NativeCandidateSet:
        return cls("full20")

    @classmethod
    def no_exhaustive16(cls) -> NativeCandidateSet:
        return cls("no_exhaustive16")

    @classmethod
    def from_name(cls, name: str) -> NativeCandidateSet:
        return cls(name)

    def candidate(self, stable_id: int) -> tuple[int, str]:
        if type(stable_id) is not int or stable_id not in self.active_ids:
            raise ValueError("Candidate must be an active canonical20 integer identity")
        return self.GRID[stable_id]


@dataclass(frozen=True)
class V3SearchResult:
    decision: UnitySearchDecision
    measured_indices: tuple[int, ...]

    @property
    def quality_checked_indices(self) -> tuple[int, ...]:
        return self.measured_indices


class UnityV3Policy:
    """Use one native rule for full replay and real, lazy forward measurements.

    The texture is explicit for every operation. Prediction callers pass properties
    derived from their model input; actual search callers pass the real encoding
    reference's properties. No predicted threshold is carried into actual search.
    """

    def __init__(
        self,
        table: JsonDict | UnitySearchPolicy,
        candidate_set: NativeCandidateSet = NativeCandidateSet(),
    ) -> None:
        if not isinstance(candidate_set, NativeCandidateSet):
            raise ValueError("Require an explicit NativeCandidateSet")
        self.candidate_set = candidate_set
        original = table.table if isinstance(table, UnitySearchPolicy) else table
        self.table = UnitySearchPolicy(dict(original)).table

    @staticmethod
    def validate_texture(texture: UnityTextureInput) -> None:
        if (
            not isinstance(texture, UnityTextureInput)
            or type(texture.width) is not int
            or type(texture.height) is not int
            or min(texture.width, texture.height) < 1
            or any(
                type(flag) is not bool
                for flag in (
                    texture.srgb,
                    texture.normal,
                    texture.need_alpha,
                    texture.alpha_constant,
                )
            )
            or type(texture.black_pixel_ratio) not in {int, float}
            or not math.isfinite(texture.black_pixel_ratio)
            or not 0 <= texture.black_pixel_ratio <= 1
        ):
            raise ValueError("Require positive dimensions, boolean flags and a finite black ratio")

    def effective_threshold(self, texture: UnityTextureInput) -> float:
        self.validate_texture(texture)
        black = float(np.float32(texture.black_pixel_ratio))
        if black > self.table["blackPixelRatioStrong"]:
            return self.table["blackElevatedPsnrStrongDb"]
        if black > self.table["blackPixelRatioMild"]:
            return self.table["blackElevatedPsnrMildDb"]
        return self.table["targetPsnrDb"]

    def _metrics(self, metrics: JsonDict, texture: UnityTextureInput) -> JsonDict:
        keys = ["psnr", "black_pixel_ratio"]
        keys += (
            ["normal_mean_deg", "normal_p95_deg"]
            if texture.normal
            else (["ms_ssim_db"] if texture.srgb else [])
        )
        if not isinstance(metrics, dict) or any(
            type(metrics.get(key)) not in {int, float}
            or not math.isfinite(metrics[key])
            or abs(metrics[key]) > float(np.finfo(np.float32).max)
            for key in keys
        ):
            raise ValueError("Missing or nonfinite applicable native quality")
        values = {key: float(np.float32(metrics[key])) for key in keys}
        if not 0 <= values["black_pixel_ratio"] <= 1 or values["black_pixel_ratio"] != float(
            np.float32(texture.black_pixel_ratio)
        ):
            raise ValueError("Quality black ratio must match this operation's reference texture")
        return values

    def _strict(self, metrics: JsonDict, texture: UnityTextureInput, threshold: float) -> bool:
        if texture.normal:
            return (
                metrics["normal_mean_deg"] <= self.table["targetNormalMeanDeg"]
                and metrics["normal_p95_deg"] <= self.table["targetNormalP95Deg"]
            )
        return metrics["psnr"] >= threshold and (
            not texture.srgb or metrics["ms_ssim_db"] >= self.table["targetMsSsimDb"]
        )

    def strict_quality(self, metrics: JsonDict, texture: UnityTextureInput) -> bool:
        threshold = self.effective_threshold(texture)
        return self._strict(self._metrics(metrics, texture), texture, threshold)

    def select(self, candidates: list[JsonDict], texture: UnityTextureInput) -> UnitySearchDecision:
        """Select a start from active predictions, keeping all twenty output slots."""
        self.validate_texture(texture)
        if (
            not isinstance(candidates, list)
            or len(candidates) != 20
            or any(not isinstance(row, dict) for row in candidates)
            or any(
                type(row.get("block")) is not int or type(row.get("preset")) is not str
                for row in candidates
            )
            or tuple((row.get("block"), row.get("preset")) for row in candidates)
            != self.candidate_set.GRID
        ):
            raise ValueError("Predictions must preserve the full ordered canonical20 grid")
        values = {
            index: self._metrics(candidates[index].get("metrics", {}), texture)
            for index in self.candidate_set.active_ids
        }
        return self.search(values.__getitem__, texture).decision

    def search(
        self,
        measure: Callable[[int], JsonDict],
        texture: UnityTextureInput,
        start: int | None = None,
    ) -> V3SearchResult:
        """Measure each active suffix candidate once, including native lock lookahead."""
        threshold = self.effective_threshold(texture)
        if not callable(measure):
            raise ValueError("Require a candidate measurement callback")
        active = self.candidate_set.active_ids
        if start is None:
            start = active[0]
        self.candidate_set.candidate(start)
        suffix = active[active.index(start) :]
        large = (
            not texture.normal
            and texture.srgb
            and texture.width * texture.height >= self.table["sizeFirstMinSideLarge"] ** 2
        )
        measured: list[int] = []
        values: dict[int, JsonDict] = {}
        locked: int | None = None
        fallback: int | None = None

        def result(index: int, reason: str, early: bool) -> V3SearchResult:
            block, preset = self.candidate_set.candidate(index)
            decision = UnitySearchDecision(
                index,
                f"{block}x{block}",
                preset,
                reason,
                len(measured),
                early,
                self._strict(values[index], texture, threshold),
                threshold,
                large,
            )
            return V3SearchResult(decision, tuple(measured))

        for index in suffix:
            values[index] = self._metrics(measure(index), texture)
            measured.append(index)
            block, _ = self.candidate_set.candidate(index)
            if large:
                psnr_pass = values[index]["psnr"] >= threshold
                if locked is None and psnr_pass:
                    locked = block
                if locked is not None:
                    # The native loop encodes the next block before checking its lock.
                    if block != locked:
                        break
                    if psnr_pass:
                        fallback = index
                        if self._strict(values[index], texture, threshold):
                            return result(index, "size_first_strict", True)
                continue
            if self._strict(values[index], texture, threshold):
                return result(index, "first_valid", True)
        if fallback is not None:
            return result(fallback, "size_first_relaxed", False)
        highest = max(measured, key=lambda index: values[index]["psnr"])
        return result(highest, "highest_psnr_fallback", False)
