"""Reject unpublished, cross-split or changed native patch batch inputs."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.patch_batches import UnityPatchBatchPreparation


def publication() -> tuple[JsonDict, list[JsonDict]]:
    batches = [
        {"split": "train", "config": {"run_id": "a"}},
        {"split": "validation", "config": {"run_id": "b"}},
        {"split": "train", "config": {"run_id": "pending"}},
    ]
    snapshot: JsonDict = {
        "status": "waiting_references",
        "test_opened": False,
        "counts": {"train": 64, "validation": 2},
        "batches": [
            {"run_id": "a", "source_split": "train", "images": 64},
            {"run_id": "b", "source_split": "validation", "images": 2},
        ],
    }
    return snapshot, batches


def test_only_published_batches_in_plan_order() -> None:
    snapshot, batches = publication()
    chosen = UnityPatchBatchPreparation.select_batches(snapshot, batches, ["b", "a"])
    assert chosen == batches[:2]


@pytest.mark.parametrize(
    ("plan_coverage", "snapshot_coverage", "planned", "counts", "expected"),
    [
        ("selected", "selected", 2, {"train": 256, "validation": 2}, "partial"),
        ("complete", "complete", 45, {"train": 10000, "validation": 1000}, "partial"),
        ("complete", "complete", 2, {"train": 256, "validation": 2}, "partial"),
        ("complete", "complete", 2, {"train": 10000, "validation": 1000}, "complete"),
    ],
)
def test_small_complete_plan_is_not_full_corpus(
    plan_coverage: str,
    snapshot_coverage: str,
    planned: int,
    counts: dict[str, int],
    expected: str,
) -> None:
    assert (
        UnityPatchBatchPreparation.coverage(
            {"coverage": snapshot_coverage, "expected_counts": counts},
            2,
            planned,
            plan_coverage,
            {"train": 10000, "validation": 1000},
        )
        == expected
    )


@pytest.mark.parametrize("names", [[], ["a", "a"], ["pending"], ["foreign"]])
def test_unpublished_or_duplicate_selection_rejected(names: list[str]) -> None:
    snapshot, batches = publication()
    with pytest.raises(ValueError, match="already published"):
        UnityPatchBatchPreparation.select_batches(snapshot, batches, names)


@pytest.mark.parametrize("damage", ["split", "count", "duplicate", "unknown", "test"])
def test_corrupt_publication_rejected(damage: str) -> None:
    snapshot, batches = publication()
    if damage == "split":
        snapshot["batches"][0]["source_split"] = "validation"
    elif damage == "count":
        snapshot["counts"]["train"] += 1
    elif damage == "duplicate":
        snapshot["batches"].append(copy.deepcopy(snapshot["batches"][0]))
    elif damage == "unknown":
        snapshot["batches"][0]["run_id"] = "foreign"
    else:
        snapshot["test_opened"] = True
    with pytest.raises(ValueError):
        UnityPatchBatchPreparation.select_batches(snapshot, batches, ["a"])


@pytest.mark.parametrize("key", ["reference", "report_sha256", "images"])
def test_revalidated_publication_must_match_snapshot(key: str) -> None:
    summary = {"report_sha256": "1" * 64, "images": 2}
    reference = {"options_sha256": "2" * 64}
    published = {"reference": reference, **summary}
    UnityPatchBatchPreparation.verify_publication(published, reference, summary)
    changed = copy.deepcopy(published)
    changed[key] = None
    with pytest.raises(ValueError, match="frozen publication"):
        UnityPatchBatchPreparation.verify_publication(changed, reference, summary)


def test_frozen_json_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    UnityPatchBatchPreparation.freeze_json(path, {"source": "first"})
    original, modified = path.read_bytes(), path.stat().st_mtime_ns
    UnityPatchBatchPreparation.freeze_json(path, {"source": "first"})
    assert path.read_bytes() == original and path.stat().st_mtime_ns == modified
    with pytest.raises(ValueError, match="protocol changed"):
        UnityPatchBatchPreparation.freeze_json(path, {"source": "different"})
    assert path.read_bytes() == original


@pytest.mark.parametrize("changed", ["config", "report", "corpus"])
def test_completed_shard_rejects_changed_artifacts(tmp_path: Path, changed: str) -> None:
    config, report, corpus = [
        tmp_path / name for name in ["config.json", "report.json", "corpus.json"]
    ]
    ArtifactStore.write_json(config, {"output": str(tmp_path), "report": str(report)})
    ArtifactStore.write_json(report, {"status": "passed"})
    ArtifactStore.write_json(corpus, {"status": "passed"})
    paths = {"config": config, "report": report, "corpus": corpus}
    ArtifactStore.write_json(
        tmp_path / "shard-complete.json",
        {f"{key}_sha256": ArtifactStore.sha256_file(path) for key, path in paths.items()},
    )
    if changed == "config":
        options = ArtifactStore.read_json(config)
        options["patch_size"] = 120
        ArtifactStore.write_json(config, options)
    else:
        paths[changed].write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Completed patch shard"):
        UnityPatchBatchPreparation.prepare_shard(config)
