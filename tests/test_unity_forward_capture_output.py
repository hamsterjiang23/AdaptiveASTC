from __future__ import annotations

import copy
from dataclasses import asdict

import pytest

from adaptive_astc.config import JsonDict
from reproductions.unity_search_baseline.forward_capture_output import (
    UnityForwardCaptureOutputAudit,
)
from reproductions.unity_search_baseline.forward_deployment import NativeForwardQueries
from reproductions.unity_search_baseline.system_variant_policy import forward_search
from tests.test_unity_forward_deployment import metrics, queries


def recorded_choice() -> tuple[JsonDict, NativeForwardQueries]:
    query, _, _ = queries(7, {8: metrics(passed=True)})
    outcome = forward_search(query)
    return {
        "source_index": 0,
        "starting_decision": asdict(query.entry["decision"]),
        "selected_index": outcome.selected_index,
        "selection_reason": outcome.reason,
        "candidates_measured": len(query.indices),
        "measured_indices": list(query.indices),
        "strict_quality_met": query.strict(outcome.selected_index),
        "queries": query.records,
        "selected_encoded_result_reused": True,
    }, query


def test_recorded_real_queries_replay_without_unmeasured_metrics() -> None:
    choice, query = recorded_choice()
    outcome = UnityForwardCaptureOutputAudit.replay_choice(
        choice, query.entry["decision"], query.policy, query.texture
    )
    assert outcome.selected_index == 8 and outcome.measured_indices == (7, 8)
    assert outcome.reason == "first_valid"


@pytest.mark.parametrize("mutation", ["start", "count", "order", "winner", "reason", "strict"])
def test_query_audit_rejects_changed_search_semantics(mutation: str) -> None:
    choice, query = recorded_choice()
    if mutation == "start":
        choice["starting_decision"]["selected_index"] = 6
    if mutation == "count":
        choice["candidates_measured"] = 1
    if mutation == "order":
        choice["queries"].reverse()
    if mutation == "winner":
        choice["selected_index"] = 7
    if mutation == "reason":
        choice["selection_reason"] = "highest_psnr_fallback"
    if mutation == "strict":
        choice["queries"][0]["strict_quality_met"] = True
    with pytest.raises(ValueError):
        UnityForwardCaptureOutputAudit.replay_choice(
            choice, query.entry["decision"], query.policy, query.texture
        )


def test_repeat_signature_ignores_timing_and_preserves_actual_queries() -> None:
    choice, _ = recorded_choice()
    changed = copy.deepcopy(choice)
    changed["queries"][0]["timings"]["encode_seconds"] = 100.0
    changed["queries"][0]["trace_hash_seconds"] = 5.0
    assert UnityForwardCaptureOutputAudit.signature(
        choice
    ) == UnityForwardCaptureOutputAudit.signature(changed)
    changed["queries"][0]["metrics"]["psnr"] += 1.0
    assert UnityForwardCaptureOutputAudit.signature(
        choice
    ) != UnityForwardCaptureOutputAudit.signature(changed)
