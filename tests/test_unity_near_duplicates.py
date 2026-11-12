"""Aligned near-duplicate screening preserves frozen pixels, alpha and split identities."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from test_unity_pixel_identity import capture

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.near_duplicates import (
    UnityAlignedPixelDistance as Distance,
)
from reproductions.unity_search_baseline.near_duplicates import UnityNearDuplicateAudit as Audit
from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit as Exact


@pytest.mark.parametrize("shape", [(2, 2, 4), (13, 17, 4), (120, 240, 4)])
@pytest.mark.parametrize("grid", [1, 8, 16])
def test_weighted_cell_distance_is_a_lower_bound_even_at_uneven_edges(
    shape: tuple[int, int, int], grid: int
) -> None:
    rng = np.random.default_rng(412)
    left = rng.integers(0, 256, shape, dtype=np.uint8)
    right = rng.integers(0, 256, shape, dtype=np.uint8)
    lower = np.linalg.norm(Distance.descriptor(left, grid) - Distance.descriptor(right, grid))
    actual = Distance.measure(left, right)["rgba_rmse_8bit"]
    assert lower <= actual + 1e-10
    if grid >= max(shape[:2]):
        assert lower == pytest.approx(actual)


def test_prefilter_retains_every_pair_within_full_pixel_threshold() -> None:
    rng = np.random.default_rng(413)
    template = rng.integers(10, 240, (17, 19, 4), dtype=np.uint8)
    images = [
        (template.astype(np.int16) + rng.integers(-scale, scale + 1, template.shape)).astype(
            np.uint8
        )
        for scale in range(1, 6)
        for _ in range(4)
    ]
    descriptors = np.stack([Distance.descriptor(image, 8) for image in images])
    retrieved = {tuple(pair) for pair in Distance.candidates(descriptors, 2.0, 10000)}
    expected = {
        (i, j)
        for i in range(len(images))
        for j in range(i + 1, len(images))
        if Distance.measure(images[i], images[j])["rgba_rmse_8bit"] <= 2.0
    }
    assert expected and expected <= retrieved
    measured = {
        (i, j)
        for i, j in retrieved
        if Distance.measure(images[i], images[j])["rgba_rmse_8bit"] <= 2.0
    }
    assert measured == expected


def test_full_resolution_check_rejects_equal_cell_means() -> None:
    pattern = np.indices((16, 16)).sum(axis=0) % 2 * 255
    left = np.repeat(pattern[..., None], 4, axis=2).astype(np.uint8)
    right = 255 - left
    descriptors = np.stack([Distance.descriptor(p, 8) for p in [left, right]])
    assert Distance.candidates(descriptors, 2.0, 1).tolist() == [[0, 1]]
    assert Distance.measure(left, right)["rgba_rmse_8bit"] == 255


def test_alpha_and_full_8bit_range_do_not_overflow() -> None:
    left = np.zeros((130, 17, 4), dtype=np.uint8)
    right = np.full_like(left, 255)
    result = Distance.measure(left, right)
    assert result["rgba_rmse_8bit"] == result["maximum_absolute_error_8bit"] == 255
    assert result["channel_rmse_8bit"] == [255] * 4
    right[..., :3] = 0
    assert Distance.measure(left, right)["rgba_rmse_8bit"] == 127.5


def test_boundary_pair_is_retrieved_and_budget_excess_is_not_a_pass() -> None:
    left = np.zeros((7, 11, 4), dtype=np.uint8)
    right = np.full_like(left, 2)
    descriptors = np.stack([Distance.descriptor(p, 8) for p in [left, right]])
    assert Distance.candidates(descriptors, 2.0, 1).tolist() == [[0, 1]]
    assert Distance.measure(left, right)["rgba_rmse_8bit"] == 2
    with pytest.raises(ValueError, match="budget exceeded"):
        Distance.candidates(np.zeros((50, 32), dtype=np.float64), 2.0, 1)


def test_different_dimensions_are_not_resized_for_comparison() -> None:
    with pytest.raises(ValueError, match="equal dimensions"):
        Distance.measure(np.zeros((2, 4, 4), np.uint8), np.zeros((4, 2, 4), np.uint8))


class Fixture:
    def __init__(
        self, root: Path, monkeypatch: pytest.MonkeyPatch, identical: bool = False
    ) -> None:
        self.root = root
        local = root / "experiment report/.local"
        public = root / "experiment report"
        exact_config = local / "exact-config.json"
        first = (10, 20, 30, 255)
        second = first if identical else (11, 21, 31, 255)
        A.write_json(
            exact_config,
            {
                "batches": [
                    capture(local / "capture", "train", first),
                    capture(local / "capture", "validation", second),
                ],
                "expected_counts": {"train": 1, "validation": 1},
                "output": str(local / "exact-details"),
                "report": str(public / "exact.json"),
            },
        )
        self.exact = Exact(exact_config).run()
        self.source = public / "exact.json"
        self.path = public / "config.json"
        self.output = local / "near-details"
        self.report = public / "near.json"
        monkeypatch.setattr(Audit, "execution_sources", staticmethod(self.sources))
        A.write_json(
            self.path,
            {
                "pixel_identity_report": {
                    "path": str(self.source),
                    "sha256": A.sha256_file(self.source),
                },
                "expected_counts": {"train": 1, "validation": 1},
                "sources_sha256": self.sources(root),
                "runtime": Audit.runtime(),
                "rgba_rmse_8bit": 2.0,
                "cell_grid": 8,
                "max_candidate_pairs": 100,
                "output": str(self.output),
                "report": str(self.report),
            },
        )

    @staticmethod
    def sources(_root: Path) -> dict[str, str]:
        return {"fixture": "source-binding"}

    def run(self) -> JsonDict:
        return Audit(self.root, self.path).run()


def test_real_file_workflow_reports_near_pairs_without_model_or_filtering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    result = fixture.run()
    assert result["status"] == "passed" and result["counts"] == {"train": 1, "validation": 1}
    assert result["near_identity_pairs"] == result["cross_split_near_identity_pairs"] == 1
    assert result["near_image_pairs"] == 1
    details = A.read_json(Path(result["details"]))
    assert details["near_pairs"][0]["rgba_rmse_8bit"] == math.sqrt(0.75)
    assert result["training_updates"] == result["model_forward_calls"] == 0
    assert result["test_opened"] is result["splits_modified"] is False
    assert result["independent_test_isolation_proven"] is False
    assert not any(
        "selected_block_size" in row or "selected_preset" in row for row in details["rows"]
    )


def test_exact_identity_groups_are_not_counted_again_as_near_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = Fixture(tmp_path, monkeypatch, identical=True).run()
    assert result["exact_duplicate_groups"] == result["exact_cross_split_groups"] == 1
    assert result["unique_rgba_identities"] == 1 and result["near_identity_pairs"] == 0


@pytest.mark.parametrize("mode", ["config", "source_report", "native_png", "membership"])
def test_changed_evidence_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    audit = Audit(tmp_path, fixture.path)
    if mode == "config":
        A.write_json(fixture.path, {})
    elif mode == "source_report":
        A.write_json(fixture.source, {})
    elif mode == "native_png":
        details = A.read_json(Path(fixture.exact["details"]))
        Path(details["rows"][0]["reference"]).write_bytes(b"changed")
    else:
        config = A.read_json(fixture.path)
        config["expected_counts"] = {"train": 2}
        A.write_json(fixture.path, config)
        audit = Audit(tmp_path, fixture.path)
    with pytest.raises(ValueError):
        audit.run()


def test_native_png_mutation_after_descriptor_stops_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    audit = Audit(tmp_path, fixture.path)
    original = audit.load

    def mutate_after_load(row: JsonDict) -> NDArray[np.uint8]:
        result = original(row)
        Path(row["reference"]).write_bytes(b"changed after loading")
        return result

    monkeypatch.setattr(audit, "load", mutate_after_load)
    with pytest.raises(ValueError, match="PNG"):
        audit.run()
    assert A.read_json(fixture.report)["status"] == "failed"


@pytest.mark.parametrize(
    "field,value",
    [("rgba_rmse_8bit", 0), ("rgba_rmse_8bit", -1), ("cell_grid", 0), ("max_candidate_pairs", 0)],
)
def test_invalid_settings_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: int
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    config = A.read_json(fixture.path)
    config[field] = value
    A.write_json(fixture.path, config)
    with pytest.raises(ValueError):
        Audit(tmp_path, fixture.path)


def test_existing_output_is_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    fixture.run()
    digest = A.sha256_file(fixture.report)
    with pytest.raises(FileExistsError):
        fixture.run()
    assert A.sha256_file(fixture.report) == digest
