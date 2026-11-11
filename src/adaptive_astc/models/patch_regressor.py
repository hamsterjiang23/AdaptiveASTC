"""Four independent native-patch log MSE outputs at ResNet-18 capacity."""

from torch import nn

from adaptive_astc.models.resnet import ASTCClassifier


class ASTCPatchRegressor(ASTCClassifier):
    def __init__(self, initialization: str, remove_maxpool: bool = True) -> None:
        if initialization not in {"scratch", "pretrained"}:
            raise ValueError("Unsupported initialization")
        super().__init__(initialization)
        if remove_maxpool:
            self.maxpool = nn.Identity()
        nn.init.normal_(self.fc.weight, std=0.001)
        nn.init.constant_(self.fc.bias, -3.5)
