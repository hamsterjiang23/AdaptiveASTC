"""Checkpoint evidence uses canonical JSON identity and keeps this entry development-only."""

from __future__ import annotations

import pytest

from reproductions.unity_search_baseline.sealed_inference import UnitySealedInferenceSmoke as Smoke


def test_checkpoint_tuple_and_json_list_have_the_same_training_identity() -> None:
    Smoke.verify_checkpoint(
        {"config": {"indices": (0, 1, 2), "learning_rate": 0.0003}, "epoch": 1},
        {
            "config": {"indices": [0, 1, 2], "learning_rate": 0.0003},
            "checkpoint_audit": {"epoch": 1},
        },
    )


@pytest.mark.parametrize("changed", ["epoch", "config"])
def test_checkpoint_identity_changes_are_rejected(changed: str) -> None:
    checkpoint = {"config": {"indices": (0, 1, 2)}, "epoch": 1}
    training = {"config": {"indices": [0, 1, 2]}, "checkpoint_audit": {"epoch": 1}}
    if changed == "epoch":
        checkpoint["epoch"] = 2
    else:
        checkpoint["config"] = {"indices": (0, 1, 3)}
    with pytest.raises(ValueError, match="checkpoint settings or epoch"):
        Smoke.verify_checkpoint(checkpoint, training)
