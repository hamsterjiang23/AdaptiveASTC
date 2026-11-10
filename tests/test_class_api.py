"""Regression coverage for class APIs and historical model compatibility."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torchvision.models import resnet18

from adaptive_astc.config import CLASSES, SEED
from adaptive_astc.data.dataset import TextureDataModule, TextureDataset
from adaptive_astc.models import ASTCClassifier
from adaptive_astc.training import make_model, train_epoch
from adaptive_astc.training.trainer import Trainer


def test_classifier_preserves_factory_weights_and_rng() -> None:
    torch.manual_seed(SEED)
    original = resnet18(weights=None)
    original.fc = nn.Linear(original.fc.in_features, len(CLASSES))
    original_rng = torch.get_rng_state()
    torch.manual_seed(SEED)
    model = ASTCClassifier("scratch")
    assert model.state_dict().keys() == original.state_dict().keys()
    for name, value in original.state_dict().items():
        assert torch.equal(value, model.state_dict()[name]), name
    assert torch.equal(original_rng, torch.get_rng_state())
    model.eval()
    original.eval()
    image = torch.zeros((1, 3, 32, 32))
    with torch.inference_mode():
        assert torch.equal(model(image), original(image))
        assert model(image).shape == (1, 4)


def test_data_module_normalization_and_seeded_loader(tmp_path: Path) -> None:
    rows = []
    for index in range(8):
        path = tmp_path / f"{index}.npy"
        np.save(path, np.full((224, 224, 3), index, dtype=np.uint8), allow_pickle=False)
        rows.append({"cache": path.name, "class_id": index % 4})
    dataset = TextureDataset(tmp_path, rows)
    image, label = dataset[0]
    assert len(dataset) == 8 and label == 0 and image.shape == (3, 224, 224)
    assert torch.equal(image[:, 0, 0], -dataset.mean.flatten() / dataset.std.flatten())
    data = TextureDataModule(tmp_path, workers=0)
    first = list(data.loader(rows, 4, shuffle=True, seed=123))
    second = list(data.loader(rows, 4, shuffle=True, seed=123))
    for (images, labels), (other_images, other_labels) in zip(first, second, strict=True):
        assert torch.equal(images, other_images)
        assert torch.equal(labels, other_labels)


def test_prepare_and_help_import_without_training_stack() -> None:
    program = (
        "import sys; from adaptive_astc.cli import ExperimentCLI; "
        "ExperimentCLI.parser(); "
        "assert 'torch' not in sys.modules; "
        "assert 'matplotlib' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", program], check=True, capture_output=True, text=True)


def test_legacy_model_and_epoch_names_are_class_adapters() -> None:
    assert make_model is ASTCClassifier
    assert train_epoch is Trainer.train_epoch
