"""Capture-only scoring rejects mismatched outputs and keeps native quality branches."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter as Adapter
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction as Q
from reproductions.unity_search_baseline.capture_output import UnityCaptureOutputAudit as Audit
from reproductions.unity_search_baseline.deployment import UnityDeploymentResult
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from tests.test_unity_capture_input import captured_row
from tests.test_unity_deployment import FakePredictor
from tests.test_unity_search_policy import policy


class Decoder(UnityASTCBackend):
    def __init__(self, pixels: NDArray[np.uint8]) -> None:
        self.pixels = pixels
        self.calls = 0

    def decode_payload(
        self, payload: bytes, width: int, height: int, block: int, *, srgb: bool
    ) -> tuple[NDArray[np.uint8], float]:
        self.calls += 1
        assert self.pixels.shape == (height, width, 4)
        return self.pixels.copy(), 0.001


class Quality(UnityQuality):
    def __init__(self) -> None:
        self.calls: list[JsonDict] = []

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
        np.testing.assert_array_equal(original, decoded)
        self.calls.append(
            {"alpha": need_alpha, "ssim": compute_ssim, "normal": normal, "mips": mip_count}
        )
        return {
            "psnr": 31.0,
            "black_pixel_ratio": float(np.mean(np.all(original[:, :, :3] == 0, axis=2))),
            "ms_ssim_db": 25.0 if compute_ssim else None,
            "normal_mean_deg": 1.0 if normal else None,
            "normal_p95_deg": 3.0 if normal else None,
            "mip_count": mip_count,
            "need_alpha": need_alpha,
        }


def inputs(
    tmp_path: Path, texture_type: str = "Default"
) -> tuple[Adapter, Decoder, Quality, JsonDict, UnityDeploymentResult]:
    row = captured_row(tmp_path, texture_type)
    row["selection"]["asset"] = row["path"]
    adapter = Adapter([row], "confirmation")
    with Image.open(adapter.textures[0].reference) as image:
        pixels = np.ascontiguousarray(np.asarray(image.convert("RGBA"))[::-1])
    backend, quality = Decoder(pixels), Quality()
    block = 12
    payload = bytes([17]) * (((250 + block - 1) // block) * ((7 + block - 1) // block) * 16)
    result = UnityDeploymentResult(
        [backend.container(payload, 250, 7, block)],
        [{"selected_index": 0}],
        None,
        {"images": 1, "encoding_calls": 1},
    )
    return adapter, backend, quality, row["selection"], result


@pytest.mark.parametrize("texture_type", ["Default", "Sprite", "NormalMap"])
def test_actual_decode_quality_and_labels_need_no_candidate_targets(
    tmp_path: Path, texture_type: str
) -> None:
    adapter, backend, quality, selection, result = inputs(tmp_path, texture_type)
    output = tmp_path / "output"
    audit = Audit.run(adapter, [policy()], [backend], [quality], [selection], result, output)
    row, summary = audit["rows"][0], audit["summary"]
    assert backend.calls == 1
    assert row["source_split"] == "confirmation"
    assert row["footprint_match"] and not row["full_choice_match"]
    assert row["effective_psnr_threshold"] == 37
    assert row["strict_quality_met"] == (texture_type == "NormalMap")
    assert row["payload_bytes"] == 21 * 16
    assert summary["footprint_accuracy"] == 1 and summary["full_choice_accuracy"] == 0
    assert summary["balanced_accuracy"] == 1
    assert summary["per_class"]["8x8"]["recall"] is None
    assert summary["all_candidate_rmse_db"] is None
    assert quality.calls == [
        {
            "alpha": True,
            "ssim": texture_type != "NormalMap",
            "normal": texture_type == "NormalMap",
            "mips": 4 if texture_type == "NormalMap" else 1,
        }
    ]
    with Image.open(output / "00000.png") as image:
        np.testing.assert_array_equal(np.asarray(image), backend.pixels[::-1])


@pytest.mark.parametrize(
    "change",
    [
        "width",
        "block",
        "payload",
        "magic",
        "index",
        "coverage",
        "calls",
        "reference",
        "label",
        "asset",
    ],
)
def test_mismatched_output_is_rejected_before_decode(tmp_path: Path, change: str) -> None:
    adapter, backend, quality, selection, result = inputs(tmp_path)
    raw = bytearray(result.containers[0])
    if change in {"width", "block", "magic"}:
        raw[{"width": 7, "block": 4, "magic": 0}[change]] ^= 1
    elif change == "payload":
        raw.pop()
    elif change == "index":
        result.choices[0]["selected_index"] = -1
    elif change == "coverage":
        result.choices.clear()
    elif change == "calls":
        result.timings["encoding_calls"] = 2
    elif change == "reference":
        adapter.textures[0].reference.write_bytes(b"changed")
    elif change == "label":
        selection["block_size"] = "4x4"
    elif change == "asset":
        selection["asset"] = "Assets/different.png"
    result.containers[0] = bytes(raw)
    with pytest.raises(ValueError):
        Audit.run(adapter, [policy()], [backend], [quality], [selection], result, tmp_path / "out")
    assert backend.calls == 0


@pytest.mark.parametrize(
    "black,expected", [(0, 30), (0.4, 30), (0.40001, 35), (0.8, 35), (0.80001, 37)]
)
def test_threshold_uses_native_float32_and_strict_black_boundaries(
    black: float, expected: float
) -> None:
    assert Audit.threshold(policy(), black) == expected


def test_selected_color_error_is_not_all_candidate_error(tmp_path: Path) -> None:
    adapter, backend, quality, selection, result = inputs(tmp_path)
    rows = Audit.run(
        adapter, [policy()], [backend], [quality], [selection], result, tmp_path / "out"
    )["rows"]
    rows[0].update(predicted_psnr=33.0, effective_psnr_threshold=30.0)
    summary = Audit.summarize(rows)
    assert summary["selected_color_near_threshold_count"] == 1
    assert summary["selected_color_near_threshold_rmse_db"] == 2
    assert summary["all_candidate_rmse_db"] is None
    rows[0]["normal"] = True
    assert Audit.summarize(rows)["selected_color_near_threshold_rmse_db"] is None


def test_empty_summary_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        Audit.summarize([])


@pytest.mark.parametrize("forged", [False, True])
def test_measured_quality_does_not_inherit_predicted_quality(tmp_path: Path, forged: bool) -> None:
    adapter, backend, quality, selection, result = inputs(tmp_path)
    predictor = FakePredictor()
    predictor.target_index = 0
    predicted, _ = predictor.run(adapter.dataset())
    result.predictions = predicted
    result.choices = [
        asdict(
            Q.select(
                policy(),
                adapter.decision_inputs[0],
                predicted["channel_mse"][0],
                predicted["channel_zero"][0],
                predicted["image_quality"][0],
            )
        )
    ]
    assert result.choices[0]["strict_quality_met"] is True
    if forged:
        result.choices[0]["selection_reason"] = "forged"
        with pytest.raises(ValueError, match="sealed model predictions"):
            Audit.run(
                adapter, [policy()], [backend], [quality], [selection], result, tmp_path / "out"
            )
    else:
        audit = Audit.run(
            adapter, [policy()], [backend], [quality], [selection], result, tmp_path / "out"
        )
        assert audit["rows"][0]["strict_quality_met"] is False
        assert audit["summary"]["quality_violation_count"] == 1
