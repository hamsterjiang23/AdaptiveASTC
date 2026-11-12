"""Reject unintended changes when joining approved replacement pixel identities."""

from copy import deepcopy

import pytest

from adaptive_astc.config import JsonDict
from reproductions.unity_search_baseline.revised_pixel_identity import (
    UnityRevisedPixelIdentityAudit as R,
)


def fixture_rows() -> tuple[list[JsonDict], list[JsonDict], JsonDict, JsonDict]:
    def row(name: str, split: str) -> JsonDict:
        return {
            "path": f"Assets/{name}.png",
            "source_split": split,
            "reference": f"C:/test/{name}.png",
            "reference_sha256": f"png-{name}",
            "callback_rgba_sha256": f"pixels-{name}",
        }

    old = [row("cube", "train"), row("retained", "validation"), row("confirm", "confirmation")]
    added = [row("replacement", "train")]
    reservation = {
        "replacements": [
            {"split": "train", "old_path": old[0]["path"], "new_path": added[0]["path"], "index": 0}
        ]
    }
    corpus = {
        "splits": {
            split: [
                {**sample, "actual_options": {"rgba_sha256": sample["callback_rgba_sha256"]}}
                for sample in [*added, old[1]]
                if sample["source_split"] == split
            ]
            for split in ["train", "validation"]
        }
    }
    return old, added, reservation, corpus


def test_only_approved_replacement_and_confirmation_order_preserved() -> None:
    old, added, reservation, corpus = fixture_rows()
    before = deepcopy(old)
    result = R.select(old, added, reservation, corpus)
    assert result == [added[0], old[1], old[2]]
    assert old == before


@pytest.mark.parametrize("damage", ["reference", "reference_sha256", "callback"])
def test_corpus_must_use_same_native_pixels(damage: str) -> None:
    old, added, reservation, corpus = fixture_rows()
    row = corpus["splits"]["validation"][0]
    if damage == "callback":
        row["actual_options"]["rgba_sha256"] = "wrong"
    else:
        row[damage] = "wrong"
    with pytest.raises(ValueError, match="pixel origin"):
        R.select(old, added, reservation, corpus)


def test_extra_replacement_is_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    added.append({**added[0], "path": "Assets/extra.png"})
    with pytest.raises(ValueError, match="approved new identities"):
        R.select(old, added, reservation, corpus)


def test_unapproved_retained_deletion_is_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    corpus["splits"]["validation"] = []
    with pytest.raises(ValueError, match="Unapproved development"):
        R.select(old, added, reservation, corpus)


def test_confirmation_replacement_is_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    reservation["replacements"][0].update(old_path=old[2]["path"], split="confirmation")
    added[0]["source_split"] = "confirmation"
    with pytest.raises(ValueError, match="Only development"):
        R.select(old, added, reservation, corpus)


def test_split_transfer_is_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    added[0]["source_split"] = "validation"
    with pytest.raises(ValueError, match="changes a split"):
        R.select(old, added, reservation, corpus)


def test_duplicate_original_paths_are_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    old.append(deepcopy(old[0]))
    with pytest.raises(ValueError, match="Duplicate asset identity"):
        R.select(old, added, reservation, corpus)
