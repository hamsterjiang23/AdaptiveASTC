from __future__ import annotations

import pytest
import torch

from adaptive_astc.data.patch_metadata import PatchMetadata
from adaptive_astc.models.metadata_patch_regressor import MetadataPatchRegressor
from adaptive_astc.models.patch_regressor import ASTCPatchRegressor


def test_metadata_uses_pixel_sizes_and_valid_fraction() -> None:
    features = PatchMetadata.encode(
        torch.tensor([[4096, 256], [16, 32]]), torch.tensor([[240, 16], [16, 32]]), 240
    )
    torch.testing.assert_close(
        features, torch.tensor([[1.0, 8 / 12, 1.0, 16 / 240], [4 / 12, 5 / 12, 16 / 240, 32 / 240]])
    )


@pytest.mark.parametrize(
    ("images", "valid", "size"),
    [
        ([[0, 16]], [[1, 16]], 240),
        ([[16, 16]], [[17, 16]], 240),
        ([[512, 512]], [[241, 16]], 240),
        ([[float("nan"), 16]], [[1, 16]], 240),
        ([[16.5, 16]], [[1, 16]], 240),
        ([[16, 16]], [[1.5, 16]], 240),
        ([[16, 16]], [[1, 16]], 0),
    ],
)
def test_invalid_metadata_is_rejected(
    images: list[list[float]], valid: list[list[float]], size: int
) -> None:
    with pytest.raises(ValueError):
        PatchMetadata.encode(torch.tensor(images), torch.tensor(valid), size)


@pytest.mark.parametrize("monotone", [False, True])
def test_zero_metadata_correction_preserves_initial_model_and_rng(monotone: bool) -> None:
    torch.manual_seed(27)
    original = ASTCPatchRegressor("scratch", False, monotone).eval()
    rng = torch.get_rng_state()
    torch.manual_seed(27)
    extended = MetadataPatchRegressor("scratch", False, monotone).eval()
    assert torch.equal(rng, torch.get_rng_state())
    for name, value in original.state_dict().items():
        assert torch.equal(value, extended.state_dict()[name])
    assert (
        sum(p.numel() for p in extended.parameters())
        == sum(p.numel() for p in original.parameters()) + 16
    )
    inputs = torch.randn(2, 3, 32, 32)
    metadata = torch.tensor([[0.5, 0.5, 1.0, 1.0], [1.0, 0.25, 0.1, 0.2]])
    with torch.no_grad():
        torch.testing.assert_close(original(inputs), extended(inputs, metadata), rtol=0, atol=0)


def test_metadata_receives_gradient_and_preserves_monotonicity() -> None:
    torch.manual_seed(3)
    model = MetadataPatchRegressor("scratch", False, True).eval()
    metadata = torch.tensor([[0.5, 0.5, 1.0, 1.0]])
    values = model(torch.randn(1, 3, 32, 32), metadata)
    values.sum().backward()
    assert model.metadata_weight.grad is not None
    assert torch.isfinite(model.metadata_weight.grad).all()
    assert torch.all(model.metadata_weight.grad != 0)
    with torch.no_grad():
        model.metadata_weight.copy_(torch.randn_like(model.metadata_weight) * 30)
        values = model(torch.randn(1, 3, 32, 32), metadata)
    assert torch.isfinite(values).all()
    assert torch.all(values[:, 1:] >= values[:, :-1])


def test_wrong_metadata_shape_is_rejected() -> None:
    model = MetadataPatchRegressor("scratch", False, False).eval()
    with pytest.raises(ValueError, match="four input-size features"):
        model(torch.zeros(1, 3, 32, 32), torch.zeros(1, 3))
