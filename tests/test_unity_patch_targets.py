"""Exercise native channel semantics that differ from RGB-average GDC targets."""

import os
from pathlib import Path

import numpy as np
import pytest
from test_unity_candidate_archive import CandidateFixture

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.patch_targets import UnityChannelErrors, UnityPatchCorpus
from reproductions.unity_search_baseline.quality import UnityQuality


def test_native_psnr_excludes_lossless_channels_and_constant_alpha() -> None:
    errors = np.array([[100, 0, 0, 6502500], [0, 0, 0, 6502500]], dtype=np.int64)
    result = UnityChannelErrors.psnr(errors, 100, need_alpha=True, alpha_constant=True)
    assert result[0] == pytest.approx(20 * np.log10(255))
    assert result[1] == 100
    included = UnityChannelErrors.psnr(errors, 100, need_alpha=True, alpha_constant=False)
    assert included[1] == 0
    ignored = UnityChannelErrors.psnr(errors, 100, need_alpha=False, alpha_constant=False)
    np.testing.assert_array_equal(result, ignored)


def test_patch_sums_cover_edges_once_per_channel() -> None:
    rng = np.random.default_rng(23)
    original = rng.integers(0, 256, (247, 509, 4), dtype=np.uint8)
    decoded = rng.integers(0, 256, original.shape, dtype=np.uint8)
    helper = UnityChannelErrors()
    boxes = helper.grid.boxes(509, 247)
    sums = helper.squared_errors(original, decoded)
    assert int((boxes[:, 2] * boxes[:, 3]).sum()) == 509 * 247
    assert not (boxes[:, :2] % 120).any()
    full = ((original.astype(np.int64) - decoded) ** 2).sum(axis=(0, 1))
    np.testing.assert_array_equal(sums.sum(axis=0), full)


@pytest.mark.parametrize("need_alpha,constant", [(False, False), (True, False), (True, True)])
def test_channel_aggregation_matches_native_library(need_alpha: bool, constant: bool) -> None:
    receipt = os.environ.get("UNITY_QUALITY_RECEIPT")
    if not receipt:
        pytest.skip("Native quality library not configured")
    rng = np.random.default_rng(41)
    reference = rng.integers(0, 256, (17, 31, 4), dtype=np.uint8)
    if constant:
        reference[:, :, 3] = 0
    decoded = reference.copy()
    decoded[:, :, 0] //= 2
    decoded[:, :, 3] = 255
    helper = UnityChannelErrors()
    sums = helper.squared_errors(reference, decoded).sum(axis=0)[None]
    predicted = helper.psnr(sums, 17 * 31, need_alpha=need_alpha, alpha_constant=constant)[0]
    measured = UnityQuality(Path(receipt)).measure(
        reference, decoded, need_alpha=need_alpha, compute_ssim=False
    )["psnr"]
    assert predicted == pytest.approx(measured, abs=1e-5)


def corpus_fixture(root: Path) -> tuple[UnityPatchCorpus, JsonDict]:
    fixture = CandidateFixture(root)
    for candidate in fixture.candidates:
        candidate["metrics"]["psnr"] = 100.0
    fixture.config["report"] = str(fixture.report)
    ArtifactStore.write_json(fixture.config_path, fixture.config)
    fixture.publish()
    ArtifactStore.write_json(fixture.folder / "receipt.json", fixture.row)
    reference = root / "input.png"
    reference.write_bytes((fixture.folder / "12x12_fastest.png").read_bytes())
    row = {
        **fixture.references[0],
        "source_split": "train",
        "capture_index": 0,
        "reference_png": str(reference),
        "reference_sha256": ArtifactStore.sha256_file(reference),
        "candidate_directory": str(fixture.folder),
        "candidate_receipt_sha256": fixture.row["candidate_receipt_sha256"],
        "candidate_report_sha256": ArtifactStore.sha256_file(fixture.report),
        "import_metadata": {"mipmaps": False},
    }
    manifest = root / "manifest.json"
    ArtifactStore.write_json(
        manifest,
        {
            "status": "passed",
            "test_opened": False,
            "original_search_labels_preserved": True,
            "splits": {"train": [row], "validation": []},
            "counts": {"train": 1, "validation": 0},
            "coverage": "selected",
        },
    )
    config = root / "patch-config.json"
    ArtifactStore.write_json(
        config,
        {
            "candidate_manifest": str(manifest),
            "candidate_manifest_sha256": ArtifactStore.sha256_file(manifest),
            "output": str(root / "patches"),
            "report": str(root / "patch-report.json"),
        },
    )
    return UnityPatchCorpus(config), row


def test_corpus_resume_binds_native_candidate_list_and_target_file(tmp_path: Path) -> None:
    corpus, _ = corpus_fixture(tmp_path)
    first, second = corpus.prepare(), corpus.prepare()
    assert first["fingerprint"] == second["fingerprint"]
    assert first["max_psnr_reconstruction_error_db"] == 0
    (corpus.output / "train/00000.npz").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="Cached patch targets"):
        corpus.prepare()


def test_unbound_image_metadata_cannot_change_alpha_semantics(tmp_path: Path) -> None:
    corpus, row = corpus_fixture(tmp_path)
    path = Path(row["candidate_directory"]) / "receipt.json"
    changed = ArtifactStore.read_json(path)
    changed["metadata"]["need_alpha"] = True
    ArtifactStore.write_json(path, changed)
    with pytest.raises(ValueError, match="image receipt changed"):
        corpus.prepare()


def test_test_rows_cannot_enter_development_corpus(tmp_path: Path) -> None:
    corpus, _ = corpus_fixture(tmp_path)
    path = Path(corpus.config["candidate_manifest"])
    manifest = ArtifactStore.read_json(path)
    manifest["splits"]["train"][0]["source_split"] = "test"
    ArtifactStore.write_json(path, manifest)
    corpus.config["candidate_manifest_sha256"] = ArtifactStore.sha256_file(path)
    with pytest.raises(ValueError, match="split identity"):
        corpus.prepare()
