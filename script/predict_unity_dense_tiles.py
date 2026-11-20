"""Predict V5 tiles from a Unity reference PNG and its importer metadata."""

import argparse
import hashlib
import io
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from adaptive_astc.data.unity_inference import UnityInferenceTexture
from adaptive_astc.evaluation.unity_dense_tile_inference import UnityDenseTileInference
from adaptive_astc.models.unity_dense_tile import UnityDenseTileRegressor
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-run", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--color-space", choices=("srgb", "linear"), required=True)
    parser.add_argument("--normal", action="store_true")
    parser.add_argument("--need-alpha", action="store_true")
    parser.add_argument("--normal-mips", type=int, default=1)
    parser.add_argument("--y-db", type=float, nargs="+", default=[28.0, 30.0])
    parser.add_argument("--x-share", type=float)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a new prediction output directory")
    run_path = args.training_run / "report.json"
    run = A.read_json(run_path)
    if (
        run["status"] != "passed"
        or run["test_opened"] is not False
        or not run["checkpoint_reloaded"]
        or run["stage"] not in {"full", "prototype", "smoke", "aligned-smoke"}
    ):
        raise ValueError("Use a successfully reloaded V5 checkpoint")
    texture = UnityInferenceTexture(
        args.reference.resolve(),
        args.color_space == "srgb",
        args.normal,
        args.need_alpha,
        args.normal_mips,
    )
    source = texture.reference.read_bytes()
    with Image.open(io.BytesIO(source)) as image:
        # Pillow exposes 16-bit truecolor PNGs through its 8-bit RGB(A) modes.
        if (
            image.format != "PNG"
            or image.mode not in {"RGB", "RGBA"}
            or source[12:16] != b"IHDR"
            or source[24:25] != b"\x08"
        ):
            raise ValueError("Reference must be an 8-bit RGB or RGBA Unity PNG")
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    v3 = A.read_json(ROOT / "experiment report/unity-v3-20261113/progress.json")["recommendation"]
    parent_path = Path(v3["checkpoint"])
    checkpoint_path = args.training_run / "best-head.pt"
    if (
        A.sha256_file(parent_path) != v3["checkpoint_sha256"]
        or A.sha256_file(checkpoint_path) != run["best_checkpoint_sha256"]
        or run["parent_sha256"] != v3["checkpoint_sha256"]
    ):
        raise ValueError("Bound V3 parent or V5 checkpoint digest changed")
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; choose CPU inference explicitly")
    parent = UnityQualityRegressor.from_checkpoint(
        torch.load(parent_path, map_location="cpu", weights_only=True), torch.device("cpu")
    )
    model = UnityDenseTileRegressor(parent)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if (
        checkpoint["parent_sha256"] != run["parent_sha256"]
        or checkpoint["epoch"] != run["best_epoch"]
        or checkpoint["corpus_sha256"] != run["corpus_sha256"]
    ):
        raise ValueError("V5 checkpoint metadata differs from the reloaded training result")
    model.load_state_dict(checkpoint["model"], strict=True)
    patch_size = 128 if run["stage"] in {"prototype", "smoke"} else 240
    if patch_size == 128 and rgba.shape[:2] != (128, 128):
        raise ValueError("The prototype checkpoint only validates native 128x128 inputs")
    inference = UnityDenseTileInference(model, device, patch_size, args.batch_size)
    prediction = inference.predict(rgba, texture)
    result, arrays = inference.screen(rgba, texture, prediction, args.y_db, args.x_share)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifact = output / "tiles.npz"
    np.savez_compressed(artifact, allow_pickle=False, **arrays)
    A.write_json(
        output / "report.json",
        {
            "status": "passed",
            "training_stage": run["stage"],
            "training_report_sha256": A.sha256_file(run_path),
            "checkpoint_sha256": run["best_checkpoint_sha256"],
            "reference_sha256": hashlib.sha256(source).hexdigest(),
            "tiles_sha256": A.sha256_file(artifact),
            "feature_patch_size": patch_size,
            "device": device.type,
            "normal": texture.normal,
            "color_space": args.color_space,
            "need_alpha": texture.need_alpha,
            "normal_metric_mips": texture.normal_metric_mips,
            **result,
        },
    )
    print(f"Predicted {prediction.shape[1] * prediction.shape[2]} tiles for twenty candidates")


if __name__ == "__main__":
    main()
