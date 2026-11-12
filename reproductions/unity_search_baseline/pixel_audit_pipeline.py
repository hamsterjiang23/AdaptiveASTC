"""Wait for native capture, then audit exact and aligned near-duplicate pixels."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import psutil

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.collection import UnityReferenceSeries as R
from reproductions.unity_search_baseline.confirmation_capture import UnityConfirmationCapture as C
from reproductions.unity_search_baseline.confirmation_series import UnityConfirmationSeries as S
from reproductions.unity_search_baseline.native_data_pipeline import UnityNativeDataPipeline as P
from reproductions.unity_search_baseline.near_duplicates import UnityNearDuplicateAudit as N
from reproductions.unity_search_baseline.pixel_identity import UnityPixelIdentityAudit as I


class UnityPixelAuditPipeline:
    """Read completed archives only; preserve all cohorts and keep model testing closed."""

    def __init__(self, root: Path, path: Path) -> None:
        self.root, self.path = root.resolve(), path.resolve()
        self.inputs: dict[str, str] = {}
        self.config = self.read(self.path)
        self.config_sha = self.inputs[str(self.path)]
        self.output = Path(self.config["output"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        public, local = self.root / "experiment report", self.root / "experiment report/.local"
        if (
            not self.output.is_relative_to(local)
            or self.output == local
            or not self.report.is_relative_to(public)
            or self.report.is_relative_to(local)
        ):
            raise ValueError("Raw audit output must be under.local and reports must be public")
        self.verify()
        self.expected = self.config["expected_counts"]
        mode = self.config["mode"]
        if mode == "confirmation_complete":
            if self.expected != {"train": 10000, "validation": 1000, "confirmation": 2000}:
                raise ValueError("Complete audit requires the frozen 10000/1000/2000 coverage")
            self.verify_smoke()
        elif mode == "development_smoke":
            if (
                set(self.expected) != {"train", "validation"}
                or any(type(n) is not int or n <= 0 for n in self.expected.values())
                or self.expected["train"] > 64
                or self.expected["validation"] > 2
                or "confirmation" in self.config
            ):
                raise ValueError("Development smoke must contain at most64/2 and no confirmation")
        else:
            raise ValueError("Unknown pixel audit pipeline mode")
        self.development = R(self.root, self.series_config("development"))
        self.confirmation = (
            S(self.root, self.series_config("confirmation"))
            if mode == "confirmation_complete"
            else None
        )
        for key, script, actions in [
            ("development", "script/collect_unity_references.py", {"collect", "assemble"}),
            ("confirmation", "script/collect_unity_confirmation_series.py", {None}),
        ]:
            if key not in self.config:
                continue
            item = self.config[key]
            command = self.read(Path(item["job"]["job_config"]), item["job"]["sha256"])["command"]
            allowed = [
                [sys.executable, "-u", script]
                + ([] if action is None else [action])
                + ["--config", str(Path(item["config"]["path"]).resolve())]
                for action in actions
            ]
            if command not in allowed:
                raise ValueError("Capture job does not execute the bound series configuration")
        self.verify_destinations()

    def verify_destinations(self) -> None:
        """Protect pending as well as completed upstream outputs before creating any file."""
        _, batches = self.development.validate()
        files = {self.development.report.resolve(), self.development.config_path.resolve()}
        directories = [self.development.output.resolve()]
        for batch in batches:
            files.update([Path(batch["path"]).resolve(), Path(batch["config"]["report"]).resolve()])
            directories.append(self.development.baseline(batch["config"]).run_dir.resolve())
        if self.confirmation is not None:
            series = self.confirmation
            files.update(
                [
                    series.report.resolve(),
                    series.path,
                    series.smoke.report,
                    series.smoke.config_path,
                ]
            )
            directories.extend([series.output, series.reports, series.smoke.baseline.run_dir])
            directories.extend(
                self.root / "experiment report/.local" / series.batch_run_id(start)
                for start, _ in series.ranges()
            )
        destinations = [
            self.output,
            self.report,
            self.stage_report("exact"),
            self.stage_report("near"),
        ]
        for destination in destinations:
            if destination in files or any(path.is_relative_to(destination) for path in files):
                raise ValueError("Pixel audit destination overlaps a protected capture file")
            if any(
                destination.is_relative_to(path) or path.is_relative_to(destination)
                for path in directories
            ):
                raise ValueError("Pixel audit destination overlaps a protected capture directory")

    @staticmethod
    def execution_sources(root: Path) -> dict[str, str]:
        extra = [
            "reproductions/unity_search_baseline/pixel_audit_pipeline.py",
            "reproductions/unity_search_baseline/pixel_identity.py",
            "script/queue_unity_pixel_audit.py",
            "script/audit_unity_pixel_identity.py",
        ]
        return (
            S.execution_sources(root)
            | N.execution_sources(root)
            | {name: A.sha256_file(root / name) for name in extra}
        )

    def read(self, path: Path, digest: str | None = None) -> JsonDict:
        path = path.resolve()
        raw = path.read_bytes()
        observed = hashlib.sha256(raw).hexdigest()
        expected = self.inputs.get(str(path), digest)
        if (expected is not None and observed != expected) or (
            digest is not None and observed != digest
        ):
            raise ValueError(f"Pixel pipeline evidence changed: {path}")
        self.inputs[str(path)] = observed
        return json.loads(raw.decode("utf-8-sig"))

    def series_config(self, key: str) -> Path:
        item = self.config[key]["config"]
        path = Path(item["path"]).resolve()
        self.read(path, item["sha256"])
        return path

    def verify_smoke(self) -> None:
        item = self.config["smoke_provenance"]
        smoke = self.read(Path(item["report"]), item["report_sha256"])
        receipt = self.read(Path(item["process_receipt"]), item["process_receipt_sha256"])
        command = receipt["command"]
        if (
            smoke["status"] != "passed"
            or smoke["mode"] != "development_smoke"
            or smoke["counts"] != {"train": 64, "validation": 2}
            or smoke["sources_sha256"] != self.config["sources_sha256"]
            or smoke["runtime"] != self.config["runtime"]
            or [stage["kind"] for stage in smoke["stages"]] != ["exact", "near"]
            or receipt["status"] != "passed"
            or receipt["process_exit_code"] != 0
            or len(command) != 5
            or command[:4]
            != [sys.executable, "-u", "script/queue_unity_pixel_audit.py", "--config"]
        ):
            raise ValueError("Full pixel audit requires the same-code native66 smoke to pass")
        smoke_config = self.read(Path(command[-1]), smoke["config_sha256"])
        if Path(smoke_config["report"]).resolve() != Path(item["report"]).resolve():
            raise ValueError("Smoke process does not bind the supplied smoke report")
        for stage in smoke["stages"]:
            self.binding(Path(stage["path"]), stage["sha256"])

    def verify(self) -> None:
        if self.execution_sources(self.root) != self.config["sources_sha256"]:
            raise ValueError("Pixel audit pipeline execution sources changed")
        if N.runtime() != self.config["runtime"]:
            raise ValueError("Pixel audit pipeline runtime changed")
        for name, digest in self.inputs.items():
            if A.sha256_file(Path(name)) != digest:
                raise ValueError(f"Pixel pipeline evidence changed: {name}")

    def stage_report(self, name: str) -> Path:
        return self.report.with_name(f"{self.report.stem}-{name}.json")

    def binding(self, path: Path, digest: str | None = None) -> JsonDict:
        self.read(path, digest)
        return {"path": str(path.resolve()), "sha256": self.inputs[str(path.resolve())]}

    def manifest(self, report: JsonDict, output: Path) -> JsonDict:
        path = (output / "manifest.json").resolve()
        if Path(report["manifest"]).resolve() != path:
            raise ValueError("Capture report points to an unexpected manifest")
        value = self.read(path, report["manifest_sha256"])
        payload = {key: item for key, item in value.items() if key != "fingerprint"}
        if value["fingerprint"] != A.fingerprint(payload):
            raise ValueError("Capture manifest fingerprint differs")
        return value

    def batch_record(
        self, run: Path, phase: str, run_id: str, split: str, options: Path, binding: JsonDict
    ) -> JsonDict:
        return {
            "run_id": run_id,
            "source_split": split,
            "reference_receipt": self.binding(
                run / f"references/normalized-{phase}/receipt.json",
                binding["reference_receipt_sha256"],
            ),
            "phase_receipt": self.binding(
                run / f"{phase}-receipt.json", binding["phase_receipt_sha256"]
            ),
            "options_receipt": self.binding(options),
        }

    @staticmethod
    def require_archive(run: Path, phase: str) -> None:
        # Existing collect() exports when its receipt is absent. Never enter that branch here.
        if not (run / f"references/normalized-{phase}/receipt.json").is_file():
            raise FileNotFoundError("Pixel audit requires an already archived reference receipt")

    def development_batches(self) -> list[JsonDict]:
        series = self.development
        source, batches = series.validate()
        report = self.read(series.report)
        expected = {key: self.expected[key] for key in ["train", "validation"]}
        if (
            report["status"] != "passed"
            or report["configuration_sha256"] != self.config["development"]["config"]["sha256"]
            or report["source_manifest_sha256"] != series.config["manifest_sha256"]
            or report["expected_counts"] != expected
            or report["counts"] != expected
            or report["coverage"] != series.config.get("coverage", "complete")
            or report["test_opened"] is not False
            or (self.confirmation is not None and report["coverage"] != "complete")
        ):
            raise ValueError("Development series is incomplete or differs from the bound plan")
        manifest = self.manifest(report, series.output)
        collected: dict[str, list[JsonDict]] = {"train": [], "validation": []}
        bindings, records = [], []
        for batch in batches:
            config = batch["config"]
            run, phase = series.baseline(config).run_dir, config["phase"]
            self.require_archive(run, phase)
            self.binding(Path(batch["path"]), batch["config_sha256"])
            rows, binding = series.verify_batch(batch)
            collected[batch["split"]].extend(rows)
            bindings.append(binding)
            options = Path(binding["options_receipt"])
            self.binding(options, binding["options_sha256"])
            self.binding(Path(config["report"]), binding["options_sha256"])
            records.append(
                self.batch_record(run, phase, config["run_id"], batch["split"], options, binding)
            )
        for split, rows in collected.items():
            by_path = {row["path"].casefold(): row for row in rows}
            collected[split] = [
                by_path[row["path"].casefold()]
                for row in source["splits"][split]
                if row["path"].casefold() in by_path
            ]
        if (
            bindings != report["batches"]
            or bindings != manifest["batch_bindings"]
            or collected != manifest["splits"]
            or {key: len(rows) for key, rows in collected.items()} != expected
        ):
            raise ValueError("Development manifest differs from re-audited native batches")
        return records

    def confirmation_batches(self) -> list[JsonDict]:
        series = self.confirmation
        if series is None:
            return []
        series.validate()
        report = self.read(series.report)
        if (
            report["status"] != "passed"
            or report["config_sha256"] != series.config_sha
            or report["source_files_sha256"] != series.config["sources_sha256"]
            or report["captured_images"] != self.expected["confirmation"]
            or report["coverage"] != "complete"
            or report["native_labels_collected"] is not True
            or report["test_opened"] is not False
            or report["model_sealed"] is not False
        ):
            raise ValueError("Confirmation series lacks complete native capture evidence")
        manifest = self.manifest(report, series.output)
        bindings, rows, records = [], [], []
        expected_ranges = [(0, 2), *series.ranges()]
        if len(report["batches"]) != len(expected_ranges):
            raise ValueError("Confirmation series batch count differs")
        for recorded, (start, count) in zip(report["batches"], expected_ranges, strict=True):
            path = Path(recorded["config"])
            self.binding(path, recorded["config_sha256"])
            capture = C(self.root, path)
            if capture.config["start"] != start or capture.config["images"] != count:
                raise ValueError("Confirmation batch range differs from reserved order")
            self.require_archive(capture.baseline.run_dir, "batch")
            captured_rows, binding = series.audit_batch(capture)
            if binding != recorded:
                raise ValueError("Confirmation batch differs from the completed series")
            original = self.read(capture.report, binding["report_sha256"])
            self.binding(
                capture.baseline.run_dir / "managed-hook/receipt.json",
                binding["managed_restoration_sha256"],
            )
            projection = self.output / "options-projections" / f"{start:05d}.json"
            A.write_json(
                projection,
                {
                    **original["options_audit"],
                    "managed_source_restoration": original["managed_source_restoration"],
                    "projection_provenance": {
                        "kind": "derived_flat_options_from_confirmation_capture_report",
                        "original_report": self.binding(capture.report),
                        "original_configuration": self.binding(path),
                    },
                },
            )
            records.append(
                self.batch_record(
                    capture.baseline.run_dir,
                    "batch",
                    capture.config["run_id"],
                    "confirmation",
                    projection,
                    binding,
                )
            )
            rows.extend(captured_rows)
            bindings.append(binding)
        if (
            manifest["status"] != "passed"
            or manifest["splits"] != {"confirmation": rows}
            or manifest["batches"] != bindings
            or manifest["reservation_manifest_sha256"]
            != series.smoke.reservation["manifest_sha256"]
            or len(rows) != self.expected["confirmation"]
        ):
            raise ValueError("Confirmation manifest differs from re-audited native batches")
        return records

    def wait(self, state: JsonDict) -> None:
        while True:
            self.verify()
            dependencies = [
                P.dependency_status(self.config[key]["job"])
                for key in ["development", "confirmation"]
                if key in self.config
            ]
            if any(item["status"] == "failed" for item in dependencies):
                raise RuntimeError("Native capture dependency failed")
            ready = all(item["status"] == "passed" for item in dependencies)
            resources = {
                "available_ram_bytes": psutil.virtual_memory().available,
                "free_disk_bytes": shutil.disk_usage(self.output).free,
            }
            resources_ready = (
                resources["available_ram_bytes"] >= 8 * 1024**3
                and resources["free_disk_bytes"] >= 5 * 1024**3
            )
            state.update(dependencies=dependencies, resources=resources)
            if ready and resources_ready:
                for item in dependencies:
                    self.binding(
                        Path(item["job"]).with_name("receipt.json"), item["receipt_sha256"]
                    )
                return
            state["status"] = "waiting_resources" if ready else "waiting_captures"
            A.write_json(self.report, state)
            time.sleep(15)

    def run(self) -> JsonDict:
        self.verify()
        if self.output.exists() or any(
            path.exists()
            for path in [self.report, self.stage_report("exact"), self.stage_report("near")]
        ):
            raise FileExistsError("Use a fresh pixel pipeline identity; retain prior evidence")
        self.output.mkdir(parents=True, exist_ok=False)
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as stream:
            stream.write("{}")
        started = time.perf_counter()
        state: JsonDict = {
            "status": "waiting_captures",
            "config_sha256": self.config_sha,
            "sources_sha256": self.config["sources_sha256"],
            "runtime": N.runtime(),
            "expected_counts": self.expected,
            "mode": self.config["mode"],
            "stages": [],
            "test_opened": False,
            "model_forward_calls": 0,
            "training_updates": 0,
            "splits_modified": False,
            "independent_test_isolation_proven": False,
            "scope": "Bound native cohorts only; exact RGBA and same-size aligned RMSE. "
            "No historical-cohort, resize/crop/semantic isolation claim or automatic removal",
        }
        try:
            self.wait(state)
            state.update(status="auditing_archives", wait_seconds=time.perf_counter() - started)
            A.write_json(self.report, state)
            stage_start = time.perf_counter()
            batches = self.development_batches() + self.confirmation_batches()
            self.verify()
            state["archive_audit_seconds"] = time.perf_counter() - stage_start
            exact_path = self.output / "exact-config.json"
            A.write_json(
                exact_path,
                {
                    "batches": batches,
                    "expected_counts": self.expected,
                    "output": str(self.output / "exact"),
                    "report": str(self.stage_report("exact")),
                },
            )
            self.binding(exact_path)
            state["status"] = "auditing_exact_pixels"
            A.write_json(self.report, state)
            exact = I(exact_path).run()
            state["stages"].append(
                {
                    "kind": "exact",
                    **self.binding(self.stage_report("exact")),
                    "wall_seconds": exact["wall_seconds"],
                }
            )
            near_path = self.output / "near-config.json"
            A.write_json(
                near_path,
                {
                    "pixel_identity_report": self.binding(self.stage_report("exact")),
                    "expected_counts": self.expected,
                    "sources_sha256": N.execution_sources(self.root),
                    "runtime": N.runtime(),
                    "rgba_rmse_8bit": 2.0,
                    "cell_grid": 8,
                    "max_candidate_pairs": 100000,
                    "output": str(self.output / "near"),
                    "report": str(self.stage_report("near")),
                },
            )
            self.binding(near_path)
            state["status"] = "auditing_near_pixels"
            A.write_json(self.report, state)
            near = N(self.root, near_path).run()
            state["stages"].append(
                {
                    "kind": "near",
                    **self.binding(self.stage_report("near")),
                    "wall_seconds": near["wall_seconds"],
                }
            )
            self.verify()
            state.update(
                status="passed",
                counts=exact["counts"],
                rgba=exact["rgba"],
                near_identity_pairs=near["near_identity_pairs"],
                cross_split_near_identity_pairs=near["cross_split_near_identity_pairs"],
                inputs_sha256=self.inputs,
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["wall_seconds"] = time.perf_counter() - started
            state["active_seconds"] = state["wall_seconds"] - state.get(
                "wait_seconds", state["wall_seconds"]
            )
            A.write_json(self.report, state)
        return state
