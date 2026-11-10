"""Deterministic torch runtime setup."""

import os
import random
from pathlib import Path

import numpy as np
import torch

from adaptive_astc.config import SEED


class ExperimentRuntime:
    """Configure the same seeds, cache, and device as the fixed protocol."""

    @staticmethod
    def configure(seed: int = SEED) -> torch.device:
        os.environ.setdefault("TORCH_HOME", str(Path(".cache/torch").resolve()))
        torch.hub.set_dir(str(Path(".cache/torch/hub").resolve()))
        torch.set_num_threads(4)
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
