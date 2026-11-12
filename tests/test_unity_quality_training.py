"""Guard image-target pairing, full-corpus admission and independent run ownership."""

import copy
from dataclasses import replace
from pathlib import Path

import pytest
import torch
from torch.utils.data import DataLoader

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_image_bags import UnityImageBags
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.training.unity_quality_trainer import UnityQualityTrainer, UnityTrainConfig
from adaptive_astc.utils.artifacts import ArtifactStore
from tests.test_unity_patch_dataset import DatasetFixture


def test_pretrained_initialization_requires_bound_weight_identity(tmp_path: Path) -> None:
    config = UnityTrainConfig(
        tmp_path / "corpus", "0" * 64, tmp_path / "output", tmp_path / "report.json", smoke=True
    )
    config.validate()
    with pytest.raises(ValueError, match="weight file and its SHA256"):
        replace(config, initialization="pretrained").validate()
    weights = tmp_path / "weights.pth"
    weights.write_bytes(b"initialization fixture")
    pretrained = replace(
        config,
        initialization="pretrained",
        pretrained_weights=weights,
        pretrained_weights_sha256=ArtifactStore.sha256_file(weights),
    )
    pretrained.validate()
    UnityQualityTrainer.verify_pretrained_weights(pretrained)
    weights.write_bytes(b"changed weights")
    with pytest.raises(ValueError, match="initialization weight file changed"):
        UnityQualityTrainer.verify_pretrained_weights(pretrained)
    with pytest.raises(ValueError, match="unused pretrained weights"):
        replace(pretrained, initialization="scratch").validate()


def paired_dataset(tmp_path: Path) -> UnityPatchDataset:
    fixture = DatasetFixture(tmp_path)
    first = fixture.document["splits"]["train"][0]
    for quality in first["image_quality"]:
        quality.update(normal_mean_deg=None, normal_p95_deg=None)
    second = copy.deepcopy(first)
    second["path"] = second["original_selection"]["asset"] = "Assets/second.png"
    second["image_quality"][0]["ms_ssim_db"] = 42.0
    fixture.document["splits"]["train"].append(second)
    fixture.document["counts"]["train"] = 2
    fixture.document["patch_counts"]["train"] = 4
    fixture.publish()
    return fixture.load()


def test_image_bags_keep_sampled_pixels_and_full_image_targets_paired(tmp_path: Path) -> None:
    dataset = paired_dataset(tmp_path)
    bags = UnityImageBags(dataset, [1, 0], 4)
    torch.manual_seed(7)
    for index, expected_image in enumerate([1, 0]):
        inputs, targets = bags[index]
        assert int(inputs["original_image_index"]) == expected_image
        assert inputs["rgba"].shape == (4, 4, 240, 240)
        assert torch.all(
            torch.from_numpy(dataset.image_ids[inputs["patch_index"]]) == expected_image
        )
        for view, patch_index in enumerate(inputs["patch_index"]):
            original = dataset[int(patch_index)]
            for key in ["rgba", "valid_mask", "channel_log_mse"]:
                torch.testing.assert_close(inputs[key][view], original[key])
        assert float(targets["image_quality"][0, 0]) == (42.0 if expected_image else 21.0)
        assert torch.equal(targets["channel_active"], torch.tensor([True, True, True, False]))


def test_shuffled_epoch_visits_every_selected_image_once(tmp_path: Path) -> None:
    bags = UnityImageBags(paired_dataset(tmp_path), [1, 0], 3)
    loader = DataLoader(
        bags, batch_size=1, shuffle=True, generator=torch.Generator().manual_seed(7)
    )
    visited = [int(inputs["original_image_index"][0]) for inputs, _ in loader]
    assert sorted(visited) == [0, 1]


@pytest.mark.parametrize("indices,views", [([], 4), ([0, 0], 4), ([2], 4), ([True], 4), ([0], 0)])
def test_invalid_image_selection_rejected(tmp_path: Path, indices: list[int], views: int) -> None:
    with pytest.raises(ValueError, match="Unique valid"):
        UnityImageBags(paired_dataset(tmp_path), indices, views)


def configuration(tmp_path: Path) -> UnityTrainConfig:
    return UnityTrainConfig(tmp_path / "corpus", "a" * 64, tmp_path / "output", tmp_path / "report")


@pytest.mark.parametrize(
    "changes",
    [
        {"coverage": "partial"},
        {"counts": {"train": 2368, "validation": 2}},
        {"expected_full_counts": {"train": 2368, "validation": 2}},
    ],
)
def test_formal_training_rejects_partial_or_mislabeled_coverage(
    tmp_path: Path, changes: JsonDict
) -> None:
    document = {
        "coverage": "complete",
        "counts": {"train": 10000, "validation": 1000},
        "expected_full_counts": {"train": 10000, "validation": 1000},
    }
    document.update(changes)
    with pytest.raises(ValueError, match="complete frozen"):
        UnityQualityTrainer.validate_coverage(document, configuration(tmp_path))
    UnityQualityTrainer.validate_coverage(document, replace(configuration(tmp_path), smoke=True))


def test_complete_formal_coverage_and_smoke_subset_have_distinct_contracts(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    config.validate()
    UnityQualityTrainer.validate_coverage(
        {
            "coverage": "complete",
            "counts": {"train": 10000, "validation": 1000},
            "expected_full_counts": {"train": 10000, "validation": 1000},
        },
        config,
    )
    with pytest.raises(ValueError, match="cannot silently select"):
        replace(config, train_image_indices=(0,)).validate()
    replace(config, smoke=True, train_image_indices=(0,)).validate()
    with pytest.raises(ValueError, match="unique nonnegative"):
        replace(config, smoke=True, train_image_indices=(0, 0)).validate()


def test_existing_report_never_overwritten_before_cuda(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    ArtifactStore.write_json(report, {"existing": "result"})
    config = tmp_path / "config.json"
    ArtifactStore.write_json(
        config,
        {
            "corpus": str(tmp_path / "corpus"),
            "corpus_sha256": "a" * 64,
            "output": str(tmp_path / "experiment report/.local/new"),
            "report": str(report),
        },
    )
    before = report.read_bytes()
    with pytest.raises(FileExistsError):
        UnityQualityTrainer(config, tmp_path).run()
    assert report.read_bytes() == before


@pytest.mark.parametrize("changed", ["best.pt", "best-validation.npz", "best-decisions.json"])
def test_checkpoint_audit_rejects_changed_selected_artifacts(tmp_path: Path, changed: str) -> None:
    names = ["best.pt", "best-validation.npz", "best-decisions.json"]
    for name in names:
        (tmp_path / name).write_bytes(b"original")
    expected = {name: ArtifactStore.sha256_file(tmp_path / name) for name in names}
    UnityQualityTrainer.verify_artifacts(tmp_path, expected)
    with (tmp_path / changed).open("ab") as stream:
        stream.write(b"appended")
    with pytest.raises(ValueError, match="Selected native artifact changed"):
        UnityQualityTrainer.verify_artifacts(tmp_path, expected)


@pytest.mark.parametrize("changed", ["reference", "targets"])
def test_final_input_recheck_detects_postload_training_mutation(
    tmp_path: Path, changed: str
) -> None:
    dataset = paired_dataset(tmp_path)
    UnityQualityTrainer.verify_input_files(dataset.rows)
    path = Path(dataset.rows[0][changed])
    with path.open("ab") as stream:
        stream.write(b"changed after training dataset initialized")
    with pytest.raises(ValueError, match="Native training input changed"):
        UnityQualityTrainer.verify_input_files(dataset.rows)
