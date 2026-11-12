"""Serially capture the complete reserved confirmation cohort after its native smoke."""

from __future__ import annotations

import copy
import re
import sys
import time
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.unity_reference import UnityReferenceCapture
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture as C
from reproductions.unity_search_baseline.metadata import UnityOptionCapture
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


class UnityConfirmationSeries:
    """Reuse the first two primary images, then collect bounded batches without prediction."""

    def __init__(self, root: Path, path: Path) -> None:
        self.root = root.resolve()
        self.path = path.resolve()
        self.config_sha = A.sha256_file(self.path)
        self.config = A.read_json(self.path)
        self.verify_bindings()
        self.smoke = C(self.root, Path(self.config["smoke_config"]["path"]))
        if (
            self.smoke.config["start"] != 0
            or self.smoke.config["images"] != 2
            or self.smoke.config.get("smoke_report") is not None
        ):
            raise ValueError("Series requires the first two primary images as its native smoke")
        job = A.read_json(Path(self.config["smoke_job"]["job_config"]))
        if job["command"] != [
            sys.executable,
            "-u",
            "script/capture_unity_confirmation.py",
            "--config",
            str(self.smoke.config_path),
        ]:
            raise ValueError("Smoke job does not execute the bound capture configuration")
        manifest = A.read_json(Path(self.smoke.reservation["manifest"]))
        self.rows = manifest["primary"]
        total, size = self.config["expected_images"], self.config["batch_size"]
        if type(total) is not int or total <= 2 or total != len(self.rows):
            raise ValueError("Series must cover the entire reserved primary cohort")
        if type(size) is not int or not 1 <= size <= 256:
            raise ValueError("Series batch size must be 1..256")
        keys = [row["path"].replace("\\", "/").casefold() for row in self.rows]
        if len(set(keys)) != total:
            raise ValueError("Reserved primary cohort contains duplicate asset paths")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.config["run_id"]):
            raise ValueError("Series run ID must be a safe directory name")
        self.output = (self.root / "experiment report/.local" / self.config["run_id"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        public = self.root / "experiment report"
        if not self.report.is_relative_to(public) or self.report.is_relative_to(public / ".local"):
            raise ValueError("Series report must be under public experiment report")
        self.reports = self.report.with_name(self.report.stem + "-batches")
        if self.smoke.report == self.report or self.smoke.report.is_relative_to(self.reports):
            raise ValueError("Series outputs overlap the smoke report")
        for start, _ in self.ranges():
            if self.batch_run_id(start) == self.smoke.config["run_id"]:
                raise ValueError("Series batch identity overlaps the smoke")

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        names = [
            "reproductions/unity_search_baseline/confirmation_series.py",
            "script/collect_unity_confirmation_series.py",
        ]
        return C.execution_sources(root) | {name: A.sha256_file(root / name) for name in names}

    def verify_bindings(self) -> None:
        if A.sha256_file(self.path) != self.config_sha:
            raise ValueError("Confirmation series configuration changed")
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Confirmation series execution sources changed or are incomplete")
        for key, field in [("smoke_config", "path"), ("smoke_job", "job_config")]:
            item = self.config[key]
            if A.sha256_file(Path(item[field])) != item["sha256"]:
                raise ValueError(f"Confirmation series binding changed: {key}")

    def ranges(self) -> list[tuple[int, int]]:
        total, size = self.config["expected_images"], self.config["batch_size"]
        return [(start, min(size, total - start)) for start in range(2, total, size)]

    def batch_run_id(self, start: int) -> str:
        return f"{self.config['run_id']}-from{start:05d}"

    def validate(self) -> JsonDict:
        self.verify_bindings()
        self.smoke.validate()
        return {
            "status": "validated",
            "images": len(self.rows),
            "reused_smoke_images": 2,
            "remaining_batches": [{"start": start, "images": n} for start, n in self.ranges()],
            "source_split": "confirmation",
            "test_opened": False,
            "scope": "Plan/source validation; no completed native smoke or full capture implied",
        }

    @staticmethod
    def audit_batch(capture: C) -> tuple[list[JsonDict], JsonDict]:
        """Require real native receipts, exact membership, restored state and archived bytes."""
        capture.validate()
        report = A.read_json(capture.report)
        baseline = capture.baseline
        baseline.verify_protocol()
        if (
            report["status"] != "passed"
            or report["config_sha256"] != capture.config_sha
            or Path(report["configuration_path"]).resolve() != capture.config_path
            or report["source_files_sha256"] != capture.config["sources_sha256"]
            or report["reservation_manifest_sha256"] != capture.reservation["manifest_sha256"]
            or Path(report["run_directory"]).resolve() != baseline.run_dir
            or report["images"] != len(capture.rows)
            or report["source_split"] != "confirmation"
            or report["test_opened"] is not False
            or report["training_updates"] != 0
            or report["native_labels_collected"] is not True
        ):
            raise ValueError("Confirmation batch lacks complete bound native evidence")
        phase_path = baseline.run_dir / "batch-receipt.json"
        phase = A.read_json(phase_path)
        restoration_path = baseline.run_dir / "managed-hook/receipt.json"
        restored = A.read_json(restoration_path)
        if (
            phase["status"] != "passed"
            or phase["process_exit_code"] != 0
            or phase["metadata_restore_conflicts"]
            or restored != report["managed_source_restoration"]
            or restored["status"] != "restored"
            or restored["original_sha256"] != restored["restored_sha256"]
        ):
            raise ValueError("Confirmation native execution or restoration failed")
        captured = UnityReferenceCapture(baseline).collect("batch")
        actual = UnityOptionCapture.audit(baseline, "batch", captured)
        if actual != report["options_audit"]:
            raise ValueError("Confirmation callback audit changed")
        imports = baseline._read_lines(baseline.run_dir / "batch-imports.jsonl")
        native_rows = baseline._read_lines(baseline.run_dir / "batch-native.jsonl")
        native = {baseline._asset_key(row["asset"]): row for row in native_rows}
        if len(native) != len(capture.rows) or len(native_rows) != len(capture.rows):
            raise ValueError("Confirmation native search coverage differs")
        archive = baseline.run_dir / "references/normalized-batch"
        rows = []
        for index, (source, reference, observed, imported) in enumerate(
            zip(capture.rows, captured["rows"], actual["rows"], imports, strict=True)
        ):
            key = baseline._asset_key(source["path"])
            if (
                any(
                    baseline._asset_key(value) != key
                    for value in [reference["path"], observed["path"], imported["asset"]]
                )
                or reference["source_split"] != "confirmation"
                or reference["source_md4"].lower() != source["fileHash"].lower()
                or reference["selection"] != native[key]
            ):
                raise ValueError("Confirmation reference membership, split or selection differs")
            rows.append(
                {
                    "path": source["path"],
                    "source_md4": source["fileHash"],
                    "source_sha256": source["source_sha256"],
                    "meta_sha256": source["meta_sha256"],
                    "source_split": "confirmation",
                    "reference_png": str(archive / f"{index:05d}" / "original.png"),
                    "reference_sha256": reference["artifacts_sha256"]["original.png"],
                    "width": reference["width"],
                    "height": reference["height"],
                    "selection": reference["selection"],
                    "actual_options": observed,
                    "import_metadata": imported,
                    "capture_directory": str(archive),
                    "capture_index": index,
                }
            )
        return rows, {
            "start": capture.config["start"],
            "images": len(rows),
            "run_id": capture.config["run_id"],
            "config": str(capture.config_path),
            "config_sha256": capture.config_sha,
            "report": str(capture.report),
            "report_sha256": A.sha256_file(capture.report),
            "reference_receipt_sha256": A.sha256_file(archive / "receipt.json"),
            "phase_receipt_sha256": A.sha256_file(phase_path),
            "managed_restoration_sha256": A.sha256_file(restoration_path),
            "editor_process_seconds": phase["process_wall_seconds"],
            "capture_wall_seconds": report["wall_seconds"],
            "callbacks": actual["candidate_callbacks"],
        }

    def batch_config(self, start: int, count: int, smoke_sha: str) -> Path:
        config = copy.deepcopy(self.smoke.config)
        config.pop("prior_attempt", None)
        run_id = self.batch_run_id(start)
        config.update(
            start=start,
            images=count,
            run_id=run_id,
            report=str(self.reports / f"{run_id}.json"),
            dependencies=[self.config["smoke_job"]],
            smoke_report={"path": str(self.smoke.report), "sha256": smoke_sha},
        )
        path = self.reports / f"{run_id}-config.json"
        if path.exists():
            raise FileExistsError("Confirmation batch config already exists")
        A.write_json(path, config)
        return path

    def publish(self, state: JsonDict, rows: list[JsonDict]) -> None:
        """Publish partial coverage explicitly; never silently filter or substitute samples."""
        expected = self.rows[: len(rows)]
        if any(
            row["source_split"] != "confirmation"
            or row["path"] != source["path"]
            or row["source_md4"] != source["fileHash"]
            for row, source in zip(rows, expected, strict=True)
        ):
            raise ValueError("Confirmation assembly differs from the frozen primary order")
        complete = len(rows) == len(self.rows)
        manifest = {
            "status": "passed" if complete else "partial",
            "config_sha256": self.config_sha,
            "reservation_manifest_sha256": self.smoke.reservation["manifest_sha256"],
            "splits": {"confirmation": rows},
            "batches": state["batches"],
            "test_opened": False,
            "training_updates": 0,
            "model_sealed": False,
            "scope": "Native capture only; pixel isolation and model acceptance remain separate",
        }
        manifest["fingerprint"] = A.fingerprint(manifest)
        path = self.output / "manifest.json"
        A.write_json(path, manifest)
        state.update(
            captured_images=len(rows),
            coverage="complete" if complete else "partial",
            native_labels_collected=complete,
            manifest=str(path),
            manifest_sha256=A.sha256_file(path),
        )
        A.write_json(self.report, state)

    def run(self) -> JsonDict:
        self.validate()
        if self.output.exists() or self.reports.exists() or self.report.exists():
            raise FileExistsError("Use a fresh confirmation series identity; retain prior records")
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        started = time.perf_counter()
        state: JsonDict = {
            "status": "waiting_smoke",
            "config_sha256": self.config_sha,
            "source_files_sha256": self.config["sources_sha256"],
            "expected_images": len(self.rows),
            "captured_images": 0,
            "coverage": "partial",
            "source_split": "confirmation",
            "batches": [],
            "test_opened": False,
            "native_labels_collected": False,
            "training_updates": 0,
            "model_sealed": False,
            "scope": "Serial reserved-primary capture; no model evaluation or training",
        }
        try:
            self.output.mkdir(parents=True, exist_ok=False)
            self.reports.mkdir(parents=True, exist_ok=False)
            while True:
                self.verify_bindings()
                self.smoke.verify_bindings()
                dependency = P.dependency_status(self.config["smoke_job"])
                state["dependency"] = dependency
                A.write_json(self.report, state)
                if dependency["status"] == "passed":
                    break
                if dependency["status"] == "failed":
                    raise RuntimeError("Confirmation smoke dependency failed")
                time.sleep(15)
            state["dependency_wait_seconds"] = time.perf_counter() - started
            rows, binding = self.audit_batch(self.smoke)
            smoke_sha = binding["report_sha256"]
            state["batches"].append(binding)
            self.publish(state, rows)
            for start, count in self.ranges():
                self.verify_bindings()
                if A.sha256_file(self.smoke.report) != smoke_sha:
                    raise ValueError("Completed smoke report changed during the series")
                state.update(status="collecting", current_start=start, current_images=count)
                A.write_json(self.report, state)
                capture = C(self.root, self.batch_config(start, count, smoke_sha))
                capture.run()
                batch_rows, binding = self.audit_batch(capture)
                rows.extend(batch_rows)
                state["batches"].append(binding)
                self.publish(state, rows)
            self.verify_bindings()
            if state["captured_images"] != len(self.rows):
                raise ValueError("Confirmation capture did not cover all reserved primary images")
            state.update(status="passed", current_start=None, current_images=None)
            state["editor_process_seconds"] = sum(
                row["editor_process_seconds"] for row in state["batches"]
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(self.report, state)
        return state
