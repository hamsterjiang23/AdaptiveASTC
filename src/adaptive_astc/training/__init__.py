"""Trainer API and thin adapters for historical experiment scripts."""

from pathlib import Path

from torch import Tensor
from torch.utils.data import DataLoader

from adaptive_astc.common import SEED, JsonDict
from adaptive_astc.data.dataset import TextureDataModule
from adaptive_astc.data.dataset import TextureDataset as TextureDataset
from adaptive_astc.evaluation.inference import Predictor
from adaptive_astc.models import ASTCClassifier
from adaptive_astc.training.trainer import Trainer as Trainer
from adaptive_astc.utils.checkpoints import CheckpointStore
from adaptive_astc.utils.runtime import ExperimentRuntime

configure = ExperimentRuntime.configure
make_model = ASTCClassifier
infer = Predictor.predict
save_checkpoint = CheckpointStore.save
train_epoch = Trainer.train_epoch
require_completed_training = CheckpointStore.require_completed


def loader(
    run_dir: Path,
    rows: list[JsonDict],
    batch_size: int,
    workers: int,
    shuffle: bool = False,
    seed: int = SEED,
) -> DataLoader:
    return TextureDataModule(run_dir, workers).loader(rows, batch_size, shuffle, seed)


def train(
    run_dir: Path,
    report_dir: Path,
    initialization: str,
    epochs: int = 30,
    micro_batch: int = 64,
    workers: int = 2,
    resume: bool = False,
    max_steps: int = 0,
) -> JsonDict:
    return Trainer(
        run_dir, report_dir, initialization, epochs, micro_batch, workers, resume, max_steps
    ).fit()


def checkpoint_inference(
    run_dir: Path, initialization: str, split: str, workers: int
) -> tuple[Tensor, Tensor, JsonDict]:
    return Predictor(run_dir, workers).from_checkpoint(initialization, split)


def calibrate(run_dir: Path, report_dir: Path, initialization: str, workers: int = 2) -> JsonDict:
    from adaptive_astc.calibration import TemperatureCalibrator

    return TemperatureCalibrator(run_dir, report_dir, initialization, workers).run()


def evaluate(run_dir: Path, report_dir: Path, workers: int = 2) -> JsonDict:
    from adaptive_astc.evaluation.evaluator import Evaluator

    return Evaluator(run_dir, report_dir, workers).run()
