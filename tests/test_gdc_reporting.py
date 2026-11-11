"""Reject cross-dataset label and training costs at the public report boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from adaptive_astc.config import CLASSES
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.gdc2023.costs import PreparationCost
from reproductions.gdc2023.reporting import GDCReport


def report_fixture(root: Path) -> tuple[Path, Path, dict[str, Any]]:
    """Create synthetic metadata containers, with no native encoding or model execution."""
    run, output = root / "run", root / "evaluation"
    folder = output / "00000"
    folder.mkdir(parents=True)
    for name in ["input.png", "selected.png", "fixed8.png"]:
        Image.new("RGB", (4, 4)).save(folder / name)
    header = bytes.fromhex("13aba15c") + bytes([8, 8, 1])
    header += (4).to_bytes(3, "little") * 2 + (1).to_bytes(3, "little")
    for kind in ["selected", "fixed8"]:
        (folder / f"{kind}.astc").write_bytes(header + bytes(16))
        (folder / f"{kind}.txt").write_text("synthetic report fixture", encoding="utf-8")
    timings = {
        name: 1.0
        for name in [
            "model_pipeline_seconds",
            "fixed8_pipeline_seconds",
            "source_rgb_seconds",
            "classifier_preprocessing_seconds",
            "inference_seconds",
            "final_encode_seconds",
            "verification_seconds",
        ]
    }
    sample = {
        "status": "passed",
        "path": "Assets/a.png",
        "fileHash": "hash",
        "lossless": True,
        "rgb_psnr": None,
        "fixed8_rgb_psnr": None,
        "fixed8_lossless": True,
        "target_met": True,
        "fixed8_target_met": True,
        "label_target_met": True,
        "payload_bytes": 16,
        "fixed8_payload_bytes": 16,
        "label_payload_bytes": 16,
        "predicted_class": 1,
        "label_class": 3,
        "timings": timings,
        "artifacts_sha256": {
            path.name: ArtifactStore.sha256_file(path) for path in folder.iterdir()
        },
    }
    ArtifactStore.write_json(folder / "receipt.json", sample)
    source = {"split": "test", "path": "Assets/a.png", "fileHash": "hash"}
    protocol = {"target_psnr": 35.0, "inputs": [source]}
    ArtifactStore.write_json(run / "protocol.json", protocol)
    labels = run / "labels/00000"
    labels.mkdir(parents=True)
    (labels / "input.png").write_bytes((folder / "input.png").read_bytes())
    candidates = []
    for name in CLASSES:
        size = int(name.split("x")[0])
        candidate_header = header[:4] + bytes([size, size, 1]) + header[7:]
        (labels / f"{name}.astc").write_bytes(candidate_header + bytes(16))
        (labels / f"{name}.png").write_bytes((folder / "input.png").read_bytes())
        (labels / f"{name}.txt").write_text("synthetic offline control", encoding="utf-8")
        candidates.append(
            {
                "name": name,
                "footprint": [size, size],
                "payload_bytes": 16,
                "container_bytes": 32,
                "rgb_psnr": None,
                "lossless": True,
                "timings": {"encode_seconds": 1.0},
            }
        )
    ArtifactStore.write_json(
        labels / "receipt.json",
        {
            "status": "passed",
            "index": 0,
            **source,
            "protocol_fingerprint": ArtifactStore.fingerprint(protocol),
            "candidates": candidates,
            "selected": candidates[-1],
            "target_met": True,
            "fallback": None,
            "artifacts_sha256": {
                path.name: ArtifactStore.sha256_file(path) for path in labels.iterdir()
            },
        },
    )
    protocol_sha = ArtifactStore.sha256_file(run / "protocol.json")
    ArtifactStore.write_json(
        run / "collection.json",
        {"status": "passed", "protocol_sha256": protocol_sha, "wall_seconds": 1.0, "workers": 1},
    )
    manifest = {
        "label_protocol_sha256": protocol_sha,
        "label_collection_sha256": ArtifactStore.sha256_file(run / "collection.json"),
        "splits": {
            "test": [
                {
                    "path": source["path"],
                    "fileHash": source["fileHash"],
                    "class_id": 3,
                    "label_receipt_sha256": ArtifactStore.sha256_file(labels / "receipt.json"),
                }
            ]
        },
        "smoke": True,
    }
    manifest["fingerprint"] = ArtifactStore.fingerprint(manifest)
    ArtifactStore.write_json(run / "manifest.json", manifest)
    model = run / "pretrained"
    model.mkdir()
    for name in ["best.pt", "last.pt", "training_complete.json"]:
        (model / name).write_bytes(b"metadata-fixture")
    model_sha = ArtifactStore.sha256_file(model / "best.pt")
    costs = {
        "status": "passed",
        "data_fingerprint": manifest["fingerprint"],
        "initialization": "pretrained",
        "model_sha256": model_sha,
        "training_complete_sha256": ArtifactStore.sha256_file(model / "training_complete.json"),
        "checkpoint_last_sha256": ArtifactStore.sha256_file(model / "last.pt"),
    }
    ArtifactStore.write_json(model / "wall-clock.json", costs)
    batch = {
        "status": "passed",
        "images": 1,
        "protocol_sha256": protocol_sha,
        "binding": {
            "data_fingerprint": manifest["fingerprint"],
            "initialization": "pretrained",
            "split": "test",
            "checkpoint_sha256": model_sha,
            "training_files_sha256": {
                name: ArtifactStore.sha256_file(model / name)
                for name in ["last.pt", "training_complete.json", "wall-clock.json"]
            },
        },
        "results": [
            {"index": 0, "receipt_sha256": ArtifactStore.sha256_file(folder / "receipt.json")}
        ],
        "scope": "synthetic_metadata_fixture",
        "setup_seconds": 1.0,
        "wall_seconds": 1.0,
    }
    ArtifactStore.write_json(output / "receipt.json", batch)
    return run, output, batch


@pytest.mark.parametrize("damage", ["manifest", "collection", "cost_data", "cost_model"])
def test_report_rejects_foreign_label_and_training_provenance(tmp_path: Path, damage: str) -> None:
    run, output, batch = report_fixture(tmp_path)
    if damage == "manifest":
        path = run / "manifest.json"
        manifest = ArtifactStore.read_json(path)
        manifest["smoke"] = False
        ArtifactStore.write_json(path, manifest)
    elif damage == "collection":
        path = run / "collection.json"
        collection = ArtifactStore.read_json(path)
        collection["wall_seconds"] = 999
        ArtifactStore.write_json(path, collection)
    else:
        path = run / "pretrained/wall-clock.json"
        costs = ArtifactStore.read_json(path)
        costs["data_fingerprint" if damage == "cost_data" else "model_sha256"] = "FOREIGN"
        ArtifactStore.write_json(path, costs)
        batch["binding"]["training_files_sha256"]["wall-clock.json"] = ArtifactStore.sha256_file(
            path
        )
        ArtifactStore.write_json(output / "receipt.json", batch)
    destination = tmp_path / "report"
    with pytest.raises(ValueError):
        GDCReport(tmp_path, run, output, destination).write()
    assert not destination.exists()


def test_report_controls_require_frozen_candidate_receipts(tmp_path: Path) -> None:
    run, output, _ = report_fixture(tmp_path)
    destination = tmp_path / "report"
    GDCReport(tmp_path, run, output, destination).write()
    summary = ArtifactStore.read_json(destination / "pretrained-test.json")
    assert set(summary["offline_fixed_footprints"]) == set(CLASSES)
    for control in summary["offline_fixed_footprints"].values():
        assert control["target_met"] == 1 and control["payload_bytes"] == 16
        assert control["lossless"] == 1 and control["finite_mean_psnr"] is None
        assert control["offline_encode_seconds"] == 1.0
    changed = run / "labels/00000/receipt.json"
    label = ArtifactStore.read_json(changed)
    label["candidates"][0]["rgb_psnr"] = 999
    ArtifactStore.write_json(changed, label)
    with pytest.raises(ValueError, match="offline control receipt changed"):
        GDCReport(tmp_path, run, output, tmp_path / "rejected").write()
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("foreign", [False, True])
def test_preparation_process_cost_binds_the_evaluated_dataset(
    tmp_path: Path, foreign: bool
) -> None:
    run, output, batch = report_fixture(tmp_path)
    preparation = {
        "status": "passed",
        "process_exit_code": 0,
        "start_utc": "2026-11-11T00:00:00+00:00",
        "end_utc": "2026-11-11T00:00:02+00:00",
        "wall_seconds": 2.0,
        "protocol_sha256": ArtifactStore.sha256_file(run / "protocol.json"),
        "collection_sha256": ArtifactStore.sha256_file(run / "collection.json"),
        "manifest_sha256": "FOREIGN"
        if foreign
        else ArtifactStore.sha256_file(run / "manifest.json"),
    }
    ArtifactStore.write_json(run / "preparation-process.json", preparation)
    batch["binding"]["preparation_process_sha256"] = ArtifactStore.sha256_file(
        run / "preparation-process.json"
    )
    ArtifactStore.write_json(output / "receipt.json", batch)
    destination = tmp_path / "report"
    writer = GDCReport(tmp_path, run, output, destination)
    if foreign:
        with pytest.raises(ValueError, match="evaluated dataset"):
            writer.write()
        assert not destination.exists()
    else:
        writer.write()
        summary = ArtifactStore.read_json(destination / "pretrained-test.json")
        assert summary["costs"]["data_preparation_process"]["wall_seconds"] == 2.0


@pytest.mark.parametrize("content", ["{}", '{"status":"passed"}', '{"status":'])
def test_incomplete_optional_process_cost_stays_unknown(tmp_path: Path, content: str) -> None:
    run, output, batch = report_fixture(tmp_path)
    path = run / "preparation-process.json"
    path.write_text(content, encoding="utf-8")
    assert PreparationCost.load_optional(path) is None
    batch["binding"]["preparation_process_sha256"] = ArtifactStore.sha256_file(path)
    ArtifactStore.write_json(output / "receipt.json", batch)
    destination = tmp_path / "report"
    GDCReport(tmp_path, run, output, destination).write()
    summary = ArtifactStore.read_json(destination / "pretrained-test.json")
    assert summary["costs"]["data_preparation_process"]["wall_seconds"] is None
