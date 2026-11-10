"""Perceptual near-duplicate index for split admission."""

from collections import defaultdict

import numpy as np

from adaptive_astc.config import JsonDict


class NearDuplicateIndex:
    """Five bands retrieve every Hamming-distance-at-most-four candidate."""

    def __init__(self) -> None:
        self.bands: dict[tuple[int, int], set[int]] = defaultdict(set)
        self.items: list[tuple[JsonDict, np.ndarray]] = []

    @staticmethod
    def keys(value: int) -> list[tuple[int, int]]:
        return [(band, (value >> (13 * band)) & 8191) for band in range(5)]

    def match(self, row: JsonDict, preview: np.ndarray) -> str | None:
        candidates: set[int] = set()
        for key in self.keys(int(row["phash"])):
            candidates.update(self.bands.get(key, set()))
        aspect = row["width"] / row["height"]
        for index in sorted(candidates):
            other, other_preview = self.items[index]
            if (int(row["phash"]) ^ int(other["phash"])).bit_count() > 4:
                continue
            if abs(aspect / (other["width"] / other["height"]) - 1) > 0.01:
                continue
            difference = preview.astype(np.float32) - other_preview.astype(np.float32)
            if float(np.mean(difference**2)) <= 9:
                return str(other["path"])
        return None

    def add(self, row: JsonDict, preview: np.ndarray) -> None:
        index = len(self.items)
        self.items.append((row, preview))
        for key in self.keys(int(row["phash"])):
            self.bands[key].add(index)
