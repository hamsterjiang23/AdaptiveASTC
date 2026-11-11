"""Keep native RGBA, valid-pixel geometry and input-only metadata separate from labels."""

import copy
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.patch_targets import PatchErrorGrid
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.dataset_audit import UnityPatchDatasetAudit
from reproductions.unity_search_baseline.patch_targets import UnityChannelErrors
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class DatasetFixture:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.path = root / "corpus.json"
        self.reference = root / "reference.png"
        self.target = root / "targets.npz"
        self.pixels = np.zeros((3, 241, 4), dtype=np.uint8)
        self.pixels[:, :, 0] = np.arange(241, dtype=np.uint8)
        self.pixels[:, :, 3] = 255
        Image.fromarray(self.pixels).save(self.reference)
        boxes = PatchErrorGrid(240).boxes(241, 3)
        errors = np.zeros((len(boxes), 20, 4), dtype=np.int64)
        errors[:, :, 0] = (boxes[:, 2] * boxes[:, 3])[:, None]
        np.savez_compressed(self.target, boxes=boxes, channel_squared_errors=errors)
        config = {"schema": "unity-rgba-channel-sse-v1", "patch_size": 240}
        binding = ArtifactStore.fingerprint(config)
        row: JsonDict = {
            "path": "Assets/train.png",
            "split": "train",
            "binding": binding,
            "reference": str(self.reference),
            "reference_sha256": ArtifactStore.sha256_file(self.reference),
            "targets": str(self.target),
            "target_sha256": ArtifactStore.sha256_file(self.target),
            "width": 241,
            "height": 3,
            "pixel_count": 723,
            "patch_count": 2,
            "candidate_grid": [
                [b, p] for b in UnityASTCBackend.BLOCKS for p in UnityASTCBackend.PRESETS
            ],
            "candidate_receipt_sha256": "c" * 64,
            "full_channel_squared_errors": errors.sum(axis=0).tolist(),
            "metadata": {"is_hdr": False, "is_normal": False, "need_alpha": True, "mip_count": 1},
            "actual_options": {
                "profile": 1,
                "channel": 4,
                "width": 241,
                "height": 3,
                "need_alpha": True,
                "texture_type_importer": "Default",
                "candidates_recorded": 17,
            },
            "original_selection": {
                "asset": "Assets/train.png",
                "search_executed": True,
                "cache_hit": False,
                "block_size": "12x12",
                "preset": "fastest",
                "candidates_measured": 17,
            },
            "import_metadata": {"srgb": False},
            "alpha_constant": True,
            "black_pixel_ratio": 1 / 241,
            "image_quality": [
                {"psnr": float(value), "ms_ssim_db": 21.0}
                for value in UnityChannelErrors.psnr(
                    errors.sum(axis=0), 723, need_alpha=True, alpha_constant=True
                )
            ],
        }
        self.document: JsonDict = {
            "status": "passed",
            "test_opened": False,
            "config": config,
            "binding": binding,
            "counts": {"train": 1, "validation": 0},
            "patch_counts": {"train": 2, "validation": 0},
            "splits": {"train": [row], "validation": []},
        }
        self.publish()

    def publish(self) -> None:
        self.document["fingerprint"] = ArtifactStore.fingerprint(
            {"binding": self.document["binding"], "splits": self.document["splits"]}
        )
        ArtifactStore.write_json(self.path, self.document)

    def load(self) -> UnityPatchDataset:
        return UnityPatchDataset(
            self.root, "train", expected_sha256=ArtifactStore.sha256_file(self.path)
        )


def test_rgba_padding_mask_and_channel_supervision(tmp_path: Path) -> None:
    fixture = DatasetFixture(tmp_path)
    dataset = fixture.load()
    sample = dataset[1]
    assert sample["rgba"].shape == (4, 240, 240)
    assert sample["channel_log_mse"].shape == sample["channel_zero_error"].shape == (20, 4)
    assert int(sample["valid_mask"].sum()) == int(sample["valid_pixels"]) == 3
    assert torch.all(sample["rgba"][3] == 1)
    assert torch.all(sample["channel_zero_error"][:, 1:])
    assert not torch.any(sample["channel_zero_error"][:, 0])
    assert float(sample["metadata"][5]) == 1
    expected = 20 * np.log10(255)
    np.testing.assert_allclose(dataset.reconstructed_psnr[0], expected)


def test_search_outputs_do_not_enter_input_metadata(tmp_path: Path) -> None:
    fixture = DatasetFixture(tmp_path)
    original = fixture.load()[0]["metadata"].clone()
    row = fixture.document["splits"]["train"][0]
    row["original_selection"].update(block_size="6x6", preset="exhaustive", candidates_measured=20)
    row["actual_options"]["candidates_recorded"] = 20
    for quality in row["image_quality"]:
        quality["ms_ssim_db"] = 99
    fixture.publish()
    torch.testing.assert_close(fixture.load()[0]["metadata"], original, rtol=0, atol=0)
    assert len(UnityPatchDataset.METADATA_NAMES) == 8


def test_external_corpus_hash_rejects_rewritten_labels(tmp_path: Path) -> None:
    fixture = DatasetFixture(tmp_path)
    original_hash = ArtifactStore.sha256_file(fixture.path)
    fixture.document["splits"]["train"][0]["original_selection"]["preset"] = "exhaustive"
    fixture.publish()
    with pytest.raises(ValueError, match="corpus SHA"):
        UnityPatchDataset(tmp_path, "train", expected_sha256=original_hash)


@pytest.mark.parametrize("split", ["test", "calibration", "validation"])
def test_unavailable_splits_are_rejected(tmp_path: Path, split: str) -> None:
    fixture = DatasetFixture(tmp_path)
    with pytest.raises(ValueError, match="does not open|empty"):
        UnityPatchDataset(tmp_path, split, expected_sha256=ArtifactStore.sha256_file(fixture.path))


def test_cross_split_duplicate_rejected(tmp_path: Path) -> None:
    fixture = DatasetFixture(tmp_path)
    row = copy.deepcopy(fixture.document["splits"]["train"][0])
    row.update(split="validation", path="assets/TRAIN.png")
    fixture.document["splits"]["validation"] = [row]
    fixture.document["counts"]["validation"] = 1
    fixture.publish()
    with pytest.raises(ValueError, match="uniqueness"):
        fixture.load()


@pytest.mark.parametrize("file", ["reference", "targets"])
def test_changed_input_file_rejected(tmp_path: Path, file: str) -> None:
    fixture = DatasetFixture(tmp_path)
    path = Path(fixture.document["splits"]["train"][0][file])
    path.write_bytes(b"damaged")
    with pytest.raises(ValueError, match=f"Frozen Unity {file}"):
        fixture.load()


@pytest.mark.parametrize("damage", ["geometry", "range", "sum", "psnr", "alpha", "order"])
def test_semantic_corruption_rejected_even_after_rehash(tmp_path: Path, damage: str) -> None:
    fixture = DatasetFixture(tmp_path)
    row = fixture.document["splits"]["train"][0]
    with np.load(fixture.target) as archive:
        boxes, errors = archive["boxes"].copy(), archive["channel_squared_errors"].copy()
    if damage == "geometry":
        boxes[1, 0] = 120
    elif damage == "range":
        errors[0, 0, 0] = 2**40
    elif damage == "sum":
        errors[0, 0, 0] += 1
    elif damage == "psnr":
        row["image_quality"][0]["psnr"] = 50
    elif damage == "alpha":
        row["alpha_constant"] = False
    else:
        row["candidate_grid"].reverse()
    np.savez_compressed(fixture.target, boxes=boxes, channel_squared_errors=errors)
    row["target_sha256"] = ArtifactStore.sha256_file(fixture.target)
    fixture.publish()
    with pytest.raises(ValueError):
        fixture.load()


def two_split_fixture(root: Path, train_asset: str, validation_asset: str) -> DatasetFixture:
    fixture = DatasetFixture(root)
    train = fixture.document["splits"]["train"][0]
    train["path"] = train_asset
    train["original_selection"]["asset"] = train_asset
    validation = copy.deepcopy(train)
    validation.update(path=validation_asset, split="validation")
    validation["original_selection"]["asset"] = validation_asset
    fixture.document["splits"]["validation"] = [validation]
    fixture.document["counts"]["validation"] = 1
    fixture.document["patch_counts"]["validation"] = 2
    fixture.publish()
    return fixture


@pytest.mark.parametrize("conflict", ["split", "target", "patch_distribution", "none"])
def test_audit_cross_corpus_identity(tmp_path: Path, conflict: str) -> None:
    first = two_split_fixture(tmp_path / "first", "Assets/A.png", "Assets/B.png")
    second = two_split_fixture(
        tmp_path / "second",
        "Assets/B.png" if conflict == "split" else "Assets/A.png",
        "Assets/B.png" if conflict == "none" else "Assets/C.png",
    )
    if conflict == "target":
        second.document["splits"]["train"][0]["original_selection"]["preset"] = "exhaustive"
        second.publish()
    elif conflict == "patch_distribution":
        with np.load(second.target) as archive:
            boxes = archive["boxes"].copy()
            errors = archive["channel_squared_errors"].copy()
        errors[0, 0, 0] -= 1
        errors[1, 0, 0] += 1
        np.savez_compressed(second.target, boxes=boxes, channel_squared_errors=errors)
        for rows in second.document["splits"].values():
            for row in rows:
                row["target_sha256"] = ArtifactStore.sha256_file(second.target)
        second.publish()
        # Each corpus remains valid on its own; only the duplicate comparison can reject it.
        first.load()
        second.load()
    config = tmp_path / "audit-config.json"
    report = tmp_path / "audit-report.json"
    ArtifactStore.write_json(
        config,
        {
            "report": str(report),
            "corpora": [
                {
                    "name": name,
                    "corpus": str(fixture.root),
                    "sha256": ArtifactStore.sha256_file(fixture.path),
                }
                for name, fixture in [("first", first), ("second", second)]
            ],
        },
    )
    if conflict == "none":
        result = UnityPatchDatasetAudit(config).run()
        assert result["unique_images"] == {"train": 1, "validation": 1}
        assert result["training_updates"] == 0
    else:
        with pytest.raises(ValueError, match="different splits|conflicting imported targets"):
            UnityPatchDatasetAudit(config).run()
        assert not report.exists()
