"""Frozen-model V4 start calibration, exhaustive probes and bounded block rescue."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from reproductions.unity_search_baseline.policy import UnitySearchDecision
from reproductions.unity_search_baseline.v3_policy import UnityV3Policy


@dataclass(frozen=True)
class V4Options:
    start_mode: str = "original"
    psnr_margin_db: float = 0.0
    ms_ssim_margin_db: float = 0.0
    remove_lookahead: bool = False
    gate_margin_db: float | None = None
    unlock: bool = False

    def __post_init__(self) -> None:
        if self.start_mode not in {
            "original",
            "back_one",
            "back_two",
            "same_block_fastest",
            "margin",
        }:
            raise ValueError("Unknown V4 start mode")
        for value in [self.psnr_margin_db, self.ms_ssim_margin_db, self.gate_margin_db]:
            if value is not None and (
                type(value) not in {int, float} or not math.isfinite(value) or value < 0
            ):
                raise ValueError("V4 margins must be finite nonnegative numbers")
        if any(type(value) is not bool for value in [self.remove_lookahead, self.unlock]):
            raise ValueError("V4 switches require explicit booleans")
        if self.start_mode != "margin" and (self.psnr_margin_db or self.ms_ssim_margin_db):
            raise ValueError("Prediction margins require margin start mode")


@dataclass(frozen=True)
class V4SearchResult:
    decision: UnitySearchDecision
    measured_indices: tuple[int, ...]
    original_start: int
    adjusted_start: int
    gate_events: tuple[JsonDict, ...]
    unlock_event: JsonDict | None

    def record(self) -> JsonDict:
        return {
            **asdict(self.decision),
            "measured_indices": list(self.measured_indices),
            "original_start": self.original_start,
            "adjusted_start": self.adjusted_start,
            "gate_events": list(self.gate_events),
            "unlock_event": self.unlock_event,
        }


class UnityV4Policy:
    def __init__(self, base: UnityV3Policy, options: V4Options) -> None:
        if base.candidate_set.name != "full20":
            raise ValueError("V4 uses the complete canonical20 candidate set")
        self.base, self.options = base, options

    def start(self, candidates: list[JsonDict], texture: UnityTextureInput) -> tuple[int, int]:
        original = self.base.select(candidates, texture).selected_index
        mode = self.options.start_mode
        if mode == "margin":
            adjusted = []
            for row in candidates:
                metrics = dict(row["metrics"])
                if not texture.normal:
                    metrics["psnr"] += self.options.psnr_margin_db
                    if texture.srgb:
                        metrics["ms_ssim_db"] += self.options.ms_ssim_margin_db
                adjusted.append({**row, "metrics": metrics})
            return original, self.base.select(adjusted, texture).selected_index
        if mode == "same_block_fastest":
            return original, original - original % 5
        shift = {"original": 0, "back_one": 1, "back_two": 2}[mode]
        return original, max(0, original - shift)

    @staticmethod
    def payload(texture: UnityTextureInput, block: int) -> int:
        return ((texture.width + block - 1) // block) * ((texture.height + block - 1) // block) * 16

    def search(
        self,
        measure: Callable[[int], JsonDict],
        texture: UnityTextureInput,
        candidates: list[JsonDict],
        *,
        prediction_texture: UnityTextureInput | None = None,
    ) -> V4SearchResult:
        original, start = self.start(candidates, prediction_texture or texture)
        threshold = self.base.effective_threshold(texture)
        large = (
            texture.srgb
            and not texture.normal
            and texture.width * texture.height >= self.base.table["sizeFirstMinSideLarge"] ** 2
        )
        values: dict[int, JsonDict] = {}
        measured: list[int] = []
        gates: list[JsonDict] = []
        locked: int | None = None
        fallback: int | None = None

        def query(index: int) -> JsonDict:
            if index not in values:
                values[index] = self.base._metrics(measure(index), texture)
                measured.append(index)
            return values[index]

        def strict(index: int) -> bool:
            return self.base._strict(values[index], texture, threshold)

        def decision(index: int, reason: str, early: bool) -> UnitySearchDecision:
            block, preset = self.base.candidate_set.candidate(index)
            return UnitySearchDecision(
                index,
                f"{block}x{block}",
                preset,
                reason,
                len(measured),
                early,
                strict(index),
                threshold,
                large,
            )

        selected: UnitySearchDecision | None = None
        for index in range(start, 20):
            block, preset = self.base.candidate_set.candidate(index)
            if large and locked is not None and block != locked and self.options.remove_lookahead:
                break
            gate_margin = self.options.gate_margin_db
            if (
                large
                and preset == "exhaustive"
                and gate_margin is not None
                and (locked is None or block == locked)
                and candidates[index]["metrics"]["ms_ssim_db"]
                < self.base.table["targetMsSsimDb"] - gate_margin
            ):
                probe = index - 1
                cached = probe in values
                metrics = query(probe)
                psnr_pass = metrics["psnr"] >= threshold
                gates.append(
                    {
                        "candidate": index,
                        "probe": probe,
                        "probe_cached": cached,
                        "predicted_ms_ssim_db": candidates[index]["metrics"]["ms_ssim_db"],
                        "margin_db": gate_margin,
                        "skipped": psnr_pass,
                        "probe_strict_pass": strict(probe),
                    }
                )
                if psnr_pass:
                    selected = decision(
                        probe, "size_first_strict" if strict(probe) else "size_first_relaxed", True
                    )
                    break
            metrics = query(index)
            if large:
                psnr_pass = metrics["psnr"] >= threshold
                if locked is None and psnr_pass:
                    locked = block
                if locked is not None:
                    if block != locked:
                        break
                    if psnr_pass:
                        fallback = index
                        if strict(index):
                            selected = decision(index, "size_first_strict", True)
                            break
            elif strict(index):
                selected = decision(index, "first_valid", True)
                break
        if selected is None:
            if fallback is not None:
                selected = decision(fallback, "size_first_relaxed", False)
            else:
                highest = max(measured, key=lambda index: values[index]["psnr"])
                selected = decision(highest, "highest_psnr_fallback", False)

        unlock_event = None
        if self.options.unlock and selected.selection_reason == "size_first_relaxed":
            before = selected
            block = self.base.candidate_set.candidate(before.selected_index)[0]
            next_block = {12: 10, 10: 8, 8: 6}.get(block)
            locked_bytes = self.payload(texture, block)
            proposed_bytes = self.payload(texture, next_block) if next_block is not None else None
            permitted = proposed_bytes is not None and 2 * proposed_bytes <= 3 * locked_bytes
            unlock_event = {
                "before_index": before.selected_index,
                "before_payload_bytes": locked_bytes,
                "next_block": next_block,
                "proposed_payload_bytes": proposed_bytes,
                "budget_permitted": permitted,
                "replaced": False,
                "rescue_queries": [],
            }
            if permitted:
                first = before.selected_index - before.selected_index % 5 + 5
                for index in range(first, first + 5):
                    query(index)
                    unlock_event["rescue_queries"].append(index)
                    if strict(index):
                        selected = decision(index, "bounded_unlock_strict", True)
                        unlock_event["replaced"] = True
                        break
            if not unlock_event["replaced"]:
                selected = decision(
                    before.selected_index, before.selection_reason, before.early_exit
                )
        return V4SearchResult(
            selected, tuple(measured), original, start, tuple(gates), unlock_event
        )
