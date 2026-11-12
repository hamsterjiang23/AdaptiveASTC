"""Wait for the active confirmation collection, then capture approved development replacements."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.jobs import ReproductionJob
from reproductions.unity_search_baseline.collection import UnityReferenceSeries
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


class UnityDevelopmentCaptureQueue:
    def __init__(self, root: Path, config: Path) -> None:
        self.root, self.path = root.resolve(), config.resolve()
        self.config = A.read_json(self.path)
        self.sha = A.sha256_file(self.path)
        self.report = Path(self.config["report"]).resolve()
        if not self.report.is_relative_to(self.root / "experiment report") or (
            self.report.is_relative_to(self.root / "experiment report/.local")
        ):
            raise ValueError("Queue report must be public")
        if not 1 <= self.config["poll_seconds"] <= 60:
            raise ValueError("Observation intervals must be bounded")
        self.verify()

    def verify(self) -> None:
        if A.sha256_file(self.path) != self.sha:
            raise ValueError("Queue configuration changed")
        for name, digest in self.config["sources_sha256"].items():
            if A.sha256_file(self.root / name) != digest:
                raise ValueError(f"Frozen capture source changed: {name}")
        for key in ["reservation", "reference_plan", "capture_job", "source_baseline"]:
            binding = self.config[key]
            if A.sha256_file(Path(binding["path"])) != binding["sha256"]:
                raise ValueError(f"Frozen capture binding changed: {key}")
        baseline = A.read_json(Path(self.config["source_baseline"]["path"]))
        required_sources = set(baseline["sources_unchanged"]) | {
            "reproductions/unity_search_baseline/development_capture_queue.py",
            "script/queue_unity_development_replacements.py",
            "script/collect_unity_references.py",
            "src/adaptive_astc/data/unity_capture_input.py",
            "src/adaptive_astc/data/unity_inference.py",
        }
        if set(self.config["sources_sha256"]) != required_sources:
            raise ValueError("Capture and input-audit execution source bindings are incomplete")
        if any(
            self.config["sources_sha256"][name] != digest
            for name, digest in baseline["sources_unchanged"].items()
        ):
            raise ValueError("Original development execution sources changed")
        reservation = A.read_json(Path(self.config["reservation"]["path"]))
        if reservation["status"] != "reserved" or reservation["replacement_counts"] != {
            "train": 13,
            "validation": 5,
        }:
            raise ValueError("Expected the approved18 replacement reservation")
        for binding in reservation["files"].values():
            if A.sha256_file(Path(binding["path"])) != binding["sha256"]:
                raise ValueError("Reserved replacement manifest changed")
        plan = A.read_json(Path(self.config["reference_plan"]["path"]))
        protected = {self.path, Path(plan["report"]).resolve()}
        protected.update(
            Path(self.config[key]["path"]).resolve()
            for key in ["reservation", "reference_plan", "capture_job", "source_baseline"]
        )
        for batch in plan["batches"]:
            path = Path(batch["config"])
            if A.sha256_file(path) != batch["sha256"]:
                raise ValueError("Frozen reference batch changed")
            protected.update([path.resolve(), Path(A.read_json(path)["report"]).resolve()])
        if self.report in protected:
            raise ValueError("Queue report aliases a protected capture report or configuration")
        source = reservation["files"]["replacements"]
        if Path(plan["manifest"]).resolve() != Path(source["path"]).resolve() or (
            plan["manifest_sha256"] != source["sha256"]
            or plan["expected_counts"] != reservation["replacement_counts"]
        ):
            raise ValueError("Capture plan differs from approved replacement membership")
        job = A.read_json(Path(self.config["capture_job"]["path"]))
        expected = [
            str(self.root / ".venv/Scripts/python.exe"),
            "-u",
            "script/collect_unity_references.py",
            "collect",
            "--config",
            self.config["reference_plan"]["path"],
        ]
        if job["command"] != expected:
            raise ValueError("Capture command does not match the bound reference plan")

    def run(self) -> JsonDict:
        state: JsonDict = {
            "status": "waiting_confirmation",
            "config_sha256": self.sha,
            "started_utc": datetime.now(UTC).isoformat(),
            "training_updates": 0,
            "test_opened": False,
        }
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as stream:
            json.dump(state, stream)
        started = time.perf_counter()
        try:
            while True:
                self.verify()
                dependency = P.dependency_status(self.config["dependency"])
                memory = psutil.virtual_memory().available / 2**30
                state.update(
                    dependency=dependency,
                    available_ram_gib=memory,
                    updated_utc=datetime.now(UTC).isoformat(),
                )
                state["status"] = (
                    "waiting_confirmation"
                    if dependency["status"] != "passed"
                    else "waiting_resources"
                )
                A.write_json(self.report, state)
                if (
                    dependency["status"] == "passed"
                    and memory >= self.config["minimum_free_ram_gib"]
                ):
                    break
                time.sleep(self.config["poll_seconds"])
            plan = UnityReferenceSeries(self.root, Path(self.config["reference_plan"]["path"]))
            source, _ = plan.validate()
            for rows in source["splits"].values():
                for row in rows:
                    path = Path(plan.config["project"]) / row["path"]
                    if A.sha256_file(path) != row["source_sha256"] or (
                        A.sha256_file(Path(str(path) + ".meta")) != row["meta_sha256"]
                    ):
                        raise ValueError("Reserved replacement input changed before capture")
            state.update(
                status="collecting_replacements", waiting_seconds=time.perf_counter() - started
            )
            A.write_json(self.report, state)
            receipt = ReproductionJob(self.root, Path(self.config["capture_job"]["path"])).run()
            if receipt["status"] != "passed" or receipt["process_exit_code"] != 0:
                raise RuntimeError("Replacement native capture failed; preserve this attempt")
            captured = A.read_json(plan.report)
            if captured["status"] != "passed" or captured["counts"] != {
                "train": 13,
                "validation": 5,
            }:
                raise ValueError("Incomplete replacement native capture")
            manifest = Path(captured["manifest"])
            if A.sha256_file(manifest) != captured["manifest_sha256"]:
                raise ValueError("Captured replacement manifest changed")
            inputs = []
            for split, rows in A.read_json(manifest)["splits"].items():
                adapter = UnityCaptureInputAdapter(rows, split)
                inputs.extend(adapter.bindings)
            self.verify()
            state.update(
                status="passed",
                images=len(inputs),
                input_bindings=inputs,
                reference_report=str(plan.report),
                reference_report_sha256=A.sha256_file(plan.report),
                manifest=str(manifest),
                manifest_sha256=captured["manifest_sha256"],
                process_exit_code=receipt["process_exit_code"],
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state.update(
                wall_seconds=time.perf_counter() - started, ended_utc=datetime.now(UTC).isoformat()
            )
            A.write_json(self.report, state)
        return state
