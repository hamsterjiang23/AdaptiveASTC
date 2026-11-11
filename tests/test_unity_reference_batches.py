"""Freeze reference batches without weakening the 10k search baseline or test boundary."""

import hashlib
import sys
from pathlib import Path

import pytest

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from script import reproduce


def make_batch(tmp_path: Path) -> UnitySearchBaseline:
    project = tmp_path / "project"
    paths = ["Assets/a.png", "Assets/b.png"]
    for path in paths:
        source = project / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"synthetic source")
        Path(str(source) + ".meta").write_bytes(b"synthetic metadata")
    plugins = project / "Assets/Editor/Astc/Plugins"
    plugins.mkdir(parents=True)
    for name in ["astcenc-avx2-shared.dll", "astcenc-avx2-static.dll"]:
        (plugins / name).write_bytes(b"protocol-only fixture, not an encoder")
    manifest = tmp_path / "manifest.json"
    ArtifactStore.write_json(
        manifest,
        {
            "fingerprint": "synthetic",
            "splits": {
                "train": [],
                "validation": [
                    {
                        "path": path,
                        "width": 4,
                        "height": 4,
                        "blockSize": "12x12",
                        "alpha_nonopaque": False,
                    }
                    for path in paths
                ],
                "test": [],
            },
        },
    )
    return UnitySearchBaseline(
        tmp_path,
        project,
        tmp_path / "unused-editor",
        manifest,
        capture_references=True,
        source_split="validation",
        capture_paths=list(reversed(paths)),
    )


def test_validation_batch_preserves_order_split_and_protocol(tmp_path: Path) -> None:
    baseline = make_batch(tmp_path)
    identity = baseline.prepare()
    assert identity["source_split"] == "validation"
    assert identity["source_split_count"] == identity["selected_count"] == 2
    assert "train_count" not in identity
    assert {path.name for path in baseline.run_dir.glob("*-config.json")} == {"batch-config.json"}
    config = ArtifactStore.read_json(baseline.run_dir / "batch-config.json")
    assert [row["path"] for row in config["assets"]] == baseline.capture_paths
    baseline.verify_protocol()
    assert baseline.prepare() == identity
    baseline.source_split = "train"
    with pytest.raises(ValueError, match="prepared protocol"):
        baseline.verify_protocol()
    baseline.source_split = "validation"
    baseline.capture_paths = ["Assets/a.png", "Assets/b.png"]
    with pytest.raises(ValueError, match="prepared protocol"):
        baseline.verify_protocol()


def test_batch_checks_membership_and_cross_split_asset_leakage(tmp_path: Path) -> None:
    baseline = make_batch(tmp_path)
    baseline.capture_paths = ["Assets/outside.png"]
    with pytest.raises(ValueError, match="outside its frozen source split"):
        baseline.prepare()
    baseline.capture_paths = ["Assets/a.png"]
    manifest = ArtifactStore.read_json(baseline.manifest)
    manifest["splits"]["train"] = [manifest["splits"]["validation"][0]]
    ArtifactStore.write_json(baseline.manifest, manifest)
    with pytest.raises(ValueError, match="shared across source splits"):
        baseline.prepare()


def test_legacy_baseline_still_requires_10000_training_images(tmp_path: Path) -> None:
    batch = make_batch(tmp_path)
    baseline = UnitySearchBaseline(tmp_path, batch.project, batch.editor, batch.manifest)
    with pytest.raises(ValueError, match="Expected 10000 training images"):
        baseline.prepare()


@pytest.mark.parametrize("source_split", ["test", "calibration"])
def test_reference_development_excludes_held_out_splits(tmp_path: Path, source_split: str) -> None:
    with pytest.raises(ValueError, match="excludes calibration and test"):
        UnitySearchBaseline(
            tmp_path,
            tmp_path,
            tmp_path,
            tmp_path,
            capture_references=True,
            source_split=source_split,
            capture_paths=["Assets/a.png"],
        )


@pytest.mark.parametrize("paths", [[], ["Assets/a.png", "assets/A.png"], ["a"] * 257])
def test_reference_batch_is_bounded_and_unique(tmp_path: Path, paths: list[str]) -> None:
    with pytest.raises(ValueError, match="1..256 unique"):
        UnitySearchBaseline(
            tmp_path, tmp_path, tmp_path, tmp_path, capture_references=True, capture_paths=paths
        )


def test_validation_requires_explicit_reference_capture(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit reference batch"):
        UnitySearchBaseline(tmp_path, tmp_path, tmp_path, tmp_path, source_split="validation")
    with pytest.raises(ValueError, match="1..256 unique"):
        UnitySearchBaseline(tmp_path, tmp_path, tmp_path, tmp_path, capture_paths=["Assets/a.png"])


def test_batch_cli_recovers_metadata_with_frozen_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = make_batch(tmp_path)
    baseline.prepare()
    target = baseline.project / "Assets/a.png.meta"
    original = target.read_bytes()
    target.write_bytes(b"temporary import override")
    backups = baseline.run_dir / "batch-meta-backups"
    backup = backups / "Assets/a.png.meta"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(original)
    Path(str(backup) + ".expected.sha256").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(reproduce, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reproduce.py",
            "recover",
            "--phase",
            "batch",
            "--run-id",
            baseline.run_dir.name,
            "--project",
            str(baseline.project),
            "--editor",
            str(baseline.editor),
            "--manifest",
            str(baseline.manifest),
        ],
    )
    reproduce.main()
    assert target.read_bytes() == original
    config_path = baseline.run_dir / "batch-config.json"
    config = ArtifactStore.read_json(config_path)
    config["backupDirectory"] = str(tmp_path / "other-backups")
    ArtifactStore.write_json(config_path, config)
    with pytest.raises(ValueError, match="Frozen protocol changed"):
        reproduce.main()


def test_baseline_cli_cannot_launch_a_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["reproduce.py", "run", "--phase", "batch"])
    with pytest.raises(SystemExit) as error:
        reproduce.main()
    assert error.value.code == 2
