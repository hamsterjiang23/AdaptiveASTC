import hashlib
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.final_encoding import UnityFinalEncoding
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class FakeBackend(UnityASTCBackend):
    def __init__(self, expected: NDArray[np.uint8]) -> None:
        self.expected = expected
        self.calls: list[tuple[int, str, bool, bool]] = []

    def encode_decode(
        self, rgba: NDArray[np.uint8], block: int, preset: str, *, srgb: bool, need_alpha: bool
    ) -> tuple[bytes, NDArray[np.uint8], JsonDict]:
        np.testing.assert_array_equal(rgba, self.expected)
        self.calls.append((block, preset, srgb, need_alpha))
        return bytes([block]) * 16, rgba.copy(), {"encode_seconds": 0.01, "decode_seconds": 0.02}


class FakeQuality(UnityQuality):
    def __init__(self, metrics: JsonDict) -> None:
        self.metrics = metrics
        self.calls: list[tuple[bool, bool, bool, int]] = []

    def measure(
        self,
        original: NDArray[np.uint8],
        decoded: NDArray[np.uint8],
        *,
        need_alpha: bool,
        compute_ssim: bool,
        normal: bool = False,
        mip_count: int = 1,
    ) -> JsonDict:
        self.calls.append((need_alpha, compute_ssim, normal, mip_count))
        return dict(self.metrics)


class AuditFixture(UnityFinalEncoding):
    def __init__(
        self, archive: Path, candidates: list[JsonDict], backend: FakeBackend, quality: FakeQuality
    ) -> None:
        self.config = {"fixed8_preset": "medium"}
        self.inputs = {}
        self.archive, self.candidates, self.backend, self.quality = (
            archive,
            candidates,
            backend,
            quality,
        )

    def candidate_source(
        self, row: JsonDict
    ) -> tuple[list[JsonDict], Path, UnityASTCBackend, UnityQuality]:
        return self.candidates, self.archive, self.backend, self.quality


def fixture(
    tmp_path: Path, normal: bool, srgb: bool
) -> tuple[AuditFixture, JsonDict, JsonDict, UnitySearchPolicy]:
    rgba = np.arange(5 * 5 * 4, dtype=np.uint8).reshape(5, 5, 4)
    reference = tmp_path / "reference.png"
    Image.fromarray(rgba[::-1]).save(reference)
    mip_count = 3 if normal else 1
    metrics = {
        "psnr": 40.0,
        "black_pixel_ratio": 0.0,
        "need_alpha": True,
        "mip_count": mip_count,
        "ms_ssim_db": 28.0 if srgb and not normal else None,
        "normal_mean_deg": 1.0 if normal else None,
        "normal_p95_deg": 2.0 if normal else None,
    }
    candidates = []
    for block, preset in UnityQualityPrediction.GRID:
        astc, png = (
            tmp_path / f"{block}x{block}_{preset}.astc",
            tmp_path / f"{block}x{block}_{preset}.png",
        )
        astc.write_bytes(UnityASTCBackend.container(bytes([block]) * 16, 5, 5, block))
        Image.fromarray(rgba[::-1]).save(png)
        candidates.append(
            {
                "block": block,
                "preset": preset,
                "payload_bytes": 16,
                "metrics": metrics,
                "astc_sha256": A.sha256_file(astc),
                "decoded_png_sha256": A.sha256_file(png),
            }
        )
    row = {
        "path": "asset.png",
        "reference": str(reference),
        "reference_sha256": A.sha256_file(reference),
        "width": 5,
        "height": 5,
        "alpha_constant": False,
        "black_pixel_ratio": 0.0,
        "metadata": {
            "is_hdr": False,
            "is_normal": normal,
            "need_alpha": True,
            "mip_count": mip_count,
        },
        "import_metadata": {"srgb": srgb},
        "actual_options": {
            "rgba_sha256": hashlib.sha256(rgba.tobytes()).hexdigest(),
            "need_alpha": True,
            "profile": 0 if srgb else 1,
            "normal_pack": False,
            "channel": 4,
        },
    }
    decision = {
        "predicted_decision": {"selected_index": 18},
        "original_decision": {"effective_psnr_threshold": 35.0},
        "actual_strict_quality_met": True,
    }
    policy = object.__new__(UnitySearchPolicy)
    policy.table = {"targetNormalMeanDeg": 2.5, "targetNormalP95Deg": 7.0, "targetMsSsimDb": 24.0}
    return (
        AuditFixture(tmp_path, candidates, FakeBackend(rgba), FakeQuality(metrics)),
        row,
        decision,
        policy,
    )


@pytest.mark.parametrize("normal,srgb", [(False, True), (False, False), (True, False)])
def test_one_encoding_per_arm_and_native_orientation_and_scope(
    tmp_path: Path, normal: bool, srgb: bool
) -> None:
    audit, row, decision, policy = fixture(tmp_path, normal, srgb)
    result = audit.encode_image(row, decision, policy, tmp_path / "outputs")
    assert audit.backend.calls == [(6, "thorough", srgb, True), (8, "medium", srgb, True)]
    assert audit.quality.calls == [(True, srgb and not normal, normal, 3 if normal else 1)] * 2
    assert all(
        arm["encoding_calls"] == 1 and arm["payload_bytes"] == 16 for arm in result["arms"].values()
    )
    assert result["arms"]["prediction"]["strict_quality_met"] is True


@pytest.mark.parametrize(
    "field,value",
    [("normal_pack", True), ("profile", 1), ("need_alpha", False), ("rgba_sha256", "bad")],
)
def test_different_native_inputs_rejected_before_encoding(
    tmp_path: Path, field: str, value: object
) -> None:
    audit, row, decision, policy = fixture(tmp_path, False, True)
    row["actual_options"][field] = value
    with pytest.raises(ValueError, match="captured options"):
        audit.encode_image(row, decision, policy, tmp_path / "outputs")
    assert not audit.backend.calls


def test_reference_and_candidate_tampering_rejected(tmp_path: Path) -> None:
    audit, row, decision, policy = fixture(tmp_path, False, True)
    row["reference_sha256"] = "wrong"
    with pytest.raises(ValueError, match="input changed"):
        audit.encode_image(row, decision, policy, tmp_path / "outputs")
    assert not audit.backend.calls


@pytest.mark.parametrize(
    "changed", [{"psnr": 39.0}, {"mip_count": 2}, {"need_alpha": False}, {"psnr": float("nan")}]
)
def test_changed_native_quality_rejected(changed: JsonDict) -> None:
    expected = {"psnr": 40.0, "mip_count": 1, "need_alpha": True}
    with pytest.raises(ValueError, match="differs"):
        UnityFinalEncoding.verify_metrics(expected | changed, expected)


def test_real_quality_must_match_frozen_prediction_outcome(tmp_path: Path) -> None:
    audit, row, decision, policy = fixture(tmp_path, False, True)
    decision["actual_strict_quality_met"] = False
    with pytest.raises(ValueError, match="strict quality differs"):
        audit.encode_image(row, decision, policy, tmp_path / "outputs")


def test_bind_detects_changes_between_read_and_final_audit(tmp_path: Path) -> None:
    audit = object.__new__(UnityFinalEncoding)
    audit.inputs = {}
    path = tmp_path / "input"
    path.write_bytes(b"a")
    audit.bind(path)
    path.write_bytes(b"b")
    with pytest.raises(ValueError, match="during audit"):
        audit.bind(path)


def test_replaced_valid_build_receipt_is_rejected(tmp_path: Path) -> None:
    audit = object.__new__(UnityFinalEncoding)
    audit.inputs = {}
    dll, path = tmp_path / "metric.dll", tmp_path / "build.json"
    dll.write_bytes(b"original")
    original = {"dll": str(dll), "dll_sha256": A.sha256_file(dll), "status": "passed"}
    dll.write_bytes(b"replacement")
    A.write_json(path, original | {"dll_sha256": A.sha256_file(dll)})
    raw = {"config": {"quality_build_receipt": str(path)}, "quality_build": original}
    with pytest.raises(ValueError, match="original frozen"):
        audit.bound_quality_receipt(raw)


def test_original_build_receipt_and_dll_are_both_required(tmp_path: Path) -> None:
    audit = object.__new__(UnityFinalEncoding)
    audit.inputs = {}
    dll, path = tmp_path / "metric.dll", tmp_path / "build.json"
    dll.write_bytes(b"original")
    original = {"dll": str(dll), "dll_sha256": A.sha256_file(dll), "status": "passed"}
    A.write_json(path, original)
    raw = {"config": {"quality_build_receipt": str(path)}, "quality_build": original}
    assert audit.bound_quality_receipt(raw) == path
    dll.write_bytes(b"replacement")
    with pytest.raises(ValueError, match="input changed"):
        audit.bound_quality_receipt(raw)


def test_candidate_artifact_tampering_rejected_before_encoding(tmp_path: Path) -> None:
    audit, row, decision, policy = fixture(tmp_path, False, True)
    (tmp_path / "6x6_thorough.astc").write_bytes(b"changed")
    with pytest.raises(ValueError, match="input changed"):
        audit.encode_image(row, decision, policy, tmp_path / "outputs")
    assert not audit.backend.calls
