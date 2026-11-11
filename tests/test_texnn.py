"""Guard published network dimensions and native block/feature pairing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from reproductions.texnn.data import TexNNLabelCollector


def make_block_labels(directory: Path) -> tuple[Path, Path, Path]:
    image = Image.new("RGB", (3, 2))
    source_pixels = [(10 * n, 10 * n + 1, 10 * n + 2) for n in range(6)]
    image.putdata(source_pixels)
    pixels = directory / "input.png"
    image.save(pixels)
    payload = bytes(range(16))
    header = bytes.fromhex("13aba15c") + bytes([4, 4, 1])
    header += (3).to_bytes(3, "little") + (2).to_bytes(3, "little")
    header += (1).to_bytes(3, "little")
    astc = directory / "image.astc"
    astc.write_bytes(header + payload)
    rgb = []
    for y in [1, 0, 0, 0]:
        for x in [0, 1, 2, 2]:
            rgb.extend(channel / 255 for channel in source_pixels[y * 3 + x])
    labels = directory / "labels.jsonl"
    labels.write_text(
        json.dumps(
            {
                "x": 0,
                "y": 0,
                "z": 0,
                "width": 3,
                "height": 2,
                "block_x": 4,
                "block_y": 4,
                "constant": True,
                "error": False,
                "partition_count": 0,
                "rgb": rgb,
                "ideal_endpoints": [0] * 24,
                "astc_hex": payload.hex(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return labels, astc, pixels


def test_native_labels_match_bottom_left_pixels_and_edge_padding(tmp_path: Path) -> None:
    labels, astc, pixels = make_block_labels(tmp_path)
    counts = TexNNLabelCollector.verify_labels(labels, astc, pixels_path=pixels)
    assert counts["blocks"] == 1
    assert counts["constant_blocks"] == 1
    row = json.loads(labels.read_text(encoding="utf-8"))
    row["rgb"][:12] = row["rgb"][12:24]
    labels.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Native RGB features differ"):
        TexNNLabelCollector.verify_labels(labels, astc, pixels_path=pixels)


def test_native_labels_reject_an_unpaired_astc_block(tmp_path: Path) -> None:
    labels, astc, _ = make_block_labels(tmp_path)
    astc.write_bytes(astc.read_bytes()[:-1] + b"\xff")
    with pytest.raises(ValueError, match="actual ASTC block"):
        TexNNLabelCollector.verify_labels(labels, astc)


def test_teacher_configuration_must_exist_in_native_catalog(tmp_path: Path) -> None:
    labels, astc, _ = make_block_labels(tmp_path)
    row = json.loads(labels.read_text(encoding="utf-8"))
    row.update(constant=False, partition_count=2, partition_index=7, block_mode=0)
    labels.write_text(json.dumps(row) + "\n", encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {"footprint": [4, 4], "partitions": [[1, 0]], "block_modes": [{"block_mode": 0}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="absent from the native catalog"):
        TexNNLabelCollector.verify_labels(labels, astc, catalog)


def test_appendix_network_layers() -> None:
    root = Path(__file__).resolve().parents[1]
    architecture = json.loads(
        (root / "reproductions/texnn/architectures.json").read_text(encoding="utf-8")
    )
    assert architecture["pnn"] == {
        "4x4": [256, 512, 1024, 2048, 3069],
        "6x6": [256, 512, 512, 1024, 2048, 3069],
        "8x8": [256, 512, 512, 1024, 1024, 2048, 3069],
    }
    assert architecture["demnn"] == {
        "4x4": [128, 256, 512, 1024, 1314],
        "6x6": [128, 256, 512, 1024, 2048, 3650],
        "8x8": [128, 256, 512, 1024, 2048, 4096, 7154],
    }
