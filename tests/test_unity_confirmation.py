"""Reservation must stay disjoint from observed groups and bind actual source files."""

from __future__ import annotations

from pathlib import Path

import pytest
from Crypto.Hash import MD4

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation import UnityConfirmationCohort


def write_asset(image_root: Path, name: str, content: bytes) -> str:
    path = image_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    Path(str(path) + ".meta").write_text("import settings", encoding="utf-8")
    return MD4.new(content).hexdigest()


def fixture_config(root: Path, suffix: str = "a") -> Path:
    images = root / "project"
    seen_hash = write_asset(images, "Assets/Seen/old.png", b"seen")
    records = {
        "Assets/Seen/old.png": {"fileHash": seen_hash},
        "Assets/Seen/another.png": {"fileHash": "1" * 32},
        "Assets/Alias/old.png": {"fileHash": seen_hash},
    }
    for i in range(12):
        name = f"Assets/New{i}/image.png"
        records[name] = {"fileHash": write_asset(images, name, f"unseen-{i}".encode())}
    snapshot = root / f"snapshot-{suffix}.json"
    exclusions = root / f"excluded-{suffix}.json"
    A.write_json(snapshot, {"entries": records})
    A.write_json(
        exclusions, {"splits": {"test": [{"path": "Assets/Seen/old.png", "fileHash": seen_hash}]}}
    )
    config: JsonDict = {
        "snapshot": {"path": str(snapshot), "sha256": A.sha256_file(snapshot)},
        "excluded_manifests": [{"path": str(exclusions), "sha256": A.sha256_file(exclusions)}],
        "image_root": str(images),
        "seed": 20261112,
        "images": 4,
        "reserves": 2,
        "minimum_groups": 2,
        "output": str(root / "experiment report/.local" / suffix),
        "report": str(root / "experiment report" / f"{suffix}.json"),
    }
    path = root / f"config-{suffix}.json"
    A.write_json(path, config)
    return path


def test_excludes_prior_test_groups_and_content_without_reading_labels(tmp_path: Path) -> None:
    path = fixture_config(tmp_path)
    result = UnityConfirmationCohort(tmp_path, path).reserve()
    manifest = A.read_json(Path(result["manifest"]))
    assert result["status"] == "reserved"
    assert (result["primary_images"], result["reserve_images"]) == (4, 2)
    assert result["exclusions"] == {"historical_group": 2, "historical_source_md4": 1}
    assert not result["test_opened"] and not result["native_labels_collected"]
    assert not result["native_pixels_audited"] and not result["model_sealed"]
    for row in manifest["primary"] + manifest["reserves"]:
        assert row["group"].startswith("assets/new")
        assert set(row) == {
            "path",
            "fileHash",
            "group",
            "rank",
            "source_sha256",
            "source_bytes",
            "meta_sha256",
        }


def test_reservation_is_deterministic(tmp_path: Path) -> None:
    first = UnityConfirmationCohort(tmp_path, fixture_config(tmp_path, "a")).reserve()
    second = UnityConfirmationCohort(tmp_path, fixture_config(tmp_path, "b")).reserve()
    a, b = (A.read_json(Path(r["manifest"])) for r in [first, second])
    assert a["primary"] == b["primary"] and a["reserves"] == b["reserves"]


@pytest.mark.parametrize("input_name", ["snapshot", "excluded_manifests"])
def test_changed_inputs_rejected_before_output_creation(tmp_path: Path, input_name: str) -> None:
    path = fixture_config(tmp_path)
    config = A.read_json(path)
    source = config[input_name] if input_name == "snapshot" else config[input_name][0]
    Path(source["path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="input changed"):
        UnityConfirmationCohort(tmp_path, path).reserve()
    assert not Path(config["output"]).exists()


def test_missing_or_changed_source_retained_as_rejection(tmp_path: Path) -> None:
    path = fixture_config(tmp_path)
    config = A.read_json(path)
    config.update(images=11, reserves=0)
    A.write_json(path, config)
    (tmp_path / "project/Assets/New0/image.png").write_bytes(b"changed")
    (tmp_path / "project/Assets/New1/image.png.meta").unlink()
    result = UnityConfirmationCohort(tmp_path, path).reserve()
    assert result["status"] == "incomplete"
    assert result["primary_images"] == 10
    assert result["exclusions"]["source_md4_changed"] == 1
    assert result["exclusions"]["missing_source_or_meta"] == 1


@pytest.mark.parametrize("bad_path", ["../x", "C:/x", "Assets/../outside.png", "/Assets/x"])
def test_unsafe_asset_paths_rejected(bad_path: str) -> None:
    with pytest.raises(ValueError, match="asset path"):
        UnityConfirmationCohort.asset_path(bad_path)


def test_existing_reservation_cannot_be_replaced(tmp_path: Path) -> None:
    path = fixture_config(tmp_path)
    result = UnityConfirmationCohort(tmp_path, path).reserve()
    digest = A.sha256_file(Path(result["manifest"]))
    with pytest.raises(FileExistsError):
        UnityConfirmationCohort(tmp_path, path)
    assert A.sha256_file(Path(result["manifest"])) == digest


def test_report_cannot_overwrite_manifest(tmp_path: Path) -> None:
    path = fixture_config(tmp_path)
    config = A.read_json(path)
    config["report"] = str(Path(config["output"]) / "manifest.json")
    A.write_json(path, config)
    with pytest.raises(ValueError, match="Report belongs"):
        UnityConfirmationCohort(tmp_path, path)


def test_package_cache_entry_is_counted_outside_project_scope(tmp_path: Path) -> None:
    path = fixture_config(tmp_path)
    config = A.read_json(path)
    snapshot_path = Path(config["snapshot"]["path"])
    snapshot = A.read_json(snapshot_path)
    snapshot["entries"]["Packages/com.unity.recorder/icon.png"] = {"fileHash": "1" * 32}
    A.write_json(snapshot_path, snapshot)
    config["snapshot"]["sha256"] = A.sha256_file(snapshot_path)
    A.write_json(path, config)
    result = UnityConfirmationCohort(tmp_path, path).reserve()
    assert result["status"] == "reserved"
    assert result["exclusions"]["outside_project_assets"] == 1


def test_report_claim_prevents_two_preconstructed_writers(tmp_path: Path) -> None:
    first_path = fixture_config(tmp_path, "a")
    second_path = fixture_config(tmp_path, "b")
    first_config = A.read_json(first_path)
    second_config = A.read_json(second_path)
    second_config["report"] = first_config["report"]
    A.write_json(second_path, second_config)
    first = UnityConfirmationCohort(tmp_path, first_path)
    second = UnityConfirmationCohort(tmp_path, second_path)
    first.reserve()
    before = A.sha256_file(Path(first_config["report"]))
    with pytest.raises(FileExistsError):
        second.reserve()
    assert before == A.sha256_file(Path(first_config["report"]))
    assert not Path(second_config["output"]).exists()


@pytest.mark.parametrize("category", ["Characters", "Monster", "Environment"])
def test_mixed_case_special_groups_are_still_historical(tmp_path: Path, category: str) -> None:
    path = fixture_config(tmp_path)
    config = A.read_json(path)
    excluded_path = Path(config["excluded_manifests"][0]["path"])
    excluded = A.read_json(excluded_path)
    excluded["splits"]["test"].append(
        {"path": f"Assets/Art/{category}/HeroA/Textures/old.png", "fileHash": "2" * 32}
    )
    A.write_json(excluded_path, excluded)
    config["excluded_manifests"][0]["sha256"] = A.sha256_file(excluded_path)
    snapshot_path = Path(config["snapshot"]["path"])
    snapshot = A.read_json(snapshot_path)
    name = f"Assets/art/{category.swapcase()}/HeroA/Materials/new.png"
    digest = write_asset(Path(config["image_root"]), name, b"new version of old group")
    snapshot["entries"][name] = {"fileHash": digest}
    A.write_json(snapshot_path, snapshot)
    config["snapshot"]["sha256"] = A.sha256_file(snapshot_path)
    A.write_json(path, config)
    result = UnityConfirmationCohort(tmp_path, path).reserve()
    assert result["exclusions"]["historical_group"] == 3
    manifest = A.read_json(Path(result["manifest"]))
    assert all(row["path"] != name for row in manifest["primary"] + manifest["reserves"])
