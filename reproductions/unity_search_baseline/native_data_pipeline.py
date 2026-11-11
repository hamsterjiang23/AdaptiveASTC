"""Wait for frozen upstream jobs, then prepare and audit the complete native corpus."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A


class UnityNativeDataPipeline:
    """Keep waiting, preparation, assembly and both audits separately observable."""

    SOURCE_FILES = (
        "reproductions/unity_search_baseline/native_data_pipeline.py",
        "reproductions/unity_search_baseline/patch_batches.py",
        "reproductions/unity_search_baseline/patch_targets.py",
        "reproductions/unity_search_baseline/patch_assembly.py",
        "reproductions/unity_search_baseline/dataset_audit.py",
        "reproductions/unity_search_baseline/prediction_audit.py",
        "reproductions/unity_search_baseline/candidate_queue.py",
        "reproductions/unity_search_baseline/candidate_archive.py",
        "reproductions/unity_search_baseline/policy.py",
        "reproductions/unity_search_baseline/policy_audit.py",
        "src/adaptive_astc/data/unity_patch_dataset.py",
        "src/adaptive_astc/data/patch_targets.py",
        "src/adaptive_astc/evaluation/unity_quality.py",
        "script/finish_unity_native_data.py",
    )

    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.path = root.resolve(), config_path.resolve()
        self.config = A.read_json(self.path)
        self.config_sha256 = A.sha256_file(self.path)
        self.output = Path(self.config["output"]).resolve()
        self.reports = Path(self.config["reports"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        local = self.root / "experiment report/.local"
        public = self.root / "experiment report/unity-accuracy90-20261111"
        if not self.output.is_relative_to(local) or not all(
            path.is_relative_to(public) for path in [self.reports, self.report]
        ):
            raise ValueError("Pipeline artifacts require separate local/public experiment paths")
        if self.report.is_relative_to(self.reports) or self.path in {self.report, self.reports}:
            raise ValueError("Pipeline reports cannot alias configuration or stage directories")
        mode = self.config["mode"]
        if mode not in {"complete", "smoke"}:
            raise ValueError("Explicit complete or smoke mode is required")
        counts = self.config["expected_counts"]
        if set(counts) != {"train", "validation"} or any(
            type(v) is not int or v <= 0 for v in counts.values()
        ):
            raise ValueError("Require positive training/validation counts")
        if mode == "complete" and (
            counts != {"train": 10000, "validation": 1000}
            or self.config.get("run_ids")
            or self.config.get("snapshot")
            or not self.config["dependencies"]
        ):
            raise ValueError("Complete mode requires full coverage and live upstream dependencies")
        if mode == "smoke" and (
            not self.config.get("run_ids") or not self.config.get("snapshot_sha256")
        ):
            raise ValueError("Smoke mode requires an explicit frozen subset snapshot")
        for key in ["poll_seconds", "minimum_free_ram_gib", "minimum_free_disk_gib"]:
            value = self.config[key]
            if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
                raise ValueError("Resource limits and polling must be finite positive values")
        if self.config["poll_seconds"] > 60:
            raise ValueError("Upstream observations must be bounded to60seconds")
        self.verify_bindings()

    def verify_bindings(self) -> None:
        if A.sha256_file(self.path) != self.config_sha256:
            raise ValueError("Pipeline configuration changed")
        expected = self.config["sources_sha256"]
        if set(expected) != set(self.SOURCE_FILES):
            raise ValueError("Pipeline source bindings are incomplete")
        for name, sha in expected.items():
            if A.sha256_file(self.root / name) != sha:
                raise ValueError(f"Pipeline source changed: {name}")
        queue = Path(self.config["candidate_queue_config"])
        if A.sha256_file(queue) != self.config["candidate_queue_config_sha256"]:
            raise ValueError("Candidate queue configuration changed")

    @staticmethod
    def await_observer(path: Path, receipt: JsonDict, status: str) -> JsonDict:
        started = datetime.fromisoformat(receipt["started_utc"]).timestamp()
        heartbeat = datetime.fromisoformat(
            receipt.get("last_observed_alive_utc", receipt["started_utc"])
        ).timestamp()
        try:
            observer = psutil.Process(receipt["process_id"])
            valid = observer.is_running() and abs(observer.create_time() - started) <= 120
        except psutil.NoSuchProcess:
            valid = False
        if not valid or time.time() - heartbeat > 120:
            latest = A.read_json(path.parent / "receipt.json")
            if latest["status"] != receipt["status"]:
                return UnityNativeDataPipeline.dependency_status(
                    {"job_config": str(path), "sha256": receipt["config_sha256"]}
                )
            raise RuntimeError("Upstream child is missing and no current observer can finish")
        return {"job": str(path), "status": status, "observer_pid": observer.pid}

    @staticmethod
    def dependency_status(item: JsonDict) -> JsonDict:
        path = Path(item["job_config"])
        if A.sha256_file(path) != item["sha256"]:
            raise ValueError("Upstream job configuration changed")
        config = A.read_json(path)
        receipt_path = path.parent / "receipt.json"
        receipt = A.read_json(receipt_path)
        if receipt["config_sha256"] != item["sha256"] or receipt["command"] != config["command"]:
            raise ValueError("Upstream receipt belongs to a different command/configuration")
        status = receipt["status"]
        if status == "passed" and receipt.get("process_exit_code") == 0:
            return {
                "job": str(path),
                "status": "passed",
                "receipt_sha256": A.sha256_file(receipt_path),
            }
        if status not in {"running", "running_child_unobserved"}:
            raise RuntimeError(f"Upstream job did not pass: {path} {status}")
        if receipt.get("child_pid") is None:
            return UnityNativeDataPipeline.await_observer(path, receipt, "awaiting_child_start")
        try:
            process = psutil.Process(receipt["child_pid"])
            created = process.create_time()
            if not process.is_running():
                raise psutil.NoSuchProcess(process.pid)
            if (
                process.cmdline()[1:] != receipt["command"][1:]
                or abs(created - datetime.fromisoformat(receipt["started_utc"]).timestamp()) > 120
            ):
                raise RuntimeError("Upstream PID identity no longer matches its receipt")
        except psutil.NoSuchProcess:
            # The observer may not have published its terminal receipt yet; never restart it.
            latest = A.read_json(receipt_path)
            if latest["status"] != status:
                return UnityNativeDataPipeline.dependency_status(item)
            return UnityNativeDataPipeline.await_observer(path, latest, "awaiting_terminal_receipt")
        return {"job": str(path), "status": "running", "pid": process.pid, "created": created}

    def snapshot(self) -> JsonDict:
        queue = A.read_json(Path(self.config["candidate_queue_config"]))
        if self.config["mode"] == "smoke":
            path = Path(self.config["snapshot"])
            if A.sha256_file(path) != self.config["snapshot_sha256"]:
                raise ValueError("Smoke snapshot changed")
        else:
            path = Path(queue["report"])
        snapshot = A.read_json(path)
        if snapshot["config_sha256"] != self.config["candidate_queue_config_sha256"]:
            raise ValueError("Candidate publication has the wrong configuration binding")
        if snapshot["test_opened"] is not False:
            raise ValueError("Require development-only candidate publication")
        if self.config["mode"] == "complete" and (
            snapshot["status"] != "passed"
            or snapshot["coverage"] != "complete"
            or snapshot["counts"] != self.config["expected_counts"]
            or snapshot["expected_counts"] != self.config["expected_counts"]
        ):
            raise ValueError("Completed upstream jobs did not publish the complete native corpus")
        names = self.config.get("run_ids") or [row["run_id"] for row in snapshot["batches"]]
        selected = [row for row in snapshot["batches"] if row["run_id"] in names]
        if (
            len(names) != len(set(names))
            or len(selected) != len(names)
            or {row["run_id"] for row in selected} != set(names)
        ):
            raise ValueError("Selected candidate batches are missing or duplicated")
        counts = {
            split: sum(row["images"] for row in selected if row["source_split"] == split)
            for split in ["train", "validation"]
        }
        if counts != self.config["expected_counts"]:
            raise ValueError("Selected candidate counts differ from the pipeline protocol")
        return snapshot

    def execute_stage(self, name: str, config: JsonDict, state: JsonDict) -> JsonDict:
        self.verify_bindings()
        path = self.reports / f"{name}-config.json"
        A.write_json(path, config)
        state.update(status="running", current_stage=name)
        A.write_json(self.report, state)
        started = time.perf_counter()
        if name == "prepare":
            from reproductions.unity_search_baseline.patch_batches import UnityPatchBatchPreparation

            result = UnityPatchBatchPreparation(self.root, path).run()
        elif name == "assembly":
            from reproductions.unity_search_baseline.patch_assembly import UnityPatchCorpusAssembly

            result = UnityPatchCorpusAssembly(self.root, path).run()
        elif name == "dataset":
            from reproductions.unity_search_baseline.dataset_audit import UnityPatchDatasetAudit

            result = UnityPatchDatasetAudit(path).run()
        elif name == "interface":
            from reproductions.unity_search_baseline.prediction_audit import UnityPredictionAudit

            result = UnityPredictionAudit(self.root, path).run()
        else:
            raise ValueError("Unknown native data stage")
        self.verify_bindings()
        if (
            result["status"] != "passed"
            or result["test_opened"] is not False
            or result["training_updates"] != 0
        ):
            raise ValueError("Native data stage did not pass development-only verification")
        if name in {"prepare", "assembly", "dataset"}:
            counts = result["unique_images"] if name == "dataset" else result["counts"]
            if counts != self.config["expected_counts"]:
                raise ValueError("Native stage coverage differs from the configured counts")
        if name in {"prepare", "assembly"} and self.config["mode"] == "complete":
            if result["coverage"] != "complete":
                raise ValueError("Partial native data cannot satisfy complete mode")
        if name == "interface" and any(
            result["results"][split]["exact_targets"]["count"] != count
            or result["results"][split]["exact_targets"]["accuracy"] != 1.0
            or result["results"][split]["exact_targets"]["full_choice_accuracy"] != 1.0
            for split, count in self.config["expected_counts"].items()
        ):
            raise ValueError("Exact-target interface did not reproduce all original choices")
        state["stages"].append(
            {
                "name": name,
                "report": config["report"],
                "report_sha256": A.sha256_file(Path(config["report"])),
                "config_sha256": A.sha256_file(path),
                "stage_wall_seconds": time.perf_counter() - started,
            }
        )
        A.write_json(self.report, state)
        return result

    def run(self, *, follow: bool = True) -> JsonDict:
        if self.report.exists() or self.reports.exists():
            raise FileExistsError("Use fresh pipeline report paths; previous attempts are retained")
        self.output.mkdir(parents=True, exist_ok=False)
        self.reports.mkdir(parents=True, exist_ok=False)
        started = time.perf_counter()
        state: JsonDict = {
            "status": "waiting_upstream",
            "mode": self.config["mode"],
            "config_sha256": self.config_sha256,
            "expected_counts": self.config["expected_counts"],
            "stages": [],
            "training_updates": 0,
            "test_opened": False,
            "scope": "Native data preparation/audits only; no trained model or production accuracy",
        }
        # Claim the public identity atomically, even when other outputs use different paths.
        initial = self.output / "initial-state.json"
        A.write_json(initial, state)
        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.report.hardlink_to(initial)
        try:
            while True:
                self.verify_bindings()
                dependencies = [self.dependency_status(row) for row in self.config["dependencies"]]
                state.update(dependencies=dependencies, updated_utc=datetime.now(UTC).isoformat())
                upstream_ready = all(row["status"] == "passed" for row in dependencies)
                resources_ready = (
                    psutil.virtual_memory().available >= self.config["minimum_free_ram_gib"] * 2**30
                    and psutil.disk_usage(str(self.root)).free
                    >= self.config["minimum_free_disk_gib"] * 2**30
                )
                state["status"] = "waiting_resources" if upstream_ready else "waiting_upstream"
                A.write_json(self.report, state)
                if upstream_ready and resources_ready:
                    break
                if not follow:
                    return state
                time.sleep(self.config["poll_seconds"])
            snapshot = self.snapshot()
            frozen = self.output / "candidate-snapshot.json"
            A.write_json(frozen, snapshot)
            state["waiting_seconds"] = time.perf_counter() - started
            state["candidate_snapshot_sha256"] = A.sha256_file(frozen)
            self.execute_stage(
                "prepare",
                {
                    "candidate_queue_config": self.config["candidate_queue_config"],
                    "candidate_queue_config_sha256": self.config["candidate_queue_config_sha256"],
                    "candidate_snapshot": str(frozen),
                    "candidate_snapshot_sha256": A.sha256_file(frozen),
                    "patch_source_sha256": self.config["sources_sha256"][
                        "reproductions/unity_search_baseline/patch_targets.py"
                    ],
                    "shards": self.config["shards"],
                    "report": str(self.reports / "prepare.json"),
                    "run_ids": self.config.get("run_ids")
                    or [row["run_id"] for row in snapshot["batches"]],
                },
                state,
            )
            assembled = self.execute_stage(
                "assembly",
                {
                    "prepared_report": str(self.reports / "prepare.json"),
                    "prepared_report_sha256": A.sha256_file(self.reports / "prepare.json"),
                    "output": str(self.output / "corpus"),
                    "report": str(self.reports / "assembly.json"),
                },
                state,
            )
            corpus = str(Path(assembled["corpus"]).parent)
            self.execute_stage(
                "dataset",
                {
                    "corpora": [
                        {
                            "name": self.config["mode"],
                            "corpus": corpus,
                            "sha256": assembled["corpus_sha256"],
                        }
                    ],
                    "report": str(self.reports / "dataset.json"),
                },
                state,
            )
            self.execute_stage(
                "interface",
                {
                    "corpus": corpus,
                    "corpus_sha256": assembled["corpus_sha256"],
                    "output": str(self.output / "interface"),
                    "report": str(self.reports / "interface.json"),
                },
                state,
            )
            if A.sha256_file(Path(assembled["corpus"])) != assembled["corpus_sha256"]:
                raise ValueError("Assembled corpus changed during the native audits")
            for stage in state["stages"]:
                if A.sha256_file(Path(stage["report"])) != stage["report_sha256"]:
                    raise ValueError("An earlier stage report changed during the pipeline")
            state.update(
                status="passed" if self.config["mode"] == "complete" else "passed_smoke",
                current_stage=None,
                corpus=corpus,
                corpus_sha256=assembled["corpus_sha256"],
                execution_seconds=sum(row["stage_wall_seconds"] for row in state["stages"]),
            )
            return state
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state.update(
                wall_seconds=time.perf_counter() - started,
                updated_utc=datetime.now(UTC).isoformat(),
            )
            A.write_json(self.report, state)
