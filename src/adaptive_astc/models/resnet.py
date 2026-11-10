"""Four-class ResNet-18 with native torchvision checkpoint keys."""

from torch import nn
from torchvision.models import ResNet18_Weights
from torchvision.models.resnet import BasicBlock, ResNet

from adaptive_astc.config import CLASSES


class ASTCClassifier(ResNet):
    """Map normalized RGB images to logits ordered by the ASTC footprint classes."""

    def __init__(self, initialization: str, pretrained: bool = True) -> None:
        # Build/load the original 1000-class head before replacing it. The RNG
        # sequence and state_dict layout match the previous resnet18 factory.
        super().__init__(BasicBlock, [2, 2, 2, 2])
        if initialization == "pretrained" and pretrained:
            weights = ResNet18_Weights.IMAGENET1K_V1
            self.load_state_dict(weights.get_state_dict(progress=True, check_hash=True))
        self.fc = nn.Linear(self.fc.in_features, len(CLASSES))
