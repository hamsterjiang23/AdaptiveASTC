"""Reject cross-dataset label and training costs at the public report boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from adaptive_astc.utils.artifacts import ArtifactStore
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
        "label_class": 1,
        "timings": timings,
        "artifacts_sha256": {
            path.name: ArtifactStore.sha256_file(path) for path in folder.iterdir()
        },
    }
    ArtifactStore.write_json(folder / "receipt.json", sample)
    ArtifactStore.write_json(run / "protocol.json", {"target_psnr": 35.0})
    protocol_sha = ArtifactStore.sha256_file(run / "protocol.json")
    ArtifactStore.write_json(
        run / "collection.json",
        {"status": "passed", "protocol_sha256": protocol_sha, "wall_seconds": 1.0, "workers": 1},
    )
    manifest = {
        "label_protocol_sha256": protocol_sha,
        "label_collection_sha256": ArtifactStore.sha256_file(run / "collection.json"),
        "splits": {"test": [{"path": "Assets/a.png", "fileHash": "hash"}]},
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
