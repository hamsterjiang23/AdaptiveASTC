"""Reject incomplete or corrupted training targets, independently of native encoding."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.candidate_archive import UnityCandidateArchive
from reproductions.unity_search_baseline.supplement import UnityASTCBackend


class CandidateFixture:
    def __init__(self, root: Path) -> None:
        self.output = root / "candidate"
        self.folder = self.output / "00000"
        self.folder.mkdir(parents=True)
        capture = root / "capture/00000"
        capture.mkdir(parents=True)
        pixels = np.arange(16, dtype=np.uint8).reshape(2, 2, 4)
        Image.fromarray(pixels[::-1]).save(capture / "unity-native.png")
        self.candidates: list[JsonDict] = []
        for block in UnityASTCBackend.BLOCKS:
            for preset in UnityASTCBackend.PRESETS:
                name = f"{block}x{block}_{preset}"
                astc, png = self.folder / f"{name}.astc", self.folder / f"{name}.png"
                astc.write_bytes(UnityASTCBackend.container(bytes(16), 2, 2, block))
                Image.fromarray(pixels).save(png)
                self.candidates.append(
                    {
                        "block": block,
                        "preset": preset,
                        "payload_bytes": 16,
                        "astc_sha256": ArtifactStore.sha256_file(astc),
                        "decoded_png_sha256": ArtifactStore.sha256_file(png),
                        "measured_in_original_search": block == 12 and preset == "fastest",
                        "metrics": {
                            "psnr": 35.0,
                            "black_pixel_ratio": 0.0,
                            "need_alpha": False,
                            "mip_count": 1,
                        },
                    }
                )
        (capture / "unity.astc").write_bytes((self.folder / "12x12_fastest.astc").read_bytes())
        selection = {"block_size": "12x12", "preset": "fastest"}
        self.references = [
            {
                "path": "Assets/train.png",
                "width": 2,
                "height": 2,
                "selection": selection,
                "actual_options": {"profile": 1},
                "capture_directory": str(capture.parent),
                "capture_index": 0,
            }
        ]
        item = {"path": "Assets/train.png", "index": 0, "is_normal": False, "need_alpha": False}
        self.config_path, self.report = root / "config.json", root / "report.json"
        self.config = {"output": str(self.output), "items": [item]}
        ArtifactStore.write_json(self.config_path, self.config)
        self.row = {
            "index": 0,
            "path": "Assets/train.png",
            "metadata": item,
            "original_selection": selection,
            "selected_payload_and_decode_match": True,
            "candidate_count": 20,
            "original_search_candidates": 1,
            "native_metric_comparisons": 1,
            "new_candidates": 19,
            "cost": {key: 0.0 for key in ["encode_seconds", "decode_seconds", "quality_seconds"]},
        }
        self.publish()

    def publish(self) -> None:
        path = self.folder / "candidates.json"
        ArtifactStore.write_json(path, self.candidates)
        self.row.update(
            candidates=self.candidates, candidate_receipt_sha256=ArtifactStore.sha256_file(path)
        )
        raw = {
            "status": "passed",
            "test_opened": False,
            "config": self.config,
            "config_sha256": ArtifactStore.sha256_file(self.config_path),
            "rows": [self.row],
            "wall_seconds": 0.0,
        }
        path = self.output / "receipt.json"
        ArtifactStore.write_json(path, raw)
        ArtifactStore.write_json(
            self.report,
            {
                **raw,
                "rows": [{key: value for key, value in self.row.items() if key != "candidates"}],
                "raw_receipt": str(path),
                "raw_receipt_sha256": ArtifactStore.sha256_file(path),
            },
        )

    def verify(self) -> tuple[list[JsonDict], JsonDict]:
        return UnityCandidateArchive.verify(self.report, self.references, self.config_path)


def test_full_grid_keeps_original_choice_and_accounts_for_new_targets(tmp_path: Path) -> None:
    fixture = CandidateFixture(tmp_path)
    rows, summary = fixture.verify()
    assert summary["candidates"] == 20 and summary["new_candidates"] == 19
    assert rows[0]["selection"] == fixture.references[0]["selection"]


@pytest.mark.parametrize("damage", ["missing", "duplicate", "reordered"])
def test_candidate_grid_is_complete_unique_and_ordered(tmp_path: Path, damage: str) -> None:
    fixture = CandidateFixture(tmp_path)
    if damage == "missing":
        fixture.candidates.pop()
    elif damage == "duplicate":
        fixture.candidates[1] = fixture.candidates[0]
    else:
        fixture.candidates.reverse()
    fixture.publish()
    with pytest.raises(ValueError, match="missing, duplicated or reordered"):
        fixture.verify()


def test_changed_decode_fails_content_identity(tmp_path: Path) -> None:
    fixture = CandidateFixture(tmp_path)
    (fixture.folder / "10x10_fastest.png").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="decoded PNG changed"):
        fixture.verify()


def test_rehashed_wrong_orientation_still_fails_original_winner_check(tmp_path: Path) -> None:
    fixture = CandidateFixture(tmp_path)
    path = fixture.folder / "12x12_fastest.png"
    with Image.open(path) as source:
        pixels = np.asarray(source)[::-1].copy()
    Image.fromarray(pixels).save(path)
    fixture.candidates[0]["decoded_png_sha256"] = ArtifactStore.sha256_file(path)
    fixture.publish()
    with pytest.raises(ValueError, match="orientation or pixels"):
        fixture.verify()


def test_original_label_cannot_be_replaced_by_supplemental_selection(tmp_path: Path) -> None:
    fixture = CandidateFixture(tmp_path)
    fixture.row["original_selection"] = {"block_size": "6x6", "preset": "exhaustive"}
    fixture.publish()
    with pytest.raises(ValueError, match="original reference or choice"):
        fixture.verify()


def test_changed_coverage_accounting_is_rejected(tmp_path: Path) -> None:
    fixture = CandidateFixture(tmp_path)
    fixture.row["new_candidates"] = 0
    fixture.publish()
    with pytest.raises(ValueError, match="coverage accounting"):
        fixture.verify()
