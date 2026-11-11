from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pytest

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCFile
from reproductions.unity_search_baseline.quality import UnityQuality, UnityQualityBuild
from reproductions.unity_search_baseline.supplement import (
    UnityASTCBackend,
    UnitySupplementalCapture,
)


@pytest.fixture
def native_quality() -> UnityQuality:
    path = os.environ.get("UNITY_QUALITY_RECEIPT")
    if not path:
        pytest.skip("Native integration requires UNITY_QUALITY_RECEIPT from build-metrics")
    return UnityQuality(Path(path))


def test_extraction_rejects_missing_native_metric() -> None:
    source = (
        "prefix\n    static float CalculatePSNR() {}\n"
        "    static float CalculateMSSSIMDb_Luma() {}\n"
        "    static NormalAngularResult CalculateNormalAngularErrorMip0To3() {}\n"
        "    // Prepare original image data: suffix"
    )
    extracted = UnityQualityBuild.extract(source)
    assert extracted.startswith(UnityQualityBuild.START)
    assert "prefix" not in extracted and "suffix" not in extracted
    with pytest.raises(ValueError, match="Required native metric"):
        UnityQualityBuild.extract(source.replace("CalculateMSSSIMDb_Luma", "missing"))


def test_native_search_table_rejects_duplicate_candidates() -> None:
    row = "12x12 | fastest | 30.03 | 21.57 | 0.00 | 0.00 | 0.06 | Valid"
    assert UnitySupplementalCapture.search_table(row) == {("12x12", "fastest"): (30.03, 21.57)}
    with pytest.raises(ValueError, match="duplicated"):
        UnitySupplementalCapture.search_table(row + "\n" + row)


def test_encoder_identity_is_bound_to_original_capture(tmp_path: Path) -> None:
    ArtifactStore.write_json(
        tmp_path / "identity.json", {"encoder_dlls": {"astcenc-avx2-shared.dll": "original-dll"}}
    )
    ArtifactStore.write_json(
        tmp_path / "probe-config.json",
        {"captureReferences": True, "assets": [{"path": "Assets/a.png"}]},
    )
    lock = {
        name: ArtifactStore.sha256_file(tmp_path / name)
        for name in ["identity.json", "probe-config.json"]
    }
    ArtifactStore.write_json(tmp_path / "protocol-lock.json", lock)
    receipt = {
        "capture_provenance": {
            "protocol_sha256": ArtifactStore.sha256_file(tmp_path / "protocol-lock.json")
        },
        "rows": [{"path": "Assets/a.png"}],
    }
    config = {
        "capture_run": str(tmp_path),
        "capture_phase": "probe",
        "encoder_dll_sha256": "original-dll",
    }
    assert (
        UnitySupplementalCapture.verify_capture_provenance(config, receipt)["encoder_dll_sha256"]
        == "original-dll"
    )
    config["encoder_dll_sha256"] = "different-self-declared-dll"
    with pytest.raises(ValueError, match="original capture DLL"):
        UnitySupplementalCapture.verify_capture_provenance(config, receipt)
    config["encoder_dll_sha256"] = "original-dll"
    ArtifactStore.write_json(
        tmp_path / "identity.json", {"encoder_dlls": {"astcenc-avx2-shared.dll": "changed"}}
    )
    with pytest.raises(ValueError, match="Frozen capture identity"):
        UnitySupplementalCapture.verify_capture_provenance(config, receipt)


def test_partial_edge_blocks_have_real_payload_size(tmp_path: Path) -> None:
    path = tmp_path / "partial.astc"
    path.write_bytes(UnityASTCBackend.container(bytes(64), 14, 14, 10))
    result = ASTCFile.read(path)
    assert (result.width, result.height, result.footprint, result.payload_bytes) == (
        14,
        14,
        (10, 10),
        64,
    )


def test_supplement_rejects_changes_to_observed_alpha_and_log(tmp_path: Path) -> None:
    log = tmp_path / "probe-options.jsonl"
    log.write_text("frozen actual callback log", encoding="utf-8")
    observed = {
        "index": 0,
        "path": "Assets/a.png",
        "width": 2,
        "height": 2,
        "profile": 0,
        "need_alpha": True,
        "normal_pack": False,
        "channel": 4,
    }
    options = {
        "status": "passed",
        "run_directory": str(tmp_path),
        "capture_receipt_sha256": "capture-sha",
        "native_provenance": {"protocol": "frozen"},
        "managed_source_restoration": {
            "status": "restored",
            "original_sha256": "original",
            "restored_sha256": "original",
        },
        "options_sha256": ArtifactStore.sha256_file(log),
        "rows": [observed],
        "audit_source_sha256": "audit-sha",
    }
    path = tmp_path / "options.json"
    ArtifactStore.write_json(path, options)
    config = {
        "options_receipt": str(path),
        "options_receipt_sha256": ArtifactStore.sha256_file(path),
        "capture_run": str(tmp_path),
        "capture_phase": "probe",
        "capture_receipt_sha256": "capture-sha",
        "items": [
            {
                "index": 0,
                "path": "Assets/a.png",
                "need_alpha": True,
                "is_hdr": False,
                "is_normal": False,
            }
        ],
    }
    receipt = {
        "capture_provenance": {"protocol": "frozen"},
        "rows": [{"path": "Assets/a.png", "width": 2, "height": 2, "srgb": True}],
    }
    assert (
        UnitySupplementalCapture.verify_actual_options(config, receipt)["status"]
        == "verified_actual_callback"
    )
    options["rows"].append(
        {**observed, "index": 1, "path": "Assets/normal.png", "normal_pack": True}
    )
    receipt["rows"].append({"path": "Assets/normal.png", "width": 2, "height": 2, "srgb": True})
    ArtifactStore.write_json(path, options)
    config["options_receipt_sha256"] = ArtifactStore.sha256_file(path)
    assert (
        UnitySupplementalCapture.verify_actual_options(config, receipt)["status"]
        == "verified_actual_callback"
    )
    config["items"].append({**config["items"][0], "index": 1, "path": "Assets/normal.png"})
    with pytest.raises(ValueError, match="disagree with actual"):
        UnitySupplementalCapture.verify_actual_options(config, receipt)
    config["items"].pop()
    config["items"][0]["need_alpha"] = False
    with pytest.raises(ValueError, match="disagree with actual"):
        UnitySupplementalCapture.verify_actual_options(config, receipt)
    config["items"][0]["need_alpha"] = True
    log.write_text("changed raw record", encoding="utf-8")
    with pytest.raises(ValueError, match="callback records changed"):
        UnitySupplementalCapture.verify_actual_options(config, receipt)


def test_native_metric_excludes_lossless_channels_and_constant_alpha(
    native_quality: UnityQuality,
) -> None:
    original = np.full((2, 2, 4), 20, dtype=np.uint8)
    original[:, :, 3] = 255
    decoded = original.copy()
    decoded[:, :, 0] += 2
    decoded[:, :, 3] = 0
    metrics = native_quality.measure(original, decoded, need_alpha=True, compute_ssim=False)
    assert metrics["psnr"] == pytest.approx(20 * math.log10(255 / 2), abs=1e-5)
    original[:, :, 3] = np.array([[0, 64], [128, 255]], dtype=np.uint8)
    decoded = original.copy()
    decoded[0, 0, 3] = 1
    with_alpha = native_quality.measure(original, decoded, need_alpha=True, compute_ssim=False)
    without_alpha = native_quality.measure(original, decoded, need_alpha=False, compute_ssim=False)
    assert with_alpha["psnr"] == pytest.approx(20 * math.log10(255 / 0.5), abs=1e-5)
    assert without_alpha["psnr"] == 100


def test_native_metrics_identical_image_and_normal_angle(native_quality: UnityQuality) -> None:
    original = np.zeros((3, 5, 4), dtype=np.uint8)
    original[:, :, 3] = 255
    same = native_quality.measure(original, original, need_alpha=True, compute_ssim=True)
    assert same["psnr"] == 100 and same["ms_ssim_db"] == pytest.approx(60, abs=1e-5)
    assert same["black_pixel_ratio"] == 1
    original[:] = [128, 128, 255, 255]
    decoded = original.copy()
    decoded[:] = [255, 128, 128, 255]
    normal = native_quality.measure(
        original, decoded, need_alpha=False, compute_ssim=False, normal=True, mip_count=4
    )
    a, b = np.array([128, 128, 255]) * (2 / 255) - 1, np.array([255, 128, 128]) * (2 / 255) - 1
    expected = math.degrees(math.acos(float(a @ b / np.linalg.norm(a) / np.linalg.norm(b))))
    assert normal["normal_mean_deg"] == pytest.approx(expected, abs=0.001)
    assert normal["normal_p95_deg"] == pytest.approx(expected, abs=0.001)
