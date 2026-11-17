"""Execute the approved V3 stages serially with retained per-command job receipts."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.jobs import ReproductionJob
from reproductions.unity_search_baseline.v3_config import UnityV3Configurations


class UnityV3Suite:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.configs = UnityV3Configurations(root)
        self.public, self.private = self.configs.public, self.configs.private
        self.path = self.public / "progress.json"
        self.state: JsonDict = (
            A.read_json(self.path)
            if self.path.exists()
            else {
                "status": "running",
                "stages": {},
                "test_opened": False,
                "confirmation_execution_authorized": False,
            }
        )

    def stage(self, name: str, arguments: list[str], report: Path) -> JsonDict:
        previous = self.state["stages"].get(name)
        if previous and previous.get("status") == "passed":
            if A.sha256_file(report) != previous["report_sha256"]:
                raise ValueError(f"Completed V3 stage changed: {name}")
            return A.read_json(report)
        self.state.update(status="running", active_stage=name)
        self.state["stages"][name] = {"status": "running", "report": str(report)}
        A.write_json(self.path, self.state)
        if report.exists():
            result = A.read_json(report)
        else:
            job = self.private / "jobs" / name / "job.json"
            command = [sys.executable, "-u", *arguments]
            config = {
                "command": command,
                "scope": f"V3 serial development stage {name}; no confirmation",
            }
            if job.exists():
                if A.read_json(job)["command"] != command:
                    raise ValueError("Job identity belongs to another command")
            else:
                job.parent.mkdir(parents=True, exist_ok=False)
                A.write_json(job, config)
            receipt = ReproductionJob(self.root, job).run()
            if receipt["status"] != "passed":
                raise RuntimeError(f"V3 stage failed, retained receipt: {name}")
            result = A.read_json(report)
        if result["status"] not in {"passed", "passed_smoke", "completed"} or result.get(
            "test_opened"
        ):
            raise ValueError(f"V3 stage output did not pass: {name}")
        self.state["stages"][name] = {
            "status": "passed",
            "report": str(report),
            "report_sha256": A.sha256_file(report),
        }
        A.write_json(self.path, self.state)
        return result

    def training_pair(self, *, smoke: bool) -> dict[str, Path]:
        heads: dict[str, Path] = {}
        for mode in ["unity", "source_aligned"]:
            for stage in ["full", "head"]:
                config = self.configs.training(
                    mode=mode, stage=stage, smoke=smoke, attempt=2 if smoke else 1
                )
                settings = A.read_json(config)
                name = Path(settings["report"]).stem
                result = self.stage(
                    name,
                    ["script/train_unity_v3.py", "--stage", stage, "--config", str(config)],
                    Path(settings["report"]),
                )
                if (
                    result["training_updates"] <= 0
                    or result["checkpoint_audit"]["status"] != "passed"
                ):
                    raise ValueError("Training stage lacks actual updates and checkpoint replay")
                if stage == "head":
                    heads[mode] = Path(result["config"]["output"]) / "best.pt"
        return heads

    def run(self) -> JsonDict:
        started = time.perf_counter()
        try:
            pilot_config = self.configs.benchmark(smoke=True)
            pilot = A.read_json(pilot_config)
            self.stage(
                "benchmark-smoke8-v1",
                ["script/run_unity_v3.py", "--stage", "benchmark", "--config", str(pilot_config)],
                Path(pilot["report"]),
            )
            self.training_pair(smoke=True)
            config = self.configs.benchmark(smoke=False)
            self.stage(
                "benchmark-v2-full1000-v1",
                ["script/run_unity_v3.py", "--stage", "benchmark", "--config", str(config)],
                Path(A.read_json(config)["report"]),
            )
            heads = self.training_pair(smoke=False)
            for mode, checkpoint in heads.items():
                name = f"benchmark-trained-{mode}-full1000-v1"
                config = self.configs.benchmark(
                    smoke=False, name=name, checkpoint=checkpoint, input_modes=[mode]
                )
                self.stage(
                    name,
                    ["script/run_unity_v3.py", "--stage", "benchmark", "--config", str(config)],
                    Path(A.read_json(config)["report"]),
                )
            from reproductions.unity_search_baseline.v3_summary import UnityV3Summary

            result = UnityV3Summary(self.root).run()
            self.state.update(
                status="completed_development",
                active_stage=None,
                summary=str(self.public / "summary.json"),
                wall_seconds=time.perf_counter() - started,
                recommendation=result["recommendation"],
            )
        except BaseException as error:
            self.state.update(
                status="failed", error=repr(error), wall_seconds=time.perf_counter() - started
            )
            A.write_json(self.path, self.state)
            raise
        A.write_json(self.path, self.state)
        return self.state
