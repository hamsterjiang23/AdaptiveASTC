"""Pair source-derived model inputs with unchanged Unity native supervision."""

from __future__ import annotations

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import Dataset

from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.data.unity_v3_input import (
    SourceInputMode,
    SourceTextureSpec,
    UnityV3InferenceInput,
)
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore


class UnityV3PatchDataset(Dataset[dict[str, Tensor]]):
    """Wrap an already validated corpus without replacing its targets or true metadata.

    ``rows`` and target arrays retain Unity identities. ``decision_inputs`` and
    ``input_metadata`` belong to the source prediction branch; real quality gates
    must use ``truth_decision_inputs`` or their own actual encoding pixels.
    """

    METADATA_NAMES = UnityPatchDataset.METADATA_NAMES

    def __init__(
        self,
        native: UnityPatchDataset,
        specs: list[SourceTextureSpec],
        mode: SourceInputMode = "source_aligned",
    ) -> None:
        if mode != "source_aligned":
            raise ValueError("Native source geometry cannot consume Unity patch supervision")
        if len(specs) != len(native.rows):
            raise ValueError("Every Unity supervision row requires its own aligned source spec")
        for row, spec in zip(native.rows, specs, strict=True):
            asset = row["path"].replace("\\", "/").casefold()
            actual_mips = row["metadata"]["mip_count"] if row["metadata"]["is_normal"] else 1
            if (
                spec.asset is None
                or spec.asset.replace("\\", "/").casefold() != asset
                or (spec.target_width, spec.target_height) != (row["width"], row["height"])
                or spec.srgb != row["import_metadata"]["srgb"]
                or spec.normal != row["metadata"]["is_normal"]
                or spec.need_alpha != row["metadata"]["need_alpha"]
                or spec.normal_metric_mips != actual_mips
            ):
                raise ValueError(
                    "Source asset, target dimensions or explicit import settings differ"
                )
        self.inputs = UnityV3InferenceInput(specs, mode, native.patch_size)
        if (
            not np.array_equal(self.inputs.boxes, native.boxes)
            or not np.array_equal(self.inputs.image_ids, native.image_ids)
            or not np.array_equal(self.inputs.pixel_counts, native.pixel_counts)
        ):
            raise ValueError("Source input grid does not exactly align with Unity supervision")
        self.rows = native.rows
        self.errors = native.errors
        self.mse = native.mse
        self.targets = native.targets
        self.zero_error = native.zero_error
        self.boxes = native.boxes
        self.image_ids = native.image_ids
        self.pixel_counts = native.pixel_counts
        self.patch_size = native.patch_size
        self.candidate_grid = native.candidate_grid
        self.reconstructed_psnr = native.reconstructed_psnr
        self.corpus_sha256 = native.corpus_sha256
        self.split = native.split
        self.input_metadata = self.inputs.input_metadata
        self.decision_inputs = self.inputs.decision_inputs
        self.truth_decision_inputs = [UnityTextureInput.from_row(row) for row in self.rows]
        self.native_fingerprint = native.fingerprint
        self.fingerprint = ArtifactStore.fingerprint(
            {
                "native_fingerprint": native.fingerprint,
                "source_inputs_fingerprint": self.inputs.fingerprint,
                "split": self.split,
            }
        )

    def __len__(self) -> int:
        return len(self.boxes)

    def verify_sources(self) -> None:
        self.inputs.verify_sources()

    def __getitem__(self, index: int) -> dict[str, Tensor]:
        item = self.inputs[index]
        image_id = int(self.image_ids[index])
        return {
            **item,
            "channel_log_mse": torch.from_numpy(self.targets[index]),
            "channel_zero_error": torch.from_numpy(self.zero_error[index]),
            "valid_pixels": torch.tensor(int(self.pixel_counts[index]), dtype=torch.int64),
            "image_index": torch.tensor(image_id, dtype=torch.int64),
        }
