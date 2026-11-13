from __future__ import annotations

import copy
from pathlib import Path

import pytest
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.system_variant_policy import VariantSpec, replay_variant
from reproductions.unity_search_baseline.system_variants import (
    FrozenInputs,
    UnitySystemVariants,
    offline_contract,
)


def make_entry(*, large: bool = False, normal: bool = False) -> JsonDict:
    policy = UnitySearchPolicy(
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
    texture = UnityTextureInput(
        512 if large else 128, 512 if large else 128, not normal, normal, False, True, 0.0
    )
    candidates = [
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
        for block, preset in UnityQualityPrediction.GRID
    ]
    return {"policy": policy, "texture": texture, "candidates": candidates}


def refresh(entry: JsonDict) -> JsonDict:
    texture = entry["texture"]
    decision = entry["policy"].select(
        entry["candidates"],
        width=texture.width,
        height=texture.height,
        srgb=texture.srgb,
        normal=texture.normal,
    )
    entry["decision"] = decision
    entry["strict"] = [
        UnityQualityPrediction.strict_quality(
            entry["policy"], texture, candidate["metrics"], decision.effective_psnr_threshold
        )
        for candidate in entry["candidates"]
    ]
    return entry


def passing(entry: JsonDict, *indices: int) -> None:
    for index in indices:
        entry["candidates"][index]["metrics"].update(
            psnr=35.0, ms_ssim_db=25.0, normal_mean_deg=2.0, normal_p95_deg=5.0
        )


def test_zero_extra_measurements_degenerates_to_pure_model() -> None:
    entry = refresh(make_entry())
    result = replay_variant(
        entry, entry["candidates"], 12, VariantSpec("zero", "forward", budget=0)
    )
    assert result.selected_index == 12
    assert result.measured_indices == (12,)
    assert result.quality_checked_indices == ()
    assert result.model_used


@pytest.mark.parametrize("large,normal", [(False, False), (True, False), (False, True)])
@pytest.mark.parametrize("winner", [0, 7, 19, None])
def test_full_canonical_budget_reproduces_original_search(
    large: bool, normal: bool, winner: int | None
) -> None:
    entry = make_entry(large=large, normal=normal)
    if winner is not None:
        passing(entry, winner)
    refresh(entry)
    result = replay_variant(
        entry, entry["candidates"], 0, VariantSpec("full", "forward", budget=20)
    )
    assert result.selected_index == entry["decision"].selected_index
    assert len(result.measured_indices) == entry["decision"].candidates_measured


def test_candidate_and_block_starts_follow_their_distinct_orders() -> None:
    entry = make_entry()
    passing(entry, 6, 10)
    refresh(entry)
    candidate = replay_variant(entry, entry["candidates"], 7, VariantSpec("idx", "forward"))
    block = replay_variant(
        entry, entry["candidates"], 7, VariantSpec("block", "forward", start_mode="block_start")
    )
    assert candidate.selected_index == 10 and candidate.measured_indices == (7, 8, 9, 10)
    assert block.selected_index == 6 and block.measured_indices == (5, 6)


def test_large_relaxed_lock_preserves_native_cross_block_measurement() -> None:
    entry = make_entry(large=True)
    entry["candidates"][7]["metrics"]["psnr"] = 34.0
    entry["candidates"][9]["metrics"]["psnr"] = 31.0
    passing(entry, 10)
    refresh(entry)
    result = replay_variant(entry, entry["candidates"], 5, VariantSpec("large", "forward"))
    assert result.selected_index == 9
    assert result.measured_indices == (5, 6, 7, 8, 9, 10)
    assert result.reason == "size_first_relaxed"


def test_fallback_records_unmeasured_prefix_without_using_it_for_selection() -> None:
    entry = make_entry()
    entry["candidates"][0]["metrics"]["psnr"] = 29.0
    refresh(entry)
    result = replay_variant(entry, entry["candidates"], 10, VariantSpec("tail", "forward"))
    assert result.selected_index == 10 and result.needs_prefix_backfill
    changed = copy.deepcopy(entry)
    changed["candidates"][0]["metrics"]["psnr"] = 100.0
    repeated = replay_variant(changed, entry["candidates"], 10, VariantSpec("tail", "forward"))
    assert repeated.selected_index == result.selected_index
    assert repeated.measured_indices == result.measured_indices


def test_bidirectional_canonical_probe_can_recover_two_coarser_blocks() -> None:
    entry = make_entry()
    passing(entry, 10, 6, 2)
    refresh(entry)
    result = replay_variant(
        entry,
        entry["candidates"],
        10,
        VariantSpec("both", "bidirectional", probe_mode="canonical_block"),
    )
    assert result.selected_index == 2
    assert result.measured_indices == (10, 5, 6, 0, 1, 2)


@pytest.mark.parametrize("budget", [2, 3, 5])
def test_bidirectional_budget_is_total_unique_encodes_and_keeps_measured_winner(
    budget: int,
) -> None:
    entry = make_entry()
    passing(entry, 10, 6, 2)
    refresh(entry)
    result = replay_variant(
        entry, entry["candidates"], 10, VariantSpec("cap", "bidirectional", budget=budget)
    )
    assert len(result.measured_indices) <= budget
    assert len(set(result.measured_indices)) == len(result.measured_indices)
    assert result.selected_index in result.measured_indices
    assert result.budget_exhausted


def test_bidirectional_predicted_preset_uses_only_predicted_ranking() -> None:
    entry = make_entry()
    passing(entry, 10, 7)
    refresh(entry)
    predicted = copy.deepcopy(entry["candidates"])
    predicted[5]["metrics"].update(psnr=40.0, ms_ssim_db=30.0)
    result = replay_variant(
        entry, predicted, 10, VariantSpec("pred", "bidirectional", probe_mode="predicted_preset")
    )
    assert result.selected_index == 10 and result.measured_indices == (10, 5)


def test_normal_native_route_bypasses_model_and_uses_original_count() -> None:
    entry = make_entry(normal=True)
    passing(entry, 7)
    refresh(entry)
    result = replay_variant(
        entry,
        entry["candidates"],
        15,
        VariantSpec("normal", "bidirectional", budget=2, normal_native=True),
    )
    assert result.selected_index == 7
    assert len(result.measured_indices) == 8
    assert result.native_routed and not result.model_used


def test_frozen_input_sha_is_checked_at_read_and_after_use(tmp_path: Path) -> None:
    path = tmp_path / "frozen.json"
    path.write_text('{"test_opened":false}', encoding="utf-8")
    frozen = FrozenInputs()
    with pytest.raises(ValueError, match="SHA"):
        frozen.read(path, "0" * 64)
    frozen.read(path)
    path.write_text('{"test_opened":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        frozen.verify()


def test_replay_never_calls_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_forward(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline variant replay called a model")

    monkeypatch.setattr(torch.nn.Module, "_call_impl", forbidden_forward)
    entry = make_entry()
    passing(entry, 8)
    refresh(entry)
    replay_variant(entry, entry["candidates"], 5, VariantSpec("offline", "bidirectional"))
    assert offline_contract() == {
        "model_forward_calls": 0,
        "training_updates": 0,
        "test_opened": False,
        "actual_encoding_calls": 0,
    }


def test_native_route_uses_original_search_time_and_archive_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = make_entry(normal=True)
    passing(entry, 7)
    refresh(entry)
    entry["row"] = {
        "path": "Assets/Art/Characters/test/a.png",
        "group": "Assets/Art/Characters/test",
        "payload_bytes": [100] * 20,
        "original_selection": {"search_ms": 123.0},
    }
    entry["timings"] = [
        {"encode_seconds": 0.001, "decode_seconds": 0.002, "quality_seconds": 0.003}
        for _ in range(20)
    ]
    monkeypatch.setattr(
        "reproductions.unity_search_baseline.system_variants.grouped_metrics",
        lambda rows, decisions: {"asset_group_macro": {"groups": 1, "accuracy": 1.0}},
    )
    outcome = replay_variant(entry, entry["candidates"], 15, VariantSpec("native", "original"))
    metrics, _ = UnitySystemVariants.summarize([entry], [outcome], 20.0)
    cost = metrics["encoding_cost_estimate"]
    assert cost["estimated_total_mean_ms"] == 123.0
    assert cost["estimated_total_median_ms"] == 123.0
    assert cost["estimated_total_p95_ms"] == 123.0
    assert cost["estimated_speedup_vs_original_search"] == 1.0
    assert cost["archive_matched_total_mean_ms"] == pytest.approx(48.0)
    assert cost["estimated_speedup_vs_archive_replay"] == 1.0
