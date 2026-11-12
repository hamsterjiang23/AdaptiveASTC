"""Native RGBA patch errors plus learned image-level, nonadditive quality heads."""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn
from torchvision.models.resnet import BasicBlock, ResNet

from adaptive_astc.config import JsonDict


class UnityQualityRegressor(nn.Module):
    """A ResNet-18 backbone with additive patch and nonadditive image quality heads."""

    def __init__(
        self, image_pooling: str = "mean_max", *, backbone_weights: dict[str, Tensor] | None = None
    ) -> None:
        super().__init__()
        if image_pooling not in ("mean_max", "mean"):
            raise ValueError("Native image pooling must be mean_max or mean")
        self.image_pooling = image_pooling
        backbone = ResNet(BasicBlock, [2, 2, 2, 2])
        rgb_weights = None
        if backbone_weights is not None:
            backbone.load_state_dict(backbone_weights, strict=True)
            rgb_weights = backbone.conv1.weight.detach().clone()
        backbone.conv1 = nn.Conv2d(5, 64, kernel_size=7, stride=2, padding=3, bias=False)
        nn.init.kaiming_normal_(backbone.conv1.weight, mode="fan_out", nonlinearity="relu")
        if rgb_weights is not None:
            with torch.no_grad():
                backbone.conv1.weight.zero_()
                backbone.conv1.weight[:, :3].copy_(rgb_weights)
        self.backbone = nn.Sequential(*list(backbone.children())[:-2])
        self.metadata_conditioner = nn.Linear(8, 1024)
        nn.init.zeros_(self.metadata_conditioner.weight)
        nn.init.zeros_(self.metadata_conditioner.bias)
        self.channel_head = nn.Linear(512, 80)
        self.image_head = nn.Linear(2 * 512 + 8, 140)
        nn.init.normal_(self.channel_head.weight, std=0.001)
        nn.init.constant_(self.channel_head.bias, -3.5)
        nn.init.normal_(self.image_head.weight, std=0.001)
        with torch.no_grad():
            self.image_head.bias[:80].fill_(-4.0)
            for index, initial in enumerate([21.0, 3.2, 9.0]):
                self.image_head.bias[80 + index :: 3].fill_(math.log(math.expm1(initial)))
        if image_pooling == "mean":
            # Initialize the paired control identically, then retain mean and metadata columns.
            self.image_head.in_features = 512 + 8
            self.image_head.weight = nn.Parameter(
                torch.cat((self.image_head.weight[:, :512], self.image_head.weight[:, -8:]), dim=1)
            )

    @classmethod
    def from_checkpoint(cls, checkpoint: JsonDict, device: torch.device) -> UnityQualityRegressor:
        model = cls(image_pooling=checkpoint["config"].get("image_pooling", "mean_max"))
        model.load_state_dict(checkpoint["model"], strict=True)
        return model.to(device)

    def encode(self, rgba: Tensor, valid_mask: Tensor, metadata: Tensor) -> dict[str, Tensor]:
        if (
            rgba.ndim != 4
            or rgba.shape[1] != 4
            or len(rgba) == 0
            or valid_mask.shape != (len(rgba), 1, *rgba.shape[2:])
            or valid_mask.dtype != torch.bool
            or not torch.isfinite(rgba).all()
            or torch.any(rgba < 0)
            or torch.any(rgba > 1)
            or not torch.all(valid_mask.flatten(1).any(1))
            or metadata.shape != (len(rgba), 8)
            or not torch.isfinite(metadata).all()
        ):
            raise ValueError("Require finite normalized RGBA and nonempty valid-pixel masks")
        features = torch.cat((rgba * 2 - 1, valid_mask.to(rgba.dtype)), dim=1)
        features = self.backbone(features)
        weights = nn.functional.adaptive_avg_pool2d(valid_mask.float(), features.shape[2:])
        pooled = (features.float() * weights).sum((2, 3)) / weights.sum((2, 3))
        scale = metadata.new_tensor([12, 12, 1, 1, 1, 1, 4, 1])
        gain, offset = self.metadata_conditioner(metadata / scale).float().chunk(2, dim=1)
        pooled = pooled * (1 + gain) + offset
        return {"features": pooled, "channel_log_mse": self.channel_head(pooled).reshape(-1, 20, 4)}

    @staticmethod
    def pool_features(
        features: Tensor,
        valid_pixels: Tensor,
        image_ids: Tensor,
        count: int,
        *,
        image_pooling: str = "mean_max",
    ) -> Tensor:
        if (
            features.ndim != 2
            or features.shape[1] != 512
            or len(features) == 0
            or image_ids.shape != (len(features),)
            or image_ids.dtype != torch.int64
            or valid_pixels.shape != image_ids.shape
            or not torch.isfinite(features).all()
            or not torch.isfinite(valid_pixels).all()
            or torch.any(valid_pixels <= 0)
            or type(count) is not int
            or count < 1
            or torch.any(image_ids < 0)
            or torch.any(image_ids >= count)
            or image_pooling not in ("mean_max", "mean")
        ):
            raise ValueError(
                "Require image-indexed finite512 features and positive valid-pixel counts"
            )
        weights = valid_pixels.to(device=features.device, dtype=torch.float32)
        ids = image_ids.to(features.device)
        # Fixed within-image order avoids CUDA atomic accumulation changing half-precision heads.
        order = torch.argsort(ids, stable=True)
        lengths = torch.bincount(ids, minlength=count)
        ordered_features = features[order]
        ordered_weights = weights[order]
        totals = torch.segment_reduce(ordered_weights, "sum", lengths=lengths)
        if torch.any(totals <= 0):
            raise ValueError("Each image must contribute at least one patch")
        sums = torch.segment_reduce(
            ordered_features * ordered_weights[:, None], "sum", lengths=lengths
        )
        means = sums / totals[:, None]
        if image_pooling == "mean":
            return means
        maxima = features.new_full((count, 512), -torch.inf).scatter_reduce_(
            0, ids[:, None].expand(-1, 512), features, reduce="amax", include_self=True
        )
        return torch.cat((means, maxima), dim=1)

    def predict_images(
        self,
        features: Tensor,
        valid_pixels: Tensor,
        image_ids: Tensor,
        metadata: Tensor,
    ) -> dict[str, Tensor]:
        if metadata.ndim != 2 or metadata.shape[1] != 8 or not torch.isfinite(metadata).all():
            raise ValueError("Require eight input-only metadata values per image")
        pooled = self.pool_features(
            features, valid_pixels, image_ids, len(metadata), image_pooling=self.image_pooling
        )
        scale = metadata.new_tensor([12, 12, 1, 1, 1, 1, 4, 1])
        outputs = self.image_head(torch.cat((pooled, metadata / scale), dim=1)).float()
        return {
            "channel_zero_logits": outputs[:, :80].reshape(-1, 20, 4),
            "image_quality": nn.functional.softplus(outputs[:, 80:].reshape(-1, 20, 3)),
        }

    def forward(
        self,
        rgba: Tensor,
        valid_mask: Tensor,
        image_ids: Tensor,
        metadata: Tensor,
    ) -> dict[str, Tensor]:
        if (
            metadata.ndim != 2
            or metadata.shape[1] != 8
            or image_ids.shape != (len(rgba),)
            or image_ids.dtype != torch.int64
            or torch.any(image_ids < 0)
            or torch.any(image_ids >= len(metadata))
        ):
            raise ValueError("Patch image identities must index input-only image metadata")
        patches = self.encode(rgba, valid_mask, metadata[image_ids])
        images = self.predict_images(
            patches["features"], valid_mask.sum((1, 2, 3)), image_ids, metadata
        )
        return {**patches, **images}
