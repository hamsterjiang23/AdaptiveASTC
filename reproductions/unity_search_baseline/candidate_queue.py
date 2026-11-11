"""Follow frozen reference batches and assemble complete native candidate targets."""

from __future__ import annotations

import json
import math
import os
import shutil
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psutil

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline import candidate_completion
from reproductions.unity_search_baseline.candidate_archive import UnityCandidateArchive
from reproductions.unity_search_baseline.candidate_completion import UnityCandidateCompletion
from reproductions.unity_search_baseline.collection import UnityReferenceSeries


class UnityCandidateQueue:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.config_path = root.resolve(), config_path.resolve()
        self.config = ArtifactStore.read_json(config_path)
        self.config_sha256 = ArtifactStore.sha256_file(self.config_path)
        self.output = Path(self.config["output"]).resolve()
        if not self.output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Candidate queue output must be an ignored local artifact directory")
        self.series = UnityReferenceSeries(self.root, Path(self.config["reference_plan"]))
        self.report = Path(self.config["report"])

    def validate(self) -> tuple[JsonDict, list[JsonDict]]:
        if ArtifactStore.sha256_file(self.config_path) != self.config_sha256:
            raise ValueError("Candidate queue configuration changed after loading")
        for key in ["minimum_free_ram_gib", "minimum_free_disk_gib", "poll_seconds"]:
            value = self.config[key]
            if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
                raise ValueError("Queue resource and polling limits must be finite and positive")
        if self.config["poll_seconds"] > 60:
            raise ValueError("Reference observations must remain bounded to60seconds")
        for path, digest in [
            (self.series.config_path, self.config["reference_plan_sha256"]),
            (Path(candidate_completion.__file__), self.config["completion_source_sha256"]),
            (Path(self.config["quality_build_receipt"]), self.config["quality_build_sha256"]),
        ]:
            if ArtifactStore.sha256_file(path) != digest:
                raise ValueError(
                    "Queue reference plan, completion source or native quality changed"
                )
        source, batches = self.series.validate()
        known = {batch["config"]["run_id"] for batch in batches}
        if not set(self.config.get("reuse", {})) <= known:
            raise ValueError("Reused candidate run is outside the frozen reference plan")
        return source, batches

    @contextmanager
    def lock(self) -> Iterator[None]:
        if os.name != "nt":
            raise RuntimeError("This native Unity candidate queue requires Windows")
        import msvcrt

        path = Path(self.series.config["project"]) / "Library/ASTCReproductionLocks/candidates.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError(
                    "Another candidate queue already owns this Unity project"
                ) from error
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    def reference_is_live(self) -> bool:
        receipt_path = Path(self.config["reference_job_receipt"])
        receipt = ArtifactStore.read_json(receipt_path)
        if receipt["status"] != "running":
            return False
        arguments = receipt["command"]
        plans = []
        for index, argument in enumerate(arguments):
            if argument == "--config" and index + 1 < len(arguments):
                plans.append(arguments[index + 1])
            elif argument.startswith("--config="):
                plans.append(argument.removeprefix("--config="))
        if len(plans) != 1 or (self.root / plans[0]).resolve() != self.series.config_path:
            return False
        try:
            process = psutil.Process(receipt["process_id"])
            started = datetime.fromisoformat(receipt["started_utc"]).timestamp()
            command = process.cmdline()
            return (
                process.is_running()
                and abs(process.create_time() - started) < 30
                and any(Path(argument).name == "run_reproduction_job.py" for argument in command)
            )
        except psutil.NoSuchProcess:
            return False

    def require_resources(self) -> None:
        if psutil.virtual_memory().available < self.config["minimum_free_ram_gib"] * 1024**3:
            raise RuntimeError("Insufficient free RAM for native candidate completion")
        if shutil.disk_usage(self.output).free < self.config["minimum_free_disk_gib"] * 1024**3:
            raise RuntimeError("Insufficient free output disk for native candidate completion")

    def prepare(self, batch: JsonDict, references: list[JsonDict]) -> Path:
        name = batch["config"]["run_id"]
        baseline = self.series.baseline(batch["config"])
        phase = batch["config"]["phase"]
        archive = baseline.run_dir / "references" / f"normalized-{phase}"
        options = baseline.run_dir / "options-receipt.json"
        imports_path = baseline.run_dir / f"{phase}-imports.jsonl"
        imports = [
            json.loads(line) for line in imports_path.read_text("utf-8-sig").splitlines() if line
        ]
        if len(imports) != len(references) or any(
            imported["asset"] != reference["path"]
            for imported, reference in zip(imports, references, strict=True)
        ):
            raise ValueError("Candidate metadata must match the verified reference order")
        config = {
            "capture": str(archive),
            "capture_run": str(baseline.run_dir),
            "capture_phase": phase,
            "capture_receipt_sha256": ArtifactStore.sha256_file(archive / "receipt.json"),
            "options_receipt": str(options),
            "options_receipt_sha256": ArtifactStore.sha256_file(options),
            "imports_sha256": ArtifactStore.sha256_file(
                baseline.run_dir / f"{phase}-imports.jsonl"
            ),
            "completion_source_sha256": self.config["completion_source_sha256"],
            "encoder_dll": str(
                baseline.project / "Assets/Editor/Astc/Plugins/astcenc-avx2-shared.dll"
            ),
            "encoder_dll_sha256": self.series.config["encoder_dlls"]["astcenc-avx2-shared.dll"],
            "quality_build_receipt": self.config["quality_build_receipt"],
            "output": str(self.output / "batches" / name),
            "report": str(self.output / "reports" / f"{name}.json"),
            "scope": (
                "Imported development references; all20candidate targets; "
                "original search choices preserved; cost separate"
            ),
            "items": [
                {
                    "index": index,
                    "path": row["path"],
                    "need_alpha": row["actual_options"]["need_alpha"],
                    "is_hdr": row["actual_options"]["profile"] not in {0, 1},
                    "is_normal": row["actual_options"]["texture_type_importer"] == "NormalMap",
                    "mip_count": (
                        UnityCandidateCompletion.normal_metric_mips(imports[index])
                        if row["actual_options"]["texture_type_importer"] == "NormalMap"
                        else 1
                    ),
                    "metadata_source": (
                        "Verified frozen reference series and actual callback; normal metric mip "
                        "depth inferred from captured Tex2D mipmaps and dimensions"
                    ),
                }
                for index, row in enumerate(references)
            ],
        }
        return self.prepare_attempt(name, config)

    def prepare_attempt(self, name: str, config: JsonDict) -> Path:
        prior: list[JsonDict] = []
        while True:
            identity = name if not prior else f"{name}-retry{len(prior):03d}"
            output = self.output / "batches" / identity
            report = self.output / "reports" / f"{identity}.json"
            attempt = {**config, "output": str(output), "report": str(report)}
            if prior:
                attempt["prior_attempts"] = list(prior)
            path = self.output / "configs" / f"{identity}.json"
            if path.exists() and ArtifactStore.read_json(path) != attempt:
                raise ValueError("A previously prepared candidate batch configuration changed")
            if not path.exists():
                ArtifactStore.write_json(path, attempt)
            if report.exists() or not output.exists() or not any(output.iterdir()):
                return path
            # The project lock excludes another queue; a prior partial attempt stays immutable.
            receipt = output / "receipt.json"
            observed = ArtifactStore.read_json(receipt) if receipt.exists() else {}
            prior.append(
                {
                    "config": str(path),
                    "config_sha256": ArtifactStore.sha256_file(path),
                    "receipt": str(receipt) if receipt.exists() else None,
                    "receipt_sha256": ArtifactStore.sha256_file(receipt)
                    if receipt.exists()
                    else None,
                    "status": observed.get("status", "incomplete_without_receipt"),
                    "wall_seconds": observed.get("wall_seconds"),
                    "error": observed.get("error"),
                }
            )

    def candidate_config(self, batch: JsonDict, references: list[JsonDict]) -> Path:
        name = batch["config"]["run_id"]
        reuse = self.config.get("reuse", {}).get(name)
        if reuse is None:
            return self.prepare(batch, references)
        path = Path(reuse["config"])
        if ArtifactStore.sha256_file(path) != reuse["config_sha256"]:
            raise ValueError("Reused candidate config changed")
        config = ArtifactStore.read_json(path)
        if ArtifactStore.sha256_file(Path(config["report"])) != reuse["report_sha256"]:
            raise ValueError("Reused candidate summary changed")
        return path

    def verify_capture_binding(self, batch: JsonDict, config: JsonDict) -> None:
        baseline = self.series.baseline(batch["config"])
        phase = batch["config"]["phase"]
        archive = baseline.run_dir / "references" / f"normalized-{phase}"
        reuse = self.config.get("reuse", {}).get(batch["config"]["run_id"], {})
        producer = reuse.get("completion_source_sha256", self.config["completion_source_sha256"])
        if (
            Path(config["capture"]).resolve() != archive.resolve()
            or Path(config["capture_run"]).resolve() != baseline.run_dir.resolve()
            or config["capture_phase"] != phase
            or Path(config["options_receipt"]).resolve()
            != (baseline.run_dir / "options-receipt.json").resolve()
            or config["completion_source_sha256"] != producer
            or Path(config["quality_build_receipt"]).resolve()
            != Path(self.config["quality_build_receipt"]).resolve()
        ):
            raise ValueError("Candidate capture or implementation differs from its frozen batch")

    def run(self, *, follow: bool = False) -> JsonDict:
        source, batches = self.validate()
        with self.lock():
            self.output.mkdir(parents=True, exist_ok=True)
            frozen = self.output / "queue-config.json"
            if frozen.exists() and ArtifactStore.read_json(frozen) != self.config:
                raise ValueError("Resume requires the identical candidate queue configuration")
            if not frozen.exists():
                ArtifactStore.write_json(frozen, self.config)
            invocation = self.output / "invocations" / uuid.uuid4().hex / "receipt.json"
            state = {
                "status": "running",
                "started_utc": datetime.now(UTC).isoformat(),
                "config_sha256": ArtifactStore.sha256_file(self.config_path),
                "implementation_sha256": ArtifactStore.sha256_file(Path(__file__)),
                "archive_verifier_sha256": ArtifactStore.sha256_file(
                    Path(__file__).with_name("candidate_archive.py")
                ),
                "expected_counts": self.series.config["expected_counts"],
                "coverage": self.series.config.get("coverage", "complete"),
                "counts": {"train": 0, "validation": 0},
                "batches": [],
                "test_opened": False,
                "invocation_receipt": str(invocation),
                "scope": (
                    "native20 candidate targets paired to original imported references "
                    "and search choices"
                ),
            }
            rows: dict[str, list[JsonDict]] = {"train": [], "validation": []}
            done: set[str] = set()
            started = time.perf_counter()

            def save() -> None:
                state["updated_utc"] = datetime.now(UTC).isoformat()
                state["wall_seconds"] = time.perf_counter() - started
                ArtifactStore.write_json(invocation, state)
                ArtifactStore.write_json(self.report, state)

            try:
                while len(done) < len(batches):
                    published = None
                    if follow and self.series.report.exists():
                        published = ArtifactStore.read_json(self.series.report)
                        if (
                            published["configuration_sha256"]
                            != self.config["reference_plan_sha256"]
                        ):
                            raise ValueError("Reference progress belongs to another frozen plan")
                    progress = False
                    for batch in batches:
                        name = batch["config"]["run_id"]
                        options = (
                            self.series.baseline(batch["config"]).run_dir / "options-receipt.json"
                        )
                        if name in done or not options.exists():
                            continue
                        if follow:
                            published_runs = (
                                {row["run_id"] for row in published["batches"]}
                                if published is not None
                                else set()
                            )
                            if name not in published_runs:
                                continue
                        if ArtifactStore.read_json(options)["status"] != "passed":
                            raise ValueError(
                                f"Reference capture failed or remains incomplete: {name}"
                            )
                        self.validate()
                        self.require_resources()
                        state.update(status="running", current_batch=name)
                        save()
                        references, reference_binding = self.series.verify_batch(batch)
                        path = self.candidate_config(batch, references)
                        candidate_config = ArtifactStore.read_json(path)
                        self.verify_capture_binding(batch, candidate_config)
                        report = Path(candidate_config["report"])
                        source_receipt = ArtifactStore.read_json(
                            Path(candidate_config["capture"]) / "receipt.json"
                        )
                        UnityCandidateCompletion.verify_capture_provenance(
                            candidate_config, source_receipt
                        )
                        UnityCandidateCompletion.verify_actual_options(
                            candidate_config, source_receipt
                        )
                        if not report.exists():
                            UnityCandidateCompletion(path).run()
                        assembled, summary = UnityCandidateArchive.verify(report, references, path)
                        rows[batch["split"]].extend(assembled)
                        state["batches"].append(
                            {
                                "run_id": name,
                                "source_split": batch["split"],
                                "reference": reference_binding,
                                "prior_attempts": candidate_config.get("prior_attempts", []),
                                "completion_source_sha256": candidate_config[
                                    "completion_source_sha256"
                                ],
                                **summary,
                            }
                        )
                        done.add(name)
                        state["counts"][batch["split"]] += len(assembled)
                        progress = True
                        save()
                    if len(done) == len(batches):
                        break
                    if not follow:
                        state.update(status="waiting_references", current_batch=None)
                        save()
                        return state
                    if not self.reference_is_live():
                        # The collector can publish its final batch after our snapshot and exit.
                        latest = (
                            ArtifactStore.read_json(self.series.report)
                            if self.series.report.exists()
                            else None
                        )
                        if latest != published:
                            continue
                        if progress:
                            continue
                        raise RuntimeError(
                            "Reference job stopped before complete candidate coverage"
                        )
                    state.update(status="waiting_references", current_batch=None)
                    save()
                    time.sleep(self.config["poll_seconds"])
                if state["counts"] != state["expected_counts"]:
                    raise ValueError("Candidate corpus does not cover the frozen source counts")
                for split in rows:
                    order = {
                        row["path"]: index for index, row in enumerate(source["splits"][split])
                    }
                    rows[split].sort(key=lambda row: order[row["path"]])
                manifest = {
                    "status": "passed",
                    "coverage": state["coverage"],
                    "splits": rows,
                    "counts": state["counts"],
                    "reference_plan_sha256": self.config["reference_plan_sha256"],
                    "candidate_grid": "12/10/8/6 x fastest/fast/medium/thorough/exhaustive",
                    "original_search_labels_preserved": True,
                    "test_opened": False,
                }
                manifest_path = self.output / "manifest.json"
                ArtifactStore.write_json(manifest_path, manifest)
                state.update(
                    status="passed",
                    current_batch=None,
                    manifest=str(manifest_path),
                    manifest_sha256=ArtifactStore.sha256_file(manifest_path),
                )
                save()
                return state
            except BaseException as error:
                state.update(status="failed", error=repr(error))
                save()
                raise
