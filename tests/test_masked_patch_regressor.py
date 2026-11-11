import pytest
import torch

from adaptive_astc.data.patch_geometry import PatchGeometry
from adaptive_astc.models.masked_patch_regressor import MaskedPatchRegressor, ValidAreaPooling
from adaptive_astc.models.patch_regressor import ASTCPatchRegressor


def test_mask_pooling_uses_coverage_and_excludes_invalid_feature_cells() -> None:
    features = torch.tensor([[[[2.0, 8.0], [100.0, 200.0]]]], requires_grad=True)
    mask = PatchGeometry.valid_mask(torch.tensor([[0, 0, 3, 2]]), 4)
    result = ValidAreaPooling()(features, mask)
    torch.testing.assert_close(result, torch.tensor([[4.0]]))
    result.sum().backward()
    torch.testing.assert_close(features.grad, torch.tensor([[[[2 / 3, 1 / 3], [0.0, 0.0]]]]))


def test_tiny_valid_region_is_finite_in_half_precision_pooling() -> None:
    features = torch.full((1, 2, 8, 8), 1.5, dtype=torch.float16)
    mask = PatchGeometry.valid_mask(torch.tensor([[0, 0, 1, 1]]))
    pooled = ValidAreaPooling()(features, mask)
    assert pooled.dtype == torch.float16 and torch.isfinite(pooled).all()
    torch.testing.assert_close(pooled, torch.full((1, 2), 1.5, dtype=torch.float16))


@pytest.mark.parametrize("remove_maxpool,monotone", [(False, False), (False, True), (True, True)])
def test_full_mask_preserves_checkpoint_layout_capacity_and_predictions(
    remove_maxpool: bool, monotone: bool
) -> None:
    torch.set_num_threads(2)
    torch.manual_seed(11)
    base = ASTCPatchRegressor("scratch", remove_maxpool, monotone).eval()
    torch.manual_seed(11)
    masked = MaskedPatchRegressor("scratch", remove_maxpool, monotone).eval()
    for name, expected_state in base.state_dict().items():
        torch.testing.assert_close(masked.state_dict()[name], expected_state, atol=0, rtol=0)
    masked.load_state_dict(base.state_dict(), strict=True)
    assert list(base.state_dict()) == list(masked.state_dict())
    assert sum(p.numel() for p in base.parameters()) == 11178564
    assert sum(p.numel() for p in masked.parameters()) == 11178564
    inputs = torch.randn(2, 3, 64, 64)
    mask = torch.ones(2, 1, 64, 64, dtype=torch.bool)
    with torch.no_grad():
        expected = base(inputs)
        actual = masked(inputs, mask)
    torch.testing.assert_close(actual, expected, atol=1e-6, rtol=1e-6)
    if monotone:
        assert torch.all(actual[:, 1:] >= actual[:, :-1])


@pytest.mark.parametrize("mask_kind", ["empty", "float", "wrong_batch"])
def test_invalid_pool_masks_fail(mask_kind: str) -> None:
    mask = torch.ones(2, 1, 4, 4, dtype=torch.bool)
    if mask_kind == "empty":
        mask[1] = False
    elif mask_kind == "float":
        mask = mask.float()
    else:
        mask = mask[:1]
    with pytest.raises(ValueError):
        ValidAreaPooling()(torch.ones(2, 3, 2, 2), mask)


def test_model_requires_input_mask_geometry_to_match() -> None:
    model = MaskedPatchRegressor("scratch")
    with pytest.raises(ValueError, match="geometry"):
        model(torch.ones(2, 3, 64, 64), torch.ones(2, 1, 32, 32, dtype=torch.bool))
