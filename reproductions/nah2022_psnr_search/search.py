"""The directional search in Nah 2022 Table 1, independent of encoder transport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

FOOTPRINTS = (
    (4, 4),
    (5, 4),
    (5, 5),
    (6, 5),
    (6, 6),
    (8, 5),
    (8, 6),
    (10, 5),
    (10, 6),
    (8, 8),
    (10, 8),
    (10, 10),
    (12, 10),
    (12, 12),
)


class QualityProbe(Protocol):
    def __call__(self, footprint: tuple[int, int], /) -> float: ...


@dataclass(frozen=True)
class SearchResult:
    footprint: tuple[int, int]
    measurements: tuple[tuple[tuple[int, int], float], ...]
    search_target_met: bool


class PSNRBlockSearch:
    """Search with fastest, then let the caller encode the winner with thorough."""

    def select(self, probe: QualityProbe, initial: tuple[int, int], target: float) -> SearchResult:
        index = FOOTPRINTS.index(initial)
        measurements: list[tuple[tuple[int, int], float]] = []

        def measure(candidate: int) -> float:
            quality = probe(FOOTPRINTS[candidate])
            measurements.append((FOOTPRINTS[candidate], quality))
            return quality

        quality = measure(index)
        if quality >= target:
            while index + 1 < len(FOOTPRINTS):
                next_quality = measure(index + 1)
                if next_quality < target:
                    break
                index += 1
                quality = next_quality
        else:
            while index > 0 and quality < target:
                index -= 1
                quality = measure(index)
        return SearchResult(FOOTPRINTS[index], tuple(measurements), quality >= target)
