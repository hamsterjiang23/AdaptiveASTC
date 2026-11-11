"""Exercise real native Dataset validation during corpus assembly."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.patch_assembly import UnityPatchCorpusAssembly
from tests.test_unity_patch_dataset import DatasetFixture, two_split_fixture


class AssemblyFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.datasets = [
            two_split_fixture(root / "first", "Assets/A.png", "Assets/V.png"),
            DatasetFixture(root / "second"),
        ]
        second = self.datasets[1].document["splits"]["train"][0]
        second["path"] = second["original_selection"]["asset"] = "Assets/B.png"
        self.source: JsonDict = {
            "splits": {
                "train": [{"path": f"Assets/{name}.png"} for name in ["B", "A", "unused"]],
                "validation": [{"path": "Assets/V.png"}],
                "test": [{"path": "Assets/H.png"}],
            }
        }
        self.prepared: JsonDict = {
            "status": "passed",
            "test_opened": False,
            "training_updates": 0,
            "coverage": "partial",
            "counts": {"train": 2, "validation": 1},
            "patch_counts": {"train": 4, "validation": 2},
        }
        self.path = root / "assembly.json"
        self.report = root / "report.json"
        self.output = root / "experiment report/.local/assembled"
        self.publish()

    def publish(self) -> None:
        source, plan, queue, prepared = [
            self.root / f"{name}.json" for name in ["source", "plan", "queue", "prepared"]
        ]
        ArtifactStore.write_json(source, self.source)
        ArtifactStore.write_json(
            plan, {"manifest": str(source), "manifest_sha256": ArtifactStore.sha256_file(source)}
        )
        ArtifactStore.write_json(
            queue,
            {"reference_plan": str(plan), "reference_plan_sha256": ArtifactStore.sha256_file(plan)},
        )
        self.prepared["config"] = {
            "candidate_queue_config": str(queue),
            "candidate_queue_config_sha256": ArtifactStore.sha256_file(queue),
            "patch_source_sha256": "a" * 64,
            "run_ids": ["first", "second"],
        }
        shards = []
        for name, fixture in zip(["first", "second"], self.datasets, strict=True):
            document = fixture.document
            document["config"]["source_sha256"] = "a" * 64
            document["binding"] = ArtifactStore.fingerprint(document["config"])
            for rows in document["splits"].values():
                for i, row in enumerate(rows):
                    row.update(binding=document["binding"], index=i, max_psnr_error_db=0.0)
            fixture.publish()
            shards.append(
                {
                    "run_id": name,
                    "corpus": str(fixture.path),
                    "corpus_sha256": ArtifactStore.sha256_file(fixture.path),
                    "counts": document["counts"],
                    "patch_counts": document["patch_counts"],
                }
            )
        self.prepared["shards"] = shards
        ArtifactStore.write_json(prepared, self.prepared)
        ArtifactStore.write_json(
            self.path,
            {
                "prepared_report": str(prepared),
                "prepared_report_sha256": ArtifactStore.sha256_file(prepared),
                "output": str(self.output),
                "report": str(self.report),
            },
        )

    def run(self) -> JsonDict:
        return UnityPatchCorpusAssembly(self.root, self.path).run()


def test_source_order_labels_and_target_bytes_preserved(tmp_path: Path) -> None:
    fixture = AssemblyFixture(tmp_path)
    original = {
        p: ArtifactStore.sha256_file(p)
        for f in fixture.datasets
        for p in [f.path, f.target, f.reference]
    }
    result = fixture.run()
    assert result["counts"] == {"train": 2, "validation": 1} and result["coverage"] == "partial"
    assert result["candidate_count"] == 60
    dataset = UnityPatchDataset(fixture.output, "train", expected_sha256=result["corpus_sha256"])
    assert [row["path"] for row in dataset.rows] == ["Assets/B.png", "Assets/A.png"]
    assert (
        dataset.rows[1]["original_selection"]
        == fixture.datasets[0].document["splits"]["train"][0]["original_selection"]
    )
    assert dataset.rows[1]["source_shard"]["index"] == 0
    for path, sha in original.items():
        assert ArtifactStore.sha256_file(path) == sha
    with pytest.raises(FileExistsError):
        fixture.run()


@pytest.mark.parametrize("damage", ["duplicate", "wrong_split", "unknown", "target"])
def test_invalid_shard_rejected_before_publication(tmp_path: Path, damage: str) -> None:
    fixture = AssemblyFixture(tmp_path)
    row = fixture.datasets[1].document["splits"]["train"][0]
    if damage == "target":
        fixture.datasets[1].target.write_bytes(b"corrupt")
    else:
        row["path"] = row["original_selection"]["asset"] = {
            "duplicate": "ASSETS/a.png",
            "wrong_split": "Assets/V.png",
            "unknown": "Assets/foreign.png",
        }[damage]
    fixture.publish()
    with pytest.raises(ValueError):
        fixture.run()
    assert not fixture.report.exists() and not (fixture.output / "corpus.json").exists()


@pytest.mark.parametrize("damage", ["incomplete", "counts", "false_full", "held_out"])
def test_preparation_and_source_contracts(tmp_path: Path, damage: str) -> None:
    fixture = AssemblyFixture(tmp_path)
    if damage == "incomplete":
        fixture.prepared["status"] = "running"
    elif damage == "counts":
        fixture.prepared["counts"]["train"] = 3
    elif damage == "false_full":
        fixture.prepared["coverage"] = "complete"
    else:
        fixture.source["splits"]["test"].append({"path": "ASSETS/a.png"})
    fixture.publish()
    with pytest.raises(ValueError):
        fixture.run()
    assert not fixture.report.exists()


def test_frozen_preparation_hash_checked(tmp_path: Path) -> None:
    fixture = AssemblyFixture(tmp_path)
    (tmp_path / "prepared.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen assembly input"):
        fixture.run()


def test_actual_full_source_coverage(tmp_path: Path) -> None:
    fixture = AssemblyFixture(tmp_path)
    fixture.source["splits"]["train"].pop()
    fixture.prepared["coverage"] = "complete"
    fixture.publish()
    result = fixture.run()
    assert result["coverage"] == "complete"
    assert result["counts"] == result["expected_full_counts"]


@pytest.mark.parametrize("relative", ["corpus.json", ".validation/corpus.json"])
def test_report_cannot_replace_corpus(tmp_path: Path, relative: str) -> None:
    fixture = AssemblyFixture(tmp_path)
    config = ArtifactStore.read_json(fixture.path)
    config["report"] = str(fixture.output / relative)
    ArtifactStore.write_json(fixture.path, config)
    with pytest.raises(ValueError, match="cannot alias"):
        fixture.run()
    assert not fixture.output.exists()


def test_concurrent_output_claim_preserves_first_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = AssemblyFixture(tmp_path)
    entered, release = Event(), Event()
    original = UnityPatchCorpusAssembly.frozen_json

    def blocked(path: Path, expected_sha256: str) -> JsonDict:
        if path.name == "prepared.json":
            entered.set()
            if not release.wait(10):
                raise TimeoutError("Assembly concurrency test did not release the first claimant")
        return original(path, expected_sha256)

    monkeypatch.setattr(UnityPatchCorpusAssembly, "frozen_json", staticmethod(blocked))
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(fixture.run)
        try:
            assert entered.wait(5)
            with pytest.raises(FileExistsError):
                fixture.run()
        finally:
            release.set()
        result = first.result(timeout=10)
    assert ArtifactStore.sha256_file(fixture.output / "corpus.json") == result["corpus_sha256"]


def test_concurrent_reports_cannot_replace_first_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = AssemblyFixture(tmp_path)
    second_config = ArtifactStore.read_json(fixture.path)
    second_config["output"] = str(tmp_path / "experiment report/.local/second-output")
    second_path = tmp_path / "second-config.json"
    ArtifactStore.write_json(second_path, second_config)
    ready = Barrier(2)
    original = UnityPatchCorpusAssembly.frozen_json

    def together(path: Path, expected_sha256: str) -> JsonDict:
        if path.name == "prepared.json":
            ready.wait(timeout=10)
        return original(path, expected_sha256)

    monkeypatch.setattr(UnityPatchCorpusAssembly, "frozen_json", staticmethod(together))
    successes: list[JsonDict] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(fixture.run),
            executor.submit(UnityPatchCorpusAssembly(tmp_path, second_path).run),
        ]
        for future in futures:
            try:
                successes.append(future.result(timeout=15))
            except FileExistsError:
                failures += 1
    assert len(successes) == failures == 1
    assert ArtifactStore.read_json(fixture.report) == successes[0]
