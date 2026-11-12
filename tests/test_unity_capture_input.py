"""Capture-only inputs preserve native pixels/properties without reading search supervision."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter as Adapter
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.candidate_completion import UnityCandidateCompletion
from reproductions.unity_search_baseline.capture_input_audit import UnityCaptureInputAudit


def captured_row(
    root: Path, texture_type: str = "Default", split: str = "confirmation"
) -> JsonDict:
    rgba = np.full((7, 250, 4), [0, 0, 0, 255], dtype=np.uint8)
    rgba[0, 1] = [20, 50, 80, 99]
    path = root / "reference.png"
    Image.fromarray(rgba).save(path)
    srgb = texture_type != "NormalMap"
    return {
        "path": "Assets/folder/image.png",
        "source_split": split,
        "reference_png": str(path),
        "reference_sha256": A.sha256_file(path),
        "width": 250,
        "height": 7,
        "actual_options": {
            "path": "Assets/folder/image.png",
            "width": 250,
            "height": 7,
            "need_alpha": True,
            "profile": 0 if srgb else 1,
            "channel": 4,
            "normal_pack": False,
            "srgb_importer": srgb,
            "texture_type_importer": texture_type,
            "rgba_sha256": hashlib.sha256(rgba[::-1].tobytes()).hexdigest(),
        },
        "import_metadata": {
            "asset": "Assets/folder/image.png",
            "success": True,
            "texture_dimension": "Tex2D",
            "srgb": srgb,
            "texture_type": texture_type,
            "mipmaps": True,
            "width": 250,
            "height": 7,
        },
        "selection": {"block_size": "12x12", "preset": "medium"},
        "targets": "does-not-exist.npz",
        "image_quality": "must-not-be-read",
    }


@pytest.mark.parametrize("texture_type", ["Default", "Sprite", "NormalMap"])
def test_capture_inputs_preserve_rgba_padding_split_and_decision_metadata(
    tmp_path: Path,
    texture_type: str,
) -> None:
    row = captured_row(tmp_path, texture_type)
    adapter = Adapter([row], "confirmation")
    dataset = adapter.dataset()
    assert adapter.split == "confirmation" and len(dataset) == 2
    assert dataset.boxes.tolist() == [[0, 0, 240, 7], [240, 0, 10, 7]]
    assert set(dataset[0]) == {"rgba", "valid_mask", "metadata", "patch_index"}
    assert dataset[0]["rgba"][3, 0, 1].item() == pytest.approx(99 / 255)
    assert dataset[1]["valid_mask"].sum().item() == 70
    texture = adapter.decision_inputs[0]
    assert not texture.alpha_constant and texture.need_alpha
    assert texture.black_pixel_ratio == pytest.approx(1 - 1 / (7 * 250))
    assert texture.normal == (texture_type == "NormalMap")
    mips = UnityCandidateCompletion.normal_metric_mips(row["import_metadata"])
    assert adapter.textures[0].normal_metric_mips == (mips if texture.normal else 1)
    assert "selection" not in adapter.bindings[0] and "targets" not in adapter.bindings[0]


def test_search_labels_and_targets_cannot_change_input_or_fingerprint(tmp_path: Path) -> None:
    row = captured_row(tmp_path)
    original = Adapter([row], "confirmation")
    changed = copy.deepcopy(row)
    changed.update(selection=None, targets="deleted.npz", image_quality=None, payload_bytes=None)
    mutated = Adapter([changed], "confirmation")
    assert original.fingerprint == mutated.fingerprint
    assert original.decision_inputs == mutated.decision_inputs
    left, right = original.dataset(), mutated.dataset()
    for index in range(len(left)):
        for key, value in left[index].items():
            torch.testing.assert_close(value, right[index][key], rtol=0, atol=0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", 2),
        ("profile", True),
        ("channel", 3),
        ("channel", True),
        ("need_alpha", 1),
        ("normal_pack", True),
        ("normal_pack", 0),
        ("width", 249),
        ("texture_type_importer", "NormalMap"),
        ("path", "Assets/wrong.png"),
        ("srgb_importer", False),
        ("rgba_sha256", "wrong"),
    ],
)
def test_mismatched_callback_properties_are_rejected(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    row = captured_row(tmp_path)
    row["actual_options"][field] = value
    with pytest.raises(ValueError):
        Adapter([row], "confirmation")


@pytest.mark.parametrize(
    "field,value",
    [
        ("texture_dimension", "Cube"),
        ("texture_type", "Lightmap"),
        ("srgb", False),
        ("mipmaps", 1),
        ("success", False),
        ("height", True),
        ("asset", "Assets/wrong.png"),
    ],
)
def test_mismatched_importer_properties_are_rejected(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    row = captured_row(tmp_path)
    row["import_metadata"][field] = value
    with pytest.raises(ValueError):
        Adapter([row], "confirmation")


@pytest.mark.parametrize("mode", ["split", "duplicate", "dimension", "png_sha", "orientation"])
def test_input_identity_checks(tmp_path: Path, mode: str) -> None:
    row = captured_row(tmp_path)
    rows = [row]
    if mode == "split":
        row["source_split"] = "train"
    elif mode == "duplicate":
        rows.append(copy.deepcopy(row))
        rows[-1]["path"] = row["path"].upper()
    elif mode == "dimension":
        row["width"] = True
    elif mode == "png_sha":
        row["reference_sha256"] = "wrong"
    else:
        with Image.open(row["reference_png"]) as image:
            row["actual_options"]["rgba_sha256"] = hashlib.sha256(image.tobytes()).hexdigest()
    with pytest.raises(ValueError):
        Adapter(rows, "confirmation")


def test_pixel_mutation_before_inference_is_rejected(tmp_path: Path) -> None:
    row = captured_row(tmp_path)
    adapter = Adapter([row], "confirmation")
    Image.new("RGBA", (250, 7)).save(row["reference_png"])
    with pytest.raises(ValueError, match="Bound native input changed"):
        adapter.dataset()


@pytest.mark.parametrize("mipmaps", [True, False])
def test_normal_mip_depth_is_derived_from_input_properties(
    tmp_path: Path,
    mipmaps: bool,
) -> None:
    row = captured_row(tmp_path, "NormalMap")
    row["import_metadata"]["mipmaps"] = mipmaps
    row["selection"] = {"mip_count": 99}
    adapter = Adapter([row], "confirmation")
    assert adapter.textures[0].normal_metric_mips == (4 if mipmaps else 1)


def test_audit_existing_report_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "experiment report/report.json"
    A.write_json(report, {"original": True})
    config = tmp_path / "config.json"
    A.write_json(config, {"report": str(report)})
    audit = UnityCaptureInputAudit(tmp_path, config)
    monkeypatch.setattr(audit, "verify", lambda: None)
    with pytest.raises(FileExistsError):
        audit.run()
    assert A.read_json(report) == {"original": True}


def test_empty_corpus_cannot_report_passed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = tmp_path / "experiment report/report.json"
    corpus = tmp_path / "corpus.json"
    A.write_json(corpus, {"splits": {"train": [], "validation": []}})
    config = tmp_path / "config.json"
    A.write_json(
        config,
        {
            "report": str(report),
            "sources_sha256": {},
            "corpora": [{"path": str(corpus), "sha256": A.sha256_file(corpus)}],
        },
    )
    audit = UnityCaptureInputAudit(tmp_path, config)
    monkeypatch.setattr(audit, "verify", lambda: None)
    with pytest.raises(ValueError, match="did not compare any"):
        audit.run()
    assert A.read_json(report)["status"] == "failed"
