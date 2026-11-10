"""Deterministic asset-isolated split and quota policy."""

import math
from collections import Counter
from pathlib import PurePosixPath

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

from adaptive_astc.config import FORMAL_SIZES, SEED, JsonDict


class DatasetSplitter:
    """Group assets, assign mother folds, select holdouts, and audit isolation."""

    @staticmethod
    def asset_group(path: str) -> str:
        parts = PurePosixPath(path).parts
        if parts[:3] in (
            ("Assets", "Art", "Characters"),
            ("Assets", "Art", "Monster"),
            ("Assets", "Art", "Environment"),
        ):
            return "/".join(parts[:4])
        parent = list(parts[:-1])
        if parent and parent[-1].upper() in {"SD", "HD", "FHD"}:
            parent.pop()
        return "/".join(parent)

    @staticmethod
    def quotas(counts: list[int], total: int) -> list[int]:
        shares = [count * total / sum(counts) for count in counts]
        result = [math.floor(share) for share in shares]
        order = sorted(
            range(len(counts)), key=lambda index: (-(shares[index] - result[index]), index)
        )
        for index in order[: total - sum(result)]:
            result[index] += 1
        return result

    @staticmethod
    def assign_folds(rows: list[JsonDict]) -> list[JsonDict]:
        labels = [row["class_id"] for row in rows]
        groups = [row["group"] for row in rows]
        splitter = StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=SEED)
        for fold, (_, indices) in enumerate(splitter.split(np.zeros(len(rows)), labels, groups)):
            for index in indices:
                rows[index]["fold"] = fold
        return rows

    @staticmethod
    def select_split_folds(
        rows: list[JsonDict], sizes: dict[str, int], min_groups: int
    ) -> dict[str, int]:
        counts = [sum(row["class_id"] == label for row in rows) for label in range(4)]
        required = DatasetSplitter.quotas(
            counts, max(sizes.values()) if min_groups == 1 else sizes["test"]
        )
        eligible: list[int] = []
        for fold in range(10):
            members = [row for row in rows if row["fold"] == fold]
            group_count = len({row["group"] for row in members})
            labels = Counter(row["class_id"] for row in members)
            if group_count >= min_groups and all(
                labels[label] >= required[label] for label in range(4)
            ):
                eligible.append(fold)
        if len(eligible) < 3:
            raise ValueError("Three class-supported, multi-asset holdout folds are required")
        return dict(zip(("test", "calibration", "validation"), eligible[:3], strict=True))

    @staticmethod
    def audit_manifests(manifests: dict[str, list[JsonDict]]) -> JsonDict:
        seen_hashes: set[str] = set()
        seen_groups: set[str] = set()
        for split in FORMAL_SIZES:
            rows = manifests[split]
            hashes = {str(row["fileHash"]) for row in rows}
            groups = {str(row["group"]) for row in rows}
            if len(hashes) != len(rows) or seen_hashes & hashes or seen_groups & groups:
                raise ValueError(f"Cross-split hash/group isolation failed for {split}")
            seen_hashes.update(hashes)
            seen_groups.update(groups)
        return {"content_hash_disjoint": True, "asset_group_disjoint": True}
