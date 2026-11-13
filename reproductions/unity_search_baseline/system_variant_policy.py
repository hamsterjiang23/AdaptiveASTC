"""Replay adaptive candidate queries using frozen predictions and archived measurements."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction


@dataclass(frozen=True)
class VariantSpec:
    name: str
    mode: str
    start_mode: str = "candidate_idx"
    probe_mode: str = "canonical_block"
    budget: int | None = None
    normal_native: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {"pure", "original", "forward", "bidirectional"}:
            raise ValueError("Unsupported system variant mode")
        if self.start_mode not in {"candidate_idx", "block_start"}:
            raise ValueError("Unsupported prediction start mode")
        if self.probe_mode not in {"canonical_block", "predicted_preset"}:
            raise ValueError("Unsupported coarser-block probe mode")
        if self.budget is not None and (type(self.budget) is not int or self.budget < 0):
            raise ValueError("Encoding budget must be a nonnegative integer or None")


@dataclass(frozen=True)
class VariantOutcome:
    selected_index: int
    measured_indices: tuple[int, ...]
    quality_checked_indices: tuple[int, ...]
    reason: str
    model_used: bool = True
    native_routed: bool = False
    budget_exhausted: bool = False
    needs_prefix_backfill: bool = False


class CandidateQueries:
    def __init__(self, entry: JsonDict, start: int, budget: int | None) -> None:
        self.entry = entry
        self.start = start
        self.budget = budget
        self.indices: list[int] = []
        self.exhausted = False

    def measure(self, index: int) -> bool:
        if index in self.indices:
            return True
        if self.budget is not None and len(self.indices) >= self.budget:
            self.exhausted = True
            return False
        self.indices.append(index)
        return True

    def psnr(self, index: int) -> float:
        if index not in self.indices:
            raise ValueError("Selection attempted to use an unmeasured PSNR")
        return float(np.float32(self.entry["candidates"][index]["metrics"]["psnr"]))

    def strict(self, index: int) -> bool:
        if index not in self.indices:
            raise ValueError("Selection attempted to use an unmeasured quality result")
        return bool(self.entry["strict"][index])

    def outcome(self, selected: int, reason: str) -> VariantOutcome:
        needs_prefix = False
        if reason == "highest_psnr_fallback":
            # Post-selection diagnostic only. These values never change the chosen index.
            needs_prefix = any(
                index not in self.indices
                and float(np.float32(self.entry["candidates"][index]["metrics"]["psnr"]))
                >= self.psnr(selected)
                for index in range(self.start)
            )
        return VariantOutcome(
            selected,
            tuple(self.indices),
            tuple(self.indices),
            reason,
            budget_exhausted=self.exhausted,
            needs_prefix_backfill=needs_prefix,
        )


def forward_search(queries: CandidateQueries) -> VariantOutcome:
    decision = queries.entry["decision"]
    locked: int | None = None
    fallback: int | None = None
    for index in range(queries.start, 20):
        if not queries.measure(index):
            break
        block = index // 5
        if decision.size_first:
            psnr_pass = queries.psnr(index) >= decision.effective_psnr_threshold
            if locked is None and psnr_pass:
                locked = block
            if locked is not None:
                # Preserve the original loop's measured cross-block lookahead.
                if block != locked:
                    break
                if psnr_pass:
                    fallback = index
                    if queries.strict(index):
                        return queries.outcome(index, "size_first_strict")
            continue
        if queries.strict(index):
            return queries.outcome(index, "first_valid")
    if fallback is not None:
        return queries.outcome(fallback, "size_first_relaxed")
    selected = max(queries.indices, key=queries.psnr)
    return queries.outcome(selected, "highest_psnr_fallback")


def preferred_preset(entry: JsonDict, candidates: list[JsonDict], block: int) -> int:
    indices = list(range(block * 5, block * 5 + 5))
    for index in indices:
        if UnityQualityPrediction.strict_quality(
            entry["policy"],
            entry["texture"],
            candidates[index]["metrics"],
            entry["decision"].effective_psnr_threshold,
        ):
            return index
    return max(indices, key=lambda index: float(np.float32(candidates[index]["metrics"]["psnr"])))


def replay_variant(
    entry: JsonDict,
    predicted_candidates: list[JsonDict],
    predicted_index: int,
    spec: VariantSpec,
) -> VariantOutcome:
    if not 0 <= predicted_index < 20 or len(predicted_candidates) != 20:
        raise ValueError("Require a canonical20 prediction and a valid selected index")
    if spec.mode == "original" or spec.normal_native and entry["texture"].normal:
        original = entry["decision"]
        indices = tuple(range(original.candidates_measured))
        return VariantOutcome(
            original.selected_index,
            indices,
            indices,
            original.selection_reason,
            model_used=False,
            native_routed=True,
        )
    if spec.mode == "pure" or spec.budget == 0:
        return VariantOutcome(predicted_index, (predicted_index,), (), "pure_model")
    start = predicted_index if spec.start_mode == "candidate_idx" else predicted_index // 5 * 5
    queries = CandidateQueries(entry, start, spec.budget)
    queries.measure(start)
    if spec.mode == "forward" or not queries.strict(start) or start // 5 == 0:
        return forward_search(queries)
    selected = start
    for block in range(start // 5 - 1, -1, -1):
        candidates = (
            [preferred_preset(entry, predicted_candidates, block)]
            if spec.probe_mode == "predicted_preset"
            else list(range(block * 5, block * 5 + 5))
        )
        coarser: int | None = None
        for index in candidates:
            if not queries.measure(index):
                break
            if queries.strict(index):
                coarser = index
                break
        if coarser is None:
            break
        selected = coarser
    return queries.outcome(selected, "bidirectional_strict")
