"""Audit native Dataset tensors on frozen development corpora without training."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.utils.artifacts import ArtifactStore


class UnityPatchDatasetAudit:
    def __init__(self, config_path: Path) -> None:
        self.path = config_path
        self.config = ArtifactStore.read_json(config_path)

    def run(self) -> JsonDict:
        started = time.perf_counter()
        output = Path(self.config["report"])
        if output.exists():
            raise FileExistsError("Use a fresh Dataset audit identity")
        torch.set_num_threads(2)
        if not self.config["corpora"]:
            raise ValueError("At least one frozen Unity corpus is required")
        summaries = []
        identities: dict[tuple[str, str], str] = {}
        asset_splits: dict[str, str] = {}
        for item in self.config["corpora"]:
            corpus = Path(item["corpus"])
            splits = {}
            for split in ["train", "validation"]:
                dataset = UnityPatchDataset(corpus, split, expected_sha256=item["sha256"])
                splits[split] = self.audit_split(dataset)
                for row in dataset.rows:
                    asset = row["path"].replace("\\", "/").casefold()
                    if asset in asset_splits and asset_splits[asset] != split:
                        raise ValueError("Asset appears in different splits across Unity corpora")
                    asset_splits[asset] = split
                    identity = ArtifactStore.fingerprint(
                        {
                            **{
                                key: row[key]
                                for key in [
                                    "reference_sha256",
                                    "candidate_receipt_sha256",
                                    "target_sha256",
                                    "width",
                                    "height",
                                    "metadata",
                                    "alpha_constant",
                                    "original_selection",
                                    "image_quality",
                                    "full_channel_squared_errors",
                                ]
                            },
                            "patch_size": dataset.patch_size,
                        }
                    )
                    key = (split, asset)
                    if key in identities and identities[key] != identity:
                        raise ValueError("Duplicate Unity asset has conflicting imported targets")
                    identities[key] = identity
            summaries.append({**item, "splits": splits})
        result = {
            "status": "passed",
            "config": self.config,
            "config_sha256": ArtifactStore.sha256_file(self.path),
            "corpora": summaries,
            "unique_images": {
                split: sum(s == split for s, _ in identities) for split in ["train", "validation"]
            },
            "metadata_names": list(UnityPatchDataset.METADATA_NAMES),
            "sources_sha256": {
                str(path): ArtifactStore.sha256_file(path)
                for path in [
                    Path(__file__),
                    Path(__file__).parents[2] / "src/adaptive_astc/data/unity_patch_dataset.py",
                ]
            },
            "test_opened": False,
            "training_updates": 0,
            "device": "cpu",
            "wall_seconds": time.perf_counter() - started,
            "scope": (
                "Native Dataset input/target/geometry verification; "
                "no model training or accuracy claim"
            ),
        }
        ArtifactStore.write_json(output, result)
        return result

    @staticmethod
    def audit_split(dataset: UnityPatchDataset) -> JsonDict:
        seen: list[int] = []
        previous_image = -1
        reference = np.empty((0, 0, 4), dtype=np.uint8)
        for batch in DataLoader(dataset, batch_size=16, shuffle=False, num_workers=0):
            indexes = batch["patch_index"].numpy()
            seen.extend(indexes.tolist())
            assert batch["rgba"].dtype == torch.float32
            assert batch["rgba"].shape[1:] == (4, dataset.patch_size, dataset.patch_size)
            assert batch["metadata"].shape[1] == len(dataset.METADATA_NAMES)
            assert torch.all((batch["rgba"] >= 0) & (batch["rgba"] <= 1))
            np.testing.assert_array_equal(batch["image_index"].numpy(), dataset.image_ids[indexes])
            np.testing.assert_array_equal(
                batch["channel_zero_error"].numpy(), dataset.errors[indexes] == 0
            )
            np.testing.assert_array_equal(
                batch["channel_log_mse"].numpy(), dataset.targets[indexes]
            )
            np.testing.assert_array_equal(
                batch["valid_pixels"].numpy(), dataset.pixel_counts[indexes]
            )
            torch.testing.assert_close(
                batch["valid_mask"].sum((1, 2, 3)), batch["valid_pixels"], rtol=0, atol=0
            )
            for offset, index in enumerate(indexes):
                image_id = int(dataset.image_ids[index])
                if image_id != previous_image:
                    with Image.open(dataset.rows[image_id]["reference"]) as image:
                        reference = np.asarray(image.convert("RGBA"))
                    previous_image = image_id
                x, y, width, height = dataset.boxes[index]
                reconstructed = (
                    (batch["rgba"][offset].permute(1, 2, 0) * 255).round().to(torch.uint8).numpy()
                )
                np.testing.assert_array_equal(
                    reconstructed[:height, :width], reference[y : y + height, x : x + width]
                )
                expected = np.pad(
                    reference[y : y + height, x : x + width],
                    ((0, dataset.patch_size - height), (0, dataset.patch_size - width), (0, 0)),
                    mode="edge",
                )
                np.testing.assert_array_equal(reconstructed, expected)
        assert seen == list(range(len(dataset)))
        full = np.asarray(
            [row["full_channel_squared_errors"] for row in dataset.rows], dtype=np.int64
        )
        expected = np.asarray([[c["psnr"] for c in row["image_quality"]] for row in dataset.rows])
        error = float(np.max(np.abs(np.asarray(dataset.reconstructed_psnr) - expected)))
        return {
            "images": len(dataset.rows),
            "patches": len(dataset),
            "candidates": len(dataset.rows) * 20,
            "exact_pixel_and_padding_checks": len(seen),
            "max_native_psnr_error_db": error,
            "normal_images": sum(row["metadata"]["is_normal"] for row in dataset.rows),
            "multimip_normal_images": sum(
                row["metadata"]["is_normal"] and row["metadata"]["mip_count"] > 1
                for row in dataset.rows
            ),
            "alpha_participating_images": sum(
                row["metadata"]["need_alpha"] and not row["alpha_constant"] for row in dataset.rows
            ),
            "image_candidates_with_a_lossless_rgb_channel": int(
                np.any(full[:, :, :3] == 0, axis=2).sum()
            ),
            "image_candidates_with_no_rgb_error": int(np.all(full[:, :, :3] == 0, axis=2).sum()),
            "patch_channel_zero_error_counts": dataset.zero_error.sum(axis=(0, 1)).tolist(),
            "corpus_fingerprint": dataset.fingerprint,
        }
