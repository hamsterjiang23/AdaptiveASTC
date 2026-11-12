"""Reject unintended changes when joining approved replacement pixel identities."""

from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.confirmation_evidence import UnityConfirmationEvidence as E
from reproductions.unity_search_baseline.near_duplicates import UnityNearDuplicateAudit as N
from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit as I
from reproductions.unity_search_baseline.revised_pixel_identity import (
    UnityRevisedPixelIdentityAudit as R,
)


def fixture_rows() -> tuple[list[JsonDict], list[JsonDict], JsonDict, JsonDict]:
    def row(name: str, split: str) -> JsonDict:
        return {
            "path": f"Assets/{name}.png",
            "source_split": split,
            "reference": f"C:/test/{name}.png",
            "reference_sha256": f"png-{name}",
            "callback_rgba_sha256": f"pixels-{name}",
        }

    old = [row("cube", "train"), row("retained", "validation"), row("confirm", "confirmation")]
    added = [row("replacement", "train")]
    reservation = {
        "replacements": [
            {"split": "train", "old_path": old[0]["path"], "new_path": added[0]["path"], "index": 0}
        ]
    }
    corpus = {
        "splits": {
            split: [
                {**sample, "actual_options": {"rgba_sha256": sample["callback_rgba_sha256"]}}
                for sample in [*added, old[1]]
                if sample["source_split"] == split
            ]
            for split in ["train", "validation"]
        }
    }
    return old, added, reservation, corpus


def test_only_approved_replacement_and_confirmation_order_preserved() -> None:
    old, added, reservation, corpus = fixture_rows()
    before = deepcopy(old)
    result = R.select(old, added, reservation, corpus)
    assert result == [added[0], old[1], old[2]]
    assert old == before


@pytest.mark.parametrize("damage", ["reference", "reference_sha256", "callback"])
def test_corpus_must_use_same_native_pixels(damage: str) -> None:
    old, added, reservation, corpus = fixture_rows()
    row = corpus["splits"]["validation"][0]
    if damage == "callback":
        row["actual_options"]["rgba_sha256"] = "wrong"
    else:
        row[damage] = "wrong"
    with pytest.raises(ValueError, match="pixel origin"):
        R.select(old, added, reservation, corpus)


def test_extra_replacement_is_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    added.append({**added[0], "path": "Assets/extra.png"})
    with pytest.raises(ValueError, match="approved new identities"):
        R.select(old, added, reservation, corpus)


def test_unapproved_retained_deletion_is_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    corpus["splits"]["validation"] = []
    with pytest.raises(ValueError, match="Unapproved development"):
        R.select(old, added, reservation, corpus)


def test_confirmation_replacement_is_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    reservation["replacements"][0].update(old_path=old[2]["path"], split="confirmation")
    added[0]["source_split"] = "confirmation"
    with pytest.raises(ValueError, match="Only development"):
        R.select(old, added, reservation, corpus)


def test_split_transfer_is_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    added[0]["source_split"] = "validation"
    with pytest.raises(ValueError, match="changes a split"):
        R.select(old, added, reservation, corpus)


def test_duplicate_original_paths_are_rejected() -> None:
    old, added, reservation, corpus = fixture_rows()
    old.append(deepcopy(old[0]))
    with pytest.raises(ValueError, match="Duplicate asset identity"):
        R.select(old, added, reservation, corpus)


@pytest.mark.parametrize(
    ("damage", "admission_damage"),
    [
        (True, "none"),
        (False, "none"),
        (False, "original"),
        (False, "corpus"),
        (False, "confirmation"),
        (False, "threshold"),
        (False, "test"),
        (False, "forward"),
    ],
)
def test_actual_png_read_and_report_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: bool, admission_damage: str
) -> None:
    # Tiny synthetic provenance exercises the full pixel I/O path, not real collection coverage.
    monkeypatch.setattr(R, "execution_sources", staticmethod(lambda root: {}))
    public = tmp_path / "experiment report"
    local = public / ".local"
    local.mkdir(parents=True)

    def bind(path: Path, value: JsonDict) -> JsonDict:
        A.write_json(path, value)
        return {"path": str(path), "sha256": A.sha256_file(path)}

    old, added, reservation, corpus = fixture_rows()
    for index, row in enumerate([*old, *added]):
        path = local / f"{index}.png"
        Image.new("RGBA", (4, 3), (index * 10, 30, 50, 255)).save(path)
        row.update(
            reference=str(path),
            reference_sha256=A.sha256_file(path),
            observed_options={"profile": 0},
            selected_block_size="8x8",
            selected_preset="fast",
            **I.pixel_identity(path.read_bytes(), 4, 3),
        )
    corpus["splits"] = {
        "train": [
            {**added[0], "actual_options": {"rgba_sha256": added[0]["callback_rgba_sha256"]}}
        ],
        "validation": [
            {**old[1], "actual_options": {"rgba_sha256": old[1]["callback_rgba_sha256"]}}
        ],
    }
    reservation.update(
        status="reserved",
        counts={"train": 1, "validation": 1},
        replacement_counts={"train": 1, "validation": 0},
    )
    approved = bind(local / "reservation.json", reservation)
    corpus["config"] = {"revision": {"reservation": approved}}
    corpus["binding"] = A.fingerprint(corpus["config"])
    corpus["fingerprint"] = A.fingerprint(
        {"binding": corpus["binding"], "splits": corpus["splits"]}
    )
    native = bind(local / "corpus.json", corpus)
    revision = bind(
        public / "revision.json",
        {"status": "passed", "corpus": native["path"], "corpus_sha256": native["sha256"]},
    )

    def audit(name: str, rows: list[JsonDict], counts: JsonDict) -> JsonDict:
        details = bind(local / f"{name}-details.json", {"rows": rows})
        return bind(
            public / f"{name}.json",
            {
                "status": "passed",
                "splits_modified": False,
                "inputs_sha256": {},
                "counts": counts,
                "details": details["path"],
                "details_sha256": details["sha256"],
                "rgba": I.group_duplicates(rows, "rgba_identity")[1],
                "rgb_only": I.group_duplicates(rows, "rgb_identity")[1],
            },
        )

    report_path = public / "revised.json"
    config = {
        "sources_sha256": {},
        "output": str(local / "revised"),
        "report": str(report_path),
        "corpus_revision_report": revision,
        "corpus": native,
        "reservation": approved,
        "original_pixels": audit("old", old, {"train": 1, "validation": 1, "confirmation": 1}),
        "replacement_pixels": audit("added", added, {"train": 1}),
        "expected_counts": {"train": 1, "validation": 1, "confirmation": 1},
    }
    config_path = public / "config.json"
    A.write_json(config_path, config)
    runner = R(tmp_path, config_path)
    if damage:
        Path(old[1]["reference"]).write_bytes(b"changed pixels")
        with pytest.raises(ValueError, match="PNG changed"):
            runner.run()
        assert A.read_json(report_path)["status"] == "failed"
    else:
        result = runner.run()
        assert result["status"] == "passed"
        assert result["counts"] == config["expected_counts"]
        assert len(A.read_json(Path(result["native_png_bindings"]))) == 3
        before = report_path.read_bytes()
        with pytest.raises(FileExistsError):
            R(tmp_path, config_path).run()
        assert report_path.read_bytes() == before
        monkeypatch.setattr(E, "EXPECTED", config["expected_counts"])
        monkeypatch.setattr(N, "execution_sources", staticmethod(lambda root: {}))

        def completed_job(self: E, item: JsonDict, script: str, path: Path) -> None:
            assert script.startswith("script/audit_unity_") and path.is_file()

        monkeypatch.setattr(E, "job", completed_job)
        exact = {
            "config": bind(config_path, config),
            "report": bind(report_path, result),
            "job": {},
        }
        details = A.read_json(Path(result["details"]))
        if admission_damage == "confirmation":
            details["rows"][-1]["path"] = "Assets/unapproved-confirmation.png"
            result["details_sha256"] = bind(Path(result["details"]), details)["sha256"]
            exact["report"] = bind(report_path, result)
        near_path, near_report = public / "near-config.json", public / "near.json"
        threshold = 1.0 if admission_damage == "threshold" else 2.0
        near_config = {
            "sources_sha256": {},
            "report": str(near_report),
            "pixel_identity_report": exact["report"],
            "expected_counts": config["expected_counts"],
            "rgba_rmse_8bit": threshold,
        }
        near_config_binding = bind(near_path, near_config)
        near_details = bind(local / "near-details.json", {"rows": [], "near_pairs": []})
        near = {
            "config": near_config_binding,
            "job": {},
            "report": bind(
                near_report,
                {
                    "status": "passed",
                    "counts": config["expected_counts"],
                    "config_sha256": near_config_binding["sha256"],
                    "sources_sha256": {},
                    "rgba_rmse_8bit": threshold,
                    "test_opened": admission_damage == "test",
                    "splits_modified": False,
                    "model_forward_calls": int(admission_damage == "forward"),
                    "training_updates": 0,
                    "inputs_sha256": {},
                    "details": near_details["path"],
                    "details_sha256": near_details["sha256"],
                },
            ),
        }
        evidence = E(tmp_path)
        evidence.corpus = corpus if admission_damage != "corpus" else {"wrong": True}
        original = dict(config["original_pixels"])
        if admission_damage == "original":
            original["sha256"] = "wrong-original-audit"
        if admission_damage == "none":
            selected = evidence.revised_pixels({"exact": exact, "near": near}, original)
            assert selected["exact"] == details
            evidence.verify()
        else:
            with pytest.raises(ValueError):
                evidence.revised_pixels({"exact": exact, "near": near}, original)
