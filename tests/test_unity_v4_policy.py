"""Regression checks for the V4 search changes specified by the experiment plan."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy
from reproductions.unity_search_baseline.v4_policy import UnityV4Policy, V4Options


def base_policy() -> UnityV3Policy:
    return UnityV3Policy(
        {
            "schemaVersion": 2,
            "astcOptimizerEnabled": True,
            "rdoGlobalEnabled": False,
            "targetPsnrDb": 30,
            "targetMsSsimDb": 21,
            "targetNormalMeanDeg": 3.2,
            "targetNormalP95Deg": 9,
            "blackPixelRatioMild": 0.4,
            "blackPixelRatioStrong": 0.8,
            "blackElevatedPsnrMildDb": 35,
            "blackElevatedPsnrStrongDb": 37,
            "sizeFirstMinSideLarge": 512,
        }
    )


def candidates(psnr: float = 20, ssim: float = 10) -> list[JsonDict]:
    return [
        {
            "block": b,
            "preset": p,
            "metrics": {
                "psnr": psnr,
                "ms_ssim_db": ssim,
                "black_pixel_ratio": 0.0,
                "normal_mean_deg": 5,
                "normal_p95_deg": 12,
            },
        }
        for b, p in NativeCandidateSet.GRID
    ]


def texture(large: bool) -> UnityTextureInput:
    return UnityTextureInput(
        512 if large else 128, 512 if large else 128, True, False, False, True, 0
    )


@pytest.mark.parametrize("large", [True, False])
@pytest.mark.parametrize("winner", [0, 4, 9, 19, None])
def test_baseline_decision_and_trace_reproduce_v3(large: bool, winner: int | None) -> None:
    base, spec = base_policy(), texture(large)
    rows = candidates()
    if winner is not None:
        rows[winner]["metrics"].update(psnr=40, ms_ssim_db=25)
    start = base.select(rows, spec).selected_index
    expected = base.search(lambda i: rows[i]["metrics"], spec, start)
    actual = UnityV4Policy(base, V4Options()).search(lambda i: rows[i]["metrics"], spec, rows)
    assert asdict(expected.decision) == asdict(actual.decision)
    assert expected.measured_indices == actual.measured_indices


def test_remove_only_cross_block_lookahead() -> None:
    base, spec = base_policy(), texture(True)
    rows = candidates(35)
    expected = UnityV4Policy(base, V4Options()).search(lambda i: rows[i]["metrics"], spec, rows)
    actual = UnityV4Policy(base, V4Options(remove_lookahead=True)).search(
        lambda i: rows[i]["metrics"], spec, rows
    )
    assert expected.measured_indices == (4, 5)
    assert actual.measured_indices == (4,)
    assert replace(expected.decision, candidates_measured=1) == actual.decision


def test_margin_moves_start_but_preserves_actual_threshold() -> None:
    base, spec = base_policy(), texture(False)
    rows = candidates(29.8, 22)
    rows[7]["metrics"]["psnr"] = 31
    policy = UnityV4Policy(base, V4Options("margin", 0.25, 0))
    assert policy.start(rows, spec) == (7, 0)
    result = policy.search(lambda i: rows[i]["metrics"], spec, rows)
    assert result.decision.selected_index == 7
    assert result.decision.effective_psnr_threshold == 30


@pytest.mark.parametrize("mode", ["original", "back_one", "back_two", "same_block_fastest"])
def test_start_clamps_to_front(mode: str) -> None:
    rows = candidates(40, 25)
    assert UnityV4Policy(base_policy(), V4Options(mode)).start(rows, texture(False)) == (0, 0)


def test_exhaustive_probe_can_precede_original_start() -> None:
    rows = candidates(35, 18)
    seen: list[int] = []

    def measure(index: int) -> JsonDict:
        seen.append(index)
        return rows[index]["metrics"]

    result = UnityV4Policy(base_policy(), V4Options(gate_margin_db=1)).search(
        measure, texture(True), rows
    )
    assert result.original_start == 4
    assert seen == [3]
    assert result.decision.selected_index == 3
    assert result.decision.selection_reason == "size_first_relaxed"
    assert result.gate_events[0]["skipped"]


def test_failed_probe_continues_exhaustive_and_cache_is_unique() -> None:
    predictions, actual = candidates(35, 18), candidates(35, 18)
    actual[3]["metrics"]["psnr"] = 29
    seen: list[int] = []

    def measure(index: int) -> JsonDict:
        seen.append(index)
        return actual[index]["metrics"]

    result = UnityV4Policy(base_policy(), V4Options(gate_margin_db=1)).search(
        measure, texture(True), predictions
    )
    assert seen == [3, 4, 5]
    assert len(seen) == len(set(seen))
    assert not result.gate_events[0]["skipped"]
    assert result.decision.selected_index == 4


@pytest.mark.parametrize("passing", [True, False])
def test_unlock_only_replaces_with_strict_pass(passing: bool) -> None:
    predictions, actual = candidates(35, 18), candidates(35, 18)
    if passing:
        actual[6]["metrics"]["ms_ssim_db"] = 22
    seen: list[int] = []

    def measure(index: int) -> JsonDict:
        seen.append(index)
        return actual[index]["metrics"]

    result = UnityV4Policy(base_policy(), V4Options(unlock=True)).search(
        measure, texture(True), predictions
    )
    assert result.unlock_event is not None
    assert result.unlock_event["budget_permitted"]
    assert result.unlock_event["replaced"] == passing
    assert result.decision.selected_index == (6 if passing else 4)
    assert len(seen) == len(set(seen))
    assert result.decision.candidates_measured == len(seen)


def test_budget_rejects_10_to_8_and_6_has_no_next_block() -> None:
    predictions = candidates()
    for index in range(5, 10):
        predictions[index]["metrics"]["psnr"] = 35
    result = UnityV4Policy(base_policy(), V4Options(unlock=True)).search(
        lambda i: predictions[i]["metrics"], texture(True), predictions
    )
    assert result.unlock_event is not None
    assert not result.unlock_event["budget_permitted"]
    assert result.decision.selected_index == 9
    predictions = candidates()
    predictions[19]["metrics"]["psnr"] = 35
    result = UnityV4Policy(base_policy(), V4Options(unlock=True)).search(
        lambda i: predictions[i]["metrics"], texture(True), predictions
    )
    assert result.unlock_event is not None
    assert result.unlock_event["next_block"] is None
    assert result.measured_indices == (19,)


def test_nonfinite_options_rejected() -> None:
    with pytest.raises(ValueError):
        V4Options(gate_margin_db=float("nan"))


@pytest.mark.parametrize("height,permitted", [(12000, True), (11981, False)])
def test_exact_integer_payload_budget_boundary(height: int, permitted: bool) -> None:
    spec = UnityTextureInput(44, height, True, False, False, True, 0)
    predictions, actual = candidates(35, 18), candidates(35, 18)
    actual[5]["metrics"]["ms_ssim_db"] = 22
    result = UnityV4Policy(base_policy(), V4Options(unlock=True)).search(
        lambda i: actual[i]["metrics"], spec, predictions
    )
    assert result.unlock_event is not None
    assert result.unlock_event["budget_permitted"] == permitted
    assert result.unlock_event["replaced"] == permitted
    assert result.decision.selected_index == (5 if permitted else 4)
    if permitted:
        assert 2 * result.unlock_event["proposed_payload_bytes"] == (
            3 * result.unlock_event["before_payload_bytes"]
        )


def test_normal_uses_angles_and_ignores_color_margins_and_gates() -> None:
    spec = UnityTextureInput(512, 512, False, True, False, True, 0)
    predictions = candidates(10, 0)
    predictions[7]["metrics"].update(normal_mean_deg=3.2, normal_p95_deg=9)
    options = V4Options("margin", 1, 1, gate_margin_db=0, unlock=True)
    result = UnityV4Policy(base_policy(), options).search(
        lambda i: predictions[i]["metrics"], spec, predictions
    )
    assert result.original_start == result.adjusted_start == 7
    assert result.decision.strict_quality_met
    assert result.measured_indices == (7,)
    assert result.gate_events == ()
    assert result.unlock_event is None


def test_actual_psnr_comparison_uses_native_float32() -> None:
    predictions = candidates(29.9999999, 21)
    result = UnityV4Policy(base_policy(), V4Options()).search(
        lambda i: predictions[i]["metrics"], texture(False), predictions
    )
    assert result.decision.selected_index == 0
    assert result.decision.strict_quality_met


def test_already_measured_thorough_is_reused_by_gate() -> None:
    predictions, actual = candidates(35, 18), candidates(35, 18)
    predictions[0]["metrics"]["ms_ssim_db"] = 22
    seen: list[int] = []

    def measure(index: int) -> JsonDict:
        seen.append(index)
        return actual[index]["metrics"]

    result = UnityV4Policy(base_policy(), V4Options(gate_margin_db=1)).search(
        measure, texture(True), predictions
    )
    assert seen == [0, 1, 2, 3]
    assert result.gate_events[0]["probe_cached"]
    assert result.gate_events[0]["skipped"]


def test_gate_records_a_possible_strict_quality_regression() -> None:
    predictions, actual = candidates(35, 18), candidates(35, 18)
    actual[4]["metrics"]["ms_ssim_db"] = 22
    baseline = UnityV4Policy(base_policy(), V4Options()).search(
        lambda i: actual[i]["metrics"], texture(True), predictions
    )
    gated = UnityV4Policy(base_policy(), V4Options(gate_margin_db=1)).search(
        lambda i: actual[i]["metrics"], texture(True), predictions
    )
    assert baseline.decision.strict_quality_met
    assert not gated.decision.strict_quality_met
    assert gated.gate_events[0]["candidate"] == 4
    assert gated.gate_events[0]["skipped"]
