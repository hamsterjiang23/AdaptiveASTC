"""Capture gates, nested confirmation provenance and real pixel-stage integration."""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_unity_pixel_identity import capture

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline import pixel_audit_pipeline as module
from reproductions.unity_search_baseline.near_duplicates import UnityNearDuplicateAudit as Near
from reproductions.unity_search_baseline.pixel_audit_pipeline import (
    UnityPixelAuditPipeline as Audit,
)


class Fixture:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root, self.monkeypatch = root, monkeypatch
        local, public = root / "experiment report/.local", root / "experiment report"
        self.path = public / "pipeline-config.json"
        self.series_path, self.series_report = public / "series-config.json", public / "series.json"
        self.manifest_path = local / "series/manifest.json"
        self.job_path = local / "jobs/series/job.json"
        self.batches: list[JsonDict] = []
        self.rows: dict[str, list[JsonDict]] = {}
        self.bindings: list[JsonDict] = []
        self.native: dict[str, tuple[list[JsonDict], JsonDict]] = {}
        for split, color in [("train", (10, 20, 30, 255)), ("validation", (11, 21, 31, 255))]:
            original = capture(local / "original", split, color)
            run = local / f"run-{split}"
            archive = run / "references/normalized-batch"
            shutil.copytree(Path(original["reference_receipt"]["path"]).parent, archive)
            shutil.copyfile(archive / "options.json", run / "options-receipt.json")
            shutil.copyfile(archive / "phase.json", run / "batch-receipt.json")
            row = {"path": f"Assets/{split}/sample.png", "source_split": split}
            self.rows[split] = [row]
            options = run / "options-receipt.json"
            binding = {
                "run_id": split,
                "source_split": split,
                "images": 1,
                "callbacks": 1,
                "options_receipt": str(options),
                "options_sha256": A.sha256_file(options),
                "reference_receipt_sha256": A.sha256_file(archive / "receipt.json"),
                "phase_receipt_sha256": A.sha256_file(run / "batch-receipt.json"),
            }
            self.bindings.append(binding)
            batch_config = {
                "run_id": split,
                "run": str(run),
                "phase": "batch",
                "report": str(options),
            }
            batch_path = public / f"{split}-config.json"
            A.write_json(batch_path, batch_config)
            self.batches.append(
                {
                    "path": str(batch_path),
                    "config": batch_config,
                    "config_sha256": A.sha256_file(batch_path),
                    "split": split,
                }
            )
            self.native[split] = ([row], binding)
        self.source = {"splits": self.rows}
        self.series_config = {
            "output": str(self.manifest_path.parent),
            "report": str(self.series_report),
            "manifest_sha256": "source-sha",
            "coverage": "selected",
        }
        A.write_json(self.series_path, self.series_config)
        self.manifest = {"splits": self.rows, "batch_bindings": self.bindings}
        self.manifest["fingerprint"] = A.fingerprint(self.manifest)
        A.write_json(self.manifest_path, self.manifest)
        self.report = {
            "status": "passed",
            "configuration_sha256": A.sha256_file(self.series_path),
            "source_manifest_sha256": "source-sha",
            "expected_counts": {"train": 1, "validation": 1},
            "counts": {"train": 1, "validation": 1},
            "coverage": "selected",
            "test_opened": False,
            "batches": self.bindings,
            "manifest": str(self.manifest_path),
            "manifest_sha256": A.sha256_file(self.manifest_path),
        }
        A.write_json(self.series_report, self.report)
        A.write_json(
            self.job_path,
            {
                "command": [
                    sys.executable,
                    "-u",
                    "script/collect_unity_references.py",
                    "assemble",
                    "--config",
                    str(self.series_path),
                ]
            },
        )
        A.write_json(self.job_path.with_name("receipt.json"), {"status": "passed"})
        self.config = {
            "mode": "development_smoke",
            "expected_counts": {"train": 1, "validation": 1},
            "development": {
                "config": {
                    "path": str(self.series_path),
                    "sha256": A.sha256_file(self.series_path),
                },
                "job": {"job_config": str(self.job_path), "sha256": A.sha256_file(self.job_path)},
            },
            "output": str(local / "pipeline"),
            "report": str(public / "pipeline.json"),
            "sources_sha256": {},
            "runtime": Near.runtime(),
        }
        A.write_json(self.path, self.config)
        self.series = SimpleNamespace(
            config=self.series_config,
            config_path=self.series_path,
            report=self.series_report,
            output=self.manifest_path.parent,
            validate=self.validate,
            baseline=self.baseline,
            verify_batch=self.verify_batch,
        )
        monkeypatch.setattr(module, "R", lambda root, path: self.series)
        monkeypatch.setattr(Audit, "execution_sources", staticmethod(lambda root: {}))
        monkeypatch.setattr(Near, "execution_sources", staticmethod(lambda root: {}))
        monkeypatch.setattr(
            module.psutil, "virtual_memory", lambda: SimpleNamespace(available=16 * 1024**3)
        )
        monkeypatch.setattr(
            module.shutil, "disk_usage", lambda path: SimpleNamespace(free=10 * 1024**3)
        )
        monkeypatch.setattr(module.P, "dependency_status", self.dependency)

    def validate(self) -> tuple[JsonDict, list[JsonDict]]:
        return self.source, self.batches

    @staticmethod
    def baseline(config: JsonDict) -> SimpleNamespace:
        return SimpleNamespace(run_dir=Path(config["run"]))

    def verify_batch(self, batch: JsonDict) -> tuple[list[JsonDict], JsonDict]:
        return self.native[batch["split"]]

    def dependency(self, item: JsonDict) -> JsonDict:
        return {
            "job": str(self.job_path),
            "status": "passed",
            "receipt_sha256": A.sha256_file(self.job_path.with_name("receipt.json")),
        }

    def audit(self) -> Audit:
        A.write_json(self.path, self.config)
        return Audit(self.root, self.path)


def test_pipeline_runs_real_exact_and_near_stages_without_filtering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    original = fixture.manifest_path.read_bytes()
    audit = fixture.audit()
    result = audit.run()
    assert result["status"] == "passed"
    assert result["counts"] == {"train": 1, "validation": 1}
    assert result["near_identity_pairs"] == result["cross_split_near_identity_pairs"] == 1
    assert result["independent_test_isolation_proven"] is False
    assert result["model_forward_calls"] == result["training_updates"] == 0
    assert result["test_opened"] is result["splits_modified"] is False
    assert fixture.manifest_path.read_bytes() == original
    with pytest.raises(FileExistsError, match="fresh"):
        audit.run()


@pytest.mark.parametrize(
    "field,value",
    [
        ("counts", {"train": 1, "validation": 0}),
        ("status", "partial"),
        ("test_opened", True),
        ("configuration_sha256", "wrong"),
    ],
)
def test_incomplete_or_unbound_development_never_reaches_pixel_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    fixture.report[field] = value
    A.write_json(fixture.series_report, fixture.report)
    audit = fixture.audit()
    with pytest.raises(ValueError, match="Development series"):
        audit.run()
    assert A.read_json(audit.report)["status"] == "failed"
    assert not audit.stage_report("exact").exists()


def test_missing_archive_does_not_call_export_capable_reaudit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    run = Path(fixture.batches[0]["config"]["run"])
    (run / "references/normalized-batch/receipt.json").unlink()
    calls = []
    fixture.series.verify_batch = lambda batch: calls.append(batch)
    with pytest.raises(FileNotFoundError, match="already archived"):
        fixture.audit().run()
    assert not calls


def test_manifest_cannot_substitute_different_rows_even_with_new_valid_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    manifest = copy.deepcopy(fixture.manifest)
    manifest["splits"]["train"][0]["path"] = "Assets/substitute.png"
    manifest.pop("fingerprint")
    manifest["fingerprint"] = A.fingerprint(manifest)
    A.write_json(fixture.manifest_path, manifest)
    fixture.report["manifest_sha256"] = A.sha256_file(fixture.manifest_path)
    A.write_json(fixture.series_report, fixture.report)
    with pytest.raises(ValueError, match="re-audited"):
        fixture.audit().run()


@pytest.mark.parametrize(
    "mutation", ["job", "source", "runtime", "full_counts", "smoke_confirmation"]
)
def test_frozen_execution_contract_rejects_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    if mutation == "job":
        job = A.read_json(fixture.job_path)
        job["command"][-1] = "other.json"
        A.write_json(fixture.job_path, job)
        fixture.config["development"]["job"]["sha256"] = A.sha256_file(fixture.job_path)
    elif mutation == "source":
        fixture.config["sources_sha256"] = {"unknown": "sha"}
    elif mutation == "runtime":
        fixture.config["runtime"] = {}
    elif mutation == "full_counts":
        fixture.config["mode"] = "confirmation_complete"
    else:
        fixture.config["confirmation"] = {}
    with pytest.raises(ValueError):
        fixture.audit()


def test_wait_checks_dependency_and_resources_before_reading_archives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    calls = []

    def dependency(item: JsonDict) -> JsonDict:
        calls.append(item)
        return {"status": "running"} if len(calls) == 1 else fixture.dependency(item)

    def sleep(seconds: float) -> None:
        assert seconds <= 60
        assert A.read_json(Path(fixture.config["report"]))["status"] in {
            "waiting_captures",
            "waiting_resources",
        }
        assert not Path(fixture.config["output"], "exact-config.json").exists()

    ram = iter([4, 4, 16])
    monkeypatch.setattr(module.P, "dependency_status", dependency)
    monkeypatch.setattr(
        module.psutil, "virtual_memory", lambda: SimpleNamespace(available=next(ram) * 1024**3)
    )
    monkeypatch.setattr(module.time, "sleep", sleep)
    assert fixture.audit().run()["status"] == "passed"
    assert len(calls) == 3


def test_failed_dependency_leaves_failure_and_no_pixel_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(module.P, "dependency_status", lambda item: {"status": "failed"})
    audit = fixture.audit()
    with pytest.raises(RuntimeError, match="dependency failed"):
        audit.run()
    assert A.read_json(audit.report)["status"] == "failed"
    assert not audit.stage_report("exact").exists()


@pytest.mark.parametrize("destination", ["main", "exact", "near"])
def test_pending_development_report_collision_is_rejected_before_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, destination: str
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    pipeline_report = Path(fixture.config["report"])
    pending = (
        pipeline_report
        if destination == "main"
        else pipeline_report.with_name(f"{pipeline_report.stem}-{destination}.json")
    )
    batch = fixture.batches[0]
    batch["config"]["report"] = str(pending)
    A.write_json(Path(batch["path"]), batch["config"])
    batch["config_sha256"] = A.sha256_file(Path(batch["path"]))
    assert not pending.exists()
    with pytest.raises(ValueError, match="protected capture file"):
        fixture.audit()
    assert not pending.exists()
    assert not Path(fixture.config["output"]).exists()


@pytest.mark.parametrize("destination", ["batch_report", "batch_directory", "smoke_report"])
def test_pending_confirmation_destinations_are_protected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, destination: str
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    audit = fixture.audit()
    public, local = tmp_path / "experiment report", tmp_path / "experiment report/.local"
    reports = public / "confirmation-batches"
    smoke = SimpleNamespace(
        report=public / "confirmation-smoke.json",
        config_path=public / "smoke-config.json",
        baseline=SimpleNamespace(run_dir=local / "smoke"),
    )
    audit.confirmation = SimpleNamespace(  # type: ignore[assignment]
        path=public / "confirmation-config.json",
        report=public / "confirmation.json",
        output=local / "confirmation",
        reports=reports,
        smoke=smoke,
        ranges=lambda: [(2, 256)],
        batch_run_id=lambda start: "confirmation-from00002",
    )
    if destination == "batch_report":
        audit.report = reports / "future-batch.json"
    elif destination == "batch_directory":
        audit.output = local / "confirmation-from00002" / "audit"
    else:
        audit.report = smoke.report
    with pytest.raises(ValueError, match="protected capture"):
        audit.verify_destinations()
    assert not audit.report.exists() and not audit.output.exists()


def test_confirmation_projection_binds_original_nested_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    audit = fixture.audit()
    audit.output.mkdir(parents=True)
    run = Path(fixture.batches[0]["config"]["run"])
    options = A.read_json(run / "options-receipt.json")
    restored = options.pop("managed_source_restoration")
    capture_path = tmp_path / "capture-config.json"
    capture_report = tmp_path / "capture-report.json"
    A.write_json(capture_path, {"start": 0, "images": 2, "run_id": "confirmation"})
    A.write_json(capture_report, {"options_audit": options, "managed_source_restoration": restored})
    A.write_json(run / "managed-hook/receipt.json", restored)
    binding = {
        "config": str(capture_path),
        "config_sha256": A.sha256_file(capture_path),
        "report_sha256": A.sha256_file(capture_report),
        "reference_receipt_sha256": A.sha256_file(run / "references/normalized-batch/receipt.json"),
        "phase_receipt_sha256": A.sha256_file(run / "batch-receipt.json"),
        "managed_restoration_sha256": A.sha256_file(run / "managed-hook/receipt.json"),
    }
    rows = [{"path": "Assets/confirmation/one.png"}, {"path": "Assets/confirmation/two.png"}]
    confirmation_output = tmp_path / "confirmation-output"
    manifest = {
        "status": "passed",
        "splits": {"confirmation": rows},
        "batches": [binding],
        "reservation_manifest_sha256": "reserved",
    }
    manifest["fingerprint"] = A.fingerprint(manifest)
    manifest_path = confirmation_output / "manifest.json"
    A.write_json(manifest_path, manifest)
    report_path = tmp_path / "confirmation-series.json"
    A.write_json(
        report_path,
        {
            "status": "passed",
            "config_sha256": "series",
            "source_files_sha256": {},
            "captured_images": 2,
            "coverage": "complete",
            "native_labels_collected": True,
            "test_opened": False,
            "model_sealed": False,
            "batches": [binding],
            "manifest": str(manifest_path),
            "manifest_sha256": A.sha256_file(manifest_path),
        },
    )
    native_capture = SimpleNamespace(
        config=A.read_json(capture_path),
        config_path=capture_path,
        report=capture_report,
        baseline=SimpleNamespace(run_dir=run),
    )
    monkeypatch.setattr(module, "C", lambda root, path: native_capture)
    audit.confirmation = SimpleNamespace(  # type: ignore[assignment]
        validate=lambda: None,
        report=report_path,
        config_sha="series",
        config={"sources_sha256": {}},
        output=confirmation_output,
        ranges=lambda: [],
        audit_batch=lambda capture: (rows, binding),
        smoke=SimpleNamespace(reservation={"manifest_sha256": "reserved"}),
    )
    audit.expected["confirmation"] = 2
    before = capture_report.read_bytes()
    result = audit.confirmation_batches()
    projected = A.read_json(Path(result[0]["options_receipt"]["path"]))
    assert projected["rows"] == options["rows"]
    assert projected["managed_source_restoration"] == restored
    assert projected["projection_provenance"]["original_report"]["sha256"] == A.sha256_file(
        capture_report
    )
    assert capture_report.read_bytes() == before
    capture_report.write_bytes(before + b" ")
    with pytest.raises(ValueError, match="evidence changed"):
        audit.verify()


@pytest.mark.parametrize("mutation", [None, "sources", "partial", "exit", "command", "config"])
def test_full_scope_requires_a_bound_successful_same_code_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str | None
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    audit = fixture.audit()
    path, config_path = tmp_path / "smoke.json", tmp_path / "smoke-config.json"
    receipt_path = tmp_path / "smoke-receipt.json"
    A.write_json(config_path, {"report": str(path)})
    stages = []
    for kind in ["exact", "near"]:
        stage = tmp_path / f"smoke-{kind}.json"
        A.write_json(stage, {"status": "passed"})
        stages.append({"kind": kind, "path": str(stage), "sha256": A.sha256_file(stage)})
    smoke = {
        "status": "passed",
        "mode": "development_smoke",
        "counts": {"train": 64, "validation": 2},
        "sources_sha256": {},
        "runtime": Near.runtime(),
        "stages": stages,
        "config_sha256": A.sha256_file(config_path),
    }
    receipt = {
        "status": "passed",
        "process_exit_code": 0,
        "command": [
            sys.executable,
            "-u",
            "script/queue_unity_pixel_audit.py",
            "--config",
            str(config_path),
        ],
    }
    if mutation == "sources":
        smoke["sources_sha256"] = {"old-code": "sha"}
    elif mutation == "partial":
        smoke["counts"]["train"] = 63
    elif mutation == "exit":
        receipt["process_exit_code"] = 1
    elif mutation == "command":
        receipt["command"][2] = "script/other.py"
    elif mutation == "config":
        A.write_json(config_path, {"report": "other-report.json"})
        smoke["config_sha256"] = A.sha256_file(config_path)
    A.write_json(path, smoke)
    A.write_json(receipt_path, receipt)
    audit.config["smoke_provenance"] = {
        "report": str(path),
        "report_sha256": A.sha256_file(path),
        "process_receipt": str(receipt_path),
        "process_receipt_sha256": A.sha256_file(receipt_path),
    }
    if mutation is None:
        audit.verify_smoke()
    else:
        with pytest.raises(ValueError):
            audit.verify_smoke()
