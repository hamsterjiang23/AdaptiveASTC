"""Exercise the compiled configuration solver when the pinned local build is available."""

from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from reproductions.common.encoder import ASTCEncoder
from reproductions.texnn.data import TexNNLabelCollector
from reproductions.texnn.runtime import TexNNConfiguration, TexNNNativeBackend


@pytest.fixture
def backend() -> TexNNNativeBackend:
    root = Path(__file__).resolve().parents[1]
    build = root / "experiment report/.local/reproduction-binaries/texnn/build-receipt.json"
    if not build.exists():
        pytest.skip("Build the pinned TexNN native targets to run native integration checks")
    return TexNNNativeBackend(root)


@pytest.mark.parametrize("size", [4, 6, 8])
def test_native_teacher_configurations_and_partition_features(
    backend: TexNNNativeBackend, tmp_path: Path, size: int
) -> None:
    source = tmp_path / "noise.png"
    Image.fromarray(np.random.default_rng(712).integers(0, 256, (11, 13, 3), dtype=np.uint8)).save(
        source
    )
    root = Path(__file__).resolve().parents[1]
    reference_dir = tmp_path / "teacher"
    TexNNLabelCollector(root).collect(source, reference_dir, (size, size))
    rows = [json.loads(line) for line in (reference_dir / "labels.jsonl").read_text().splitlines()]
    choices = [[TexNNConfiguration.from_teacher(row)] for row in rows]
    predictions = tmp_path / "oracle.bin"
    backend.write_predictions(predictions, source, (size, size), choices)
    features_file = tmp_path / "features.jsonl"
    backend.features(source, predictions, features_file, (size, size), "exhaustive")
    features = list(backend.iter_features(features_file))
    for feature in features:
        np.testing.assert_allclose(
            feature.endpoints, rows[feature.block_index]["ideal_endpoints"], rtol=0, atol=1e-7
        )
    # Inference has no teacher block mode, dual-plane selector or endpoint target yet.
    partition_only = tmp_path / "partitions.bin"
    backend.write_predictions(
        partition_only,
        source,
        (size, size),
        [
            [TexNNConfiguration(choice[0].partition_count, choice[0].partition_index)]
            for choice in choices
        ],
    )
    other_features = tmp_path / "partition-features.jsonl"
    backend.features(source, partition_only, other_features, (size, size), "exhaustive")
    assert features_file.read_bytes() == other_features.read_bytes()
    decisions = tmp_path / "decisions.jsonl"
    backend.encode(
        source, predictions, tmp_path / "oracle.astc", (size, size), "exhaustive", decisions
    )
    backend.encoder.decode(tmp_path / "oracle.astc", tmp_path / "oracle.tga")
    with (
        Image.open(tmp_path / "oracle.tga") as actual,
        Image.open(reference_dir / "teacher.tga") as expected,
    ):
        np.testing.assert_array_equal(np.asarray(actual), np.asarray(expected))
    selected = [json.loads(line) for line in decisions.read_text().splitlines()]
    assert len(features) == len(selected) == len(rows)
    assert all(row["predicted"] and not row["fallback"] and not row["error"] for row in selected)


def test_native_fallback_constant_and_bad_header(
    backend: TexNNNativeBackend, tmp_path: Path
) -> None:
    pixels = np.zeros((4, 8, 3), dtype=np.uint8)
    pixels[:, 4:, :] = np.random.default_rng(712).integers(0, 256, (4, 4, 3), dtype=np.uint8)
    source = tmp_path / "mixed.png"
    Image.fromarray(pixels).save(source)
    predictions = tmp_path / "empty.bin"
    backend.write_predictions(predictions, source, (4, 4), [[], []])
    feature_file = tmp_path / "features.jsonl"
    backend.features(source, predictions, feature_file, (4, 4), "exhaustive")
    assert feature_file.read_bytes() == b""
    decisions = tmp_path / "decisions.jsonl"
    backend.encode(source, predictions, tmp_path / "out.astc", (4, 4), "exhaustive", decisions)
    rows = [json.loads(line) for line in decisions.read_text().splitlines()]
    assert sum(row["constant"] for row in rows) == 1
    assert sum(row["fallback"] for row in rows) == 1
    backend.encoder.decode(tmp_path / "out.astc", tmp_path / "out.tga")
    assert ASTCEncoder.psnr_rgb(source, tmp_path / "out.tga") > 10
    damaged = bytearray(predictions.read_bytes())
    damaged[8:12] = struct.pack("<I", 7)
    invalid = tmp_path / "different-image.bin"
    invalid.write_bytes(damaged)
    with pytest.raises(subprocess.CalledProcessError):
        backend.encode(source, invalid, tmp_path / "bad.astc", (4, 4), "exhaustive")
