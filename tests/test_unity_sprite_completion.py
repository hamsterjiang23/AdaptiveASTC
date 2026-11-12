"""Sprite references use the native LDR color path with actual callback evidence."""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.supplement import UnitySupplementalCapture


@pytest.mark.parametrize("texture_type", ["Default", "Sprite"])
def test_color_usage_preserves_importer_type(tmp_path: Path, texture_type: str) -> None:
    path = tmp_path / "config.json"
    A.write_json(path, {"options_receipt": "bound-in-run"})
    row = {"texture_type": texture_type}
    item = {"is_hdr": False, "is_normal": False, "need_alpha": True, "metadata_source": "callback"}
    UnitySupplementalCapture(path).validate_color_input(row, item)
    assert row["texture_type"] == texture_type


def test_sprite_cannot_use_historical_assumed_options(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    A.write_json(path, {})
    item = {"is_hdr": False, "is_normal": False, "need_alpha": True, "metadata_source": "assumed"}
    with pytest.raises(ValueError, match="actual encoder options"):
        UnitySupplementalCapture(path).validate_color_input({"texture_type": "Sprite"}, item)


@pytest.mark.parametrize(
    "is_hdr,is_normal,usage",
    [
        (True, False, "Sprite"),
        (False, True, "Sprite"),
        (False, False, "NormalMap"),
        (False, False, "Unknown"),
    ],
)
def test_other_protocols_cannot_be_admitted_as_color(
    tmp_path: Path,
    is_hdr: bool,
    is_normal: bool,
    usage: str,
) -> None:
    path = tmp_path / "config.json"
    A.write_json(path, {"options_receipt": "bound-in-run"})
    item = {
        "is_hdr": is_hdr,
        "is_normal": is_normal,
        "need_alpha": True,
        "metadata_source": "callback",
    }
    with pytest.raises(ValueError, match="supported LDR"):
        UnitySupplementalCapture(path).validate_color_input({"texture_type": usage}, item)
