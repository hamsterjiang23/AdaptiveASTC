import pytest
import torch

from adaptive_astc.data.patch_geometry import PatchGeometry


def test_valid_area_uses_width_and_height_not_global_origin() -> None:
    boxes = torch.tensor([[0, 0, 4, 4], [240, 120, 3, 1], [12, 6, 1, 4]])
    masks = PatchGeometry.valid_mask(boxes, 4)
    assert masks.shape == (3, 1, 4, 4) and masks.dtype == torch.bool
    assert masks.sum((1, 2, 3)).tolist() == [16, 3, 4]
    assert masks[1, 0, 0].tolist() == [True, True, True, False]
    assert not masks[1, 0, 1:].any()
    assert masks[2, 0, :, 0].all() and not masks[2, 0, :, 1:].any()


@pytest.mark.parametrize(
    "boxes,patch_size",
    [
        ([[0, 0, 0, 4]], 4),
        ([[0, 0, 5, 4]], 4),
        ([[-1, 0, 4, 4]], 4),
        ([[0, 0, 4, 4]], 0),
        ([[0, 0, 4, 4]], True),
        ([[0, 0, 4]], 4),
    ],
)
def test_invalid_geometry_is_rejected(boxes: list[list[int]], patch_size: int) -> None:
    with pytest.raises(ValueError, match="geometry"):
        PatchGeometry.valid_mask(torch.tensor(boxes), patch_size)


def test_empty_and_noninteger_boxes_are_rejected() -> None:
    for boxes in [torch.empty((0, 4), dtype=torch.int64), torch.ones((1, 4))]:
        with pytest.raises(ValueError, match="geometry"):
            PatchGeometry.valid_mask(boxes)
