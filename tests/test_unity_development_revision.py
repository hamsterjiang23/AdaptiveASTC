"""Protect input-only replacement membership and frozen original positions."""

from pathlib import Path

import pytest
from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.development_revision import UnityDevelopmentRevision as R


def test_replacement_preserves_positions_and_held_out() -> None:
    source = {
        "train": [{"path": "Assets/keep.png"}, {"path": "Assets/cube.png"}],
        "validation": [{"path": "Assets/vcube.png"}],
        "test": [{"path": "Assets/test.png"}],
    }
    revised, mapping = R.replace_rows(
        source,
        {"train": {"assets/cube.png"}, "validation": {"assets/vcube.png"}},
        {"train": [{"path": "Assets/new.png"}], "validation": [{"path": "Assets/newv.png"}]},
    )
    assert revised["train"][0] == source["train"][0]
    assert revised["test"] == source["test"]
    assert revised["train"][1]["path"] == "Assets/new.png"
    assert source["train"][1]["path"] == "Assets/cube.png"
    assert [row["index"] for row in mapping] == [1, 0]


@pytest.mark.parametrize("replacement", ["Assets/other.png", "assets/cube.png"])
def test_replacement_rejects_cross_split_collision(replacement: str) -> None:
    with pytest.raises(ValueError, match="cross-split"):
        R.replace_rows(
            {
                "train": [{"path": "Assets/cube.png"}],
                "validation": [{"path": "Assets/other.png"}],
                "test": [{"path": "assets/cube.png"}],
            },
            {"train": {"assets/cube.png"}, "validation": set()},
            {"train": [{"path": replacement}], "validation": []},
        )


def test_missing_exclusion_is_not_silently_ignored() -> None:
    with pytest.raises(ValueError, match="membership"):
        R.replace_rows(
            {"train": [{"path": "Assets/a.png"}], "validation": []},
            {"train": {"assets/missing.png"}, "validation": set()},
            {"train": [{"path": "Assets/new.png"}], "validation": []},
        )


def candidate(tmp_path: Path, shape: int, kind: int) -> tuple[R, JsonDict]:
    path = tmp_path / "Assets/a.png"
    path.parent.mkdir()
    Image.new("RGBA", (8, 4), (100, 120, 140, 80)).save(path)
    Path(str(path) + ".meta").write_text(
        f"TextureImporter:\n  textureShape: {shape}\n  textureType: {kind}\n", encoding="utf-8"
    )
    revision = R.__new__(R)
    revision.project = tmp_path
    return revision, {"path": "Assets/a.png", "fileHash": MD4.new(path.read_bytes()).hexdigest()}


@pytest.mark.parametrize(("shape", "kind"), [(2, 0), (1, 2), (1, 5)])
def test_outside_explicit_source_scope_is_rejected(tmp_path: Path, shape: int, kind: int) -> None:
    revision, row = candidate(tmp_path, shape, kind)
    result, reason = revision.inspect(row)
    assert result is None and reason == "not_explicit_Default_Sprite_NormalMap_Tex2D"


def test_source_identity_and_alpha_are_checked(tmp_path: Path) -> None:
    revision, row = candidate(tmp_path, 1, 0)
    result, reason = revision.inspect(row)
    assert result is not None and reason is None
    assert (result["width"], result["height"], result["alpha_nonopaque"]) == (8, 4, True)
    row["fileHash"] = "0" * 32
    assert revision.inspect(row) == (None, "source_md4_changed")


def test_report_cannot_overwrite_local_manifest(tmp_path: Path) -> None:
    output = tmp_path / "experiment report/.local/revision"
    config = tmp_path / "config.json"
    A.write_json(
        config,
        {
            "output": str(output),
            "report": str(output / "manifest.json"),
            "project": str(tmp_path),
            "expected_replacements": {"train": 13, "validation": 5},
        },
    )
    with pytest.raises(ValueError, match="public"):
        R(tmp_path, config)


def test_two_preconstructed_revisions_cannot_overwrite_report(tmp_path: Path) -> None:
    report = tmp_path / "experiment report/revision.json"
    instances = []
    for number in range(2):
        config = tmp_path / f"config{number}.json"
        A.write_json(
            config,
            {
                "output": str(tmp_path / f"experiment report/.local/revision{number}"),
                "report": str(report),
                "project": str(tmp_path),
                "expected_replacements": {"train": 13, "validation": 5},
            },
        )
        instances.append(R(tmp_path, config))
    instances[0].claim_outputs()
    before = report.read_bytes()
    with pytest.raises(FileExistsError):
        instances[1].claim_outputs()
    assert report.read_bytes() == before
    assert not instances[1].output.exists()
