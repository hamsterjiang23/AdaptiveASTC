"""Exact imported-pixel identity preserves dimensions, alpha and frozen membership."""

from __future__ import annotations

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit as Audit


def png(color: tuple[int, int, int, int], size: tuple[int, int] = (2, 2)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def binding(path: Path, value: JsonDict) -> JsonDict:
    A.write_json(path, value)
    return {"path": str(path), "sha256": A.sha256_file(path)}


def capture(
    root: Path, split: str, color: tuple[int, int, int, int], raw_png: bytes | None = None
) -> JsonDict:
    archive = root / split
    folder = archive / "00000"
    folder.mkdir(parents=True)
    raw = png(color) if raw_png is None else raw_png
    path = folder / "original.png"
    path.write_bytes(raw)
    pixels = Audit.pixel_identity(raw, 2, 2)
    asset = f"Assets/{split}/sample.png"
    row = {
        "path": asset,
        "source_split": split,
        "source_md4": "source-identity",
        "width": 2,
        "height": 2,
        "reference_rgb_sha256": pixels["rgb_sha256"],
        "artifacts_sha256": {"original.png": A.sha256_file(path)},
        "selection": {"block_size": "12x12", "preset": "fastest"},
    }
    manifest = binding(
        archive / "manifest.json",
        {
            "reference_capture": [row],
            "splits": {split: [{"path": asset}]},
        },
    )
    reference = binding(
        archive / "receipt.json",
        {
            "status": "passed",
            "images": 1,
            "rows": [row],
            "manifest_sha256": manifest["sha256"],
        },
    )
    options = binding(
        archive / "options.json",
        {
            "status": "passed",
            "images": 1,
            "capture_receipt_sha256": reference["sha256"],
            "managed_source_restoration": {
                "status": "restored",
                "original_sha256": "same",
                "restored_sha256": "same",
            },
            "rows": [
                {
                    "index": 0,
                    "path": asset,
                    "width": 2,
                    "height": 2,
                    "rgba_sha256": pixels["callback_rgba_sha256"],
                    "need_alpha": True,
                    "profile": 0,
                    "normal_pack": False,
                    "channel": 4,
                    "srgb_importer": True,
                    "texture_type_importer": "Default",
                }
            ],
        },
    )
    phase = binding(
        archive / "phase.json",
        {
            "status": "passed",
            "process_exit_code": 0,
            "metadata_restore_conflicts": [],
        },
    )
    return {
        "run_id": split,
        "source_split": split,
        "reference_receipt": reference,
        "options_receipt": options,
        "phase_receipt": phase,
    }


def config(root: Path, alpha: int = 255) -> Path:
    path = root / "config.json"
    A.write_json(
        path,
        {
            "batches": [
                capture(root, "train", (10, 20, 30, 255)),
                capture(root, "validation", (10, 20, 30, alpha)),
            ],
            "expected_counts": {"train": 1, "validation": 1},
            "output": str(root / "details"),
            "report": str(root / "report.json"),
        },
    )
    return path


def test_exact_duplicates_are_reported_without_changing_splits(tmp_path: Path) -> None:
    result = Audit(config(tmp_path)).run()
    assert result["rgba"]["cross_split_groups"] == 1
    assert result["rgba"]["cross_split_images"] == {"train": 1, "validation": 1}
    assert result["constant_rgba_images"] == 2
    assert result["counts"] == {"train": 1, "validation": 1}
    assert result["training_updates"] == 0
    assert result["splits_modified"] is False
    assert result["independent_test_isolation_proven"] is False
    assert result["test_opened"] is False


def test_rgb_only_duplicate_is_not_rgba_identity(tmp_path: Path) -> None:
    result = Audit(config(tmp_path, 100)).run()
    assert result["rgba"]["duplicate_groups"] == 0
    assert result["rgb_only"]["cross_split_groups"] == 1
    assert result["rgb_only"]["groups_with_different_rgba"] == 1


def test_dimensions_are_part_of_exact_identity() -> None:
    first = Audit.pixel_identity(png((1, 2, 3, 255), (2, 4)), 2, 4)
    other = Audit.pixel_identity(png((1, 2, 3, 255), (4, 2)), 4, 2)
    assert first["rgba_sha256"] == other["rgba_sha256"]
    assert first["rgba_identity"] != other["rgba_identity"]
    assert first["rgb_identity"] != other["rgb_identity"]


def test_lossless_file_encoding_and_modes_do_not_define_pixel_identity() -> None:
    rgba = png((1, 2, 3, 255))
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (1, 2, 3)).save(buffer, format="PNG", compress_level=0)
    assert hashlib.sha256(rgba).digest() != hashlib.sha256(buffer.getvalue()).digest()
    assert Audit.pixel_identity(rgba, 2, 2) == Audit.pixel_identity(buffer.getvalue(), 2, 2)


def test_native_callback_rows_are_flipped_but_pixel_identity_is_not(tmp_path: Path) -> None:
    top = bytes([1, 2, 3, 255] * 2)
    bottom = bytes([40, 50, 60, 100] * 2)
    buffer = io.BytesIO()
    Image.frombytes("RGBA", (2, 2), top + bottom).save(buffer, format="PNG")
    raw = buffer.getvalue()
    identities = Audit.pixel_identity(raw, 2, 2)
    assert identities["rgba_sha256"] == hashlib.sha256(top + bottom).hexdigest()
    assert identities["callback_rgba_sha256"] == hashlib.sha256(bottom + top).hexdigest()
    path = config(tmp_path)
    batch = capture(tmp_path, "confirmation", (0, 0, 0, 0), raw)
    assert Audit(path).batch_rows(batch)[0]["rgba_identity"] == identities["rgba_identity"]


@pytest.mark.parametrize("failure", ["png", "manifest", "options", "reference", "phase"])
def test_changed_frozen_artifact_is_rejected(tmp_path: Path, failure: str) -> None:
    path = config(tmp_path)
    batch = A.read_json(path)["batches"][0]
    if failure == "png":
        victim = tmp_path / "train/00000/original.png"
        victim.write_bytes(png((40, 20, 30, 255)))
    else:
        victim = (
            tmp_path / "train/manifest.json"
            if failure == "manifest"
            else Path(batch[f"{failure}_receipt"]["path"])
        )
        victim.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        Audit(path).run()
    assert A.read_json(tmp_path / "report.json")["status"] == "failed"


@pytest.mark.parametrize("failure", ["callback_hash", "restoration", "order", "split", "exit"])
def test_consistently_rebound_but_invalid_capture_is_rejected(
    tmp_path: Path,
    failure: str,
) -> None:
    path = config(tmp_path)
    cfg = A.read_json(path)
    batch = cfg["batches"][0]
    key = "phase_receipt" if failure == "exit" else "options_receipt"
    target = Path(batch[key]["path"])
    value = A.read_json(target)
    if failure == "callback_hash":
        value["rows"][0]["rgba_sha256"] = "incorrect"
    elif failure == "restoration":
        value["managed_source_restoration"]["restored_sha256"] = "changed"
    elif failure == "order":
        value["rows"][0]["index"] = 1
    elif failure == "split":
        batch["source_split"] = "test"
    else:
        value["process_exit_code"] = 1
    batch[key] = binding(target, value)
    A.write_json(path, cfg)
    with pytest.raises(ValueError):
        Audit(path).run()


def test_repeated_asset_or_wrong_counts_cannot_masquerade_as_coverage(tmp_path: Path) -> None:
    path = config(tmp_path)
    cfg = A.read_json(path)
    cfg["batches"].append(cfg["batches"][0])
    cfg["expected_counts"]["train"] = 2
    A.write_json(path, cfg)
    with pytest.raises(ValueError, match="more than once"):
        Audit(path).run()


def test_wrong_expected_counts_fail(tmp_path: Path) -> None:
    path = config(tmp_path)
    cfg = A.read_json(path)
    cfg["expected_counts"]["train"] = 10000
    A.write_json(path, cfg)
    with pytest.raises(ValueError, match="coverage"):
        Audit(path).run()


def test_existing_run_is_never_overwritten(tmp_path: Path) -> None:
    path = config(tmp_path)
    Audit(path).run()
    original = (tmp_path / "report.json").read_bytes()
    with pytest.raises(FileExistsError):
        Audit(path).run()
    assert (tmp_path / "report.json").read_bytes() == original


def test_dimension_mismatch_fails() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        Audit.pixel_identity(png((1, 2, 3, 255)), 3, 3)


def test_report_cannot_alias_or_live_inside_raw_output(tmp_path: Path) -> None:
    path = config(tmp_path)
    cfg = A.read_json(path)
    cfg["report"] = str(Path(cfg["output"]) / "pixel-identities.json")
    A.write_json(path, cfg)
    with pytest.raises(ValueError, match="outside"):
        Audit(path).run()
    assert not Path(cfg["output"]).exists()


def test_concurrent_runs_cannot_share_public_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = config(tmp_path)
    cfg = A.read_json(first)
    cfg["output"] = str(tmp_path / "other-details")
    second = tmp_path / "second-config.json"
    A.write_json(second, cfg)
    barrier = Barrier(2)
    original_mkdir = Path.mkdir
    outputs = {tmp_path / "details", tmp_path / "other-details"}

    def synchronized_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)
        if self in outputs and not exist_ok:
            barrier.wait(timeout=10)

    def attempt(path: Path) -> str:
        try:
            return Audit(path).run()["status"]
        except FileExistsError:
            return "identity_already_claimed"

    monkeypatch.setattr(Path, "mkdir", synchronized_mkdir)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attempt, [first, second]))
    assert sorted(statuses) == ["identity_already_claimed", "passed"]
    report = A.read_json(tmp_path / "report.json")
    assert report["status"] == "passed"
    assert A.sha256_file(Path(report["details"])) == report["details_sha256"]
    assert len(A.read_json(Path(report["details"]))["rows"]) == 2
