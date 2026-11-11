import numpy as np
import pytest
import torch

from adaptive_astc.data.patch_bags import ImagePatchBatchSampler
from adaptive_astc.data.patch_dataset import NativePatchDataset
from adaptive_astc.training.patch_loss import PatchRegressionLoss


def test_bags_preserve_identity_budget_seed_and_partial_last_batch() -> None:
    rows = [{"group": "a"}, {"group": "a"}, {"group": "b"}]
    ids = np.array([2, 0, 1, 2, 2], dtype=np.int64)

    def sampler(seed: int) -> ImagePatchBatchSampler:
        return ImagePatchBatchSampler(
            rows,
            ids,
            batch_size=8,
            bag_size=4,
            num_samples=20,
            generator=torch.Generator().manual_seed(seed),
            group_image_cap=1,
        )

    first = sampler(7)
    np.testing.assert_allclose(first.image_weights.numpy(), [0.5, 0.5, 1])
    batches = list(first)
    assert batches == list(sampler(7))
    assert len(first) == len(batches) == 3
    assert [len(batch) for batch in batches] == [8, 8, 4]
    for batch in batches:
        bag_ids = ids[batch].reshape(-1, 4)
        assert np.all(bag_ids == bag_ids[:, :1])


@pytest.mark.parametrize("batch,bag,budget", [(7, 4, 20), (8, 4, 19), (True, 1, 2), (8, 0, 20)])
def test_sampler_rejects_incomplete_bags(batch: int, bag: int, budget: int) -> None:
    with pytest.raises(ValueError):
        ImagePatchBatchSampler(
            [{"group": "a"}],
            np.array([0], dtype=np.int64),
            batch_size=batch,
            bag_size=bag,
            num_samples=budget,
            generator=torch.Generator(),
        )


def test_aggregate_matches_real_mse_weighting_not_mean_psnr() -> None:
    mse = torch.tensor([[[0.01], [0.0001]]])
    pixels = torch.tensor([[1, 9]])
    actual = PatchRegressionLoss.aggregate_log_mse(torch.log10(mse + 1e-10), pixels)
    expected = torch.log10(torch.tensor([[(0.01 + 9 * 0.0001) / 10 + 1e-10]]))
    torch.testing.assert_close(actual, expected)
    assert abs(float(actual) - float(torch.log10(mse).mean())) > 0.03


def test_full_bag_matches_existing_inference_including_zero_and_clipping() -> None:
    values = np.array([[-12, -4, 2, -3], [-10, -2, -3, -4]], dtype=np.float32)
    dataset = NativePatchDataset.__new__(NativePatchDataset)
    dataset.mse = np.zeros((2, 4))
    dataset.rows = [{}]
    dataset.image_ids = np.array([0, 0], dtype=np.int64)
    dataset.pixel_counts = np.array([57600, 240], dtype=np.int64)
    expected = np.log10(dataset.aggregate(values.astype(np.float64)) + 1e-10)
    actual = PatchRegressionLoss.aggregate_log_mse(
        torch.from_numpy(values)[None], torch.from_numpy(dataset.pixel_counts)[None]
    )
    np.testing.assert_allclose(actual.numpy(), expected, rtol=0, atol=1e-6)


def test_zero_weight_preserves_existing_loss_and_gradient_exactly() -> None:
    prediction = torch.tensor([[-3.0, -4.2], [-3.1, -2.5]], requires_grad=True)
    targets = torch.tensor([[-3.5, -4.0], [-3.2, -2.0]])
    weights = 1 + 2 * torch.exp(-torch.abs(-10 * targets - 35) / 3)
    expected = (
        torch.nn.functional.huber_loss(prediction, targets, delta=0.1, reduction="none") * weights
    ).mean()
    actual, patch, aggregate = PatchRegressionLoss(2, 0)(
        prediction, targets, torch.tensor([20, 10]), torch.tensor([0, 0])
    )
    torch.testing.assert_close(actual, expected, rtol=0, atol=0)
    torch.testing.assert_close(patch, expected, rtol=0, atol=0)
    assert float(aggregate) == 0
    expected_gradient = torch.autograd.grad(expected, prediction, retain_graph=True)[0]
    actual_gradient = torch.autograd.grad(actual, prediction)[0]
    torch.testing.assert_close(actual_gradient, expected_gradient, rtol=0, atol=0)


def test_aggregate_loss_has_finite_gradient_and_exact_target_zero_loss() -> None:
    targets = torch.tensor([[-2.0, -3.0], [-4.0, -5.0]])
    prediction = (targets + 0.3).requires_grad_()
    criterion = PatchRegressionLoss(2, 1)
    pixels, ids = torch.tensor([100, 30]), torch.tensor([1, 1])
    loss, patch, aggregate = criterion(prediction, targets, pixels, ids)
    assert loss > patch > 0 and aggregate > 0
    loss.backward()
    assert prediction.grad is not None and torch.isfinite(prediction.grad).all()
    assert torch.count_nonzero(prediction.grad) == prediction.numel()
    zero, _, _ = criterion(targets, targets, pixels, ids)
    assert float(zero) == 0


def test_cross_image_bag_and_invalid_pixels_rejected() -> None:
    values = torch.full((2, 4), -3.0)
    with pytest.raises(ValueError, match="mix image"):
        PatchRegressionLoss(2, 1)(values, values, torch.ones(2), torch.tensor([0, 1]))
    with pytest.raises(ValueError, match="positive finite"):
        PatchRegressionLoss.aggregate_log_mse(values[None], torch.tensor([[0, 1]]))


@pytest.mark.parametrize("bag,weight", [(1, 1), (2, -1), (2, float("nan")), (False, 0)])
def test_invalid_loss_configuration_rejected(bag: int, weight: float) -> None:
    with pytest.raises(ValueError):
        PatchRegressionLoss(bag, weight)
