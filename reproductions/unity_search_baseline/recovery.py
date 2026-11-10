"""Recover failed imports while preserving every original measurement and process outcome."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline


class BaselineRecovery:
    def __init__(self, baseline: UnitySearchBaseline) -> None:
        self.baseline = baseline
        self.repair = UnitySearchBaseline(
            baseline.root,
            baseline.project,
            baseline.editor,
            baseline.manifest,
            run_id=baseline.run_dir.name + "-repair",
        )

    @staticmethod
    def _override_metadata(original: str) -> str:
        """Reconstruct only the four Android settings written by ImportOne."""
        if "    buildTarget: Android\n" not in original:
            platforms = re.search(
                r"^  platformSettings:\n(?:  - [^\n]*\n|    [^\n]*\n)*", original, re.MULTILINE
            )
            if platforms is None:
                raise ValueError(
                    "No platform settings available to reconstruct the Android override"
                )
            defaults = re.search(
                r"^  - serializedVersion: 3\n    buildTarget: DefaultTexturePlatform\n"
                r"(?:    [^\n]*\n)*",
                platforms[0],
                re.MULTILINE,
            )
            if defaults is None:
                raise ValueError("Cannot reconstruct this version of the default platform settings")
            android_settings = defaults[0].replace(
                "buildTarget: DefaultTexturePlatform", "buildTarget: Android", 1
            )
            android_settings = BaselineRecovery._override_metadata(android_settings)
            return original[: platforms.end()] + android_settings + original[platforms.end() :]
        android = False
        lines = []
        values = {
            "textureFormat": "51",
            "overridden": "1",
            "textureCompression": "1",
            "crunchedCompression": "0",
        }
        for line in original.splitlines(keepends=True):
            if line.strip() == "buildTarget: Android":
                android = True
            elif android and line.strip() and not line.startswith("    "):
                android = False
            if android:
                for key, value in values.items():
                    if line.startswith(f"    {key}: "):
                        line = f"    {key}: {value}\n"
            lines.append(line)
        return "".join(lines)

    def _recover_interrupted_metadata(self, failed: list[dict[str, Any]]) -> None:
        config = json.loads(
            (self.baseline.run_dir / "full-config.json").read_text(encoding="utf-8")
        )
        backup_dir = Path(config["backupDirectory"])
        evidence_path = self.baseline.run_dir / "metadata-recovery-evidence.json"
        evidence = (
            json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else []
        )
        reviewed_path = self.baseline.run_dir / "reviewed-metadata-overrides.json"
        reviewed = (
            json.loads(reviewed_path.read_text(encoding="utf-8")) if reviewed_path.exists() else {}
        )
        if reviewed:
            launch = json.loads(
                (self.baseline.run_dir / "full-launch.json").read_text(encoding="utf-8")
            )
            if (
                reviewed.get("_protocol_sha256") != self.baseline.verify_protocol()
                or reviewed.get("_editor_sha256") != launch["editor_sha256"]
            ):
                raise ValueError("Reviewed metadata changes belong to another baseline identity")
        for row in failed:
            relative = Path(row["asset"] + ".meta")
            backup = backup_dir / relative
            target = (self.baseline.project / relative).resolve()
            if not target.is_relative_to(self.baseline.project / "Assets"):
                raise ValueError("Metadata recovery escaped project Assets")
            if not backup.exists() or backup.read_bytes() == target.read_bytes():
                continue
            original = backup.read_text(encoding="utf-8-sig")
            current = target.read_bytes()
            try:
                expected_override = self._override_metadata(original)
            except ValueError:
                expected_override = None
            verification = "reconstructed_android_override"
            if current.decode("utf-8-sig").replace("\r\n", "\n") != expected_override:
                checked = reviewed.get(row["asset"], {})
                if (
                    checked.get("original_sha256") != self._sha(backup)
                    or checked.get("override_sha256") != hashlib.sha256(current).hexdigest()
                ):
                    raise ValueError(
                        f"Metadata includes changes beyond the benchmark override: {relative}"
                    )
                verification = "reviewed_exact_importer_migration"
            expected = self.baseline.metadata_recovery_hash_path(backup_dir, relative)
            expected.parent.mkdir(parents=True, exist_ok=True)
            expected.write_text(hashlib.sha256(current).hexdigest(), encoding="utf-8")
            evidence.append(
                {
                    "asset": row["asset"],
                    "original_sha256": self._sha(backup),
                    "override_sha256": hashlib.sha256(current).hexdigest(),
                    "verification": verification,
                }
            )
        self.baseline._write(evidence_path, evidence)
        conflicts = self.baseline.restore_metadata(backup_dir)
        if conflicts:
            raise ValueError(f"Metadata recovery conflicts remain: {conflicts}")

    def run(self) -> dict[str, object]:
        self.baseline.require_project_closed()
        self.baseline.verify_protocol()
        primary = self.baseline.run_dir
        receipt = json.loads((primary / "full-receipt.json").read_text(encoding="utf-8"))
        imports = self.baseline._read_lines(primary / "full-imports.jsonl")
        if len(imports) != receipt.get("expected", 10_000) or len(imports) != 10_000:
            raise ValueError("Complete the original 10000-image attempt before targeted recovery")
        failed = [row for row in imports if not row["success"]]
        if not failed:
            raise ValueError("No failed import records to recover")
        self._recover_interrupted_metadata(failed)
        self.repair.run_dir.mkdir(parents=True, exist_ok=True)
        self.repair._write_frozen(
            self.repair.run_dir / "identity.json",
            json.loads((primary / "identity.json").read_text(encoding="utf-8")),
        )
        original = json.loads((primary / "full-config.json").read_text(encoding="utf-8"))
        config = {
            "assets": [{"path": row["asset"]} for row in failed],
            "warmup": original["warmup"],
            "runId": "repair",
            "output": str(self.repair.run_dir / "repair-imports.jsonl"),
            "backupDirectory": str(self.repair.run_dir / "repair-meta-backups"),
            "cacheDirectory": f"ASTC_Cache/benchmark/{self.repair.run_dir.name}/repair",
        }
        self.repair._write_frozen(self.repair.run_dir / "repair-config.json", config)
        self.repair._write_frozen(
            self.repair.run_dir / "protocol-lock.json",
            {
                path.name: self._sha(path)
                for path in [
                    self.repair.run_dir / "identity.json",
                    self.repair.run_dir / "repair-config.json",
                ]
            },
        )
        installed = (
            self.baseline.project
            / "Assets/Editor/ASTCReproductionBenchmarkRunner/BenchmarkRunner.cs"
        )
        launch = json.loads((primary / "full-launch.json").read_text(encoding="utf-8"))
        template = Path(__file__).with_name("BenchmarkRunner.cs")
        if self._sha(installed) != self._sha(template):
            if self._sha(installed) != launch["runner_sha256"]:
                raise ValueError("Installed runner changed outside this benchmark")
            (self.repair.run_dir / "previous-BenchmarkRunner.cs").write_bytes(
                installed.read_bytes()
            )
            installed.write_bytes(template.read_bytes())
        (self.repair.run_dir / "BenchmarkRunner.cs").write_bytes(installed.read_bytes())
        prior_receipt = self.repair.run_dir / "repair-receipt.json"
        if prior_receipt.exists():
            prior = json.loads(prior_receipt.read_text(encoding="utf-8"))
            if prior["status"] == "passed":
                return self.assemble()
            if (self.repair.project / config["cacheDirectory"]).exists():
                raise ValueError(
                    "Recovery created a measurement cache. Preserve it before another trial."
                )
            attempts = self.repair.run_dir / "attempts"
            attempts.mkdir(exist_ok=True)
            archive = attempts / f"startup-{len(list(attempts.iterdir())) + 1}"
            archive.mkdir()
            for path in self.repair.run_dir.glob("repair-*"):
                if path.name == "repair-config.json" or path.is_dir():
                    continue
                path.replace(archive / path.name)
        result = self.repair.run("repair")
        if result["status"] != "passed":
            return result
        return self.assemble()

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def assemble(self) -> dict[str, object]:
        self.baseline.require_project_closed()
        protocol = self.baseline.verify_protocol()
        self.repair.audit("repair")
        repaired_receipt = json.loads(
            (self.repair.run_dir / "repair-receipt.json").read_text(encoding="utf-8")
        )
        if repaired_receipt["status"] != "passed" or repaired_receipt["process_exit_code"] != 0:
            raise ValueError("The targeted recovery attempt must pass before assembly")
        archive = self.baseline.run_dir / "attempts/full-initial-cohort"
        complete_path = archive / "complete.json"
        if not complete_path.exists():
            archive.mkdir(parents=True, exist_ok=True)
            sources = {}
            for suffix in ["imports.jsonl", "native.jsonl", "receipt.json", "launch.json"]:
                sources[f"full-{suffix}"] = self.baseline.run_dir / f"full-{suffix}"
            config = json.loads(
                (self.baseline.run_dir / "full-config.json").read_text(encoding="utf-8")
            )
            sources["full-parameters.jsonl"] = (
                self.baseline.project / config["cacheDirectory"] / "parameter_cache_detail.jsonl"
            )
            hashes = {}
            for name, source in sources.items():
                temporary = archive / (name + ".tmp")
                shutil.copyfile(source, temporary)
                expected = self._sha(source)
                if self._sha(temporary) != expected:
                    raise ValueError(f"Original measurement changed while archiving: {name}")
                temporary.replace(archive / name)
                hashes[name] = expected
            temporary_complete = complete_path.with_suffix(".tmp")
            self.baseline._write(temporary_complete, hashes)
            temporary_complete.replace(complete_path)
        for name, expected in json.loads(complete_path.read_text(encoding="utf-8")).items():
            if self._sha(archive / name) != expected:
                raise ValueError(f"Archived original measurement changed: {name}")
        config = json.loads(
            (self.baseline.run_dir / "full-config.json").read_text(encoding="utf-8")
        )
        snapshot = self.baseline.project / config["cacheDirectory"] / "parameter_cache_detail.json"
        if snapshot.exists() and not (archive / "full-parameters.json").exists():
            temporary_snapshot = archive / "full-parameters.json.tmp"
            shutil.copyfile(snapshot, temporary_snapshot)
            if self._sha(temporary_snapshot) != self._sha(snapshot):
                raise ValueError("Native snapshot changed while archiving")
            temporary_snapshot.replace(archive / "full-parameters.json")
            hashes = json.loads(complete_path.read_text(encoding="utf-8"))
            hashes["full-parameters.json"] = self._sha(archive / "full-parameters.json")
            temporary_complete = complete_path.with_suffix(".tmp")
            self.baseline._write(temporary_complete, hashes)
            temporary_complete.replace(complete_path)
        original = json.loads((archive / "full-receipt.json").read_text(encoding="utf-8"))
        primary_rows = self.baseline._read_lines(archive / "full-imports.jsonl")
        failed = {
            self.baseline._asset_key(row["asset"]) for row in primary_rows if not row["success"]
        }
        retry_rows = self.baseline._read_lines(self.repair.run_dir / "repair-imports.jsonl")
        if {self.baseline._asset_key(row["asset"]) for row in retry_rows} != failed:
            raise ValueError("Recovery rows differ from the original failed asset set")
        records = {self.baseline._asset_key(row["asset"]): row for row in primary_rows}
        records.update({self.baseline._asset_key(row["asset"]): row for row in retry_rows})
        native_rows = [
            row
            for row in self.baseline._read_lines(archive / "full-native.jsonl")
            if self.baseline._asset_key(row["asset"]) not in failed
        ]
        native_rows += self.baseline._read_lines(self.repair.run_dir / "repair-native.jsonl")
        retry_config = json.loads(
            (self.repair.run_dir / "repair-config.json").read_text(encoding="utf-8")
        )
        retry_parameters = (
            self.repair.project / retry_config["cacheDirectory"] / "parameter_cache_detail.jsonl"
        )
        parameters = self.baseline.read_parameter_cache(archive / "full-parameters.jsonl")
        extra = self.baseline.read_parameter_cache(retry_parameters)
        policy = [row for row in parameters if "tableConfig" in row]
        if len(policy) != 1 or policy != [row for row in extra if "tableConfig" in row]:
            raise ValueError("Original and recovery native quality policies differ")
        merged_parameters = policy + [
            row
            for row in parameters
            if "filePath" in row and self.baseline._asset_key(row["filePath"]) not in failed
        ]
        merged_parameters += [row for row in extra if "filePath" in row]
        stage = self.baseline.run_dir / "assembled"
        stage.mkdir(exist_ok=True)
        for path in [
            *self.baseline.run_dir.glob("*-config.json"),
            self.baseline.run_dir / "identity.json",
            self.baseline.run_dir / "protocol-lock.json",
            self.baseline.run_dir / "full-launch.json",
        ]:
            shutil.copyfile(path, stage / path.name)
        for name, rows in [
            ("full-imports.jsonl", list(records.values())),
            ("full-native.jsonl", native_rows),
            ("full-parameters.jsonl", merged_parameters),
        ]:
            (stage / name).write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )
        inputs = [
            *sorted(archive.glob("full-*")),
            complete_path,
            *sorted(self.baseline.run_dir.glob("*-config.json")),
            self.baseline.run_dir / "identity.json",
            self.baseline.run_dir / "protocol-lock.json",
            self.repair.run_dir / "repair-imports.jsonl",
            self.repair.run_dir / "repair-native.jsonl",
            self.repair.run_dir / "repair-receipt.json",
            self.repair.run_dir / "repair-launch.json",
            self.repair.run_dir / "repair-config.json",
            self.repair.run_dir / "protocol-lock.json",
            self.repair.run_dir / "identity.json",
            self.repair.run_dir / "BenchmarkRunner.cs",
            retry_parameters,
        ]
        inputs.extend(
            path
            for path in [
                self.baseline.run_dir / "metadata-recovery-evidence.json",
                self.baseline.run_dir / "reviewed-metadata-overrides.json",
            ]
            if path.is_file()
        )
        bundle = {
            "protocol_sha256": protocol,
            "inputs": [{"path": str(path.resolve()), "sha256": self._sha(path)} for path in inputs],
            "outputs": {
                name: self._sha(stage / name)
                for name in ["full-imports.jsonl", "full-native.jsonl", "full-parameters.jsonl"]
            },
        }
        self.baseline._write(stage / "full-assembly.json", bundle)
        validator = UnitySearchBaseline(
            self.baseline.root, self.baseline.project, self.baseline.editor, self.baseline.manifest
        )
        validator.run_dir = stage
        summary = validator.summarize("full")
        provenance = validator.audit("full")
        if summary["status"] != "passed":
            raise ValueError(
                f"Recovered measurements failed coverage validation: {summary['errors']}"
            )
        config = json.loads(
            (self.baseline.run_dir / "full-config.json").read_text(encoding="utf-8")
        )
        conflicts = self.baseline.restore_metadata(Path(config["backupDirectory"]))
        conflicts += self.repair.restore_metadata(Path(retry_config["backupDirectory"]))
        if conflicts:
            raise ValueError(f"Unresolved metadata conflicts: {conflicts}")
        for name in [
            "full-imports.jsonl",
            "full-native.jsonl",
            "full-parameters.jsonl",
            "full-assembly.json",
        ]:
            (stage / name).replace(self.baseline.run_dir / name)
        summary.update(
            {
                "status": "passed_with_retries",
                "provenance": provenance,
                "metadata_restore_conflicts": [],
                "process_exit_code": original["process_exit_code"],
                "process_exit_codes": [
                    original["process_exit_code"],
                    repaired_receipt["process_exit_code"],
                ],
                "process_wall_seconds": original["process_wall_seconds"]
                + repaired_receipt["process_wall_seconds"],
                "recovery": {
                    "status": "passed",
                    "recovered_imports": len(failed),
                    "unrecovered_imports": 0,
                    "original_status": original["status"],
                    "repair_run": str(self.repair.run_dir),
                },
            }
        )
        self.baseline._write(self.baseline.run_dir / "full-receipt.json", summary)
        return summary
