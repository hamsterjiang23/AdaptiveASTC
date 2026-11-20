"""Train a frozen native V3 encoder with the V5 dense tile head on development data."""

import argparse
from pathlib import Path

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.training.unity_dense_tile_trainer import (
    UnityDenseTileTrainer,
    UnityDenseTrainConfig,
)
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--corpus-sha256", required=True)
    parser.add_argument(
        "--stage", choices=("smoke", "aligned-smoke", "prototype", "full"), required=True
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--loss-cap-db", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "experiment report/.local/unity-v5-20261119"):
        parser.error("V5 training outputs must be in the local V5 experiment directory")
    matrix = A.read_json(ROOT / "experiment plan/V5/matrix.json")
    archive = UnityTileArchive(
        ROOT / "experiment report/unity-accuracy90-20261111/unity-v2-data-inputs.json"
    )
    parent = ROOT / "experiment report/.local/unity-v3-20261113/train-unity-head-full-v1/best.pt"
    config = UnityDenseTrainConfig(
        args.stage,
        args.corpus.resolve(),
        args.corpus_sha256,
        parent,
        matrix["parent"]["checkpoint_sha256"],
        output,
        args.epochs,
        args.batch_size,
        loss_cap_db=args.loss_cap_db,
    )
    result = UnityDenseTileTrainer(archive, config).run()
    print(
        f"{result['status']}: {result['training_updates']} updates and checkpoint reload verified"
    )


if __name__ == "__main__":
    main()
