"""Run native batch smoke, then start formal CUDA training only from complete audited data."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import psutil

from adaptive_astc.config import JsonDict
from adaptive_astc.training.unity_quality_trainer import UnityQualityTrainer, UnityTrainConfig
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.jobs import ReproductionJob
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


class UnityTrainingQueue:
    """A fixed two-stage training handoff; no model selection on the independent test."""

    EXTRA_SOURCES = (
        "src/adaptive_astc/training/unity_quality_trainer.py",
        "src/adaptive_astc/training/unity_quality_loss.py",
        "src/adaptive_astc/data/unity_image_bags.py",
        "src/adaptive_astc/models/unity_quality.py",
        "src/adaptive_astc/utils/runtime.py",
        "reproductions/common/jobs.py",
        "reproductions/unity_search_baseline/training_queue.py",
        "script/train_unity_quality.py",
        "script/queue_unity_training.py",
    )

    @classmethod
    def execution_sources(cls, root: Path) -> dict[str, str]:
        return {name: A.sha256_file(root / name) for name in (*P.SOURCE_FILES, *cls.EXTRA_SOURCES)}

    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.path = root.resolve(), config_path.resolve()
        self.config = A.read_json(self.path)
        self.config_sha = A.sha256_file(self.path)
        self.output = Path(self.config["output"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        self.reports = Path(self.config["reports"]).resolve()
        if (
            not self.output.is_relative_to(self.root / "experiment report/.local")
            or not self.reports.is_relative_to(self.root / "experiment report")
            or not self.report.is_relative_to(self.root / "experiment report")
            or self.report.is_relative_to(self.output)
            or self.report.is_relative_to(self.reports)
            or self.output.is_relative_to(self.reports)
            or self.reports.is_relative_to(self.output)
        ):
            raise ValueError("Use separate local training and public report paths")
        if (
            not isinstance(self.config["cuda_dependencies"], list)
            or not self.config["cuda_dependencies"]
        ):
            raise ValueError("Bound CUDA dependencies are required")
        recipe = self.config["recipe"]
        forbidden = {"corpus", "corpus_sha256", "output", "report", "smoke", "train_image_indices"}
        if forbidden.intersection(recipe):
            raise ValueError("Recipe cannot override data identity or formal training scope")
        formal = UnityTrainConfig(
            self.output, "pending", self.output / "formal", self.reports / "formal.json", **recipe
        )
        formal.validate()
        self.verify_bindings()
        smoke = UnityQualityTrainer(Path(self.config["smoke_config"]), self.root).config
        if (
            not smoke.smoke
            or smoke.epochs != 2
            or len(smoke.train_image_indices) < 2 * formal.image_batch_size
            or smoke.output != self.output / "smoke"
            or smoke.report != self.reports / "smoke.json"
        ):
            raise ValueError("Require a separate two-epoch smoke with two full training batches")
        for key in asdict(formal):
            if key not in forbidden | {"epochs", "patience"} and getattr(formal, key) != getattr(
                smoke, key
            ):
                raise ValueError(f"Smoke does not exercise the formal recipe: {key}")
        dependency = self.config["data_dependency"]
        if A.sha256_file(Path(dependency["job_config"])) != dependency["sha256"]:
            raise ValueError("Data dependency job identity changed")
        command = A.read_json(Path(dependency["job_config"]))["command"]
        if (
            not isinstance(command, list)
            or len(command) < 2
            or command[-2] != "--config"
            or Path(command[-1]).resolve() != Path(self.config["pipeline_config"]).resolve()
        ):
            raise ValueError("Data dependency must execute the bound native pipeline configuration")

    def verify_bindings(self) -> None:
        if A.sha256_file(self.path) != self.config_sha or self.config[
            "sources_sha256"
        ] != self.execution_sources(self.root):
            raise ValueError("Training queue configuration or sources changed")
        for key in ["smoke_config", "pipeline_config"]:
            if A.sha256_file(Path(self.config[key])) != self.config[f"{key}_sha256"]:
                raise ValueError(f"Training queue {key} changed")
        P(self.root, Path(self.config["pipeline_config"])).verify_bindings()

    @staticmethod
    def resources() -> JsonDict:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "-i",
                "0",
                "--query-gpu=memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        free, utilization = (float(item.strip()) for item in completed.stdout.strip().split(","))
        ram = psutil.virtual_memory().available
        return {
            "free_ram_bytes": ram,
            "free_vram_mib": free,
            "gpu_utilization_percent": utilization,
            "ready": ram >= 12 * 1024**3 and free >= 6 * 1024 and utilization <= 20,
        }

    def wait(self, dependencies: list[JsonDict], state: JsonDict, stage: str, *, gpu: bool) -> None:
        started = time.perf_counter()
        while True:
            self.verify_bindings()
            observed = [P.dependency_status(row) for row in dependencies]
            passed = all(row["status"] == "passed" for row in observed)
            resources = self.resources() if passed and gpu else {"ready": True}
            state.update(status=f"waiting_{stage}", dependencies=observed, resources=resources)
            A.write_json(self.report, state)
            if passed and resources["ready"]:
                state.setdefault("wait_seconds", {})[stage] = time.perf_counter() - started
                return
            time.sleep(30)

    def complete_corpus(self) -> tuple[Path, str]:
        pipeline_config = A.read_json(Path(self.config["pipeline_config"]))
        result = A.read_json(Path(pipeline_config["report"]))
        if (
            result["status"] != "passed"
            or result["mode"] != "complete"
            or result["config_sha256"] != self.config["pipeline_config_sha256"]
            or result["expected_counts"] != {"train": 10000, "validation": 1000}
            or result["test_opened"]
            or result["training_updates"] != 0
            or [row["name"] for row in result["stages"]]
            != ["prepare", "assembly", "dataset", "interface"]
        ):
            raise ValueError("Formal training requires all four completed native data stages")
        for row in result["stages"]:
            if A.sha256_file(Path(row["report"])) != row["report_sha256"]:
                raise ValueError("Native data stage report changed")
            evidence = A.read_json(Path(row["report"]))
            if (
                evidence["status"] != "passed"
                or evidence["test_opened"]
                or evidence["training_updates"] != 0
            ):
                raise ValueError("Native stage did not pass development verification")
            expected = {"train": 10000, "validation": 1000}
            if row["name"] in {"prepare", "assembly", "dataset"}:
                counts = (
                    evidence["unique_images"] if row["name"] == "dataset" else evidence["counts"]
                )
                if counts != expected:
                    raise ValueError("Native stage has incomplete development coverage")
            if row["name"] in {"prepare", "assembly"} and evidence["coverage"] != "complete":
                raise ValueError("Native stage coverage is partial")
            if row["name"] == "interface" and any(
                evidence["results"][split]["exact_targets"]["count"] != count
                or evidence["results"][split]["exact_targets"]["accuracy"] != 1.0
                or evidence["results"][split]["exact_targets"]["full_choice_accuracy"] != 1.0
                for split, count in expected.items()
            ):
                raise ValueError("Native exact-target interface differs from original policy")
        corpus, digest = Path(result["corpus"]), result["corpus_sha256"]
        if corpus.resolve() != (Path(pipeline_config["output"]) / "corpus").resolve():
            raise ValueError("Native corpus is outside the bound pipeline output")
        if A.sha256_file(corpus / "corpus.json") != digest:
            raise ValueError("Native completed corpus changed")
        document = A.read_json(corpus / "corpus.json")
        config = UnityTrainConfig(
            corpus,
            digest,
            self.output / "formal",
            self.reports / "formal.json",
            **self.config["recipe"],
        )
        UnityQualityTrainer.validate_coverage(document, config)
        if document["test_opened"] or document["status"] != "passed":
            raise ValueError("Native corpus is not a passed development corpus")
        if {name: len(rows) for name, rows in document["splits"].items()} != document["counts"]:
            raise ValueError("Native corpus row counts differ from declared coverage")
        return corpus, digest

    def train(self, name: str, config_path: Path, state: JsonDict) -> JsonDict:
        self.verify_bindings()
        config = A.read_json(config_path)
        config_sha = A.sha256_file(config_path)
        job = self.output / f"{name}-job" / "job.json"
        if job.exists():
            raise FileExistsError("Use a fresh training stage identity")
        A.write_json(
            job,
            {
                "scope": f"Native {name} CUDA training, including process startup",
                "command": [
                    sys.executable,
                    "-u",
                    "script/train_unity_quality.py",
                    "--config",
                    str(config_path),
                ],
            },
        )
        state.update(
            status=f"training_{name}", current_job=str(job), current_config_sha256=config_sha
        )
        A.write_json(self.report, state)
        receipt = ReproductionJob(self.root, job).run()
        if receipt["status"] != "passed" or receipt["process_exit_code"] != 0:
            raise RuntimeError(
                f"Native {name} training process failed; retain logs and use a fresh retry"
            )
        self.verify_bindings()
        if A.sha256_file(config_path) != config_sha:
            raise ValueError("Native training stage configuration changed")
        result = A.read_json(Path(config["report"]))
        if (
            result["status"] != ("passed_smoke" if name == "smoke" else "completed")
            or result["test_opened"]
            or result["training_updates"] <= 0
            or result["checkpoint_audit"]["status"] != "passed"
        ):
            raise ValueError("Native training did not pass updates and checkpoint reload")
        expected = result["best_artifacts_sha256"]
        audit = result["checkpoint_audit"]
        if (
            set(expected) != {"best.pt", "best-validation.npz", "best-decisions.json"}
            or audit["selected_artifacts_sha256"] != expected
            or audit["checkpoint_sha256"] != expected["best.pt"]
            or result["checkpoint_sha256"] != expected["best.pt"]
            or audit["test_opened"]
        ):
            raise ValueError("Native reload audit does not bind all selected artifacts")
        for key, value in config.items():
            if result["config"][key] != value:
                raise ValueError("Native training result differs from its bound configuration")
        for filename, digest in result["best_artifacts_sha256"].items():
            if A.sha256_file(Path(config["output"]) / filename) != digest:
                raise ValueError("Native selected checkpoint artifacts changed")
        stage = {
            "name": name,
            "report": config["report"],
            "report_sha256": A.sha256_file(Path(config["report"])),
            "job": str(job),
            "job_receipt_sha256": A.sha256_file(job.parent / "receipt.json"),
            "process_seconds": receipt["wall_seconds"],
            "training_updates": result["training_updates"],
            "checkpoint_sha256": result["checkpoint_sha256"],
            "validation_metrics": result["checkpoint_audit"]["metrics"],
        }
        state["stages"].append(stage)
        A.write_json(self.report, state)
        return result

    def run(self) -> JsonDict:
        if self.report.exists() or self.reports.exists():
            raise FileExistsError("Use a new queue identity; preserve prior training attempts")
        self.output.mkdir(parents=True, exist_ok=False)
        self.reports.mkdir(parents=True, exist_ok=False)
        state: JsonDict = {
            "status": "waiting_cuda",
            "stages": [],
            "test_opened": False,
            "config_sha256": self.config_sha,
            "goal_complete": False,
        }
        initial = self.output / "initial.json"
        A.write_json(initial, state)
        self.report.parent.mkdir(parents=True, exist_ok=True)
        os.link(initial, self.report)
        initial.unlink()
        started = time.perf_counter()
        try:
            self.wait(self.config["cuda_dependencies"], state, "cuda", gpu=True)
            self.train("smoke", Path(self.config["smoke_config"]), state)
            self.wait([self.config["data_dependency"]], state, "data", gpu=True)
            corpus, digest = self.complete_corpus()
            values = asdict(
                UnityTrainConfig(
                    corpus,
                    digest,
                    self.output / "formal",
                    self.reports / "formal.json",
                    **self.config["recipe"],
                )
            )
            values = {
                key: str(value) if isinstance(value, Path) else value
                for key, value in values.items()
            }
            path = self.reports / "formal-config.json"
            if path.exists():
                raise FileExistsError("Formal config cannot be replaced")
            A.write_json(path, values)
            state.update(corpus=str(corpus), corpus_sha256=digest)
            self.train("formal", path, state)
            if self.complete_corpus() != (corpus, digest):
                raise ValueError("Native corpus binding changed during formal training")
            state.update(
                status="passed",
                scope=(
                    "Completed development training; "
                    "independent test and 90% goal still require acceptance"
                ),
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(self.report, state)
        return state
