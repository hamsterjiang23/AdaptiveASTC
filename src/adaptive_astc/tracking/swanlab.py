"""SwanLab lifecycle, scalar metrics, and aggregate report media."""

import json
import math
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Literal

from adaptive_astc.config import JsonDict, SwanLabConfig
from adaptive_astc.utils.artifacts import ArtifactStore

if TYPE_CHECKING:
    from swanlab.sdk.internal.run import Run


class SwanLabTracker:
    """Own one stage run and persist its identity for training resume."""

    def __init__(
        self,
        config: SwanLabConfig,
        run_dir: Path,
        stage: str,
        metadata: JsonDict,
        initialization: str = "both",
        resume: bool = False,
    ) -> None:
        self.config = config
        self.run_dir = run_dir
        self.stage = stage
        self.metadata = metadata
        self.initialization = initialization
        self.resume = resume
        self.run: Run | None = None
        self.identity_path = run_dir / "tracking" / f"{stage}-{initialization}.json"
        self.identity: JsonDict = {}

    def __enter__(self) -> "SwanLabTracker":
        if self.config.mode == "disabled":
            return self
        import swanlab

        previous = None
        if self.resume and self.identity_path.exists():
            previous = ArtifactStore.read_json(self.identity_path)
            expected = {
                "project": self.config.project,
                "workspace": self.config.workspace,
                "mode": self.config.mode,
                "data_fingerprint": self.metadata.get("data_fingerprint"),
            }
            if any(previous.get(key) != value for key, value in expected.items()):
                raise ValueError("SwanLab resume identity differs from the requested experiment")
        resume_mode: Literal["must", "allow"] | None = None
        if previous is not None:
            resume_mode = "must" if self.config.mode == "online" else "allow"
        self.run = swanlab.init(
            project=self.config.project,
            workspace=self.config.workspace,
            name=self.config.name or f"{self.run_dir.name}-{self.initialization}-{self.stage}",
            mode=self.config.mode,
            log_dir=str(self.run_dir / "swanlog"),
            config=self.metadata,
            job_type=self.stage,
            tags=list(self.config.tags),
            public=False,
            id=previous["id"] if previous else None,
            resume=resume_mode,
            on_online_error="raise",
            settings=swanlab.Settings(interactive=False),
        )
        self.identity = {
            "id": self.run.id,
            "url": self.run.url if self.config.mode == "online" else None,
            "project": self.config.project,
            "workspace": self.config.workspace,
            "mode": self.config.mode,
            "stage": self.stage,
            "initialization": self.initialization,
            "data_fingerprint": self.metadata.get("data_fingerprint"),
            "state": "running",
        }
        try:
            ArtifactStore.write_json(self.identity_path, self.identity)
        except BaseException as error:
            self.run.finish(state="crashed", error=str(error))
            raise
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.run is None:
            return
        state: Literal["success", "crashed", "aborted"] = "success"
        if error is not None:
            state = "aborted" if isinstance(error, KeyboardInterrupt) else "crashed"
        try:
            self.run.finish(state=state, error=str(error) if error else None)
        except Exception as finish_error:
            self.identity.update(state="tracking_failed", error=str(finish_error))
            ArtifactStore.write_json(self.identity_path, self.identity)
            if error is None:
                raise
        else:
            self.identity["state"] = state
            ArtifactStore.write_json(self.identity_path, self.identity)

    @staticmethod
    def scalars(values: JsonDict, prefix: str = "") -> dict[str, int | float]:
        result: dict[str, int | float] = {}
        for name, value in values.items():
            key = f"{prefix}/{name}" if prefix else name
            if isinstance(value, dict):
                result.update(SwanLabTracker.scalars(value, key))
            elif isinstance(value, (int, float)) and math.isfinite(value):
                result[key] = int(value) if isinstance(value, bool) else value
        return result

    def log_metrics(self, prefix: str, values: JsonDict, step: int = 0) -> None:
        if self.run is not None:
            self.run.log(self.scalars(values, prefix), step=step)

    def log_epoch(self, record: JsonDict) -> None:
        if self.run is None:
            return
        values = {
            "train": record["train"],
            "validation": record["validation"],
            "optimization": {"learning_rate": record["lr"]},
            "resources": {
                name: record[name] for name in ("epoch_seconds", "peak_vram_mib", "rss_mib")
            },
        }
        if "micro_batch" in record:
            values["optimization"]["micro_batch"] = record["micro_batch"]
        self.log_metrics("", values, int(record["epoch"]))

    def log_payload(self, name: str, values: JsonDict, step: int = 0) -> None:
        if self.run is not None:
            import swanlab

            self.run.log({name: swanlab.Text(json.dumps(values, ensure_ascii=False))}, step=step)

    def log_report(self, report_dir: Path, step: int = 0) -> None:
        if self.run is None:
            return
        import swanlab

        images = {
            f"report/{name}": swanlab.Image(str(report_dir / f"{name}.png"))
            for name in ("training_curves", "reliability", "confusion_matrix")
            if (report_dir / f"{name}.png").is_file()
        }
        if images:
            self.run.log(images, step=step)
