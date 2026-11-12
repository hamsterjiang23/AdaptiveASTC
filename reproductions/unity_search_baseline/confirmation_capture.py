"""Collect reserved confirmation pixels/labels with a separate, non-training identity."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

import psutil
from Crypto.Hash import MD4

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.common.unity_reference import UnityReferenceCapture
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.collection import UnityReferenceSeries
from reproductions.unity_search_baseline.confirmation import UnityConfirmationCohort
from reproductions.unity_search_baseline.metadata import ManagedCaptureHook, UnityOptionCapture
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P


class ConfirmationSearchBaseline(UnitySearchBaseline):
    """Explicit confirmation contract; the development constructor stays unchanged."""

    def __init__(self, capture: UnityConfirmationCapture) -> None:
        self.capture = capture
        self.root = capture.root
        self.project = Path(capture.environment["project"]).resolve()
        self.editor = Path(capture.environment["editor"]).resolve()
        self.run_dir = self.root / "experiment report/.local" / capture.config["run_id"]
        self.manifest = self.run_dir / "confirmation-manifest.json"
        self.capture_references = True
        self.source_split = "confirmation"
        self.capture_paths = [row["path"] for row in capture.rows]

    def prepare(self) -> dict[str, object]:
        self.capture.verify_bindings()
        self.capture.verify_environment()
        self.capture.verify_assets()
        self.run_dir.mkdir(parents=True, exist_ok=False)
        manifest = {
            "splits": {"confirmation": self.capture.rows},
            "reservation_manifest_sha256": self.capture.reservation["manifest_sha256"],
            "scope": "Original reserved source identities; not training or validation",
        }
        manifest["fingerprint"] = A.fingerprint(manifest)
        A.write_json(self.manifest, manifest)
        identity = {
            "manifest": str(self.manifest),
            "manifest_sha256": A.sha256_file(self.manifest),
            "data_fingerprint": manifest["fingerprint"],
            "project": str(self.project),
            "editor": str(self.editor),
            "encoder_dlls": self.capture.environment["encoder_dlls"],
            "source_split": self.source_split,
            "capture_paths": self.capture_paths,
            "capture_kind": "confirmation_reference_batch",
            "selected_count": len(self.capture.rows),
            "reservation_manifest_sha256": self.capture.reservation["manifest_sha256"],
            "capture_config_sha256": self.capture.config_sha,
        }
        self._write_frozen(self.run_dir / "identity.json", identity)
        config = {
            "assets": [{"path": row["path"]} for row in self.capture.rows],
            "warmup": [{"path": row["path"]} for row in self.capture.rows[:2]],
            "output": str(self.run_dir / "batch-imports.jsonl"),
            "backupDirectory": str(self.run_dir / "batch-meta-backups"),
            "cacheDirectory": f"ASTC_Cache/benchmark/{self.run_dir.name}/batch",
            "runId": "batch",
            "captureReferences": True,
        }
        self._write_frozen(self.run_dir / "batch-config.json", config)
        self._write_frozen(
            self.run_dir / "protocol-lock.json",
            {
                name: A.sha256_file(self.run_dir / name)
                for name in ["identity.json", "batch-config.json"]
            },
        )
        return identity

    def verify_protocol(self) -> str:
        self.capture.verify_bindings()
        self.capture.verify_environment()
        digest = super().verify_protocol()
        manifest = A.read_json(self.manifest)
        if manifest["splits"] != {"confirmation": self.capture.rows}:
            raise ValueError("Confirmation membership differs from the reserved primary slice")
        return digest

    def run(self, phase: str, no_upm: bool = False) -> dict[str, object]:
        if phase != "batch":
            raise ValueError("Confirmation collection only supports explicit batches")
        return super().run(phase, no_upm=no_upm)


class UnityConfirmationCapture:
    """Wait for frozen development jobs, then capture a reserved slice without prediction."""

    def __init__(self, root: Path, config: Path) -> None:
        self.root = root.resolve()
        self.config_path = config.resolve()
        self.config_sha = A.sha256_file(self.config_path)
        self.config = A.read_json(self.config_path)
        self.verify_bindings()
        self.environment = A.read_json(Path(self.config["development_series"]["path"]))
        self.reservation = A.read_json(Path(self.config["reservation_report"]["path"]))
        reservation_config = A.read_json(Path(self.config["reservation_config"]["path"]))
        manifest_path = Path(self.reservation["manifest"])
        if A.sha256_file(manifest_path) != self.reservation["manifest_sha256"]:
            raise ValueError("Confirmation reservation manifest changed")
        manifest = A.read_json(manifest_path)
        fingerprint = manifest.pop("fingerprint")
        if fingerprint != A.fingerprint(manifest) or manifest["status"] != "reserved":
            raise ValueError("Confirmation reservation is incomplete or has changed")
        if (
            self.reservation["status"] != "reserved"
            or self.reservation["config_sha256"] != self.config["reservation_config"]["sha256"]
        ):
            raise ValueError("Reservation report is not bound to its source configuration")
        if (
            Path(reservation_config["image_root"]).resolve()
            != Path(self.environment["project"]).resolve()
        ):
            raise ValueError("Confirmation and development capture use different Unity projects")
        start, count = self.config["start"], self.config["images"]
        if type(start) is not int or type(count) is not int or start < 0 or not 1 <= count <= 256:
            raise ValueError("Confirmation requires a primary slice of 1..256 images")
        self.rows = manifest["primary"][start : start + count]
        if len(self.rows) != count:
            raise ValueError("Confirmation slice exceeds the primary cohort")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.config["run_id"]):
            raise ValueError("Confirmation run ID must be a safe directory name")
        self.report = Path(self.config["report"]).resolve()
        if not self.report.is_relative_to(
            self.root / "experiment report"
        ) or self.report.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Confirmation report must be under public experiment report")
        if not self.config["dependencies"]:
            raise ValueError("Confirmation requires bound development dependencies")
        for key in ["minimum_free_ram_gib", "minimum_free_disk_gib"]:
            value = self.config[key]
            if type(value) not in {int, float} or not 0 < value < float("inf"):
                raise ValueError("Confirmation resource limits must be finite and positive")
        if count > 2 and not self.config.get("smoke_report"):
            raise ValueError("Larger confirmation batches require a completed two-image smoke")
        self.baseline = ConfirmationSearchBaseline(self)

    def verify_bindings(self) -> None:
        if A.sha256_file(self.config_path) != self.config_sha:
            raise ValueError("Confirmation capture configuration changed")
        for key in ["reservation_report", "reservation_config", "development_series"]:
            record = self.config[key]
            if A.sha256_file(Path(record["path"])) != record["sha256"]:
                raise ValueError(f"Confirmation binding changed: {key}")
        reserved = A.read_json(Path(self.config["reservation_report"]["path"]))
        if A.sha256_file(Path(reserved["manifest"])) != reserved["manifest_sha256"]:
            raise ValueError("Confirmation reservation manifest changed")
        for name, digest in self.config["sources_sha256"].items():
            if A.sha256_file(self.root / name) != digest:
                raise ValueError(f"Confirmation execution source changed: {name}")
        if self.config["sources_sha256"] != self.execution_sources(self.root):
            raise ValueError("Confirmation execution sources are incomplete")

    def verify_environment(self) -> None:
        UnityReferenceSeries(
            self.root, Path(self.config["development_series"]["path"])
        ).verify_environment()

    def verify_assets(self) -> None:
        for row in self.rows:
            path = (
                Path(self.environment["project"]) / UnityConfirmationCohort.asset_path(row["path"])
            ).resolve()
            if not path.is_relative_to(Path(self.environment["project"]).resolve() / "Assets"):
                raise ValueError("Confirmation asset escapes the project")
            content = path.read_bytes()
            if (
                MD4.new(content).hexdigest() != row["fileHash"]
                or A.sha256_file(path) != row["source_sha256"]
            ):
                raise ValueError("Reserved confirmation source changed")
            if A.sha256_file(Path(str(path) + ".meta")) != row["meta_sha256"]:
                raise ValueError("Reserved confirmation import settings changed")

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        files = [
            "reproductions/unity_search_baseline/confirmation_capture.py",
            "reproductions/unity_search_baseline/confirmation.py",
            "reproductions/unity_search_baseline/benchmark.py",
            "reproductions/unity_search_baseline/metadata.py",
            "reproductions/unity_search_baseline/supplement.py",
            "reproductions/unity_search_baseline/collection.py",
            "reproductions/unity_search_baseline/native_data_pipeline.py",
            "reproductions/unity_search_baseline/BenchmarkRunner.cs",
            "reproductions/unity_search_baseline/ASTCSearchBaseline.asmdef",
            "reproductions/unity_search_baseline/native/capture_options.cs.txt",
            "reproductions/common/unity_reference.py",
            "reproductions/common/encoder.py",
            "reproductions/common/jobs.py",
            "src/adaptive_astc/utils/artifacts.py",
            "script/capture_unity_confirmation.py",
        ]
        return {name: A.sha256_file(root / name) for name in files}

    def validate(self) -> JsonDict:
        self.verify_bindings()
        self.verify_environment()
        self.verify_assets()
        if self.config.get("smoke_report"):
            binding = self.config["smoke_report"]
            path = Path(binding["path"])
            if A.sha256_file(path) != binding["sha256"]:
                raise ValueError("Confirmation smoke report changed")
            smoke = A.read_json(path)
            if (
                smoke["status"] != "passed"
                or smoke["images"] != 2
                or smoke["reservation_manifest_sha256"] != self.reservation["manifest_sha256"]
            ):
                raise ValueError("Confirmation smoke did not pass for this reserved cohort")
            if (
                not {
                    "configuration_path",
                    "config_sha256",
                    "options_audit",
                    "managed_source_restoration",
                    "native_labels_collected",
                }
                <= smoke.keys()
                or smoke["native_labels_collected"] is not True
            ):
                raise ValueError("Confirmation smoke lacks complete native evidence")
            prior = UnityConfirmationCapture(self.root, Path(smoke["configuration_path"]))
            if (
                prior.config_sha != smoke["config_sha256"]
                or len(prior.rows) != 2
                or prior.config.get("smoke_report") is not None
                or prior.config["sources_sha256"] != self.config["sources_sha256"]
                or prior.environment != self.environment
            ):
                raise ValueError("Confirmation smoke execution contract differs")
            phase = A.read_json(prior.baseline.run_dir / "batch-receipt.json")
            restored = A.read_json(prior.baseline.run_dir / "managed-hook/receipt.json")
            if (
                phase["status"] != "passed"
                or phase["process_exit_code"] != 0
                or phase["metadata_restore_conflicts"]
                or restored != smoke["managed_source_restoration"]
                or restored["status"] != "restored"
                or restored["original_sha256"] != restored["restored_sha256"]
            ):
                raise ValueError("Confirmation smoke native execution or recovery is incomplete")
            reference_receipt = prior.baseline.run_dir / "references/normalized-batch/receipt.json"
            if not reference_receipt.is_file():
                raise ValueError("Confirmation smoke reference archive is missing")
            captured = UnityReferenceCapture(prior.baseline).collect("batch")
            actual = UnityOptionCapture.audit(prior.baseline, "batch", captured)
            if actual != smoke["options_audit"]:
                raise ValueError("Confirmation smoke callback audit changed")
        return {
            "status": "validated",
            "images": len(self.rows),
            "source_split": "confirmation",
            "test_opened": False,
        }

    def run(self) -> JsonDict:
        self.validate()
        if self.baseline.run_dir.exists():
            raise FileExistsError("Use a new confirmation capture identity")
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        started = time.perf_counter()
        state: JsonDict = {
            "status": "waiting_dependencies",
            "images": len(self.rows),
            "source_split": "confirmation",
            "test_opened": False,
            "training_updates": 0,
            "native_labels_collected": False,
            "config_sha256": self.config_sha,
            "configuration_path": str(self.config_path),
            "source_files_sha256": self.config["sources_sha256"],
            "reservation_manifest_sha256": self.reservation["manifest_sha256"],
            "scope": "Reserved primary pixels and original search labels only; no model evaluation",
        }
        hook = ManagedCaptureHook(self.baseline.run_dir / "managed-hook")
        previous = os.environ.get("ASTC_TRAINING_CAPTURE_OPTIONS")
        try:
            while True:
                self.verify_bindings()
                dependencies = [P.dependency_status(row) for row in self.config["dependencies"]]
                state["dependencies"] = dependencies
                A.write_json(self.report, state)
                if any(row["status"] == "failed" for row in dependencies):
                    raise RuntimeError(
                        "Confirmation dependency failed; keep original capture results"
                    )
                if all(row["status"] == "passed" for row in dependencies):
                    break
                time.sleep(15)
            state["dependency_wait_seconds"] = time.perf_counter() - started
            series = UnityReferenceSeries(
                self.root, Path(self.config["development_series"]["path"])
            )
            with series.project_lock():
                self.baseline.require_project_closed()
                if (
                    psutil.virtual_memory().available
                    < self.config["minimum_free_ram_gib"] * 1024**3
                ):
                    raise RuntimeError("Insufficient RAM for confirmation Editor")
                for path in [self.root, self.baseline.project]:
                    if (
                        shutil.disk_usage(path).free
                        < self.config["minimum_free_disk_gib"] * 1024**3
                    ):
                        raise RuntimeError("Insufficient disk for confirmation capture")
                self.validate()
                self.baseline.prepare()
                try:
                    hook.install(self.baseline.project / "Assets/Editor/Astc/astccustom.cs")
                    os.environ["ASTC_TRAINING_CAPTURE_OPTIONS"] = str(
                        self.baseline.run_dir / "batch-options.jsonl"
                    )
                    state["status"] = "collecting"
                    A.write_json(self.report, state)
                    result = self.baseline.run("batch")
                    if result["status"] != "passed":
                        raise RuntimeError(
                            "Confirmation native capture failed; retain original receipts"
                        )
                    captured = UnityReferenceCapture(self.baseline).collect("batch")
                    state["options_audit"] = UnityOptionCapture.audit(
                        self.baseline, "batch", captured
                    )
                finally:
                    if (hook.folder / "receipt.json").exists():
                        self.baseline.require_project_closed()
                        state["managed_source_restoration"] = hook.restore()
                self.verify_assets()
                self.verify_bindings()
                state.update(
                    status="passed",
                    native_labels_collected=True,
                    run_directory=str(self.baseline.run_dir),
                )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            if previous is None:
                os.environ.pop("ASTC_TRAINING_CAPTURE_OPTIONS", None)
            else:
                os.environ["ASTC_TRAINING_CAPTURE_OPTIONS"] = previous
            state["wall_seconds"] = time.perf_counter() - started
            A.write_json(self.report, state)
        return state
