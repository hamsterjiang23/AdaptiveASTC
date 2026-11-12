import copy
from pathlib import Path

import numpy as np
import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from script.calibrate_unity_decisions import UnityDecisionCalibration


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


def test_margin_calibration_preserves_cached_predictions_and_applies_sign() -> None:
    candidates = grid()
    for candidate in candidates:
        candidate["metrics"].update(psnr=31.0, ms_ssim_db=22.0)
    calibration = object.__new__(UnityDecisionCalibration)
    calibration.entries = [
        {"texture": UnityTextureInput(32, 32, True, False, False, True, 0.0), "policy": policy()}
    ]
    calibration.candidate_cache = {0.5: [candidates]}
    parameters = {
        "zero_probability_threshold": 0.5,
        "psnr_margin_db": 0.0,
        "ssim_margin_db": 0.0,
        "mean_angle_margin_deg": 0.0,
        "p95_angle_margin_deg": 0.0,
    }
    snapshot = copy.deepcopy(candidates)
    baseline = calibration.select(parameters)
    stricter = calibration.select({**parameters, "psnr_margin_db": 2.0})
    assert baseline[0]["selection_reason"] == "first_valid"
    assert stricter[0]["selection_reason"] == "highest_psnr_fallback"
    assert calibration.select(parameters) == baseline
    assert candidates == snapshot


def test_calibration_rejects_active_attribution_before_artifact_access(tmp_path: Path) -> None:
    attribution = tmp_path / "attribution.json"
    ArtifactStore.write_json(attribution, {"status": "running"})
    path = tmp_path / "config.json"
    ArtifactStore.write_json(
        path,
        {
            "attribution_report": str(attribution),
            "attribution_report_sha256": ArtifactStore.sha256_file(attribution),
            "smoke": False,
            "passes": 1,
            "grids": {
                name: [0.5 if name == "zero_probability_threshold" else 0.0]
                for name in UnityDecisionCalibration.PARAMETERS
            },
            "output": str(tmp_path / "forbidden-output"),
        },
    )
    with pytest.raises(ValueError, match="completed development-only attribution"):
        UnityDecisionCalibration(path).run()
    assert not (tmp_path / "forbidden-output").exists()


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
