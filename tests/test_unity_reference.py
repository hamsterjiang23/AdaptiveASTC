"""Regress the native PNG row-origin correction observed in the Unity export probe."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.unity_reference import UnityReferenceCapture
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline


@pytest.mark.parametrize("source_split", ["train", "validation"])
def test_native_reference_rows_are_normalized_before_quality_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_split: str
) -> None:
    project = tmp_path / "project"
    source = project / "Assets/a.png"
    source.parent.mkdir(parents=True)
    image = Image.new("RGB", (4, 4))
    image.putdata([(y * 60, x * 60, 30) for y in range(4) for x in range(4)])
    image.save(source)
    manifest = tmp_path / "source.json"
    ArtifactStore.write_json(
        manifest,
        {
            "splits": {
                source_split: [
                    {"path": "Assets/a.png", "fileHash": MD4.new(source.read_bytes()).hexdigest()}
                ]
            }
        },
    )
    baseline = UnitySearchBaseline(
        tmp_path,
        project,
        tmp_path / "unused-editor",
        manifest,
        capture_references=True,
        source_split=source_split,
        capture_paths=["Assets/a.png"] if source_split == "validation" else None,
    )
    baseline.run_dir.mkdir(parents=True)
    debug = project / "ASTC_Cache/a_1"
    debug.mkdir(parents=True)
    image.save(debug / "original.png")
    image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(debug / "4x4_fastest_decompressed.png")
    header = bytes.fromhex("13aba15c") + bytes([4, 4, 1])
    header += (4).to_bytes(3, "little") * 2 + (1).to_bytes(3, "little")
    (debug / "4x4_fastest.astc").write_bytes(header + bytes(16))
    (debug / "parameter_test_report.txt").write_text(
        "synthetic row-origin fixture", encoding="utf-8"
    )
    ArtifactStore.write_json(
        baseline.run_dir / "probe-config.json",
        {"captureReferences": True, "assets": [{"path": "Assets/a.png"}]},
    )
    ArtifactStore.write_json(
        baseline.run_dir / "probe-receipt.json",
        {"status": "passed", "process_exit_code": 0, "metadata_restore_conflicts": []},
    )
    for kind, row in [
        (
            "imports",
            {
                "asset": "Assets/a.png",
                "reference_directory": str(debug),
                "srgb": True,
                "texture_type": "Default",
                "success": True,
            },
        ),
        ("native", {"asset": "Assets/a.png", "block_size": "4x4", "preset": "fastest"}),
    ]:
        path = baseline.run_dir / f"probe-{kind}.jsonl"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    def passed_audit(phase: str) -> dict[str, str]:
        return {"status": "passed", "scope": "synthetic metadata fixture"}

    monkeypatch.setattr(baseline, "audit", passed_audit)
    monkeypatch.setattr(baseline, "summarize", passed_audit)
    capture = UnityReferenceCapture(baseline)
    result = capture.collect("probe")
    assert result["source_rgb_equal"] == 1
    assert result["rows"][0]["unity_lossless"]
    assert result["rows"][0]["unity_rgb_psnr"] is None
    assert result["rows"][0]["source_split"] == source_split
    archived_manifest = ArtifactStore.read_json(
        baseline.run_dir / "references/normalized-probe/manifest.json"
    )
    assert list(archived_manifest["splits"]) == [source_split]
    assert capture.collect("probe") == result
    mirrored = baseline.run_dir / "references/normalized-probe/project/Assets/a.png"
    original_mirror = mirrored.read_bytes()
    mirrored.write_bytes(b"damaged mirror")
    with pytest.raises(ValueError, match="Mirrored reference pixels changed"):
        capture.collect("probe")
    mirrored.write_bytes(original_mirror)
    archived = baseline.run_dir / "references/normalized-probe/00000/unity.png"
    archived.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="Archived reference pixels changed"):
        capture.collect("probe")
    (baseline.run_dir / "probe-imports.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="complete frozen input cohort"):
        capture.collect("probe")
