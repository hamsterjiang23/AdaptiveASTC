from __future__ import annotations

import copy
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from PIL import Image
from torch import Tensor, nn

from adaptive_astc.data.patch_targets import PatchErrorGrid
from adaptive_astc.data.unity_image_bags import UnityImageBags
from adaptive_astc.data.unity_inference import UnityInferenceInput
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.data.unity_v3_dataset import UnityV3PatchDataset
from adaptive_astc.data.unity_v3_input import (
    SourceInputMode,
    SourceTextureSpec,
    UnityV3InferenceInput,
)
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


def source_pixels() -> NDArray[np.uint8]:
    pixels = np.zeros((123, 250, 4), dtype=np.uint8)
    pixels[:, :, 3] = 255
    pixels[0, 0] = [10, 20, 30, 255]
    pixels[-1, -1] = [40, 50, 60, 255]
    return pixels


def source_spec(pixels: NDArray[np.uint8] | None = None) -> SourceTextureSpec:
    return SourceTextureSpec.from_rgba(
        source_pixels() if pixels is None else pixels,
        target_width=250,
        target_height=123,
        srgb=True,
        normal=False,
        need_alpha=True,
        asset="Assets/Texture.png",
    )


def native_fixture(tmp_path: Path) -> UnityPatchDataset:
    native = object.__new__(UnityPatchDataset)
    native.patch_size = 240
    native.boxes = PatchErrorGrid().boxes(250, 123)
    native.image_ids = np.zeros(len(native.boxes), dtype=np.int64)
    native.pixel_counts = native.boxes[:, 2] * native.boxes[:, 3]
    native.errors = np.ones((len(native.boxes), 20, 4), dtype=np.int64)
    native.mse = native.errors / (native.pixel_counts[:, None, None] * 255**2)
    native.targets = np.log10(native.mse + 1e-10).astype(np.float32)
    native.zero_error = native.errors == 0
    native.candidate_grid = [
        [b, p] for b in UnityASTCBackend.BLOCKS for p in UnityASTCBackend.PRESETS
    ]
    native.reconstructed_psnr = [np.full(20, 40.0)]
    native.corpus_sha256 = "a" * 64
    native.fingerprint = "b" * 64
    native.split = "train"
    native.rows = [
        {
            "path": "Assets/Texture.png",
            "reference": str(tmp_path / "must-not-be-read.png"),
            "width": 250,
            "height": 123,
            "metadata": {"is_hdr": False, "is_normal": False, "need_alpha": True, "mip_count": 1},
            "import_metadata": {"srgb": True},
            "alpha_constant": False,
            "black_pixel_ratio": 0.0,
            "full_channel_squared_errors": native.errors.sum(axis=0).tolist(),
            "image_quality": [
                {"psnr": 40.0, "ms_ssim_db": 22.0, "normal_mean_deg": None, "normal_p95_deg": None}
                for _ in range(20)
            ],
        }
    ]
    return native


def test_memory_input_is_owned_and_keeps_row_order_and_padding() -> None:
    pixels = source_pixels()
    spec = source_spec(pixels)
    pixels[:] = 255
    inputs = UnityV3InferenceInput([spec])
    assert inputs.sizes == [(250, 123)]
    assert inputs.boxes.tolist() == [[0, 0, 240, 123], [240, 0, 10, 123]]
    assert inputs[0]["rgba"][:, 0, 0].tolist() == pytest.approx([10 / 255, 20 / 255, 30 / 255, 1])
    assert inputs[1]["rgba"][:, 239, 239].tolist() == pytest.approx(
        [40 / 255, 50 / 255, 60 / 255, 1]
    )
    assert inputs[1]["valid_mask"].sum().item() == 10 * 123
    assert inputs.decision_inputs[0].alpha_constant is True
    assert inputs.decision_inputs[0].black_pixel_ratio == 1 - 2 / (250 * 123)
    assert not spec.decoded_pixels().flags.writeable


def test_source_native_geometry_keeps_target_dimensions_for_prediction() -> None:
    spec = replace(source_spec(), target_width=24, target_height=12)
    inputs = UnityV3InferenceInput([spec], mode="source_native")
    assert inputs.sizes == [(250, 123)]
    assert inputs.source_sizes == [(250, 123)]
    assert inputs.decision_inputs[0].width == 24
    assert inputs.decision_inputs[0].height == 12
    np.testing.assert_array_equal(
        inputs.input_metadata[0, :2], np.log2([24, 12]).astype(np.float32)
    )
    assert len(inputs) == 2


def test_source_aligned_matches_declared_pillow_resize() -> None:
    spec = replace(source_spec(), target_width=24, target_height=12)
    inputs = UnityV3InferenceInput([spec], mode="source_aligned")
    expected = np.asarray(
        Image.fromarray(source_pixels()).resize((24, 12), resample=Image.Resampling.BICUBIC)
    )
    np.testing.assert_array_equal(inputs.pixels(0), expected)
    assert inputs.sizes == [(24, 12)]
    assert inputs.pixel_counts.tolist() == [24 * 12]
    assert inputs.timings["resize_seconds"] > 0
    assert inputs.bindings[0]["input_rgba_sha256"] == hashlib.sha256(expected.tobytes()).hexdigest()


def test_file_input_reads_only_source_and_converts_rgb_to_rgba(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source.png"
    Image.fromarray(source_pixels()[:, :, :3]).save(path)
    spec = SourceTextureSpec.from_file(
        path,
        target_width=250,
        target_height=123,
        srgb=True,
        normal=False,
        need_alpha=False,
        file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    opened: list[Path] = []
    read_bytes = Path.read_bytes

    def guarded_read(file: Path) -> bytes:
        assert file == path, "Source prediction attempted to read another file"
        opened.append(file)
        return read_bytes(file)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    inputs = UnityV3InferenceInput([spec])
    np.testing.assert_array_equal(inputs.pixels(0), source_pixels())
    assert opened == [path]
    assert inputs.timings["pixel_load_seconds"] > 0
    assert inputs.timings["resize_seconds"] == 0


def test_missing_corrupt_changed_or_wrong_size_source_rejected(tmp_path: Path) -> None:
    path = tmp_path / "source.png"
    spec = replace(source_spec(), source=path)
    with pytest.raises(FileNotFoundError):
        UnityV3InferenceInput([spec])
    path.write_bytes(b"not an image")
    with pytest.raises(OSError):
        UnityV3InferenceInput([spec])
    Image.fromarray(source_pixels()).save(path)
    with pytest.raises(ValueError, match="SHA256"):
        UnityV3InferenceInput([replace(spec, file_sha256="0" * 64)])
    with pytest.raises(ValueError, match="dimensions"):
        UnityV3InferenceInput([replace(spec, source_width=1)])


def test_source_identity_recheck_detects_same_dimension_file_change(tmp_path: Path) -> None:
    path = tmp_path / "source.png"
    pixels = source_pixels()
    Image.fromarray(pixels).save(path)
    inputs = UnityV3InferenceInput([replace(source_spec(), source=path)])
    inputs.verify_sources()
    pixels[0, 0, 0] += 1
    Image.fromarray(pixels).save(path)
    with pytest.raises(ValueError, match="Source identity changed"):
        inputs.verify_sources()
    inputs.pixels.cache_clear()
    with pytest.raises(ValueError, match="Source identity changed"):
        inputs.pixels(0)


@pytest.mark.parametrize("width,height", [(0, 1), (1, 0), (True, 2)])
def test_invalid_target_dimensions_rejected(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        replace(source_spec(), target_width=width, target_height=height)


@pytest.mark.parametrize(
    "srgb,normal,mips",
    [(True, True, 1), (False, True, 0), (False, True, 5), (True, False, 2)],
)
def test_invalid_normal_scope_rejected(srgb: bool, normal: bool, mips: int) -> None:
    with pytest.raises(ValueError, match="normal/mip"):
        replace(source_spec(), srgb=srgb, normal=normal, normal_metric_mips=mips)


def test_nonboolean_flags_and_invalid_memory_rejected() -> None:
    with pytest.raises(ValueError, match="boolean"):
        replace(source_spec(), need_alpha=cast(bool, 1))
    with pytest.raises(ValueError, match="RGBA8"):
        source_spec(cast(NDArray[np.uint8], np.zeros((2, 2, 4), dtype=np.float32)))
    with pytest.raises(ValueError, match="RGBA8"):
        source_spec(np.zeros((2, 2, 3), dtype=np.uint8))
    with pytest.raises(ValueError, match="declared source"):
        replace(source_spec(), source_height=12)
    with pytest.raises(ValueError, match="file_sha256"):
        replace(source_spec(), file_sha256="a" * 64)


def test_training_wrapper_does_not_read_reference_or_mutate_supervision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = native_fixture(tmp_path)
    before = copy.deepcopy(native.rows)

    def forbid_read(file: Path) -> bytes:
        raise AssertionError(f"Unexpected reference/target file read: {file}")

    monkeypatch.setattr(Path, "read_bytes", forbid_read)
    wrapped = UnityV3PatchDataset(native, [source_spec()])
    assert wrapped.rows == before
    assert wrapped.errors is native.errors
    assert wrapped.targets is native.targets
    assert wrapped.decision_inputs[0].alpha_constant is True
    assert wrapped.truth_decision_inputs[0].alpha_constant is False
    assert wrapped.decision_inputs[0].black_pixel_ratio > 0.99
    assert wrapped.truth_decision_inputs[0].black_pixel_ratio == 0
    assert wrapped.fingerprint != native.fingerprint
    for index in range(len(wrapped)):
        item = wrapped[index]
        torch.testing.assert_close(item["channel_log_mse"], torch.from_numpy(native.targets[index]))
        assert item["valid_pixels"].item() == native.pixel_counts[index]
        assert item["metadata"][5].item() == 1
    bags = UnityImageBags(cast(UnityPatchDataset, wrapped), [0], 4)
    assert bags.targets["channel_active"][0, 3].item() is True
    assert bags[0][0]["rgba"].shape == (4, 4, 240, 240)
    assert native.rows == before


@pytest.mark.parametrize("mutation", ["asset", "size", "srgb", "normal", "alpha", "mips"])
def test_training_wrapper_rejects_wrong_pair(tmp_path: Path, mutation: str) -> None:
    native, spec = native_fixture(tmp_path), source_spec()
    if mutation == "asset":
        spec = replace(spec, asset="Assets/Different.png")
    elif mutation == "size":
        spec = replace(spec, target_width=128)
    elif mutation == "srgb":
        spec = replace(spec, srgb=False)
    elif mutation == "normal":
        spec = replace(spec, srgb=False, normal=True)
    elif mutation == "alpha":
        spec = replace(spec, need_alpha=False)
    else:
        native.rows[0]["metadata"]["is_normal"] = True
        native.rows[0]["import_metadata"]["srgb"] = False
        native.rows[0]["metadata"]["mip_count"] = 4
        spec = replace(spec, normal=True, srgb=False, normal_metric_mips=1)
    with pytest.raises(ValueError, match="differ"):
        UnityV3PatchDataset(native, [spec])


def test_training_wrapper_rejects_native_geometry_and_mismatched_grid(tmp_path: Path) -> None:
    native = native_fixture(tmp_path)
    with pytest.raises(ValueError, match="geometry"):
        UnityV3PatchDataset(native, [source_spec()], mode="source_native")
    with pytest.raises(ValueError, match="Every"):
        UnityV3PatchDataset(native, [])
    native.boxes[1, 0] -= 1
    with pytest.raises(ValueError, match="grid"):
        UnityV3PatchDataset(native, [source_spec()])


class TinyModel(UnityQualityRegressor):
    def __init__(self) -> None:
        nn.Module.__init__(self)
        self.channel_head = nn.Linear(512, 80)

    def encode(self, rgba: Tensor, valid_mask: Tensor, metadata: Tensor) -> dict[str, Tensor]:
        return {
            "features": torch.ones(len(rgba), 512),
            "channel_log_mse": torch.full((len(rgba), 20, 4), -3.0),
        }

    def predict_images(
        self,
        features: Tensor,
        valid_pixels: Tensor,
        image_ids: Tensor,
        metadata: Tensor,
    ) -> dict[str, Tensor]:
        return {
            "channel_zero_logits": torch.full((len(metadata), 20, 4), -4.0),
            "image_quality": torch.ones(len(metadata), 20, 3),
        }


@pytest.mark.parametrize("mode", ["source_native", "source_aligned"])
def test_source_dataset_runs_existing_cpu_inference(mode: SourceInputMode) -> None:
    specs = [replace(source_spec(), target_width=24, target_height=12)]
    inputs = UnityV3InferenceInput(specs, mode=mode)
    predictions, timing = UnityQualityInference(TinyModel(), torch.device("cpu"), 2).run(
        cast(UnityInferenceInput, inputs)
    )
    assert predictions["channel_mse"].shape == (1, 20, 4)
    np.testing.assert_allclose(predictions["channel_mse"], 0.001 - 1e-10)
    assert timing["patches"] == (2 if mode == "source_native" else 1)
