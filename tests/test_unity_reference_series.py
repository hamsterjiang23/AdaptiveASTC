"""Exercise corpus boundaries and resumable serial scheduling without Unity or GPU."""

from pathlib import Path

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.unity_reference import UnityReferenceCapture
from reproductions.unity_search_baseline.collection import UnityReferenceSeries
from reproductions.unity_search_baseline.metadata import UnityOptionCapture


def make_series(tmp_path: Path) -> UnityReferenceSeries:
    manifest = tmp_path / "source.json"
    ArtifactStore.write_json(
        manifest,
        {
            "splits": {
                "train": [{"path": "Assets/train.png"}],
                "validation": [{"path": "Assets/validation.png"}],
                "test": [{"path": "Assets/test.png"}],
            }
        },
    )
    project = tmp_path / "project"
    project.mkdir()
    editor = tmp_path / "unused-editor"
    editor.write_bytes(b"synthetic executable identity")
    libraries = project / "Assets/Editor/Astc/Plugins"
    libraries.mkdir(parents=True)
    dlls = {}
    for name in ["astcenc-avx2-shared.dll", "astcenc-avx2-static.dll"]:
        path = libraries / name
        path.write_bytes(b"synthetic DLL identity")
        dlls[name] = ArtifactStore.sha256_file(path)
    entries = []
    for split in ["train", "validation"]:
        path = tmp_path / f"{split}-config.json"
        ArtifactStore.write_json(
            path,
            {
                "project": str(project),
                "editor": str(tmp_path / "unused-editor"),
                "manifest": str(manifest),
                "run_id": f"synthetic-{split}",
                "phase": "batch",
                "source_split": split,
                "capture_paths": [f"Assets/{split}.png"],
                "report": str(tmp_path / f"{split}-options.json"),
            },
        )
        entries.append({"config": str(path), "sha256": ArtifactStore.sha256_file(path)})
    config = tmp_path / "series.json"
    ArtifactStore.write_json(
        config,
        {
            "project": str(project),
            "editor": str(tmp_path / "unused-editor"),
            "editor_sha256": ArtifactStore.sha256_file(editor),
            "encoder_dlls": dlls,
            "manifest": str(manifest),
            "manifest_sha256": ArtifactStore.sha256_file(manifest),
            "expected_counts": {"train": 1, "validation": 1},
            "batches": entries,
            "output": str(tmp_path / "experiment report/.local/corpus"),
            "report": str(tmp_path / "summary.json"),
        },
    )
    return UnityReferenceSeries(tmp_path, config)


def test_complete_plan_identity_and_disjoint_coverage(tmp_path: Path) -> None:
    series = make_series(tmp_path)
    _, batches = series.validate()
    assert [batch["split"] for batch in batches] == ["train", "validation"]
    series.config["batches"].pop()
    with pytest.raises(ValueError, match="complete development splits"):
        series.validate()
    series.config["batches"].append(series.config["batches"][0])
    with pytest.raises(ValueError, match="output identity"):
        series.validate()


def test_changed_batch_config_is_rejected_before_execution(tmp_path: Path) -> None:
    series = make_series(tmp_path)
    path = Path(series.config["batches"][0]["config"])
    config = ArtifactStore.read_json(path)
    config["capture_paths"] = ["Assets/test.png"]
    ArtifactStore.write_json(path, config)
    with pytest.raises(ValueError, match="configuration changed"):
        series.validate()
    series.config["batches"][0]["sha256"] = ArtifactStore.sha256_file(path)
    with pytest.raises(ValueError, match="membership"):
        series.validate()


def test_selected_probe_cannot_claim_complete_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = make_series(tmp_path)
    series.config["batches"].pop()
    series.config["expected_counts"]["validation"] = 0
    with pytest.raises(ValueError, match="expected counts"):
        series.validate()
    series.config["coverage"] = "selected"
    assert len(series.validate()[1]) == 1
    batch = series.validate()[1][0]
    ArtifactStore.write_json(
        series.baseline(batch["config"]).run_dir / "options-receipt.json", {"fixture": True}
    )

    def verify(batch: JsonDict) -> tuple[list[JsonDict], JsonDict]:
        return [{"path": batch["paths"][0], "source_split": "train"}], {"synthetic": True}

    monkeypatch.setattr(series, "verify_batch", verify)
    result = series.run()
    manifest = ArtifactStore.read_json(Path(result["manifest"]))
    assert manifest["coverage"] == "selected"
    assert len(manifest["splits"]["train"]) == 1
    assert manifest["splits"]["validation"] == []


def test_cross_split_asset_paths_are_rejected(tmp_path: Path) -> None:
    series = make_series(tmp_path)
    manifest = Path(series.config["manifest"])
    source = ArtifactStore.read_json(manifest)
    source["splits"]["test"].append(source["splits"]["train"][0])
    ArtifactStore.write_json(manifest, source)
    series.config["manifest_sha256"] = ArtifactStore.sha256_file(manifest)
    with pytest.raises(ValueError, match="held-out"):
        series.validate()


def test_series_environment_cannot_drift_between_batches(tmp_path: Path) -> None:
    series = make_series(tmp_path)
    Path(series.config["editor"]).write_bytes(b"replacement executable")
    with pytest.raises(ValueError, match="Editor binary changed"):
        series.validate()


@pytest.mark.parametrize("key", ["minimum_free_ram_gib", "minimum_free_disk_gib"])
@pytest.mark.parametrize("value", ["NaN", -1, 0, float("inf")])
def test_resource_gates_reject_invalid_budgets(tmp_path: Path, key: str, value: object) -> None:
    series = make_series(tmp_path)
    series.config[key] = value
    with pytest.raises(ValueError, match="finite positive"):
        series.validate()


def test_reference_receipt_must_match_the_original_options_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = make_series(tmp_path)
    batch = series.validate()[1][0]
    baseline = series.baseline(batch["config"])
    ArtifactStore.write_json(
        baseline.run_dir / "identity.json", {"encoder_dlls": series.config["encoder_dlls"]}
    )
    options = {
        "status": "passed",
        "managed_source_restoration": {
            "status": "restored",
            "original_sha256": "original",
            "restored_sha256": "original",
        },
        "rows": [],
        "images": 1,
        "candidate_callbacks": 1,
        "options_sha256": "synthetic-log",
        "native_provenance": {"editor_sha256": series.config["editor_sha256"]},
        "capture_receipt_sha256": "original-reference-receipt",
    }
    ArtifactStore.write_json(baseline.run_dir / "options-receipt.json", options)
    ArtifactStore.write_json(Path(batch["config"]["report"]), options)

    def collect(self: UnityReferenceCapture, phase: str) -> JsonDict:
        return {"synthetic": phase}

    def audit(baseline: object, phase: str, captured: JsonDict) -> JsonDict:
        return {**options, "capture_receipt_sha256": "replaced-reference-receipt"}

    monkeypatch.setattr(UnityReferenceCapture, "collect", collect)
    monkeypatch.setattr(UnityOptionCapture, "audit", staticmethod(audit))
    with pytest.raises(ValueError, match="capture_receipt_sha256"):
        series.verify_batch(batch)


def test_project_lock_excludes_other_series_and_releases(tmp_path: Path) -> None:
    series = make_series(tmp_path)
    other_root = tmp_path / "other-checkout"
    other_config = other_root / "config.json"
    ArtifactStore.write_json(
        other_config,
        {**series.config, "output": str(other_root / "experiment report/.local/corpus")},
    )
    peer = UnityReferenceSeries(other_root, other_config)
    with series.project_lock():
        with pytest.raises(RuntimeError, match="owns this Unity project"):
            with peer.project_lock():
                pytest.fail("Concurrent project owner entered")
    with peer.project_lock():
        pass


def test_assembly_rechecks_completed_batches_and_preserves_failed_invocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = make_series(tmp_path)
    for batch in series.validate()[1]:
        folder = series.baseline(batch["config"]).run_dir
        ArtifactStore.write_json(folder / "options-receipt.json", {"fixture": True})
    checked: list[str] = []

    def verify(batch: JsonDict) -> tuple[list[JsonDict], JsonDict]:
        checked.append(batch["split"])
        return [{"path": batch["paths"][0], "source_split": batch["split"]}], {
            "synthetic": batch["split"]
        }

    monkeypatch.setattr(series, "verify_batch", verify)
    result = series.run()
    assert result["status"] == "passed" and result["counts"] == {"train": 1, "validation": 1}
    manifest = ArtifactStore.read_json(Path(result["manifest"]))
    assert manifest["coverage"] == "complete"
    assert list(manifest["splits"]) == ["train", "validation"]
    series.run()
    assert checked == ["train", "validation", "train", "validation"]

    def reject(batch: JsonDict) -> tuple[list[JsonDict], JsonDict]:
        raise ValueError(f"Synthetic damaged archive: {batch['split']}")

    monkeypatch.setattr(series, "verify_batch", reject)
    with pytest.raises(ValueError, match="damaged archive"):
        series.run()
    attempts = [
        ArtifactStore.read_json(path) for path in series.output.glob("invocations/*/*.json")
    ]
    assert sorted(row["status"] for row in attempts) == ["failed", "passed", "passed"]
    assert ArtifactStore.read_json(series.report)["status"] == "failed"
