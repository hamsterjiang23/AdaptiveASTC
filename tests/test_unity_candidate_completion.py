import json
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from PIL import Image

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.candidate_completion import UnityCandidateCompletion
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


def test_partial_normal_search_keeps_angular_targets() -> None:
    text = "12x12 | fastest | 35.00 | 0.00 | 1.20 | 4.30 | 7.56 | Valid"
    assert UnityCandidateCompletion.normal_table(text) == {("12x12", "fastest"): (1.2, 4.3)}
    with pytest.raises(ValueError, match="duplicated"):
        UnityCandidateCompletion.normal_table(text + "\n" + text)
    with pytest.raises(ValueError, match="coverage differ"):
        UnityCandidateCompletion.normal_table(text + "\n10x10 | fast | 36.00 | 0.00 | missing")


def test_mip_scope_uses_hashed_actual_import_metadata(tmp_path: Path) -> None:
    path = tmp_path / "batch-imports.jsonl"
    imported = {
        "asset": "Assets/normal.png",
        "success": True,
        "texture_type": "NormalMap",
        "srgb": False,
        "mipmaps": False,
        "texture_dimension": "Tex2D",
        "width": 512,
        "height": 512,
    }
    path.write_text(json.dumps(imported) + "\n", encoding="utf-8")
    config = {
        "capture_run": str(tmp_path),
        "capture_phase": "batch",
        "imports_sha256": ArtifactStore.sha256_file(path),
        "items": [{"index": 0, "is_normal": True, "mip_count": 1}],
    }
    receipt = {"rows": [{"path": "Assets/normal.png", "width": 512, "height": 512}]}
    UnityCandidateCompletion.verify_normal_imports(config, receipt)
    config["items"][0]["mip_count"] = True
    with pytest.raises(ValueError, match="mip scope"):
        UnityCandidateCompletion.verify_normal_imports(config, receipt)
    config["items"][0]["mip_count"] = 1
    imported["mipmaps"] = True
    path.write_text(json.dumps(imported) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="metadata changed"):
        UnityCandidateCompletion.verify_normal_imports(config, receipt)
    config["imports_sha256"] = ArtifactStore.sha256_file(path)
    with pytest.raises(ValueError, match="mip scope"):
        UnityCandidateCompletion.verify_normal_imports(config, receipt)
    config["items"][0]["mip_count"] = 4
    UnityCandidateCompletion.verify_normal_imports(config, receipt)


@pytest.mark.parametrize(
    "width,height,depth", [(1, 1, 1), (2, 1, 2), (4, 4, 3), (8, 8, 4), (512, 512, 4)]
)
def test_normal_evaluation_depth_is_clamped(width: int, height: int, depth: int) -> None:
    imported = {"mipmaps": True, "texture_dimension": "Tex2D", "width": width, "height": height}
    assert UnityCandidateCompletion.normal_metric_mips(imported) == depth
    assert UnityCandidateCompletion.normal_metric_mips({**imported, "mipmaps": False}) == 1


@pytest.mark.parametrize(
    "field,value", [("mipmaps", 1), ("width", 0), ("height", True), ("texture_dimension", "Cube")]
)
def test_invalid_normal_metadata_cannot_infer_evaluation_depth(field: str, value: object) -> None:
    imported = {"mipmaps": True, "texture_dimension": "Tex2D", "width": 512, "height": 512}
    imported[field] = value
    with pytest.raises(ValueError, match="metadata"):
        UnityCandidateCompletion.normal_metric_mips(imported)


def test_completion_source_is_bound(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    ArtifactStore.write_json(path, {"completion_source_sha256": "changed"})
    with pytest.raises(ValueError, match="implementation changed"):
        UnityCandidateCompletion(path)


def test_normal_winner_header_must_match_label_before_encoding(tmp_path: Path) -> None:
    folder = tmp_path / "00000"
    folder.mkdir()
    for name in ["original.png", "unity-native.png"]:
        Image.fromarray(np.full((1, 1, 4), 128, dtype=np.uint8)).save(folder / name)
    (folder / "unity.astc").write_bytes(UnityASTCBackend.container(bytes(16), 1, 1, 8))
    (folder / "parameter_test_report.txt").write_text(
        "12x12 | fastest | 35.00 | 0.00 | 1.20 | 4.30 | 0.02 | Valid", encoding="utf-8"
    )
    reference = {
        "path": "Assets/normal.png",
        "width": 1,
        "height": 1,
        "artifacts_sha256": {
            path.name: ArtifactStore.sha256_file(path) for path in folder.iterdir()
        },
        "selection": {"block_size": "12x12", "preset": "fastest"},
    }
    completion = object.__new__(UnityCandidateCompletion)
    with pytest.raises(ValueError, match="footprint differs"):
        completion.collect_image(
            tmp_path,
            {"rows": [reference]},
            {"index": 0, "is_normal": True},
            tmp_path,
            cast(UnityASTCBackend, object()),
            cast(UnityQuality, object()),
        )
