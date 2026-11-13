"""Exercise actual tiny PNG I/O, native input projection and immutable audit publication."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import torch
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_revision_pixels import (
    UnityConfirmationRevisionPixelAudit as R,
)
from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit as I


def fixture_config(root: Path) -> tuple[Path, list[JsonDict]]:
    public = root / "experiment report"
    local = public / ".local"
    local.mkdir(parents=True)

    def bind(name: str, value: JsonDict) -> JsonDict:
        path = local / name
        A.write_json(path, value)
        return {"path": str(path), "sha256": A.sha256_file(path)}

    pixels = []
    sources = []
    for index, split in enumerate(["train", "validation", "confirmation", "confirmation",
                                   "confirmation"]):
        path = local / f"{index}.png"
        Image.new("RGBA", (4, 3), (index * 20, 30, 50, 255)).save(path)
        asset = f"Assets/{index}.png"
        source = {
            "path": asset, "fileHash": str(index),
            "source_sha256": A.sha256_file(path), "meta_sha256": str(index) * 64,
        }
        sources.append(source)
        pixels.append({
            "path": asset, "source_split": split, "source_md4": source["fileHash"],
            "reference": str(path), "reference_sha256": A.sha256_file(path),
            "observed_options": {
                "need_alpha": False, "profile": 0, "normal_pack": False, "channel": 4,
                "srgb_importer": True, "texture_type_importer": "Default",
            },
            "selected_block_size": "8x8", "selected_preset": "fast",
            **I.pixel_identity(path.read_bytes(), 4, 3),
        })

    def audit(name: str, values: list[JsonDict]) -> JsonDict:
        details = bind(f"{name}-details.json", {"rows": values})
        return bind(f"{name}.json", {
            "status": "passed", "splits_modified": False,
            "inputs_sha256": {}, "counts": dict(Counter(row["source_split"] for row in values)),
            "details": details["path"], "details_sha256": details["sha256"],
            "rgba": I.group_duplicates(values, "rgba_identity")[1],
            "rgb_only": I.group_duplicates(values, "rgb_identity")[1],
        })

    proposal = bind("proposal.json", {"proposed_replacements": [{
        "primary_index_zero_based": 1, "original": sources[3], "replacement": sources[4],
    }]})
    primary = {"status": "reserved", "primary": [sources[2], sources[4]]}
    primary["fingerprint"] = A.fingerprint(primary)
    primary_binding = bind("primary.json", primary)
    revision = bind("revision.json", {
        "status": "reserved", "scope_revision_authorized": True,
        "manifest": primary_binding["path"], "manifest_sha256": primary_binding["sha256"],
        "identity_review": proposal, "model_forward_calls": 0, "training_updates": 0,
        "test_opened": False,
    })
    capture_rows = []
    for index in [2, 4]:
        source, pixel = sources[index], pixels[index]
        actual = {
            "path": source["path"], "width": 4, "height": 3,
            "need_alpha": False, "normal_pack": False, "profile": 0, "channel": 4,
            "texture_type_importer": "Default", "srgb_importer": True,
            "rgba_sha256": pixel["callback_rgba_sha256"],
        }
        imported = {
            "asset": source["path"], "width": 4, "height": 3, "success": True,
            "texture_type": "Default", "texture_dimension": "Tex2D",
            "srgb": True, "mipmaps": False,
        }
        capture_rows.append({
            "path": source["path"], "source_split": "confirmation",
            "source_md4": source["fileHash"], "source_sha256": source["source_sha256"],
            "meta_sha256": source["meta_sha256"], "reference_png": pixel["reference"],
            "reference_sha256": pixel["reference_sha256"], "width": 4, "height": 3,
            "actual_options": actual, "import_metadata": imported,
            "selection": {"block_size": "8x8", "preset": "fast"},
        })
    captured = {
        "status": "passed", "splits": {"confirmation": capture_rows},
        "reservation_manifest_sha256": primary_binding["sha256"],
        "model_forward_calls": 0, "training_updates": 0, "test_opened": False,
    }
    captured["fingerprint"] = A.fingerprint(captured)
    captured_binding = bind("captured.json", captured)
    capture_report = bind("capture-report.json", {
        "status": "passed", "captured_images": 2, "manifest": captured_binding["path"],
        "manifest_sha256": captured_binding["sha256"], "inputs_sha256": {},
        "model_forward_calls": 0, "training_updates": 0, "test_opened": False,
    })
    config = {
        "sources_sha256": {}, "output": str(local / "result"),
        "report": str(public / "result.json"), "confirmation_reservation": revision,
        "identity_review": proposal, "confirmation_capture": capture_report,
        "original_pixels": audit("old", pixels[:4]),
        "replacement_pixels": audit("added", pixels[4:]),
        "expected_counts": {"train": 1, "validation": 1, "confirmation": 2},
    }
    path = public / "config.json"
    A.write_json(path, config)
    return path, pixels


@pytest.mark.parametrize(
    "damage", ["none", "pixels", "binding", "capture_sha", "observed_profile", "observed_alpha"]
)
def test_real_small_pixel_audit_and_zero_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    monkeypatch.setattr(R, "execution_sources", staticmethod(lambda root: {}))

    def reject_forward(self: torch.nn.Module, *args: object, **kwargs: object) -> None:
        raise AssertionError("Pixel audit must perform zero model forward calls")

    monkeypatch.setattr(torch.nn.Module, "_call_impl", reject_forward)
    path, pixels = fixture_config(tmp_path)
    config = A.read_json(path)
    if damage == "pixels":
        Path(pixels[0]["reference"]).write_bytes(b"changed pixels")
    elif damage == "binding":
        config["identity_review"]["sha256"] = "0" * 64
        A.write_json(path, config)
    elif damage == "capture_sha":
        Path(config["confirmation_capture"]["path"]).write_text("{}")
    elif damage in {"observed_profile", "observed_alpha"}:
        capture_report_path = Path(config["confirmation_capture"]["path"])
        capture_report = A.read_json(capture_report_path)
        captured_path = Path(capture_report["manifest"])
        captured = A.read_json(captured_path)
        native = captured["splits"]["confirmation"][0]
        if damage == "observed_profile":
            native["actual_options"].update(profile=1, srgb_importer=False)
            native["import_metadata"]["srgb"] = False
        else:
            native["actual_options"]["need_alpha"] = True
        captured.pop("fingerprint")
        captured["fingerprint"] = A.fingerprint(captured)
        A.write_json(captured_path, captured)
        capture_report["manifest_sha256"] = A.sha256_file(captured_path)
        A.write_json(capture_report_path, capture_report)
        config["confirmation_capture"]["sha256"] = A.sha256_file(capture_report_path)
        A.write_json(path, config)
    runner = R(tmp_path, path)
    if damage != "none":
        error_match = "native options" if damage.startswith("observed_") else None
        with pytest.raises(ValueError, match=error_match):
            runner.run()
        if damage == "pixels":
            assert A.read_json(Path(config["report"]))["status"] == "failed"
        return
    result = runner.run()
    assert result["status"] == "passed"
    assert result["model_forward_calls"] == result["training_updates"] == 0
    assert result["counts"] == config["expected_counts"]
    assert result["native_confirmation_input_images"] == 2
    assert len(A.read_json(Path(result["native_png_bindings"]))) == 4
    assert [row["path"] for row in A.read_json(Path(result["details"]))["rows"]] == [
        pixels[index]["path"] for index in [0, 1, 2, 4]
    ]
    before = Path(config["report"]).read_bytes()
    with pytest.raises(FileExistsError):
        R(tmp_path, path).run()
    assert Path(config["report"]).read_bytes() == before
