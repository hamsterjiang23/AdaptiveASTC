"""Bind replacement measurements to approved native sources, including retained origins."""

from copy import deepcopy
from pathlib import Path

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.development_corpus_revision import (
    UnityDevelopmentCorpusRevision as R,
)


def origin_fixture(folder: Path) -> tuple[R, JsonDict, JsonDict, JsonDict, Path]:
    asset = "Assets/a.png"
    run = folder / "capture"
    backup = run / "backups/original.meta"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"original importer metadata")
    (backup.parent / "index.jsonl").write_text(
        '{"asset":"Assets/a.png","backup":"original.meta"}\n', encoding="utf-8"
    )
    expected = {
        "path": asset,
        "fileHash": "1" * 32,
        "source_sha256": "2" * 64,
        "source_bytes": 8,
        "meta_sha256": A.sha256_file(backup),
    }
    source = folder / "replacements.json"
    A.write_json(source, {"splits": {"train": [expected]}})
    binding = {"path": str(source), "sha256": A.sha256_file(source)}
    identity = run / "identity.json"
    A.write_json(identity, {"manifest": str(source), "manifest_sha256": binding["sha256"]})
    phase = run / "batch-config.json"
    A.write_json(phase, {"backupDirectory": str(backup.parent)})
    summary = folder / "candidate-summary.json"
    receipt = folder / "candidates/receipt.json"
    A.write_json(
        receipt,
        {
            "status": "passed",
            "test_opened": False,
            "config": {"report": str(summary), "capture_run": str(run), "capture_phase": "batch"},
            "capture_binding": {
                "identity_sha256": A.sha256_file(identity),
                "phase_config_sha256": A.sha256_file(phase),
            },
        },
    )
    A.write_json(
        summary, {"raw_receipt": str(receipt), "raw_receipt_sha256": A.sha256_file(receipt)}
    )
    row: JsonDict = {
        "path": asset,
        "split": "train",
        "reference_sha256": "reference",
        "original_selection": {"block_size": "8x8"},
        "actual_options": {"rgba_sha256": "pixels"},
        "import_metadata": {"srgb": True},
        "index": 0,
        "binding": "patch-binding",
    }
    candidate = {
        "path": asset,
        "source_md4": expected["fileHash"],
        "reference_sha256": row["reference_sha256"],
        "selection": row["original_selection"],
        "actual_options": row["actual_options"],
        "import_metadata": row["import_metadata"],
        "candidate_directory": str(receipt.parent / "00000"),
        "candidate_report_sha256": A.sha256_file(summary),
    }
    candidates = folder / "candidate-manifest.json"
    A.write_json(candidates, {"splits": {"train": [candidate]}})
    shard = folder / "shard/corpus.json"
    A.write_json(
        shard,
        {
            "config": {
                "candidate_manifest": str(candidates),
                "candidate_manifest_sha256": A.sha256_file(candidates),
            },
            "splits": {"train": [deepcopy(row)]},
        },
    )
    row["source_shard"] = {
        "corpus": str(shard),
        "sha256": A.sha256_file(shard),
        "binding": "patch-binding",
        "index": 0,
    }
    revision = R.__new__(R)
    revision.provenance_inputs = {}
    revision.provenance_documents = {}
    return revision, row, expected, binding, backup


def test_complete_native_source_chain_is_accepted(tmp_path: Path) -> None:
    revision, row, expected, binding, backup = origin_fixture(tmp_path)
    revision.verify_new_identity(row, expected, binding)
    assert str(backup.resolve()) in revision.provenance_inputs


@pytest.mark.parametrize("key", ["fileHash", "source_sha256", "meta_sha256"])
def test_same_path_different_approved_source_is_rejected(tmp_path: Path, key: str) -> None:
    revision, row, expected, binding, _ = origin_fixture(tmp_path)
    expected[key] = "0" * len(expected[key])
    with pytest.raises(ValueError, match="source|metadata"):
        revision.verify_new_identity(row, expected, binding)


def test_different_capture_manifest_is_rejected(tmp_path: Path) -> None:
    revision, row, expected, binding, _ = origin_fixture(tmp_path)
    binding["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source manifest"):
        revision.verify_new_identity(row, expected, binding)


def test_original_importer_backup_must_match(tmp_path: Path) -> None:
    revision, row, expected, binding, backup = origin_fixture(tmp_path)
    backup.write_bytes(b"different importer settings")
    with pytest.raises(ValueError, match="original metadata"):
        revision.verify_new_identity(row, expected, binding)


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_retained_patch_origins_must_remain_available(tmp_path: Path, damage: str) -> None:
    revision, row, _, _, _ = origin_fixture(tmp_path)
    shard = Path(row["source_shard"]["corpus"])
    if damage == "missing":
        shard.unlink()
    else:
        shard.write_text("{}", encoding="utf-8")
    with pytest.raises((FileNotFoundError, ValueError)):
        revision.origin(row)
