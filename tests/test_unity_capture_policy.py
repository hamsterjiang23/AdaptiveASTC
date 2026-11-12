"""Capture policy provenance is independent of candidate supplementation and model evaluation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from test_unity_search_policy import policy

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.capture_policy import UnityCapturePolicyBinding as Binding


class Fixture:
    def __init__(
        self, root: Path, monkeypatch: pytest.MonkeyPatch, split: str = "confirmation"
    ) -> None:
        baseline = object.__new__(UnitySearchBaseline)
        baseline.run_dir = root / "run"
        baseline.project = root / "project"
        baseline.editor = root / "Editor.exe"
        baseline.editor.write_bytes(b"fixture Editor")
        baseline.manifest = root / "manifest.json"
        baseline.source_split = split
        self.baseline = baseline
        self.phase = baseline.run_dir / "batch-receipt.json"
        self.reference = baseline.run_dir / "references/normalized-batch/receipt.json"
        self.cache = baseline.project / "ASTC_Cache/test/parameter_cache_detail.jsonl"
        self.table = policy().table
        self.native = [
            {
                "asset": f"Assets/group/image{i}.png",
                "block_size": "12x12",
                "preset": "fast",
                "search_executed": True,
                "cache_hit": False,
            }
            for i in range(2)
        ]
        self.records = [
            {
                "filePath": row["asset"],
                "fileHash": f"hash{i}",
                "blockSize": "12x12",
                "qualityLevel": "fast",
                "rdo": False,
            }
            for i, row in enumerate(self.native)
        ]
        self.provenance = {
            "editor_sha256": A.sha256_file(baseline.editor),
            "native_policy_verified": True,
        }
        library = baseline.project / "Assets/Editor/Astc/Plugins/fixture.dll"
        library.parent.mkdir(parents=True)
        library.write_bytes(b"fixture DLL")
        A.write_json(
            baseline.run_dir / "identity.json",
            {"encoder_dlls": {library.name: A.sha256_file(library)}},
        )
        A.write_json(baseline.run_dir / "protocol-lock.json", {})
        A.write_json(baseline.run_dir / "batch-launch.json", {})
        A.write_json(baseline.manifest, {"splits": {split: []}})
        A.write_json(
            baseline.run_dir / "batch-config.json",
            {
                "assets": [{"path": r["asset"]} for r in self.native],
                "cacheDirectory": "ASTC_Cache/test",
            },
        )
        A.write_json(
            self.phase,
            {
                "status": "passed",
                "process_exit_code": 0,
                "metadata_restore_conflicts": [],
                "provenance": self.provenance,
            },
        )
        A.write_json(
            self.reference,
            {
                "status": "passed",
                "images": 2,
                "capture_provenance": self.provenance,
                "rows": [
                    {
                        "path": row["asset"],
                        "source_split": split,
                        "source_md4": f"hash{i}",
                        "selection": row,
                    }
                    for i, row in enumerate(self.native)
                ],
            },
        )
        self.write_lines(baseline.run_dir / "batch-native.jsonl", self.native)
        self.write_cache()
        monkeypatch.setattr(baseline, "audit", lambda _phase: copy.deepcopy(self.provenance))

    @staticmethod
    def write_lines(path: Path, rows: list[JsonDict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def write_cache(self) -> None:
        self.write_lines(
            self.cache,
            [{"_kind": "astc_cache_table_config", "tableConfig": self.table}, *self.records],
        )

    def bind(self) -> Binding:
        return Binding(
            self.baseline,
            "batch",
            reference_sha256=A.sha256_file(self.reference),
            phase_sha256=A.sha256_file(self.phase),
        )


@pytest.mark.parametrize("split", ["train", "validation", "confirmation"])
def test_policy_is_bound_without_candidate_or_supervision_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    split: str,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch, split)
    result = fixture.bind()
    assert result.binding["source_split"] == split and result.binding["images"] == 2
    assert result.policy.table["targetPsnrDb"] == 30
    assert result.policy.table["targetMsSsimDb"] == 21
    assert result.inputs[str(fixture.cache.with_suffix(".json"))] is None
    result.verify()


@pytest.mark.parametrize(
    "key,value",
    [
        ("status", "running"),
        ("process_exit_code", 1),
        ("metadata_restore_conflicts", ["asset"]),
        ("provenance", {}),
    ],
)
def test_incomplete_or_foreign_phase_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: object,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    phase = A.read_json(fixture.phase)
    phase[key] = value
    A.write_json(fixture.phase, phase)
    with pytest.raises(ValueError):
        fixture.bind()


@pytest.mark.parametrize(
    "field,value",
    [
        ("fileHash", "wrong"),
        ("blockSize", "6x6"),
        ("qualityLevel", "exhaustive"),
        ("rdo", True),
    ],
)
def test_original_choice_and_source_hash_must_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    fixture.records[0][field] = value
    fixture.write_cache()
    with pytest.raises(ValueError, match="hash or search selection"):
        fixture.bind()


@pytest.mark.parametrize("change", ["split", "order", "selection", "count", "duplicate"])
def test_capture_membership_cannot_be_relabelled_or_reordered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    data = A.read_json(fixture.reference)
    if change == "split":
        data["rows"][0]["source_split"] = "train"
    elif change == "order":
        data["rows"].reverse()
    elif change == "selection":
        data["rows"][0]["selection"]["cache_hit"] = True
    elif change == "count":
        data["images"] = 1
    else:
        data["rows"][1] = data["rows"][0]
    A.write_json(fixture.reference, data)
    with pytest.raises(ValueError):
        fixture.bind()


def test_wrong_supplied_receipt_hash_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="input changed"):
        Binding(
            fixture.baseline,
            "batch",
            reference_sha256="wrong",
            phase_sha256=A.sha256_file(fixture.phase),
        )


@pytest.mark.parametrize("split", ["train", "validation", "confirmation"])
def test_legacy_missing_split_is_only_compatible_with_train(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, split: str
) -> None:
    fixture = Fixture(tmp_path, monkeypatch, split)
    reference = A.read_json(fixture.reference)
    for row in reference["rows"]:
        del row["source_split"]
    A.write_json(fixture.reference, reference)
    if split == "train":
        assert fixture.bind().binding["legacy_train_rows_without_split"] == 2
    else:
        with pytest.raises(ValueError, match="source split"):
            fixture.bind()


@pytest.mark.parametrize("mode", ["journal", "new_snapshot", "new_assembly", "editor", "policy"])
def test_mutation_after_binding_stops_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    bound = fixture.bind()
    if mode == "journal":
        fixture.cache.write_text("changed", encoding="utf-8")
    elif mode == "new_snapshot":
        A.write_json(fixture.cache.with_suffix(".json"), {})
    elif mode == "new_assembly":
        A.write_json(fixture.baseline.run_dir / "batch-assembly.json", {})
    elif mode == "editor":
        fixture.baseline.editor.write_bytes(b"changed")
    else:
        bound.policy.table["targetPsnrDb"] = 35
    with pytest.raises(ValueError):
        bound.verify()


def test_snapshot_and_journal_are_both_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    snapshot = fixture.cache.with_suffix(".json")
    A.write_json(
        snapshot,
        {
            "tableConfig": fixture.table,
            "entries": {row["filePath"]: row for row in fixture.records},
        },
    )
    bound = fixture.bind()
    assert bound.inputs[str(snapshot)] == A.sha256_file(snapshot)
    A.write_json(snapshot, {"changed": True})
    with pytest.raises(ValueError):
        bound.verify()


@pytest.mark.parametrize("changed", ["input", "output"])
def test_recovery_evidence_changes_after_binding_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    run = fixture.baseline.run_dir
    cache = run / "batch-parameters.jsonl"
    cache.write_bytes(fixture.cache.read_bytes())
    original = tmp_path / "prior-receipt.json"
    merged = run / "merged.json"
    A.write_json(original, {"status": "passed"})
    A.write_json(merged, {"status": "passed"})
    A.write_json(
        run / "batch-assembly.json",
        {
            "inputs": [{"path": str(original), "sha256": A.sha256_file(original)}],
            "outputs": {
                merged.name: A.sha256_file(merged),
                cache.name: A.sha256_file(cache),
            },
        },
    )
    bound = fixture.bind()
    assert bound.binding["cache_path"] == str(cache)
    A.write_json(original if changed == "input" else merged, {"status": "changed"})
    with pytest.raises(ValueError, match="input changed"):
        bound.verify()


def test_existing_probe_phase_can_bind_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch, "train")
    run = fixture.baseline.run_dir
    for suffix in ["config.json", "receipt.json", "launch.json", "native.jsonl"]:
        (run / f"batch-{suffix}").rename(run / f"probe-{suffix}")
    (run / "references/normalized-batch").rename(run / "references/normalized-probe")
    result = Binding(
        fixture.baseline,
        "probe",
        reference_sha256=A.sha256_file(run / "references/normalized-probe/receipt.json"),
        phase_sha256=A.sha256_file(run / "probe-receipt.json"),
    )
    assert result.binding["phase"] == "probe" and result.binding["images"] == 2
