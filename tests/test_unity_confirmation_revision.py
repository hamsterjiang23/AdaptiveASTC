"""Eligibility revisions preserve ordering, old evidence and historical isolation."""

from __future__ import annotations

from pathlib import Path

import pytest
from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation import UnityConfirmationCohort as C
from reproductions.unity_search_baseline.confirmation_revision import UnityConfirmationRevision as R


def make_revision(root: Path) -> Path:
    project = root / "project"
    entries: JsonDict = {}
    for index in range(9):
        path = project / f"Assets/Group{index}/image.png"
        path.parent.mkdir(parents=True)
        Image.new("RGBA", (4, 4), (index, index, index, 255)).save(path)
        Path(str(path) + ".meta").write_text(
            "TextureImporter:\n  textureType: 0\n  textureShape: 1\n", encoding="utf-8"
        )
        entries[str(path.relative_to(project)).replace("\\", "/")] = {
            "fileHash": MD4.new(path.read_bytes()).hexdigest()
        }
    snapshot = root / "snapshot.json"
    excluded = root / "excluded.json"
    A.write_json(snapshot, {"entries": entries})
    A.write_json(excluded, {"splits": {"train": []}})
    config: JsonDict = {
        "snapshot": {"path": str(snapshot), "sha256": A.sha256_file(snapshot)},
        "excluded_manifests": [{"path": str(excluded), "sha256": A.sha256_file(excluded)}],
        "image_root": str(project),
        "seed": 1,
        "images": 4,
        "reserves": 4,
        "minimum_groups": 2,
        "output": str(root / "experiment report/.local/old"),
        "report": str(root / "experiment report/old.json"),
    }
    old_config = root / "old-config.json"
    A.write_json(old_config, config)
    result = C(root, old_config).reserve()
    manifest_path = Path(result["manifest"])
    manifest = A.read_json(manifest_path)
    # Freeze a synthetic prior cohort containing one primary and one reserve GUI.
    for row in [manifest["primary"][1], manifest["reserves"][0]]:
        meta = Path(str(project / row["path"]) + ".meta")
        meta.write_text("TextureImporter:\n  textureType: 2\n  textureShape: 1\n")
        row["meta_sha256"] = A.sha256_file(meta)
    manifest.pop("fingerprint")
    manifest["fingerprint"] = A.fingerprint(manifest)
    A.write_json(manifest_path, manifest)
    result["manifest_sha256"] = A.sha256_file(manifest_path)
    A.write_json(Path(config["report"]), result)
    revised = dict(config)
    revised.update(
        output=str(root / "experiment report/.local/new"),
        report=str(root / "experiment report/new.json"),
        reserves=2,
        expected_replacements=1,
        prior={
            name: {"path": str(path), "sha256": A.sha256_file(path)}
            for name, path in {
                "config": old_config,
                "report": Path(config["report"]),
                "manifest": manifest_path,
            }.items()
        },
    )
    revised_path = root / "new-config.json"
    A.write_json(revised_path, revised)
    return revised_path


def test_revision_preserves_positions_and_consumes_original_reserves(tmp_path: Path) -> None:
    config_path = make_revision(tmp_path)
    config = A.read_json(config_path)
    old = A.read_json(Path(config["prior"]["manifest"]["path"]))
    result = R(tmp_path, config_path).revise()
    revised = A.read_json(Path(result["manifest"]))
    assert revised["primary"] == [old["primary"][0], old["reserves"][1], *old["primary"][2:]]
    assert revised["reserves"] == old["reserves"][2:]
    assert result["replaced_primary"] == 1 and result["eligible_readable_sources"] == 6
    assert result["historical_asset_group_source_md4_overlaps"] == 0
    assert not result["test_opened"] and not result["native_pixels_audited"]
    for binding in config["prior"].values():
        assert A.sha256_file(Path(binding["path"])) == binding["sha256"]
    with pytest.raises(FileExistsError):
        R(tmp_path, config_path)


@pytest.mark.parametrize("change", ["source", "meta", "manifest", "count", "decode"])
def test_invalid_revision_fails_before_output(tmp_path: Path, change: str) -> None:
    config_path = make_revision(tmp_path)
    config = A.read_json(config_path)
    manifest_path = Path(config["prior"]["manifest"]["path"])
    manifest = A.read_json(manifest_path)
    source = Path(config["image_root"]) / manifest["primary"][0]["path"]
    if change == "source":
        source.write_bytes(b"changed")
    elif change == "meta":
        Path(str(source) + ".meta").write_text("changed")
    elif change == "manifest":
        manifest_path.write_text("{}")
    elif change == "count":
        config["expected_replacements"] = 2
        A.write_json(config_path, config)
    else:
        # A hash-valid unreadable image must fail, never be silently replaced.
        source.write_bytes(b"not an image")
        row = manifest["primary"][0]
        row.update(
            fileHash=MD4.new(source.read_bytes()).hexdigest(),
            source_sha256=A.sha256_file(source),
            source_bytes=source.stat().st_size,
        )
        manifest.pop("fingerprint")
        manifest["fingerprint"] = A.fingerprint(manifest)
        A.write_json(manifest_path, manifest)
        prior_report = Path(config["prior"]["report"]["path"])
        report = A.read_json(prior_report)
        report["manifest_sha256"] = A.sha256_file(manifest_path)
        A.write_json(prior_report, report)
        config["prior"]["report"]["sha256"] = A.sha256_file(prior_report)
        config["prior"]["manifest"]["sha256"] = A.sha256_file(manifest_path)
        A.write_json(config_path, config)
    with pytest.raises((ValueError, OSError)):
        R(tmp_path, config_path).revise()
    assert not Path(config["output"]).exists()
    assert not Path(config["report"]).exists()


def test_missing_legacy_fields_are_not_guessed() -> None:
    assert (
        R.metadata_integer("TextureImporter:\n  mipmaps:\n    textureType: 2\n", "textureType")
        is None
    )
    assert R.metadata_integer("  textureType: 5\n", "textureType") == 5
    with pytest.raises(ValueError, match="Ambiguous"):
        R.metadata_integer("  textureType: 0\n  textureType: 2\n", "textureType")
