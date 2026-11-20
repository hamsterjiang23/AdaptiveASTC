"""Run the V3 production selection path on an approved V5 native checkpoint."""

import argparse
import time
from pathlib import Path

import torch

from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_dense_native_regression import UnityDenseNativeRegression
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", type=int, nargs="+")
    parser.add_argument("--native-checkpoint", type=Path)
    parser.add_argument("--native-checkpoint-sha256")
    args = parser.parse_args()
    if bool(args.native_checkpoint) != bool(args.native_checkpoint_sha256):
        parser.error("Bind the native checkpoint path and SHA together")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "experiment report/.local/unity-v5-20261119"):
        parser.error("Keep V5 raw results in its local experiment directory")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        matrix = A.read_json(ROOT / "experiment plan/V5/matrix.json")
        parent = (
            ROOT / "experiment report/.local/unity-v3-20261113/train-unity-head-full-v1/best.pt"
        )
        parent_sha = matrix["parent"]["checkpoint_sha256"]
        checkpoint = args.native_checkpoint or parent
        expected_sha = args.native_checkpoint_sha256 or parent_sha
        if A.sha256_file(checkpoint) != expected_sha:
            raise ValueError("Checkpoint SHA-256 differs from the locked identity")
        if not torch.cuda.is_available():
            raise RuntimeError("V3 native comparison requires CUDA for parity")
        device = torch.device("cuda")
        torch.backends.cudnn.benchmark = False
        handoff = ROOT / "experiment report/unity-accuracy90-20261111/unity-v2-data-inputs.json"
        archive = UnityTileArchive(handoff)
        model = UnityQualityRegressor.from_checkpoint(
            torch.load(checkpoint, map_location="cpu", weights_only=True), device
        )
        result = UnityDenseNativeRegression(ROOT, archive, args.indices or list(range(1000))).run(
            model, device
        )
        result.update(checkpoint_sha256=expected_sha, training_updates=0, actual_encoding_calls=0)
        if (
            args.native_checkpoint is None
            and args.indices is None
            and any(result["changes_from_v3"].values())
        ):
            result["status"] = "parent_parity_mismatch"
        result["wall_seconds"] = time.perf_counter() - started
        A.write_json(output / "report.json", result)
        changes = len(result["changes_from_v3"]["selected_index"])
        print(f"{result['status']}: {result['images']} images; {changes} changed choices")
        if result["status"] != "passed":
            raise SystemExit(1)
    except Exception as error:
        A.write_json(output / "failure.json", {"status": "failed", "error": str(error)})
        raise


if __name__ == "__main__":
    main()
