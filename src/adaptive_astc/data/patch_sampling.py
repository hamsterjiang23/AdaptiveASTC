"""Sampling weights for image-balanced and capped asset-group patch controls."""

from collections import Counter

import numpy as np
from numpy.typing import NDArray

from adaptive_astc.config import JsonDict


class PatchSampling:
    @staticmethod
    def weights(
        rows: list[JsonDict], image_ids: NDArray[np.int64], group_image_cap: int = 0
    ) -> NDArray[np.float64]:
        if type(group_image_cap) is not int or group_image_cap < 0:
            raise ValueError("Asset group cap must be a nonnegative integer; zero disables it")
        if (
            not rows
            or image_ids.ndim != 1
            or not len(image_ids)
            or not np.issubdtype(image_ids.dtype, np.integer)
            or image_ids.min() < 0
            or image_ids.max() >= len(rows)
        ):
            raise ValueError("Require valid patch-to-image indexes")
        counts = np.bincount(image_ids, minlength=len(rows))
        if np.any(counts == 0):
            raise ValueError("Every training image must have at least one patch")
        weights = 1.0 / counts[image_ids]
        if group_image_cap:
            groups = [row["group"] for row in rows]
            if any(not isinstance(group, str) or not group for group in groups):
                raise ValueError("Asset group sampling requires nonempty group names")
            group_counts = Counter(groups)
            image_weights = np.array(
                [min(1.0, group_image_cap / group_counts[group]) for group in groups],
                dtype=np.float64,
            )
            weights *= image_weights[image_ids]
        return weights
