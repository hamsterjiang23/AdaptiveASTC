"""Protect timing acceptance and the published directional-search boundaries."""

import hashlib
import json
import math
from pathlib import Path

import pytest
from PIL import Image

from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.common.upstream import BaselineGate
from reproductions.nah2022_psnr_search.search import FOOTPRINTS, PSNRBlockSearch
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.recovery import BaselineRecovery


def test_search_returns_smallest_even_if_target_is_unattainable() -> None:
    result = PSNRBlockSearch().select(lambda _block: 10.0, (6, 6), 35.0)
    assert result.footprint == (4, 4)
    assert not result.search_target_met


def test_search_stops_at_first_failure_in_larger_direction() -> None:
    def quality(block: tuple[int, int]) -> float:
        return 36.0 if FOOTPRINTS.index(block) <= 6 else 34.0

    result = PSNRBlockSearch().select(quality, (6, 6), 35.0)
    assert result.footprint == (8, 6)
    assert result.measurements[-1] == ((10, 5), 34.0)


def test_missing_native_telemetry_rejects_successful_import(tmp_path: Path) -> None:
    baseline = UnitySearchBaseline(tmp_path, tmp_path, tmp_path / "Unity.exe", tmp_path)
    baseline.run_dir.mkdir(parents=True)
    (baseline.run_dir / "probe-config.json").write_text(
        json.dumps({"assets": [{"path": "Assets/test.png"}]}), encoding="utf-8"
    )
    (baseline.run_dir / "probe-imports.jsonl").write_text(
        json.dumps({"asset": "Assets/test.png", "success": True, "import_wall_ms": 1}) + "\n",
        encoding="utf-8",
    )
    receipt = baseline.summarize("probe")
    assert receipt["status"] == "failed"
    assert receipt["native_records"] == 0


def test_cache_hit_is_not_accepted_as_search(tmp_path: Path) -> None:
    baseline = UnitySearchBaseline(tmp_path, tmp_path, tmp_path / "Unity.exe", tmp_path)
    baseline.run_dir.mkdir(parents=True)
    asset = "Assets/test.png"
    (baseline.run_dir / "probe-config.json").write_text(
        json.dumps({"assets": [{"path": asset}]}), encoding="utf-8"
    )
    (baseline.run_dir / "probe-imports.jsonl").write_text(
        json.dumps({"asset": asset, "success": True, "import_wall_ms": 1}) + "\n", encoding="utf-8"
    )
    (baseline.run_dir / "probe-native.jsonl").write_text(
        json.dumps(
            {
                "asset": asset,
                "success": True,
                "cache_hit": True,
                "search_executed": False,
                "candidates_attempted": 0,
                "candidates_measured": 0,
                "search_ms": 0,
                "select_and_encode_ms": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    receipt = baseline.summarize("probe")
    assert receipt["status"] == "failed"


def test_astc_header_uses_ceil_blocks_and_separates_container(tmp_path: Path) -> None:
    path = tmp_path / "tiny.astc"
    header = bytes.fromhex("13aba15c") + bytes([6, 6, 1])
    header += (7).to_bytes(3, "little") + (8).to_bytes(3, "little")
    header += (1).to_bytes(3, "little")
    path.write_bytes(header + bytes(64))
    parsed = ASTCFile.read(path)
    assert parsed.footprint == (6, 6)
    assert parsed.payload_bytes == 64
    assert parsed.container_bytes == 80


def test_png_rgba_psnr_keeps_reference_channel_averaging(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    decoded = tmp_path / "decoded.png"
    Image.new("RGB", (2, 2), (100, 100, 100)).save(reference)
    Image.new("RGB", (2, 2), (110, 110, 110)).save(decoded)
    rgb = ASTCEncoder.psnr_rgb(reference, decoded)
    rgba = ASTCEncoder.psnr_rgba(reference, decoded)
    assert rgb == pytest.approx(10 * math.log10(255**2 / 100))
    assert rgba - rgb == pytest.approx(10 * math.log10(4 / 3))
    assert math.isinf(ASTCEncoder.psnr_rgba(reference, reference))


def test_metadata_restore_requires_the_last_written_hash(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = project / "Assets/test.png.meta"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"benchmark override")
    backup_dir = tmp_path / "backups"
    backup = backup_dir / "Assets/test.png.meta"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"original importer settings")
    Path(str(backup) + ".expected.sha256").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8"
    )
    baseline = UnitySearchBaseline(tmp_path, project, tmp_path / "Unity.exe", tmp_path)
    assert baseline.restore_metadata(backup_dir) == []
    assert target.read_bytes() == b"original importer settings"


def test_metadata_restore_preserves_a_concurrent_edit(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = project / "Assets/test.png.meta"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"concurrent user edit")
    backup_dir = tmp_path / "backups"
    backup = backup_dir / "Assets/test.png.meta"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"original importer settings")
    Path(str(backup) + ".expected.sha256").write_text(
        hashlib.sha256(b"benchmark override").hexdigest(), encoding="utf-8"
    )
    baseline = UnitySearchBaseline(tmp_path, project, tmp_path / "Unity.exe", tmp_path)
    assert baseline.restore_metadata(backup_dir)
    assert target.read_bytes() == b"concurrent user edit"


def test_native_asset_casing_is_matched_on_windows(tmp_path: Path) -> None:
    baseline = UnitySearchBaseline(tmp_path, tmp_path, tmp_path / "Unity.exe", tmp_path)
    baseline.run_dir.mkdir(parents=True)
    (baseline.run_dir / "probe-config.json").write_text(
        json.dumps({"assets": [{"path": "Assets/Texture_D.tga"}]}), encoding="utf-8"
    )
    (baseline.run_dir / "probe-imports.jsonl").write_text(
        json.dumps({"asset": "Assets/Texture_D.tga", "success": True, "import_wall_ms": 3}),
        encoding="utf-8",
    )
    entry = {
        "asset": "Assets/Texture_d.tga",
        "success": True,
        "cache_hit": False,
        "search_executed": True,
        "candidates_attempted": 1,
        "candidates_measured": 1,
        "search_ms": 1,
        "select_and_encode_ms": 2,
    }
    (baseline.run_dir / "probe-native.jsonl").write_text(json.dumps(entry), encoding="utf-8")
    receipt = baseline.summarize("probe")
    assert receipt["status"] == "passed"


def test_prepared_config_cannot_be_replaced(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    UnitySearchBaseline._write_frozen(path, {"assets": ["first"]})
    with pytest.raises(FileExistsError, match="Frozen protocol differs"):
        UnitySearchBaseline._write_frozen(path, {"assets": ["other"]})
    assert json.loads(path.read_text()) == {"assets": ["first"]}


def test_literature_gate_requires_native_coverage(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps({"status": "passed", "phase": "full", "expected": 10_000, "imports": 10_000}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="coverage"):
        BaselineGate.require(path)


def test_flat_metadata_index_allows_identical_warmup_entries(tmp_path: Path) -> None:
    project = tmp_path / "project"
    target = project / "Assets/test.png.meta"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"temporary settings")
    backups = tmp_path / "backups"
    backups.mkdir()
    backup = backups / "hashed.meta"
    backup.write_bytes(b"original")
    row = json.dumps({"asset": "Assets/test.png", "backup": "hashed.meta"})
    (backups / "index.jsonl").write_text(row + "\n" + row + "\n", encoding="utf-8")
    Path(str(backup) + ".expected.sha256").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8"
    )
    baseline = UnitySearchBaseline(tmp_path, project, tmp_path / "Unity.exe", tmp_path)
    assert baseline.restore_metadata(backups) == []
    assert target.read_bytes() == b"original"


def test_legacy_metadata_accepts_short_recovery_hash_location(tmp_path: Path) -> None:
    project = tmp_path / "project"
    relative = Path("Assets/test.png.meta")
    target = project / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"temporary settings")
    backups = tmp_path / "backups"
    backup = backups / relative
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"original")
    expected = UnitySearchBaseline.metadata_recovery_hash_path(backups, relative)
    expected.parent.mkdir(parents=True)
    expected.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8")
    baseline = UnitySearchBaseline(tmp_path, project, tmp_path / "Unity.exe", tmp_path)
    assert baseline.restore_metadata(backups) == []
    assert target.read_bytes() == b"original"


def test_override_reconstruction_changes_only_android_settings() -> None:
    original = (
        "  platformSettings:\n  - serializedVersion: 3\n    buildTarget: Android\n"
        "    textureFormat: -1\n    overridden: 0\n    textureCompression: 1\n"
        "    crunchedCompression: 0\n  - serializedVersion: 3\n    buildTarget: iPhone\n"
        "    textureFormat: -1\n    overridden: 0\n"
    )
    expected = original.replace("    textureFormat: -1", "    textureFormat: 51", 1)
    expected = expected.replace("    overridden: 0", "    overridden: 1", 1)
    assert BaselineRecovery._override_metadata(original) == expected


def test_override_reconstruction_appends_android_from_default_settings() -> None:
    defaults = (
        "  - serializedVersion: 3\n    buildTarget: DefaultTexturePlatform\n"
        "    maxTextureSize: 1024\n    textureFormat: -1\n    overridden: 0\n"
        "    textureCompression: 0\n    crunchedCompression: 0\n"
    )
    original = "  platformSettings:\n" + defaults + "  spriteSheet:\n"
    android = defaults.replace("DefaultTexturePlatform", "Android")
    android = android.replace("textureFormat: -1", "textureFormat: 51")
    android = android.replace("overridden: 0", "overridden: 1")
    android = android.replace("textureCompression: 0", "textureCompression: 1")
    assert BaselineRecovery._override_metadata(original) == (
        "  platformSettings:\n" + defaults + android + "  spriteSheet:\n"
    )


@pytest.mark.parametrize("ending", [b'{"asset":', b'{"asset":"\xe4'])
def test_interrupted_metadata_index_still_restores_the_valid_prefix(
    tmp_path: Path, ending: bytes
) -> None:
    project = tmp_path / "project"
    target = project / "Assets/test.png.meta"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"temporary settings")
    backups = tmp_path / "backups"
    backups.mkdir()
    backup = backups / "hashed.meta"
    backup.write_bytes(b"original")
    row = json.dumps({"asset": "Assets/test.png", "backup": "hashed.meta"})
    (backups / "index.jsonl").write_bytes(row.encode("utf-8") + b"\n" + ending)
    Path(str(backup) + ".expected.sha256").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest(), encoding="utf-8"
    )
    baseline = UnitySearchBaseline(tmp_path, project, tmp_path / "Unity.exe", tmp_path)
    conflicts = baseline.restore_metadata(backups)
    assert len(conflicts) == 1
    assert "entry 2" in conflicts[0]
    assert target.read_bytes() == b"original"


def test_native_cache_replays_compacted_snapshot_and_later_updates(tmp_path: Path) -> None:
    log = tmp_path / "parameters.jsonl"
    log.with_suffix(".json").write_text(
        json.dumps(
            {
                "tableConfig": {"psnr": 30},
                "entries": {"Assets/a.png": {"fileHash": "old"}, "Assets/b.png": {"fileHash": "b"}},
            }
        ),
        encoding="utf-8",
    )
    log.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"tableConfig": {"psnr": 30}},
                {"filePath": "Assets/a.png", "fileHash": "updated"},
                {"filePath": "Assets/c.png", "fileHash": "c"},
            ]
        ),
        encoding="utf-8",
    )
    rows = UnitySearchBaseline.read_parameter_cache(log)
    entries = {row["filePath"]: row["fileHash"] for row in rows if "filePath" in row}
    assert entries == {"Assets/a.png": "updated", "Assets/b.png": "b", "Assets/c.png": "c"}


def test_native_cache_rejects_a_snapshot_log_policy_mismatch(tmp_path: Path) -> None:
    log = tmp_path / "parameters.jsonl"
    log.with_suffix(".json").write_text(
        json.dumps({"tableConfig": {"psnr": 30}, "entries": {}}), encoding="utf-8"
    )
    log.write_text(json.dumps({"tableConfig": {"psnr": 35}}), encoding="utf-8")
    with pytest.raises(ValueError, match="incompatible"):
        UnitySearchBaseline.read_parameter_cache(log)
