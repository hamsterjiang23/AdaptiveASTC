"""Prepare and execute paired Unity search timing runs."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import shutil
import statistics
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

import psutil


class UnitySearchBaseline:
    def __init__(
        self,
        root: Path,
        project: Path,
        editor: Path,
        manifest: Path,
        *,
        run_id: str = "unity-search-baseline-lite-rdo-off",
    ) -> None:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be one directory name")
        self.root = root.resolve()
        self.project = project.resolve()
        self.editor = editor.resolve()
        self.manifest = manifest.resolve()
        self.run_dir = self.root / "experiment report/.local" / run_id

    def prepare(self) -> dict[str, object]:
        document = json.loads(self.manifest.read_text(encoding="utf-8"))
        records = document["splits"]["train"]
        if len(records) != 10_000:
            raise ValueError(f"Expected 10000 training images, got {len(records)}")
        buckets: dict[tuple[str, int, bool], list[dict[str, object]]] = defaultdict(list)
        for row in records:
            asset = Path(str(row["path"]))
            if asset.is_absolute() or ".." in asset.parts or asset.parts[0] != "Assets":
                raise ValueError(f"Unsafe asset path: {asset}")
            source = self.project / asset
            if not source.is_file() or not Path(str(source) + ".meta").is_file():
                raise FileNotFoundError(source)
            size_bin = max(int(row["width"]), int(row["height"])).bit_length()
            key = str(row["blockSize"]), size_bin, bool(row["alpha_nonopaque"])
            buckets[key].append(row)
        rng = random.Random(20261109)
        for group in buckets.values():
            rng.shuffle(group)
        selected: list[dict[str, object]] = []
        while len(selected) < 64:
            for key in sorted(buckets):
                if buckets[key] and len(selected) < 64:
                    selected.append(buckets[key].pop())
        self.run_dir.mkdir(parents=True, exist_ok=True)
        identity = {
            "manifest": str(self.manifest),
            "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "data_fingerprint": document["fingerprint"],
            "project": str(self.project),
            "editor": str(self.editor),
            "train_count": len(records),
            "smoke_count": len(selected),
            "seed": 20261109,
            "quality": {
                "psnr": 30,
                "ms_ssim_db": 21,
                "normal_mean": 3.2,
                "normal_p95": 9,
                "rdo": False,
            },
            "hardware": {
                "processor": platform.processor(),
                "logical_cpus": psutil.cpu_count(),
                "physical_cpus": psutil.cpu_count(logical=False),
                "memory_bytes": psutil.virtual_memory().total,
            },
            "encoder_dlls": {
                name: hashlib.sha256(
                    (self.project / "Assets/Editor/Astc/Plugins" / name).read_bytes()
                ).hexdigest()
                for name in ["astcenc-avx2-shared.dll", "astcenc-avx2-static.dll"]
            },
        }
        self._write_frozen(self.run_dir / "identity.json", identity)
        for phase in ["probe", "smoke1", "smoke2", "smoke3", "full"]:
            rows = records if phase == "full" else selected[:2] if phase == "probe" else selected
            config = {
                "assets": [{"path": row["path"]} for row in rows],
                "warmup": [{"path": row["path"]} for row in selected[:2]],
                "output": str(self.run_dir / f"{phase}-imports.jsonl"),
                "backupDirectory": str(self.run_dir / f"{phase}-meta-backups"),
                "cacheDirectory": f"ASTC_Cache/benchmark/{self.run_dir.name}/{phase}",
                "runId": phase,
            }
            self._write_frozen(self.run_dir / f"{phase}-config.json", config)
        lock = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                self.run_dir / "identity.json",
                *sorted(self.run_dir.glob("*-config.json")),
            ]
        }
        self._write_frozen(self.run_dir / "protocol-lock.json", lock)
        return identity

    @staticmethod
    def _write(path: Path, document: object) -> None:
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _write_frozen(path: Path, document: object) -> None:
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != document:
                raise FileExistsError(f"Frozen protocol differs: {path}")
            return
        UnitySearchBaseline._write(path, document)

    def verify_protocol(self) -> str:
        lock_path = self.run_dir / "protocol-lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        required_files = {
            "identity.json",
            *(path.name for path in self.run_dir.glob("*-config.json")),
        }
        if set(lock) != required_files:
            raise ValueError("Protocol lock does not cover the complete prepared configuration set")
        for name, expected in lock.items():
            if hashlib.sha256((self.run_dir / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Frozen protocol changed: {name}")
        identity = json.loads((self.run_dir / "identity.json").read_text(encoding="utf-8"))
        if (
            identity["project"] != str(self.project)
            or identity["editor"] != str(self.editor)
            or identity["manifest"] != str(self.manifest)
            or identity["manifest_sha256"] != hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        ):
            raise ValueError("Current paths or manifest differ from the prepared protocol")
        for name, expected in identity["encoder_dlls"].items():
            actual = self.project / "Assets/Editor/Astc/Plugins" / name
            if hashlib.sha256(actual.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Encoder DLL changed: {name}")
        return hashlib.sha256(lock_path.read_bytes()).hexdigest()

    def audit(self, phase: str) -> dict[str, object]:
        """Validate the actual source hashes and quality policy written by the native search."""
        protocol_hash = self.verify_protocol()
        config = json.loads((self.run_dir / f"{phase}-config.json").read_text(encoding="utf-8"))
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        known = {
            self._asset_key(row["path"]): row["fileHash"] for row in manifest["splits"]["train"]
        }
        expected = {self._asset_key(row["path"]) for row in config["assets"]}
        assembly = self.run_dir / f"{phase}-assembly.json"
        cache_path = self.project / config["cacheDirectory"] / "parameter_cache_detail.jsonl"
        if assembly.exists():
            bundle = json.loads(assembly.read_text(encoding="utf-8"))
            if bundle["protocol_sha256"] != protocol_hash:
                raise ValueError("Recovery assembly belongs to another frozen protocol")
            for item in bundle["inputs"]:
                if hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError(f"Recovery input changed: {item['path']}")
            for name, expected_hash in bundle["outputs"].items():
                if Path(name).name != name:
                    raise ValueError("Recovery output must be a file within the run directory")
                if hashlib.sha256((self.run_dir / name).read_bytes()).hexdigest() != expected_hash:
                    raise ValueError(f"Recovered output changed: {name}")
            cache_path = self.run_dir / f"{phase}-parameters.jsonl"
        cache = self.read_parameter_cache(cache_path)
        policies = [
            row["tableConfig"] for row in cache if row.get("_kind") == "astc_cache_table_config"
        ]
        required = {
            "schemaVersion": 2,
            "astcOptimizerEnabled": True,
            "targetPsnrDb": 30.0,
            "targetMsSsimDb": 21.0,
            "targetNormalMeanDeg": 3.2,
            "targetNormalP95Deg": 9.0,
            "blackPixelRatioMild": 0.4,
            "blackElevatedPsnrMildDb": 35.0,
            "blackPixelRatioStrong": 0.8,
            "blackElevatedPsnrStrongDb": 37.0,
            "sizeFirstMinSideLarge": 512,
            "rdoRefineMarginDb": 0.0,
            "rdoGlobalEnabled": False,
            "rdoQualityScalar": 0.5,
            "rdoLookback": 256,
        }
        if len(policies) != 1 or policies[0] != required:
            raise ValueError("Native cache policy differs from the frozen LITE/RDO-off policy")
        records = [row for row in cache if "filePath" in row]
        if (
            len(records) != len(expected)
            or {self._asset_key(x["filePath"]) for x in records} != expected
        ):
            raise ValueError("Native parameter-cache coverage differs from the phase input list")
        selected = {
            self._asset_key(row["asset"]): (row["block_size"], row["preset"])
            for row in self._read_lines(self.run_dir / f"{phase}-native.jsonl")
        }
        for row in records:
            asset = self._asset_key(row["filePath"])
            if (
                row["fileHash"].lower() != known.get(asset, "").lower()
                or row.get("rdo") is not False
            ):
                raise ValueError(f"Source hash or RDO mismatch: {row['filePath']}")
            if selected.get(asset) != (row["blockSize"], row["qualityLevel"]):
                raise ValueError(f"Cached choice differs from native selection: {row['filePath']}")
        launch = json.loads((self.run_dir / f"{phase}-launch.json").read_text(encoding="utf-8"))
        editor_hash = hashlib.sha256(self.editor.read_bytes()).hexdigest()
        if editor_hash != launch["editor_sha256"]:
            raise ValueError("Measured Editor differs from the current instrumented Editor")
        return {
            "protocol_sha256": protocol_hash,
            "editor_sha256": editor_hash,
            "source_hashes_verified": len(records),
            "native_policy_verified": True,
            "assembly_sha256": hashlib.sha256(assembly.read_bytes()).hexdigest()
            if assembly.exists()
            else None,
        }

    def run(self, phase: str, no_upm: bool = False) -> dict[str, object]:
        protocol_hash = self.verify_protocol()
        self.require_project_closed()
        if phase == "full":
            for trial in ["smoke1", "smoke2", "smoke3"]:
                receipt = json.loads(
                    (self.run_dir / f"{trial}-receipt.json").read_text(encoding="utf-8")
                )
                if receipt["status"] != "passed":
                    raise RuntimeError(f"Smoke gate failed: {trial}")
                if receipt.get("provenance", {}).get("protocol_sha256") != protocol_hash:
                    raise RuntimeError(f"Smoke receipt belongs to another protocol: {trial}")
                self.audit(trial)
        config_path = self.run_dir / f"{phase}-config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        editor_bytes = self.editor.read_bytes()
        if b"ASTC_BENCHMARK_LOG" not in editor_bytes:
            raise RuntimeError("The selected Editor lacks native benchmark instrumentation")
        if (self.project / config["cacheDirectory"]).exists():
            raise FileExistsError(
                "This phase has already created its cache. Use a new run identity."
            )
        installed_dir = self.project / "Assets/Editor/ASTCReproductionBenchmarkRunner"
        installed_dir.mkdir(parents=True, exist_ok=True)
        for name in ["BenchmarkRunner.cs", "ASTCSearchBaseline.asmdef"]:
            template = Path(__file__).with_name(name)
            installed = installed_dir / name
            if installed.exists() and installed.read_bytes() != template.read_bytes():
                raise FileExistsError(installed)
            if not installed.exists():
                shutil.copyfile(template, installed)
        environment = os.environ.copy()
        # UPM 4.5 joins this Windows variable while loading its global configuration.
        environment.setdefault("ALLUSERSPROFILE", environment.get("PROGRAMDATA", "C:\\ProgramData"))
        environment["ASTC_BENCHMARK_CONFIG"] = str(config_path)
        environment["ASTC_BENCHMARK_LOG"] = str(self.run_dir / f"{phase}-native.jsonl")
        command = [
            str(self.editor),
            "-batchmode",
            "-disable-cache-server",
            "-projectPath",
            str(self.project),
            "-buildTarget",
            "Android",
            "-executeMethod",
            "ASTCReproduction.BenchmarkRunner.Run",
            "-logFile",
            str(self.run_dir / f"{phase}-editor.log"),
        ]
        if no_upm:
            command.append("-noUpm")
        launch_path = self.run_dir / f"{phase}-launch.json"
        launch = {
            "command": command,
            "editor_sha256": hashlib.sha256(editor_bytes).hexdigest(),
            "started_unix": time.time(),
            "protocol_sha256": protocol_hash,
            "runner_sha256": hashlib.sha256(
                Path(__file__).with_name("BenchmarkRunner.cs").read_bytes()
            ).hexdigest(),
        }
        self._write(launch_path, launch)
        started = time.perf_counter()
        exit_code: int | None = None
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(command, cwd=self.project, env=environment)
            try:
                launch["pid"] = process.pid
                launch["process_create_time"] = psutil.Process(process.pid).create_time()
                self._write(launch_path, launch)
                exit_code = process.wait()
            finally:
                if process.poll() is None:
                    # Stop our own Editor before restoring files it may still be writing.
                    process.terminate()
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        finally:
            if process is not None and process.poll() is None:
                raise RuntimeError(
                    "Editor is still running. Defer metadata recovery until it exits."
                )
            conflicts = self.restore_metadata(Path(config["backupDirectory"]))
            try:
                summary = self.summarize(phase)
            except (OSError, ValueError, KeyError, TypeError) as error:
                summary = {"status": "failed", "phase": phase, "errors": [str(error)]}
            try:
                summary["provenance"] = self.audit(phase)
            except (OSError, ValueError, KeyError, TypeError) as error:
                summary["status"] = "failed"
                errors = cast(list[str], summary["errors"])
                errors.append(str(error))
            summary["metadata_restore_conflicts"] = conflicts
            summary["process_exit_code"] = exit_code
            summary["process_wall_seconds"] = time.perf_counter() - started
            if exit_code != 0 or conflicts:
                summary["status"] = "failed"
            self._write(self.run_dir / f"{phase}-receipt.json", summary)
        return summary

    def restore_metadata(self, backup_dir: Path) -> list[str]:
        self.require_project_closed()
        conflicts: list[str] = []
        if not backup_dir.exists():
            return conflicts
        index: dict[str, str] = {}
        index_path = backup_dir / "index.jsonl"
        journal = index_path.read_bytes() if index_path.exists() else b""
        for line_number, line in enumerate(journal.splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                conflicts.append(f"index.jsonl: incomplete or invalid entry {line_number}")
                break
            name = str(row["backup"])
            relative_name = str(row["asset"]) + ".meta"
            if Path(name).name != name or index.get(name, relative_name) != relative_name:
                raise ValueError("Invalid or ambiguous metadata backup index")
            index[name] = relative_name
        for backup in backup_dir.rglob("*.meta"):
            relative = backup.relative_to(backup_dir)
            if backup.parent == backup_dir:
                if backup.name not in index:
                    conflicts.append(backup.name)
                    continue
                relative = Path(index[backup.name])
            target = (self.project / relative).resolve()
            if not target.is_relative_to(self.project / "Assets"):
                raise ValueError(f"Metadata restore escaped Assets: {target}")
            expected_path = Path(str(backup) + ".expected.sha256")
            if not expected_path.is_file():
                expected_path = self.metadata_recovery_hash_path(backup_dir, relative)
            if not target.is_file():
                conflicts.append(str(relative))
                continue
            original = backup.read_bytes()
            current = target.read_bytes()
            if current == original:
                continue
            if not expected_path.is_file():
                conflicts.append(str(relative))
                continue
            expected = expected_path.read_text(encoding="utf-8-sig").strip()
            if current != original and hashlib.sha256(current).hexdigest() != expected:
                conflicts.append(str(relative))
                continue
            target.write_bytes(original)
        return conflicts

    @staticmethod
    def metadata_recovery_hash_path(backup_dir: Path, relative: Path) -> Path:
        digest = hashlib.sha256(relative.as_posix().casefold().encode("utf-8")).hexdigest()
        return backup_dir / "recovery-hashes" / f"{digest}.sha256"

    def require_project_closed(self) -> None:
        for process in psutil.process_iter(["name", "cmdline"]):
            if str(process.info["name"]).casefold() != "unity.exe":
                continue
            command = process.info["cmdline"]
            if command is None:
                raise RuntimeError("Cannot identify a live Unity process before metadata recovery")
            paths = {argument.replace("\\", "/").rstrip("/").casefold() for argument in command}
            if self.project.as_posix().casefold() in paths:
                raise RuntimeError(f"The benchmark project is open in Unity PID {process.pid}")

    def summarize(self, phase: str) -> dict[str, object]:
        config = json.loads((self.run_dir / f"{phase}-config.json").read_text(encoding="utf-8"))
        imports = self._read_lines(self.run_dir / f"{phase}-imports.jsonl")
        native = self._read_lines(self.run_dir / f"{phase}-native.jsonl")
        # Unity can canonicalize path casing on this Windows project.
        expected = {self._asset_key(row["path"]) for row in config["assets"]}
        measured: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in native:
            measured[self._asset_key(row["asset"])].append(row)
        errors: list[str] = []
        if (
            len(expected) != len(config["assets"])
            or len(imports) != len(expected)
            or {self._asset_key(row["asset"]) for row in imports} != expected
        ):
            errors.append("Import coverage does not match the frozen asset list")
        if set(measured) != expected:
            errors.append("Native coverage does not match the frozen asset list")
        for row in imports:
            asset = str(row["asset"])
            entries = measured.get(self._asset_key(asset), [])
            if not row["success"] or len(entries) != 1:
                errors.append(f"Missing/failed/ambiguous native search: {asset}")
                continue
            entry = entries[0]
            if (
                entry["cache_hit"]
                or not entry["search_executed"]
                or int(entry["candidates_attempted"]) < 1
                or not entry["success"]
                or int(entry["candidates_measured"]) < 1
            ):
                errors.append(f"Search was bypassed: {asset}")
            if not 0 < float(entry["search_ms"]) <= float(entry["select_and_encode_ms"]):
                errors.append(f"Invalid timer nesting: {asset}")
        timings: dict[str, object] = {}
        for key in ["search_ms", "select_and_encode_ms", "candidates_attempted", "import_wall_ms"]:
            source_rows = imports if key == "import_wall_ms" else native
            values = [
                float(row[key]) for row in source_rows if self._asset_key(row["asset"]) in expected
            ]
            if values:
                ordered = sorted(values)
                timings[key] = {
                    "sum": sum(values),
                    "mean": statistics.mean(values),
                    "median": statistics.median(values),
                    "p95": ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)],
                    "max": max(values),
                }
        return {
            "status": "passed" if not errors else "failed",
            "phase": phase,
            "expected": len(expected),
            "imports": len(imports),
            "native_records": len(native),
            "timings": timings,
            "errors": errors,
        }

    @staticmethod
    def _asset_key(path: str) -> str:
        return path.replace("\\", "/").casefold()

    @staticmethod
    def read_parameter_cache(log_path: Path) -> list[dict[str, Any]]:
        """Replay the native compacted snapshot followed by its append-only journal."""
        snapshot_path = log_path.with_suffix(".json")
        policy = None
        entries: dict[str, dict[str, Any]] = {}
        if snapshot_path.exists():
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
            policy = snapshot["tableConfig"]
            for asset, row in snapshot["entries"].items():
                entries[UnitySearchBaseline._asset_key(asset)] = dict(row, filePath=asset)
        journal = UnitySearchBaseline._read_lines(log_path)
        if journal:
            headers = [row["tableConfig"] for row in journal if "tableConfig" in row]
            if len(headers) != 1 or (policy is not None and policy != headers[0]):
                raise ValueError("Snapshot and append log have incompatible native cache policies")
            policy = headers[0]
            for row in journal:
                if "filePath" in row:
                    entries[UnitySearchBaseline._asset_key(row["filePath"])] = row
        if policy is None:
            raise ValueError("Native parameter cache has no quality-policy header")
        return [{"_kind": "astc_cache_table_config", "tableConfig": policy}, *entries.values()]

    @staticmethod
    def _read_lines(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
