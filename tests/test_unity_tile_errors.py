import numpy as np

from adaptive_astc.data.unity_tile_errors import UnityTileGrid, UnityTileViews


def test_partial_tiles_are_bottom_aligned_and_exclude_padding() -> None:
    grid = UnityTileGrid(height=9, width=10)
    reference = np.zeros((9, 10, 4), dtype=np.uint8)
    decoded = reference.copy()
    decoded[0, -1, 0] = 255
    decoded[1, 0, 1] = 2
    sse = grid.squared_errors(reference, decoded)
    assert grid.counts().tolist() == [[8, 2], [64, 16]]
    assert sse[..., 0].tolist() == [[0, 255**2], [0, 0]]
    assert sse[..., 1].tolist() == [[0, 0], [4, 0]]
    psnr = grid.psnr(sse[..., 0], grid.counts())
    assert np.isposinf(psnr[0, 0])
    assert np.isclose(psnr[0, 1], 10 * np.log10(2))


def test_display_composites_alpha_in_linear_light_and_keeps_encoded_opaque_rgb() -> None:
    image = np.array(
        [[[255, 255, 255, 0], [255, 255, 255, 128], [64, 1, 127, 255]]], dtype=np.uint8
    )
    assert UnityTileViews.display(image, True).tolist() == [
        [[64, 64, 64], [192, 192, 192], [64, 1, 127]]
    ]
    np.testing.assert_array_equal(UnityTileViews.display(image, False), image[..., :3])
