from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from adaptive_astc.config import CLASSES, JsonDict
from adaptive_astc.data.patch_targets import GDCPatchCorpus, PatchErrorGrid
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.gdc2023.dataset import GDCLabelSelection


def test_exact_patch_aggregation_with_small_edges_and_zero_error() -> None:
    grid = PatchErrorGrid(240)
    reference = np.zeros((241, 481, 3), dtype=np.uint8)
    decoded = reference.copy()
    decoded[:, 240:480] = 11
    decoded[240:, 480:] = 255
    boxes, errors = grid.squared_errors(reference, decoded)
    counts = boxes[:, 2] * boxes[:, 3]
    assert counts.sum() == 241 * 481
    assert len(boxes) == 6
    assert np.all(boxes[:, :2] % 120 == 0)
    full_mse = np.square(reference.astype(np.float64) - decoded).mean() / 255**2
    patch_mse = errors / (counts * 3 * 255**2)
    np.testing.assert_allclose(np.average(patch_mse, weights=counts), full_mse, rtol=1e-14)
    assert not np.isclose(patch_mse.mean(), full_mse)
    assert np.isinf(grid.psnr(np.array([0.0]))[0])


def test_strict_threshold_and_nonmonotonic_fallback() -> None:
    quality = np.array([[40, 36, 35, 30], [30, 34, 31, 32], [40, 32, 36, 34]])
    assert PatchErrorGrid.choose(quality).tolist() == [1, 1, 2]
    assert PatchErrorGrid.choose(quality, 1.0).tolist() == [0, 1, 0]
    ties = np.array([[34, 34, 34, 34], [33, 34, 34, 32]])
    assert PatchErrorGrid.choose(ties).tolist() == [3, 2]


def test_grid_rejects_misalignment() -> None:
    with pytest.raises(ValueError):
        PatchErrorGrid(256)


def make_measured_fixture(root: Path) -> None:
    splits: dict[str, list[JsonDict]] = {"train": [], "validation": []}
    inputs: list[JsonDict] = []
    for index, split in enumerate(splits):
        folder = root / "labels" / f"{index:05d}"
        folder.mkdir(parents=True)
        reference = np.full((241, 244, 3), 100, dtype=np.uint8)
        Image.fromarray(reference).save(folder / "input.png")
        candidates = []
        for candidate_id, name in enumerate(CLASSES):
            delta = candidate_id + 1
            decoded = reference.copy()
            decoded[::2] += delta
            Image.fromarray(decoded).save(folder / f"{name}.png")
            mse = np.square((decoded.astype(float) - reference) / 255).mean()
            block = int(name.split("x")[0])
            candidates.append(
                {
                    "name": name,
                    "footprint": [block, block],
                    "rgb_psnr": float(-10 * np.log10(mse)),
                    "lossless": False,
                    "payload_bytes": ((244 + block - 1) // block)
                    * ((241 + block - 1) // block)
                    * 16,
                }
            )
        selected, passed = GDCLabelSelection.choose(candidates, 35)
        identity = {"split": split, "path": f"Assets/{split}.png", "fileHash": str(index)}
        inputs.append(identity)
        hashes = {path.name: ArtifactStore.sha256_file(path) for path in folder.glob("*.png")}
        receipt = {
            "status": "passed",
            "index": index,
            **identity,
            "candidates": candidates,
            "selected": selected,
            "target_met": passed,
            "artifacts_sha256": hashes,
        }
        ArtifactStore.write_json(folder / "receipt.json", receipt)
        splits[split].append(
            {
                **identity,
                "group": split,
                "width": 244,
                "height": 241,
                "class_id": CLASSES.index(selected["name"]),
                "label_receipt_sha256": ArtifactStore.sha256_file(folder / "receipt.json"),
            }
        )
    ArtifactStore.write_json(root / "protocol.json", {"target_psnr": 35, "inputs": inputs})
    ArtifactStore.write_json(
        root / "manifest.json",
        {
            "classes": list(CLASSES),
            "splits": splits,
            "label_protocol_sha256": ArtifactStore.sha256_file(root / "protocol.json"),
        },
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("class_id", 0),
        ("split", "test"),
        ("reference", "elsewhere.png"),
        ("full_squared_errors", [0, 0, 0, 0]),
        ("patch_count", 999),
    ],
)
def test_cache_identity_and_statistics_tampering_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    measured, output = tmp_path / "measured", tmp_path / "patches"
    make_measured_fixture(measured)
    builder = GDCPatchCorpus(measured, output)
    first = builder.prepare()
    assert builder.prepare()["fingerprint"] == first["fingerprint"]
    sidecar = output / "targets/00000.json"
    row = ArtifactStore.read_json(sidecar)
    row[field] = value
    ArtifactStore.write_json(sidecar, row)
    with pytest.raises(ValueError, match="Patch cache"):
        builder.prepare()


def test_dataset_aggregates_exact_log_targets(tmp_path: Path) -> None:
    from adaptive_astc.data.patch_dataset import NativePatchDataset

    measured, output = tmp_path / "measured", tmp_path / "patches"
    make_measured_fixture(measured)
    GDCPatchCorpus(measured, output).prepare()
    dataset = NativePatchDataset(output, "train")
    restored = dataset.aggregate(np.log10(dataset.mse + 1e-10))
    expected = dataset.errors.sum(axis=0) / (241 * 244 * 3 * 255**2)
    np.testing.assert_allclose(restored[0], expected, rtol=1e-12)
    image, target, index = dataset[3]
    assert image.shape == (3, 240, 240) and target.shape == (4,) and index == 3


def test_dataset_rejects_changed_preprocessing(tmp_path: Path) -> None:
    from adaptive_astc.data.patch_dataset import NativePatchDataset

    measured, output = tmp_path / "measured", tmp_path / "patches"
    make_measured_fixture(measured)
    GDCPatchCorpus(measured, output).prepare()
    corpus = ArtifactStore.read_json(output / "corpus.json")
    corpus["config"]["patch_size"] = 480
    ArtifactStore.write_json(output / "corpus.json", corpus)
    with pytest.raises(ValueError, match="preprocessing"):
        NativePatchDataset(output, "train")
