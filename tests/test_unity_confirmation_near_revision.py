"""Approved near-identity changes preserve exact slots, reserve order and development rows."""

from __future__ import annotations

import copy

import pytest

from adaptive_astc.config import JsonDict
from reproductions.unity_search_baseline.confirmation_near_revision import (
    UnityConfirmationNearRevision as R,
)


def proposal_fixture() -> tuple[JsonDict, JsonDict]:
    primary = [{"path": f"Assets/Primary/{i}.png", "fileHash": str(i)} for i in range(3)]
    reserves = [{"path": f"Assets/Reserve/{i}.png", "fileHash": str(i + 3)} for i in range(3)]
    proposal = {
        "proposed_replacements": [{
            "primary_index_zero_based": 1,
            "primary_position_one_based": 2,
            "reserve_position_one_based": 1,
            "original": primary[1],
            "replacement": reserves[0],
        }],
        "selection_uses_model_predictions_quality_or_native_labels": False,
        "model_forward_calls": 0,
        "training_updates": 0,
        "cohort_modified": False,
    }
    return {"primary": primary, "reserves": reserves}, proposal


def test_approved_mapping_preserves_specific_slot_and_first_reserve() -> None:
    manifest, proposal = proposal_fixture()
    assert R.approved_mapping(manifest, proposal) == {"Assets/Primary/1.png"}


@pytest.mark.parametrize("field", ["slot", "reserve", "identity", "prediction", "duplicate"])
def test_changed_proposal_is_rejected(field: str) -> None:
    manifest, proposal = proposal_fixture()
    row = proposal["proposed_replacements"][0]
    if field == "slot":
        row["primary_index_zero_based"] = 0
    elif field == "reserve":
        row["replacement"] = manifest["reserves"][1]
    elif field == "identity":
        row["original"] = {**row["original"], "fileHash": "changed"}
    elif field == "prediction":
        proposal["selection_uses_model_predictions_quality_or_native_labels"] = True
    else:
        proposal["proposed_replacements"].append(copy.deepcopy(row))
    with pytest.raises(ValueError):
        R.approved_mapping(manifest, proposal)


def test_pixel_selection_preserves_development_and_confirmation_order() -> None:
    manifest, proposal = proposal_fixture()
    old = [{"path": "Assets/Train/0.png", "source_split": "train", "source_md4": "T"}]
    old.extend({
        "path": row["path"], "source_split": "confirmation", "source_md4": row["fileHash"]
    } for row in manifest["primary"])
    added = [{
        "path": manifest["reserves"][0]["path"],
        "source_split": "confirmation", "source_md4": manifest["reserves"][0]["fileHash"],
    }]
    primary = [manifest["primary"][0], manifest["reserves"][0], manifest["primary"][2]]
    selected = R.select_pixels(old, added, primary, proposal)
    assert selected == [old[0], old[1], added[0], old[3]]
    assert old[2]["path"] == "Assets/Primary/1.png"
    for bad_added in [[], [added[0], added[0]], [{**added[0], "source_split": "train"}]]:
        with pytest.raises(ValueError):
            R.select_pixels(old, bad_added, primary, proposal)
    with pytest.raises(ValueError):
        R.select_pixels([old[0], old[2], old[1], old[3]], added, primary, proposal)
    with pytest.raises(ValueError, match="order"):
        R.select_pixels(old, added, [primary[2], primary[1], primary[0]], proposal)
