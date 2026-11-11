"""Guard the strict talk target, rounded bytes and explicit infeasible fallback."""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from adaptive_astc.config import CLASSES
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.gdc2023.dataset import GDCLabelSelection, GDCMeasuredDataset


def candidate(size: int, payload: int, psnr: float | None) -> dict[str, Any]:
    return {
        "footprint": [size, size],
        "payload_bytes": payload,
        "rgb_psnr": psnr,
        "lossless": psnr is None,
    }


def test_strict_target_and_payload_objective() -> None:
    rows = [candidate(12, 16, 35.0), candidate(10, 32, 35.1), candidate(8, 64, 40.0)]
    selected, valid = GDCLabelSelection.choose(rows, 35.0)
    assert valid and selected is rows[1]


def test_equal_rounded_payload_prefers_larger_footprint() -> None:
    rows = [candidate(6, 16, 45.0), candidate(12, 16, 35.1)]
    selected, valid = GDCLabelSelection.choose(rows, 35.0)
    assert valid and selected is rows[1]


def test_no_feasible_candidate_preserves_highest_quality() -> None:
    rows = [candidate(12, 16, 30.0), candidate(10, 32, 34.0), candidate(6, 64, 33.0)]
    selected, valid = GDCLabelSelection.choose(rows, 35.0)
    assert not valid and selected is rows[1]


def test_lossless_and_invalid_quality() -> None:
    rows = [candidate(12, 16, None), candidate(6, 64, 42.0)]
    selected, valid = GDCLabelSelection.choose(rows, 35.0)
    assert valid and selected is rows[0]
    with pytest.raises(ValueError, match="Invalid measured"):
        GDCLabelSelection.choose([candidate(6, 64, float("nan"))], 35.0)


def make_receipt(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Synthetic containers exercise metadata admission, without claiming native codec coverage."""
    Image.new("RGB", (4, 4)).save(directory / "input.png")
    rows = []
    for name in CLASSES:
        size = int(name.split("x")[0])
        Image.new("RGB", (4, 4)).save(directory / f"{name}.png")
        header = bytes.fromhex("13aba15c") + bytes([size, size, 1])
        header += (4).to_bytes(3, "little") * 2 + (1).to_bytes(3, "little")
        (directory / f"{name}.astc").write_bytes(header + bytes(16))
        (directory / f"{name}.txt").write_text("synthetic metadata test", encoding="utf-8")
        rows.append({**candidate(size, 16, None), "name": name, "container_bytes": 32})
    expected = {"split": "train", "path": "Assets/test.png", "fileHash": "0" * 32}
    receipt = {
        "status": "passed",
        "index": 0,
        **expected,
        "protocol_fingerprint": "frozen",
        "candidates": rows,
        "selected": rows[-1],
        "target_met": True,
        "fallback": None,
        "artifacts_sha256": {
            path.name: ArtifactStore.sha256_file(path) for path in directory.iterdir()
        },
    }
    return receipt, expected


@pytest.mark.parametrize(
    "damage", ["empty", "duplicate", "missing", "selection", "bytes", "quality"]
)
def test_receipt_rejects_incomplete_or_contradictory_measurements(
    tmp_path: Path, damage: str
) -> None:
    receipt, expected = make_receipt(tmp_path)
    GDCMeasuredDataset.validate_receipt(
        tmp_path, receipt, 0, expected, {"target_psnr": 35.0}, "frozen"
    )
    receipt = copy.deepcopy(receipt)
    if damage == "empty":
        receipt["candidates"] = []
    elif damage == "duplicate":
        receipt["candidates"].append(receipt["candidates"][0])
    elif damage == "missing":
        receipt["artifacts_sha256"].pop("input.png")
    elif damage == "selection":
        receipt["target_met"] = False
    elif damage == "bytes":
        receipt["candidates"][0]["payload_bytes"] += 16
    else:
        receipt["candidates"][0].update(rgb_psnr=1.0, lossless=False)
    with pytest.raises(ValueError):
        GDCMeasuredDataset.validate_receipt(
            tmp_path, receipt, 0, expected, {"target_psnr": 35.0}, "frozen"
        )


def test_nah_full_input_does_not_silently_run_smoke(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "script/reproduce.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "run",
            "--method",
            "nah2022_psnr_search",
            "--input-set",
            "full",
            "--run-id",
            "reject-full",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "supported only by the GDC label pipeline" in result.stderr
