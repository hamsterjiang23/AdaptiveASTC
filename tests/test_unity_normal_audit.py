from __future__ import annotations

import numpy as np
import pytest

from reproductions.unity_search_baseline.normal_audit import UnityNormalCandidateAudit
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


def normal_table() -> str:
    header = "Target Normal Angular (mip0..3 wavg): mean<=3.20 deg, p95<=9.00 deg\n"
    return header + "\n".join(
        f"{block}x{block} | {preset} | 31.32 | 0.00 | 2.94 | 11.60 | 16.00 | Below Target"
        for block in UnityASTCBackend.BLOCKS
        for preset in UnityASTCBackend.PRESETS
    )


def test_normal_audit_keeps_angles_and_native_thresholds() -> None:
    rows, mean_gate, p95_gate = UnityNormalCandidateAudit.table(normal_table())
    assert len(rows) == 20 and (mean_gate, p95_gate) == (3.2, 9)
    assert rows[-1]["normal_mean_deg"] == 2.94
    assert rows[-1]["normal_p95_deg"] == 11.60
    assert rows[-1]["status"] == "Below Target"
    assert rows[-1]["psnr"] > 30


def test_normal_audit_rejects_incomplete_or_reordered_table() -> None:
    text = normal_table()
    with pytest.raises(ValueError, match="all20"):
        UnityNormalCandidateAudit.table(text.replace("6x6 | exhaustive", "8x8 | exhaustive"))
    with pytest.raises(ValueError, match="all20"):
        UnityNormalCandidateAudit.table("\n".join(text.splitlines()[:-1]))
    with pytest.raises(ValueError, match="thresholds"):
        UnityNormalCandidateAudit.table("\n".join(text.splitlines()[1:]))


def test_last_candidate_can_be_valid_and_marked_best() -> None:
    text = normal_table()
    last = text.rsplit("\n", 1)[1]
    text = text[: -len(last)] + last.replace("11.60", "8.50").replace(
        "Below Target", "Valid [BEST]"
    )
    rows, mean_gate, p95_gate = UnityNormalCandidateAudit.table(text)
    winner = rows[-1]
    assert winner["normal_mean_deg"] <= mean_gate and winner["normal_p95_deg"] <= p95_gate
    assert UnityNormalCandidateAudit.native_status_valid(winner["status"])
    assert not UnityNormalCandidateAudit.native_status_valid("Below Target")
    with pytest.raises(ValueError, match="Unknown native"):
        UnityNormalCandidateAudit.native_status_valid("Valid corrupt")


def test_normal_thresholds_use_native_float32_and_bound_runtime_policy() -> None:
    policy = {"targetNormalMeanDeg": 3.2, "targetNormalP95Deg": 9.0}
    configured = {"normal_mean": 3.2, "normal_p95": 9.0}
    mean, p95 = UnityNormalCandidateAudit.native_thresholds(policy, configured, (3.2, 9.0))
    native_mean = float(np.float32(3.2))
    assert native_mean > 3.2 and native_mean <= mean and p95 == 9.0
    for changed in [3.2001, float("nan"), -3.2]:
        with pytest.raises(ValueError, match="thresholds disagree"):
            UnityNormalCandidateAudit.native_thresholds(
                {**policy, "targetNormalMeanDeg": changed}, configured, (3.2, 9.0)
            )
    with pytest.raises(ValueError, match="thresholds disagree"):
        UnityNormalCandidateAudit.native_thresholds(policy, configured, (3.21, 9.0))


@pytest.mark.parametrize(
    "width,height,block,length", [(14, 14, 10, 16), (0, 14, 10, 0), (14, 14, 99, 16)]
)
def test_native_decoder_rejects_invalid_payload_before_call(
    width: int, height: int, block: int, length: int
) -> None:
    decoder = object.__new__(UnityASTCBackend)
    with pytest.raises(ValueError, match="payload dimensions"):
        decoder.decode_payload(bytes(length), width, height, block, srgb=False)
