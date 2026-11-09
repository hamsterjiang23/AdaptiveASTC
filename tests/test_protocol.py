"""Regression tests for data isolation, candidate filtering, and calibration."""

import struct
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pytest
import torch
from PIL import Image

from adaptive_astc.common import CLASSES, fingerprint, write_json
from adaptive_astc.data import (
    NearDuplicateIndex,
    asset_group,
    assign_folds,
    audit_manifests,
    catalog,
    decode_candidate,
    quotas,
    select_split_folds,
)
from adaptive_astc.metrics import fit_temperature, probability_metrics
from adaptive_astc.training import require_completed_training, save_checkpoint


def test_quotas_and_classes() -> None:
    assert CLASSES == ("6x6", "8x8", "10x10", "12x12")
    assert quotas([1, 1, 1, 1], 7) == [2, 2, 2, 1]
    assert sum(quotas([36569, 26117, 21333, 78320], 10000)) == 10000


def test_asset_resolution_and_character_groups() -> None:
    assert asset_group("Assets/Art/Effects/Common/HD/a.png") == asset_group(
        "Assets/Art/Effects/Common/SD/b.png"
    )
    assert asset_group("Assets/Art/Characters/HeroA/skin/a.png") == "Assets/Art/Characters/HeroA"


def test_folds_are_deterministic_and_group_disjoint() -> None:
    rows = [
        {"path": str(index), "class_id": index % 4, "group": str(index // 4)}
        for index in range(160)
    ]
    first = assign_folds([dict(row) for row in rows])
    second = assign_folds([dict(row) for row in rows])
    assert fingerprint(first) == fingerprint(second)
    for group in {row["group"] for row in first}:
        assert len({row["fold"] for row in first if row["group"] == group}) == 1


def test_single_asset_fold_cannot_become_formal_holdout() -> None:
    rows = [
        {
            "fold": fold,
            "group": "giant" if fold == 0 else f"{fold}-{index // 4}",
            "class_id": index % 4,
        }
        for fold in range(4)
        for index in range(20)
    ]
    chosen = select_split_folds(rows, {"test": 8, "calibration": 4, "validation": 4, "train": 8}, 2)
    assert chosen == {"test": 1, "calibration": 2, "validation": 3}


def test_near_duplicate_requires_all_criteria() -> None:
    index = NearDuplicateIndex()
    row = {"path": "a.png", "width": 32, "height": 32, "phash": 5}
    preview = np.full((32, 32, 3), 100, dtype=np.uint8)
    index.add(row, preview)
    assert index.match({**row, "path": "b.png", "phash": 7}, preview + 2) == "a.png"
    assert index.match(row, preview + 10) is None
    assert index.match({**row, "width": 64}, preview) is None


def test_cross_split_duplicate_rejected() -> None:
    row = {"fileHash": "same", "group": "same"}
    with pytest.raises(ValueError, match="isolation"):
        audit_manifests({"test": [row], "calibration": [row], "validation": [], "train": []})


def test_catalog_conflicts_deduplication_and_missing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import adaptive_astc.data as data_module
    from adaptive_astc.common import sha256_file

    paths = [
        "Assets/Art/a.png",
        "Assets/Art/copy.png",
        "Assets/Art/b.png",
        "Assets/Art/conflict.png",
        "Assets/Art/missing.png",
    ]
    entries = {}
    for index, path in enumerate(paths):
        if index < 4:
            source = tmp_path / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"placeholder")
        entries[path] = {
            "fileHash": ["duplicate", "duplicate", "conflict", "conflict", "missing"][index],
            "blockSize": ["8x8", "8x8", "6x6", "12x12", "10x10"][index],
            "qualityLevel": "fastest",
            "rdo": False,
            "psnr": 35,
            "msSsimDb": 21,
            "fileSize": 100,
        }
    snapshot = tmp_path / "snapshot.json"
    write_json(snapshot, {"entries": entries, "tableConfig": {}})
    monkeypatch.setattr(data_module, "SNAPSHOT_SHA256", sha256_file(snapshot))
    rows, counts, _ = catalog(snapshot, tmp_path)
    assert len(rows) == 1
    assert counts["conflicting_records"] == 2
    assert counts["conflicting_hash_groups"] == 1
    assert counts["deduplicated_records"] == 1
    assert counts["missing_records"] == 1


def test_corrupt_and_mismatched_images(tmp_path: Path) -> None:
    from Crypto.Hash import MD4

    image = tmp_path / "image.png"
    Image.new("RGBA", (16, 16), (100, 20, 30, 0)).save(image)
    row = {"path": "image.png", "fileHash": "wrong"}
    with pytest.raises(ValueError, match="md4_mismatch"):
        decode_candidate(row, tmp_path, tmp_path / "cache")
    row["fileHash"] = MD4.new(image.read_bytes()).hexdigest()
    decoded, _ = decode_candidate(row, tmp_path, tmp_path / "cache")
    assert decoded["alpha_nonopaque"]
    assert np.load(tmp_path / "cache" / decoded["cache"]).shape == (224, 224, 3)
    with pytest.raises(FileNotFoundError):
        decode_candidate({"path": "missing.png", "fileHash": "none"}, tmp_path, tmp_path)
    image.write_bytes(b"invalid")
    row["fileHash"] = MD4.new(image.read_bytes()).hexdigest()
    with pytest.raises(OSError):
        decode_candidate(row, tmp_path, tmp_path)
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    row["fileHash"] = MD4.new(image.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="truncated_png_header"):
        decode_candidate(row, tmp_path, tmp_path)


def test_temperature_fit_and_argmax() -> None:
    logits = torch.tensor([[9.0, 0, 0, 0], [0, 9.0, 0, 0], [0, 0, 9.0, 0], [0, 0, 0, 9.0]])
    labels = torch.tensor([0, 1, 3, 0])
    fitted = fit_temperature(logits, labels)
    assert fitted["status"] != "failed"
    assert fitted["temperature"] > 0
    assert fitted["fitted_nll"] <= fitted["initial_nll"]
    assert torch.equal(logits.argmax(1), (logits / fitted["temperature"]).argmax(1))
    raw = probability_metrics(logits, labels)
    calibrated = probability_metrics(logits, labels, fitted["temperature"])
    assert raw["accuracy"] == calibrated["accuracy"]
    assert calibrated["nll"] < raw["nll"]


def test_temperature_accepts_inference_mode_outputs() -> None:
    with torch.inference_mode():
        logits = torch.tensor([[9.0, 0, 0, 0], [0, 9.0, 0, 0]])
        labels = torch.tensor([1, 1])
    fitted = fit_temperature(logits, labels)
    assert fitted["status"] != "failed"
    assert fitted["fitted_nll"] <= fitted["initial_nll"]


def test_16_bit_rgb_tiff_rejected(tmp_path: Path) -> None:
    from Crypto.Hash import MD4

    tags = [
        (256, 4, 1, 1),
        (257, 4, 1, 1),
        (258, 3, 3, 134),
        (259, 3, 1, 1),
        (262, 3, 1, 2),
        (273, 4, 1, 140),
        (277, 3, 1, 3),
        (278, 4, 1, 1),
        (279, 4, 1, 6),
        (284, 3, 1, 1),
    ]
    content = (
        b"II"
        + struct.pack("<HIH", 42, 8, len(tags))
        + b"".join(struct.pack("<HHII", *tag) for tag in tags)
        + struct.pack("<IHHHHHH", 0, 16, 16, 16, 65535, 32768, 0)
    )
    path = tmp_path / "highbit.tif"
    path.write_bytes(content)
    row = {"path": path.name, "fileHash": MD4.new(content).hexdigest()}
    with pytest.raises(ValueError, match="unsupported_tiff_bit_depth"):
        decode_candidate(row, tmp_path, tmp_path)


def test_reprepare_preserves_existing_cache_on_recipe_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from Crypto.Hash import MD4

    source = tmp_path / "source.png"
    Image.new("RGB", (16, 16), (100, 50, 20)).save(source)
    row = {"path": source.name, "fileHash": MD4.new(source.read_bytes()).hexdigest()}
    cached, _ = decode_candidate(row, tmp_path, tmp_path / "prepared")
    target = tmp_path / "prepared" / cached["cache"]
    original = target.read_bytes()
    repeated, _ = decode_candidate(row, tmp_path, tmp_path / "prepared")
    assert repeated == cached
    original_save = np.save

    def changed_recipe(file: BinaryIO, array: np.ndarray, allow_pickle: bool) -> None:
        original_save(file, np.zeros_like(array), allow_pickle=allow_pickle)

    monkeypatch.setattr(np, "save", changed_recipe)
    with pytest.raises(RuntimeError, match="new run directory"):
        decode_candidate(row, tmp_path, tmp_path / "prepared")
    assert target.read_bytes() == original


def test_brier_and_bin_boundaries() -> None:
    metrics = probability_metrics(torch.zeros((4, 4)), torch.arange(4))
    assert metrics["brier"] == pytest.approx(0.75)
    assert metrics["nll"] == pytest.approx(np.log(4))
    assert sum(row["count"] for row in metrics["reliability_bins"]) == 4
    with pytest.raises(ValueError):
        probability_metrics(torch.zeros((4, 4)), torch.arange(4), 0)


def test_partial_history_cannot_open_formal_calibration_or_test(tmp_path: Path) -> None:
    write_json(
        tmp_path / "scratch" / "training_complete.json",
        {
            "completed_epochs": 30,
            "config": {"max_steps": 0},
        },
    )
    history = [{"train": {"samples": 128, "steps": 2}} for _ in range(29)]
    history.append({"train": {"samples": 10000, "steps": 157}})
    write_json(tmp_path / "scratch" / "history.json", {"epochs": history})
    with pytest.raises(ValueError, match="30 complete"):
        require_completed_training(tmp_path, "scratch", {"smoke": False})
    require_completed_training(tmp_path, "scratch", {"smoke": True})
    write_json(
        tmp_path / "scratch" / "history.json",
        {
            "epochs": [{"train": {"samples": 10000, "steps": 157}} for _ in range(30)],
        },
    )
    require_completed_training(tmp_path, "scratch", {"smoke": False})


def test_atomic_checkpoint_failure_preserves_previous_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "logits.pt"
    save_checkpoint(destination, {"logits": torch.ones(1)})
    previous = destination.read_bytes()

    def interrupted_save(value: object, path: Path) -> None:
        path.write_bytes(b"partial")
        raise OSError("simulated interruption")

    monkeypatch.setattr(torch, "save", interrupted_save)
    with pytest.raises(OSError, match="interruption"):
        save_checkpoint(destination, {"logits": torch.zeros(1)})
    assert destination.read_bytes() == previous
