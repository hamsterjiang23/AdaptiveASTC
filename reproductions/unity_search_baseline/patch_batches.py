"""Prepare reusable native patch shards from a frozen completed-batch snapshot."""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

import psutil

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.candidate_archive import UnityCandidateArchive
from reproductions.unity_search_baseline.candidate_queue import UnityCandidateQueue
from reproductions.unity_search_baseline.patch_targets import UnityPatchCorpus


class UnityPatchBatchPreparation:
    """Each shard is immutable; a partial snapshot never claims full corpus coverage."""

    def __init__(self, root: Path, config_path: Path) -> None:
        self.root = root.resolve()
        self.path = config_path.resolve()
        self.config = ArtifactStore.read_json(self.path)
        self.shards = Path(self.config["shards"]).resolve()
        if not self.shards.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Patch shards must remain under ignored local experiment storage")

    @staticmethod
    def select_batches(
        snapshot: JsonDict, batches: list[JsonDict], names: list[str]
    ) -> list[JsonDict]:
        if snapshot["test_opened"] is not False or snapshot["status"] not in {
            "running",
            "waiting_references",
            "passed",
            "failed",
        }:
            raise ValueError("Require published development candidate batches")
        planned = {batch["config"]["run_id"]: batch for batch in batches}
        published: dict[str, JsonDict] = {}
        counts = {"train": 0, "validation": 0}
        for row in snapshot["batches"]:
            name = row["run_id"]
            if name in published or name not in planned or not re.fullmatch(r"[\w.-]+", name):
                raise ValueError("Duplicate, unknown or unsafe published batch identity")
            if row["source_split"] != planned[name]["split"]:
                raise ValueError("Published candidate split differs from the original plan")
            counts[row["source_split"]] += row["images"]
            published[name] = row
        if counts != snapshot["counts"]:
            raise ValueError("Published candidate count accounting differs")
        if not names or len(set(names)) != len(names) or not set(names) <= published.keys():
            raise ValueError("Select unique, already published candidate batch identities")
        # Keep the frozen plan order regardless of the user's list ordering.
        return [batch for batch in batches if batch["config"]["run_id"] in names]

    @staticmethod
    def freeze_json(path: Path, value: JsonDict) -> None:
        if path.exists():
            if ArtifactStore.read_json(path) != value:
                raise ValueError("Existing shard manifest or protocol changed")
        else:
            ArtifactStore.write_json(path, value)

    @staticmethod
    def verify_publication(published: JsonDict, reference: JsonDict, summary: JsonDict) -> None:
        if published["reference"] != reference or any(
            published.get(key) != value for key, value in summary.items()
        ):
            raise ValueError("Revalidated candidate batch differs from its frozen publication")

    @staticmethod
    def coverage(
        snapshot: JsonDict,
        selected_count: int,
        planned_count: int,
        plan_coverage: str,
        source_counts: dict[str, int],
    ) -> str:
        return (
            "complete"
            if (
                selected_count == planned_count
                and plan_coverage == snapshot["coverage"] == "complete"
                and snapshot["expected_counts"] == source_counts
            )
            else "partial"
        )

    def run(self) -> JsonDict:
        import msvcrt

        self.shards.mkdir(parents=True, exist_ok=True)
        with (self.shards / "prepare.lock").open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("Another patch preparation owns this shard directory") from error
            try:
                return self.prepare()
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    @staticmethod
    def prepare_shard(config: Path) -> JsonDict:
        options = ArtifactStore.read_json(config)
        output = Path(options["output"])
        report = Path(options["report"])
        complete = output / "shard-complete.json"
        if complete.exists():
            frozen = ArtifactStore.read_json(complete)
            for path, key in [
                (config, "config"),
                (report, "report"),
                (output / "corpus.json", "corpus"),
            ]:
                if ArtifactStore.sha256_file(path) != frozen[f"{key}_sha256"]:
                    raise ValueError("Completed patch shard or its protocol changed")
        if report.exists():
            prepared = ArtifactStore.read_json(report)
            if prepared["status"] != "passed" or prepared["test_opened"] is not False:
                raise ValueError("Existing patch shard has no completed development receipt")
            binding = prepared["config"]
            if (
                any(binding.get(key) != value for key, value in options.items())
                or binding["source_sha256"]
                != ArtifactStore.sha256_file(Path(__file__).with_name("patch_targets.py"))
                or binding["grid_source_sha256"]
                != ArtifactStore.sha256_file(
                    Path(__file__).parents[2] / "src/adaptive_astc/data/patch_targets.py"
                )
                or Path(prepared["corpus"]).resolve() != (output / "corpus.json").resolve()
            ):
                raise ValueError("Existing patch shard belongs to another extraction protocol")
        else:
            prepared = UnityPatchCorpus(config).prepare()
        for split, count in prepared["counts"].items():
            if count:
                UnityPatchDataset(output, split, expected_sha256=prepared["corpus_sha256"])
        UnityPatchBatchPreparation.freeze_json(
            complete,
            {
                "config_sha256": ArtifactStore.sha256_file(config),
                "report_sha256": ArtifactStore.sha256_file(report),
                "corpus_sha256": ArtifactStore.sha256_file(output / "corpus.json"),
            },
        )
        return prepared

    def prepare(self) -> JsonDict:
        report = Path(self.config["report"])
        if report.exists():
            raise FileExistsError("Use a fresh batch-preparation report identity")
        started = time.perf_counter()
        queue_path = Path(self.config["candidate_queue_config"])
        snapshot_path = Path(self.config["candidate_snapshot"])
        for path, digest in [
            (queue_path, self.config["candidate_queue_config_sha256"]),
            (snapshot_path, self.config["candidate_snapshot_sha256"]),
            (Path(__file__).with_name("patch_targets.py"), self.config["patch_source_sha256"]),
        ]:
            if ArtifactStore.sha256_file(path) != digest:
                raise ValueError("Frozen patch preparation input or implementation changed")
        queue = UnityCandidateQueue(self.root, queue_path)
        source, batches = queue.validate()
        source_counts = {split: len(source["splits"][split]) for split in ["train", "validation"]}
        snapshot = ArtifactStore.read_json(snapshot_path)
        if (
            snapshot["config_sha256"] != self.config["candidate_queue_config_sha256"]
            or snapshot["implementation_sha256"]
            != ArtifactStore.sha256_file(Path(__file__).with_name("candidate_queue.py"))
            or snapshot["archive_verifier_sha256"]
            != ArtifactStore.sha256_file(Path(__file__).with_name("candidate_archive.py"))
            or snapshot["expected_counts"] != queue.series.config["expected_counts"]
        ):
            raise ValueError("Candidate snapshot does not belong to the frozen queue")
        selected = self.select_batches(snapshot, batches, self.config["run_ids"])
        published = {row["run_id"]: row for row in snapshot["batches"]}
        state: JsonDict = {
            "status": "running",
            "config": self.config,
            "config_sha256": ArtifactStore.sha256_file(self.path),
            "implementation_sha256": ArtifactStore.sha256_file(Path(__file__)),
            "dataset_validator_sha256": ArtifactStore.sha256_file(
                Path(__file__).parents[2] / "src/adaptive_astc/data/unity_patch_dataset.py"
            ),
            "expected_full_counts": source_counts,
            "expected_plan_counts": snapshot["expected_counts"],
            "coverage": self.coverage(
                snapshot,
                len(selected),
                len(batches),
                queue.series.config.get("coverage", "complete"),
                source_counts,
            ),
            "counts": {"train": 0, "validation": 0},
            "patch_counts": {"train": 0, "validation": 0},
            "shards": [],
            "test_opened": False,
            "training_updates": 0,
        }
        self.shards.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        try:
            for batch in selected:
                if psutil.virtual_memory().available < 20 * 1024**3:
                    raise RuntimeError("Require20GiB free RAM before native patch extraction")
                if shutil.disk_usage(self.shards).free < 40 * 1024**3:
                    raise RuntimeError("Require40GiB free disk before native patch extraction")
                name, split = batch["config"]["run_id"], batch["split"]
                state.update(current_batch=name, wall_seconds=time.perf_counter() - started)
                ArtifactStore.write_json(report, state)
                references, reference_binding = queue.series.verify_batch(batch)
                publication = published[name]
                candidate_report = Path(publication["report"])
                reuse = queue.config.get("reuse", {}).get(name)
                candidate_config = (
                    Path(reuse["config"])
                    if reuse
                    else queue.output / "configs" / f"{candidate_report.stem}.json"
                )
                if reuse and ArtifactStore.sha256_file(candidate_config) != reuse["config_sha256"]:
                    raise ValueError("Reused candidate configuration changed")
                queue.verify_capture_binding(batch, ArtifactStore.read_json(candidate_config))
                rows, summary = UnityCandidateArchive.verify(
                    candidate_report, references, candidate_config
                )
                self.verify_publication(publication, reference_binding, summary)
                for row in rows:
                    identity = row["path"].replace("\\", "/").casefold()
                    if identity in seen or row["source_split"] != split:
                        raise ValueError(
                            "Duplicate asset or split conflict across native patch shards"
                        )
                    seen.add(identity)
                manifest = {
                    "status": "passed",
                    "coverage": "partial",
                    "splits": {s: rows if s == split else [] for s in ["train", "validation"]},
                    "counts": {s: len(rows) if s == split else 0 for s in ["train", "validation"]},
                    "reference_plan_sha256": queue.config["reference_plan_sha256"],
                    "candidate_batch": publication,
                    "original_search_labels_preserved": True,
                    "test_opened": False,
                }
                manifest_path = self.shards / "manifests" / f"{name}.json"
                self.freeze_json(manifest_path, manifest)
                options = {
                    "candidate_manifest": str(manifest_path),
                    "candidate_manifest_sha256": ArtifactStore.sha256_file(manifest_path),
                    "patch_size": 240,
                    "output": str(self.shards / "corpora" / name),
                    "report": str(self.shards / "reports" / f"{name}.json"),
                }
                config = self.shards / "configs" / f"{name}.json"
                self.freeze_json(config, options)
                prepared = self.prepare_shard(config)
                if prepared["counts"] != manifest["counts"]:
                    raise ValueError("Prepared patch shard does not cover the original batch")
                state["shards"].append({"run_id": name, "source_split": split, **prepared})
                for s in state["counts"]:
                    state["counts"][s] += prepared["counts"][s]
                    state["patch_counts"][s] += prepared["patch_counts"][s]
                state["wall_seconds"] = time.perf_counter() - started
                ArtifactStore.write_json(report, state)
                print({"completed_batch": name, "counts": state["counts"]}, flush=True)
            if state["coverage"] == "complete" and state["counts"] != state["expected_full_counts"]:
                raise ValueError("Complete patch coverage differs from the original source counts")
            state.update(
                status="passed", current_batch=None, wall_seconds=time.perf_counter() - started
            )
            ArtifactStore.write_json(report, state)
            return state
        except BaseException as error:
            state.update(
                status="failed", error=repr(error), wall_seconds=time.perf_counter() - started
            )
            ArtifactStore.write_json(report, state)
            raise
