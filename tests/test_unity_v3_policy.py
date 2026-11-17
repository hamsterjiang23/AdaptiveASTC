from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.system_variant_policy import VariantSpec, replay_variant
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy


def table() -> JsonDict:
    return {
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


def texture(*, large: bool = False, normal: bool = False) -> UnityTextureInput:
    return UnityTextureInput(
        512 if large else 128, 512 if large else 128, not normal, normal, False, True, 0.0
    )


def candidates(black: float = 0.0) -> list[JsonDict]:
    return [
        {
            "block": block,
            "preset": preset,
            "metrics": {
                "psnr": 20.0,
                "black_pixel_ratio": black,
                "ms_ssim_db": 10.0,
                "normal_mean_deg": 5.0,
                "normal_p95_deg": 12.0,
            },
        }
        for block, preset in NativeCandidateSet.GRID
    ]


def passing(rows: list[JsonDict], index: int) -> None:
    rows[index]["metrics"].update(
        psnr=40.0, ms_ssim_db=25.0, normal_mean_deg=2.0, normal_p95_deg=5.0
    )


def test_candidate_sets_preserve_original_ids() -> None:
    assert NativeCandidateSet.full20().active_ids == tuple(range(20))
    reduced = NativeCandidateSet.no_exhaustive16()
    assert reduced.active_ids == (0, 1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18)
    assert reduced.candidate(5) == (10, "fastest")
    assert NativeCandidateSet.from_name("no_exhaustive16") == reduced
    with pytest.raises(ValueError):
        NativeCandidateSet("unknown")


@pytest.mark.parametrize("normal,large", [(False, False), (False, True), (True, False)])
@pytest.mark.parametrize("winner", [0, 4, 7, 19, None])
def test_full_grid_reproduces_all_original_decision_fields(
    normal: bool, large: bool, winner: int | None
) -> None:
    data = candidates()
    spec = texture(large=large, normal=normal)
    if winner is not None:
        passing(data, winner)
    expected = UnitySearchPolicy(table()).select(
        data, width=spec.width, height=spec.height, srgb=spec.srgb, normal=spec.normal
    )
    policy = UnityV3Policy(table())
    assert policy.select(data, spec) == expected
    seen: list[int] = []

    def measure(index: int) -> JsonDict:
        seen.append(index)
        return data[index]["metrics"]

    actual = policy.search(measure, spec)
    assert actual.decision == expected
    assert actual.measured_indices == tuple(seen) == tuple(range(expected.candidates_measured))
    assert actual.quality_checked_indices == actual.measured_indices


@pytest.mark.parametrize("normal,large", [(False, False), (False, True), (True, False)])
def test_nonmonotonic_grid_and_float32_boundary_match_v2(normal: bool, large: bool) -> None:
    rng = np.random.default_rng(4321)
    for ratio in [0.0, 0.4, 0.4000001, 0.8, 0.8000001, 1.0]:
        spec = replace(texture(large=large, normal=normal), black_pixel_ratio=ratio)
        for _ in range(30):
            data = candidates(ratio)
            for row in data:
                row["metrics"].update(
                    psnr=float(rng.choice([20, 30, 35, 37, 37.00000001, 40])),
                    ms_ssim_db=float(rng.choice([10, 20.99999999, 21, 25])),
                    normal_mean_deg=float(rng.choice([2, 3.2, 3.20000001, 4])),
                    normal_p95_deg=float(rng.choice([5, 9, 9.00000001, 10])),
                )
            original = UnitySearchPolicy(table())
            expected = original.select(
                data, width=spec.width, height=spec.height, srgb=spec.srgb, normal=spec.normal
            )
            assert UnityV3Policy(original).select(data, spec) == expected


def test_reduced_start_is_recomputed_and_excluded_candidate_is_never_measured() -> None:
    data = candidates()
    passing(data, 4)
    passing(data, 6)
    spec = texture()
    assert UnityV3Policy(table()).select(data, spec).selected_index == 4
    policy = UnityV3Policy(table(), NativeCandidateSet.no_exhaustive16())
    assert policy.select(data, spec).selected_index == 6
    measured: list[int] = []

    def measure(index: int) -> JsonDict:
        assert data[index]["preset"] != "exhaustive"
        measured.append(index)
        return data[index]["metrics"]

    result = policy.search(measure, spec)
    assert result.measured_indices == (0, 1, 2, 3, 5, 6) == tuple(measured)
    assert result.decision.candidates_measured == 6
    with pytest.raises(ValueError, match="active"):
        policy.search(measure, spec, start=4)


@pytest.mark.parametrize(
    "candidate_set,expected",
    [
        (NativeCandidateSet.full20(), (5, 6, 7, 8, 9, 10)),
        (NativeCandidateSet.no_exhaustive16(), (5, 6, 7, 8, 10)),
    ],
)
def test_size_first_relaxed_retains_next_block_measurement(
    candidate_set: NativeCandidateSet, expected: tuple[int, ...]
) -> None:
    data = candidates()
    data[7]["metrics"]["psnr"] = 34.0
    data[8]["metrics"]["psnr"] = 32.0
    data[9]["metrics"]["psnr"] = 31.0
    passing(data, 10)
    policy = UnityV3Policy(table(), candidate_set)
    result = policy.search(lambda index: data[index]["metrics"], texture(large=True), start=5)
    assert result.measured_indices == expected
    assert result.decision.selected_index == (9 if candidate_set.name == "full20" else 8)
    assert result.decision.selection_reason == "size_first_relaxed"
    assert not result.decision.strict_quality_met


def test_last_block_relaxation_and_linear_psnr_only() -> None:
    data = candidates()
    data[18]["metrics"]["psnr"] = 35.0
    policy = UnityV3Policy(table(), NativeCandidateSet.no_exhaustive16())
    result = policy.search(lambda index: data[index]["metrics"], texture(large=True), start=15)
    assert result.decision.selected_index == 18
    assert result.decision.selection_reason == "size_first_relaxed"
    linear = replace(texture(), srgb=False)
    for row in data:
        row["metrics"]["ms_ssim_db"] = None
    decision = policy.select(data, linear)
    assert decision.selected_index == 18
    assert decision.strict_quality_met


def test_highest_psnr_fallback_ignores_inactive_and_unmeasured_candidates() -> None:
    data = candidates()
    data[4]["metrics"]["psnr"] = 100.0
    data[1]["metrics"]["psnr"] = 29.0
    data[6]["metrics"]["psnr"] = 28.0
    data[8]["metrics"]["psnr"] = 28.0 + 1e-8
    policy = UnityV3Policy(table(), NativeCandidateSet.no_exhaustive16())
    result = policy.search(lambda index: data[index]["metrics"], texture(), start=5)
    assert result.decision.selected_index == 6
    assert result.decision.selection_reason == "highest_psnr_fallback"
    assert result.measured_indices == (5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18)


def test_prediction_and_real_thresholds_are_separate() -> None:
    policy = UnityV3Policy(table())
    predicted = candidates(0.0)
    passing(predicted, 0)
    predicted[0]["metrics"]["psnr"] = 32.0
    start = policy.select(predicted, texture()).selected_index
    assert start == 0
    actual = candidates(0.9)
    passing(actual, 1)
    actual[0]["metrics"].update(psnr=32.0, ms_ssim_db=25.0)
    real_texture = replace(texture(), black_pixel_ratio=0.9)
    result = policy.search(lambda index: actual[index]["metrics"], real_texture, start)
    assert result.decision.selected_index == 1
    assert result.decision.effective_psnr_threshold == 37.0
    with pytest.raises(ValueError, match="reference texture"):
        policy.search(lambda index: actual[index]["metrics"], texture(), start)


@pytest.mark.parametrize("start", [True, -1, 20, 1.0, "1"])
def test_invalid_start_is_rejected_before_measurement(start: object) -> None:
    def measure(index: int) -> JsonDict:
        pytest.fail("Invalid start must not query a candidate")

    with pytest.raises(ValueError):
        UnityV3Policy(table()).search(measure, texture(), start)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value",
    [
        ("width", 0),
        ("height", True),
        ("srgb", 1),
        ("normal", "false"),
        ("need_alpha", None),
        ("alpha_constant", 0),
        ("black_pixel_ratio", float("nan")),
        ("black_pixel_ratio", 1.1),
    ],
)
def test_invalid_texture_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        UnityV3Policy(table()).select(candidates(), replace(texture(), **{field: value}))


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf"), 1e300])
def test_nonfinite_applicable_quality_is_rejected(value: object) -> None:
    data = candidates()
    data[0]["metrics"]["psnr"] = value
    with pytest.raises(ValueError, match="native quality"):
        UnityV3Policy(table()).select(data, texture())


def test_partial_or_reordered_candidate_array_is_rejected() -> None:
    data = candidates()
    policy = UnityV3Policy(table(), NativeCandidateSet.no_exhaustive16())
    with pytest.raises(ValueError, match="canonical20"):
        policy.select(data[:16], texture())
    data[0], data[1] = data[1], data[0]
    with pytest.raises(ValueError, match="canonical20"):
        policy.select(data, texture())


@pytest.mark.parametrize("normal,large", [(False, False), (False, True), (True, False)])
def test_full_grid_forward_traces_match_v2_from_every_start(normal: bool, large: bool) -> None:
    rng = np.random.default_rng(4321)
    spec = texture(normal=normal, large=large)
    old_policy = UnitySearchPolicy(table())
    new_policy = UnityV3Policy(old_policy)
    for _ in range(10):
        data = candidates()
        for row in data:
            row["metrics"].update(
                psnr=float(rng.choice([20, 30, 35, 40])),
                ms_ssim_db=float(rng.choice([10, 21, 25])),
                normal_mean_deg=float(rng.choice([2, 3.2, 4])),
                normal_p95_deg=float(rng.choice([5, 9, 10])),
            )
        decision = old_policy.select(
            data, width=spec.width, height=spec.height, srgb=spec.srgb, normal=spec.normal
        )
        entry = {
            "policy": old_policy,
            "texture": spec,
            "candidates": data,
            "decision": decision,
            "strict": [new_policy.strict_quality(row["metrics"], spec) for row in data],
        }
        for start in range(20):
            old = replay_variant(entry, data, start, VariantSpec("forward", "forward"))
            new = new_policy.search(lambda index: data[index]["metrics"], spec, start)
            assert new.decision.selected_index == old.selected_index
            assert new.decision.selection_reason == old.reason
            assert new.measured_indices == old.measured_indices
