"""Collect frozen development reference batches serially and retain their source splits."""

from __future__ import annotations

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
from reproductions.common.unity_reference import UnityReferenceCapture
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.metadata import UnityOptionCapture


class UnityReferenceSeries:
    """A successful series proves reference/selection coverage, not supplemental targets."""

    def __init__(self, root: Path, config: Path) -> None:
        self.root = root.resolve()
        self.config_path = config.resolve()
        self.config = ArtifactStore.read_json(self.config_path)
        self.output = Path(self.config["output"]).resolve()
        if not self.output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Reference corpus must live under experiment report/.local")
        self.report = Path(self.config["report"])

    def baseline(self, config: JsonDict) -> UnitySearchBaseline:
        return UnitySearchBaseline(
            self.root,
            Path(config["project"]),
            Path(config["editor"]),
            Path(config["manifest"]),
            run_id=config["run_id"],
            capture_references=True,
            source_split=config.get("source_split", "train"),
            capture_paths=config.get("capture_paths"),
        )

    def verify_environment(self) -> None:
        if ArtifactStore.sha256_file(Path(self.config["editor"])) != self.config["editor_sha256"]:
            raise ValueError("Series Editor binary changed")
        libraries = self.config["encoder_dlls"]
        if set(libraries) != {"astcenc-avx2-shared.dll", "astcenc-avx2-static.dll"}:
            raise ValueError("Series must bind both original encoder DLLs")
        for name, expected in libraries.items():
            path = Path(self.config["project"]) / "Assets/Editor/Astc/Plugins" / name
            if ArtifactStore.sha256_file(path) != expected:
                raise ValueError(f"Series encoder binary changed: {name}")

    def validate(self) -> tuple[JsonDict, list[JsonDict]]:
        self.verify_environment()
        for key, default in [("minimum_free_ram_gib", 20), ("minimum_free_disk_gib", 40)]:
            value = self.config.get(key, default)
            if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be a finite positive number")
        manifest_path = Path(self.config["manifest"])
        if ArtifactStore.sha256_file(manifest_path) != self.config["manifest_sha256"]:
            raise ValueError("Series source manifest changed")
        source = ArtifactStore.read_json(manifest_path)
        expected = self.config["expected_counts"]
        coverage = self.config.get("coverage", "complete")
        if coverage not in {"complete", "selected"}:
            raise ValueError("Reference coverage must be complete or selected")
        if set(expected) != {"train", "validation"}:
            raise ValueError("Reference series must preserve train and validation only")
        known: dict[str, set[str]] = {}
        for split in expected:
            rows = source["splits"][split]
            keys = {UnitySearchBaseline._asset_key(row["path"]) for row in rows}
            if (
                type(expected[split]) is not int
                or not 0 <= expected[split] <= len(rows)
                or (coverage == "complete" and len(rows) != expected[split])
                or len(rows) != len(keys)
            ):
                raise ValueError("Series expected counts differ from unique frozen source rows")
            known[split] = keys
        if known["train"] & known["validation"]:
            raise ValueError("Source train and validation share asset paths")
        held_out = {
            UnitySearchBaseline._asset_key(row["path"])
            for split, rows in source["splits"].items()
            if split not in expected
            for row in rows
        }
        if (known["train"] | known["validation"]) & held_out:
            raise ValueError("Development assets overlap a held-out source split")
        seen: dict[str, set[str]] = {split: set() for split in expected}
        run_ids: set[str] = set()
        reports: set[Path] = set()
        batches = []
        for entry in self.config["batches"]:
            path = Path(entry["config"])
            if ArtifactStore.sha256_file(path) != entry["sha256"]:
                raise ValueError("Frozen batch configuration changed")
            config = ArtifactStore.read_json(path)
            baseline = self.baseline(config)
            if (
                baseline.manifest != manifest_path.resolve()
                or baseline.project != Path(self.config["project"]).resolve()
                or baseline.editor != Path(self.config["editor"]).resolve()
                or config["run_id"] in run_ids
                or Path(config["report"]).resolve() in reports
            ):
                raise ValueError("Batch environment or output identity differs from the series")
            run_ids.add(config["run_id"])
            reports.add(Path(config["report"]).resolve())
            if baseline.capture_paths is None:
                baseline.verify_protocol()
                prepared = ArtifactStore.read_json(
                    baseline.run_dir / f"{config['phase']}-config.json"
                )
                paths = [row["path"] for row in prepared["assets"]]
            else:
                if config["phase"] != "batch":
                    raise ValueError("Explicit reference paths require batch phase")
                paths = baseline.capture_paths
            keys = {baseline._asset_key(path) for path in paths}
            split = baseline.source_split
            if (
                not paths
                or len(paths) != len(keys)
                or not keys <= known[split]
                or keys & seen[split]
            ):
                raise ValueError("Reference batch membership is missing, duplicated or overlaps")
            seen[split].update(keys)
            batches.append(
                {
                    "config": config,
                    "path": str(path),
                    "config_sha256": entry["sha256"],
                    "paths": paths,
                    "split": split,
                }
            )
        if (
            not batches
            or any(len(seen[split]) != expected[split] for split in expected)
            or (coverage == "complete" and seen != known)
        ):
            raise ValueError("Reference series does not cover the complete development splits")
        return source, batches

    def verify_batch(self, batch: JsonDict) -> tuple[list[JsonDict], JsonDict]:
        config = batch["config"]
        baseline = self.baseline(config)
        phase = config["phase"]
        identity = ArtifactStore.read_json(baseline.run_dir / "identity.json")
        if identity["encoder_dlls"] != self.config["encoder_dlls"]:
            raise ValueError("Batch encoders differ from the frozen series environment")
        options_path = baseline.run_dir / "options-receipt.json"
        options = ArtifactStore.read_json(options_path)
        restoration = options["managed_source_restoration"]
        if (
            options["status"] != "passed"
            or restoration["status"] != "restored"
            or restoration["original_sha256"] != restoration["restored_sha256"]
            or ArtifactStore.sha256_file(Path(config["report"]))
            != ArtifactStore.sha256_file(options_path)
        ):
            raise ValueError("Batch options or managed-source restoration is incomplete")
        captured = UnityReferenceCapture(baseline).collect(phase)
        actual = UnityOptionCapture.audit(baseline, phase, captured)
        if actual["native_provenance"]["editor_sha256"] != self.config["editor_sha256"]:
            raise ValueError("Batch Editor differs from the frozen series environment")
        for key in [
            "rows",
            "images",
            "candidate_callbacks",
            "options_sha256",
            "native_provenance",
            "capture_receipt_sha256",
        ]:
            if actual[key] != options[key]:
                raise ValueError(f"Archived callback audit changed: {key}")
        expected = [baseline._asset_key(path) for path in batch["paths"]]
        if [baseline._asset_key(row["path"]) for row in captured["rows"]] != expected:
            raise ValueError("Archived reference order differs from the series plan")
        archive = baseline.run_dir / "references" / f"normalized-{phase}"
        imports = baseline._read_lines(baseline.run_dir / f"{phase}-imports.jsonl")
        native = {
            baseline._asset_key(row["asset"]): row
            for row in baseline._read_lines(baseline.run_dir / f"{phase}-native.jsonl")
        }
        source_rows = {
            baseline._asset_key(row["path"]): row
            for row in ArtifactStore.read_json(baseline.manifest)["splits"][batch["split"]]
        }
        rows = []
        for index, (reference, observed, imported) in enumerate(
            zip(captured["rows"], actual["rows"], imports, strict=True)
        ):
            if reference.get("source_split", "train") != batch["split"]:
                raise ValueError("Archived source split differs from the batch")
            key = baseline._asset_key(reference["path"])
            if (
                reference["source_md4"].lower() != source_rows[key]["fileHash"].lower()
                or reference["selection"] != native[key]
            ):
                raise ValueError(
                    "Archived source MD4 or selection differs from the original search"
                )
            rows.append(
                {
                    "path": reference["path"],
                    "source_md4": reference["source_md4"],
                    "source_split": batch["split"],
                    "reference_png": str(archive / f"{index:05d}" / "original.png"),
                    "reference_sha256": reference["artifacts_sha256"]["original.png"],
                    "width": reference["width"],
                    "height": reference["height"],
                    "selection": reference["selection"],
                    "actual_options": observed,
                    "import_metadata": imported,
                    "capture_directory": str(archive),
                    "capture_index": index,
                }
            )
        receipt = ArtifactStore.read_json(baseline.run_dir / f"{phase}-receipt.json")
        binding = {
            "run_id": config["run_id"],
            "source_split": batch["split"],
            "images": len(rows),
            "callbacks": actual["candidate_callbacks"],
            "options_receipt": str(options_path),
            "options_sha256": ArtifactStore.sha256_file(options_path),
            "reference_receipt_sha256": ArtifactStore.sha256_file(archive / "receipt.json"),
            "phase_receipt_sha256": ArtifactStore.sha256_file(
                baseline.run_dir / f"{phase}-receipt.json"
            ),
            "editor_process_seconds": receipt["process_wall_seconds"],
        }
        return rows, binding

    def require_resources(self) -> None:
        minimum_ram = float(self.config.get("minimum_free_ram_gib", 20)) * 1024**3
        minimum_disk = float(self.config.get("minimum_free_disk_gib", 40)) * 1024**3
        if psutil.virtual_memory().available < minimum_ram:
            raise RuntimeError("Insufficient free RAM for another Unity Editor; retain this plan")
        for path in [self.output, Path(self.config["project"])]:
            if shutil.disk_usage(path).free < minimum_disk:
                raise RuntimeError("Insufficient free disk for another reference batch")

    @contextmanager
    def project_lock(self) -> Iterator[None]:
        if os.name != "nt":
            raise RuntimeError("This Unity Windows collection requires Windows file locking")
        import msvcrt

        # Different repository checkouts can share one Unity project.
        path = Path(self.config["project"]).resolve() / "Library/ASTCReproductionLocks/series.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("Another reference series owns this Unity project") from error
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    def run(self, *, collect: bool = False) -> JsonDict:
        source, batches = self.validate()
        if not batches:
            raise ValueError("Reference series must contain at least one batch")
        with self.project_lock():
            return self.execute(source, batches, collect=collect)

    def execute(self, source: JsonDict, batches: list[JsonDict], *, collect: bool) -> JsonDict:
        baseline = self.baseline(batches[0]["config"])
        baseline.require_project_closed()
        self.output.mkdir(parents=True, exist_ok=True)
        locked_config = self.output / "series-config.json"
        if locked_config.exists():
            if ArtifactStore.read_json(locked_config) != self.config:
                raise ValueError("Series configuration changed; use a new output identity")
        else:
            ArtifactStore.write_json(locked_config, self.config)
        owner_path = self.output / "owner.json"
        owner = {"pid": os.getpid(), "created": psutil.Process().create_time()}
        ArtifactStore.write_json(owner_path, owner)
        invocation = self.output / "invocations" / uuid.uuid4().hex / "receipt.json"
        state: JsonDict = {
            "status": "running",
            "started_utc": datetime.now(UTC).isoformat(),
            "configuration_sha256": ArtifactStore.sha256_file(self.config_path),
            "implementation_sha256": ArtifactStore.sha256_file(Path(__file__)),
            "source_manifest_sha256": self.config["manifest_sha256"],
            "expected_counts": self.config["expected_counts"],
            "coverage": self.config.get("coverage", "complete"),
            "counts": {"train": 0, "validation": 0},
            "batches": [],
            "scope": (
                "imported RGBA references and original-search labels; supplemental targets separate"
            ),
            "invocation_receipt": str(invocation),
            "test_opened": False,
            "current_batch": None,
        }
        splits: dict[str, list[JsonDict]] = {"train": [], "validation": []}
        started = time.perf_counter()
        try:
            for batch in batches:
                config = batch["config"]
                state["current_batch"] = config["run_id"]
                ArtifactStore.write_json(self.report, state)
                self.verify_environment()
                if (
                    ArtifactStore.sha256_file(Path(self.config["manifest"]))
                    != self.config["manifest_sha256"]
                    or ArtifactStore.sha256_file(Path(batch["path"])) != batch["config_sha256"]
                ):
                    raise ValueError(
                        "Source or pending batch configuration changed during collection"
                    )
                path = self.baseline(config).run_dir / "options-receipt.json"
                if not path.exists():
                    if not collect:
                        raise FileNotFoundError(
                            f"Reference batch has not completed: {config['run_id']}"
                        )
                    self.require_resources()
                    capture = UnityOptionCapture(self.root, Path(batch["path"]))
                    if capture.config != config:
                        raise ValueError("Pending batch configuration changed before launch")
                    capture.run()
                rows, binding = self.verify_batch(batch)
                splits[batch["split"]].extend(rows)
                state["counts"][batch["split"]] += len(rows)
                state["batches"].append(binding)
                ArtifactStore.write_json(self.report, state)
            for split, rows in splits.items():
                by_path = {baseline._asset_key(row["path"]): row for row in rows}
                splits[split] = [
                    by_path[baseline._asset_key(row["path"])]
                    for row in source["splits"][split]
                    if state["coverage"] == "complete"
                    or baseline._asset_key(row["path"]) in by_path
                ]
            manifest = {
                "splits": splits,
                "source_manifest_sha256": self.config["manifest_sha256"],
                "batch_bindings": state["batches"],
                "scope": state["scope"],
                "coverage": state["coverage"],
            }
            manifest["fingerprint"] = ArtifactStore.fingerprint(manifest)
            manifest_path = self.output / "manifest.json"
            ArtifactStore.write_json(manifest_path, manifest)
            state.update(
                status="passed",
                current_batch=None,
                manifest=str(manifest_path),
                manifest_sha256=ArtifactStore.sha256_file(manifest_path),
            )
        except BaseException as error:
            state.update(status="failed", error=repr(error))
            raise
        finally:
            state["invocation_seconds"] = time.perf_counter() - started
            state["ended_utc"] = datetime.now(UTC).isoformat()
            ArtifactStore.write_json(invocation, state)
            ArtifactStore.write_json(self.report, state)
            ArtifactStore.write_json(owner_path, {**owner, "finished": True})
        return state
