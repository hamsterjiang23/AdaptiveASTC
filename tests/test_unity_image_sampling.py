"""Native per-epoch capping, explicit normal repeats and observed input identity."""

from collections import Counter

import pytest
import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_image_sampling import UnityImageSampler as S


def rows() -> list[JsonDict]:
    return [
        {
            "group": group,
            "path": f"Assets/{group}/{index}.png",
            "width": 240,
            "height": 240,
            "import_metadata": {"srgb": True},
            "metadata": {"is_hdr": False, "is_normal": index in (0, 8), "need_alpha": False},
            "actual_options": {"normal_pack": False},
            "alpha_constant": True,
            "black_pixel_ratio": 0.0,
        }
        for index, group in enumerate(["large"] * 8 + ["small"] * 2 + ["singleton"])
    ]


@pytest.mark.parametrize("cap,repeats", [(-1, 1), (False, 1), (0, 0), (0, True), (2, 2)])
def test_invalid_sampling_options_rejected(cap: int, repeats: int) -> None:
    with pytest.raises(ValueError):
        S(rows(), torch.Generator(), group_image_cap=cap, normal_image_repeats=repeats)


@pytest.mark.parametrize("cap,repeats", [(0, 1), (3, 1), (0, 2)])
def test_epoch_draws_and_receipts_are_reproducible(cap: int, repeats: int) -> None:
    samplers = [
        S(
            rows(),
            torch.Generator().manual_seed(7),
            group_image_cap=cap,
            normal_image_repeats=repeats,
        )
        for _ in range(2)
    ]
    source_indices = list(range(20, 31))
    for _ in range(3):
        orders = [list(sampler) for sampler in samplers]
        assert orders[0] == orders[1]
        observed = [source_indices[i] for i in orders[0]]
        receipt = samplers[0].receipt(source_indices, observed)
        assert receipt["image_draws"] == len(samplers[0])
        assert receipt["image_indices"] == observed
        if cap:
            assert len(orders[0]) == len(set(orders[0])) == 6
            assert receipt["maximum_asset_group_draws"] == 3
            assert {8, 9, 10} <= set(orders[0])
        else:
            counts = Counter(orders[0])
            assert counts == {i: repeats if i in (0, 8) else 1 for i in range(11)}
            assert receipt["normal_image_draws"] == 2 * repeats
            assert receipt["unique_images"] == 11


def test_cap_rotates_training_membership_without_mutating_rows() -> None:
    inputs = rows()
    sampler = S(inputs, torch.Generator().manual_seed(4), group_image_cap=3)
    seen = set()
    for _ in range(16):
        seen.update(list(sampler))
    assert seen == set(range(11))
    assert [row["group"] for row in inputs] == ["large"] * 8 + ["small"] * 2 + ["singleton"]


@pytest.mark.parametrize("damage", ["order", "incomplete", "source_mapping"])
def test_observed_training_inputs_must_match_drawn_order(damage: str) -> None:
    sampler = S(rows(), torch.Generator().manual_seed(9), normal_image_repeats=2)
    order = list(sampler)
    observed = [i + 100 for i in order]
    source = list(range(100, 111))
    if damage == "order":
        observed.reverse()
    if damage == "incomplete":
        observed.pop()
    if damage == "source_mapping":
        source.pop()
    with pytest.raises(ValueError, match="Observed native training image order"):
        sampler.receipt(source, observed)


def test_empty_corpus_and_missing_group_names_rejected() -> None:
    with pytest.raises(ValueError, match="nonempty training rows"):
        S([], torch.Generator())
    inputs = rows()
    inputs[0]["path"] = "invalid"
    with pytest.raises(ValueError, match="asset-group names"):
        S(inputs, torch.Generator())


def test_asset_family_cap_merges_resolution_and_character_subdirectories() -> None:
    inputs = rows()[:5]
    paths = [
        "Assets/Art/Effects/Thing/SD/a.png",
        "Assets/Art/Effects/Thing/HD/b.png",
        "Assets/Art/Effects/Thing/FHD/c.png",
        "Assets/Art/Characters/Hero/skin1/a.png",
        "Assets/Art/Characters/Hero/skin2/b.png",
    ]
    for row, path in zip(inputs, paths, strict=True):
        row["path"] = path
    sampler = S(inputs, torch.Generator().manual_seed(1), group_image_cap=1)
    assert sampler.groups[:3] == ["assets/art/effects/thing"] * 3
    assert sampler.groups[3:] == ["assets/art/characters/hero"] * 2
    assert len(list(sampler)) == 2
