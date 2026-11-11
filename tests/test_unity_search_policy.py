import copy

import numpy as np
import pytest

from adaptive_astc.config import JsonDict
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


def policy() -> UnitySearchPolicy:
    return UnitySearchPolicy(
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


def grid() -> list[JsonDict]:
    return [
        {
            "block": block,
            "preset": preset,
            "metrics": {
                "psnr": 20.0,
                "black_pixel_ratio": 0.0,
                "ms_ssim_db": 10.0,
                "normal_mean_deg": 5.0,
                "normal_p95_deg": 12.0,
            },
        }
        for block in UnityASTCBackend.BLOCKS
        for preset in UnityASTCBackend.PRESETS
    ]


def test_first_valid_respects_candidate_order_and_inclusive_threshold() -> None:
    rows = grid()
    rows[3]["metrics"].update(psnr=30.0, ms_ssim_db=21.0)
    rows[4]["metrics"].update(psnr=50.0, ms_ssim_db=30.0)
    choice = policy().select(rows, width=128, height=128, srgb=True, normal=False)
    assert (choice.selected_index, choice.candidates_measured, choice.selection_reason) == (
        3,
        4,
        "first_valid",
    )


def test_large_fallback_is_last_psnr_pass_and_counts_cross_group_measurement() -> None:
    rows = grid()
    rows[1]["metrics"]["psnr"] = 40.0
    rows[3]["metrics"]["psnr"] = 31.0
    rows[5]["metrics"].update(psnr=50.0, ms_ssim_db=60.0)
    choice = policy().select(rows, width=512, height=512, srgb=True, normal=False)
    assert (choice.selected_index, choice.candidates_measured) == (3, 6)
    assert choice.selection_reason == "size_first_relaxed"
    assert not choice.strict_quality_met and not choice.early_exit


def test_large_strict_choice_stops_within_locked_group() -> None:
    rows = grid()
    rows[5]["metrics"]["psnr"] = 30.0
    rows[7]["metrics"].update(psnr=30.0, ms_ssim_db=21.0)
    choice = policy().select(rows, width=1024, height=256, srgb=True, normal=False)
    assert (choice.selected_index, choice.candidates_measured, choice.selection_reason) == (
        7,
        8,
        "size_first_strict",
    )


def test_normal_gates_ignore_psnr_and_use_native_float32_threshold() -> None:
    rows = grid()
    rows[0]["metrics"].update(normal_mean_deg=float(np.float32(3.2)), normal_p95_deg=9.0)
    choice = policy().select(rows, width=512, height=512, srgb=False, normal=True)
    assert choice.selected_index == 0 and choice.strict_quality_met and not choice.size_first


@pytest.mark.parametrize("normal,srgb", [(True, False), (False, True), (False, False)])
def test_no_feasible_candidate_falls_back_to_first_highest_psnr(normal: bool, srgb: bool) -> None:
    rows = grid()
    rows[2]["metrics"]["psnr"] = rows[19]["metrics"]["psnr"] = 29.0
    choice = policy().select(rows, width=512, height=512, srgb=srgb, normal=normal)
    assert choice.selected_index == 2 and choice.candidates_measured == 20
    assert choice.selection_reason == "highest_psnr_fallback" and not choice.strict_quality_met


@pytest.mark.parametrize("ratio,threshold", [(0.4, 30), (0.40001, 35), (0.8, 35), (0.80001, 37)])
def test_black_thresholds_are_strict_and_strong_tier_first(ratio: float, threshold: int) -> None:
    rows = grid()
    for row in rows:
        row["metrics"].update(black_pixel_ratio=ratio, psnr=38.0)
    choice = policy().select(rows, width=128, height=128, srgb=False, normal=False)
    assert choice.effective_psnr_threshold == threshold and choice.selected_index == 0


@pytest.mark.parametrize("damage", ["missing", "duplicate", "nan", "black_mismatch"])
def test_bad_candidate_inputs_fail(damage: str) -> None:
    rows = copy.deepcopy(grid())
    if damage == "missing":
        rows.pop()
    elif damage == "duplicate":
        rows[1] = rows[0]
    elif damage == "nan":
        rows[1]["metrics"]["psnr"] = float("nan")
    else:
        rows[1]["metrics"]["black_pixel_ratio"] = 0.5
    with pytest.raises(ValueError):
        policy().select(rows, width=128, height=128, srgb=True, normal=False)
