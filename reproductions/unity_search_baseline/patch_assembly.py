"""Assemble frozen native patch shards into one source-ordered development corpus."""

from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.utils.artifacts import ArtifactStore


class UnityPatchCorpusAssembly:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.path = root.resolve(), config_path.resolve()
        self.config = ArtifactStore.read_json(self.path)
        self.output = Path(self.config["output"]).resolve()
        if not self.output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError("Assembled corpus must remain under local experiment storage")

    @staticmethod
    def asset_key(path: str) -> str:
        return path.replace("\\", "/").casefold()

    @staticmethod
    def frozen_json(path: Path, expected_sha256: str) -> JsonDict:
        if ArtifactStore.sha256_file(path) != expected_sha256:
            raise ValueError(f"Frozen assembly input changed: {path}")
        return ArtifactStore.read_json(path)

    def run(self) -> JsonDict:
        started = time.perf_counter()
        report = Path(self.config["report"]).resolve()
        if report in {
            self.output,
            self.output / "corpus.json",
            self.output / ".validation",
            self.output / ".validation/corpus.json",
        }:
            raise ValueError("Assembly report cannot alias a corpus or staging path")
        if report.exists():
            raise FileExistsError("Use a fresh assembly identity; previous artifacts remain intact")
        # Atomic claim: a concurrent or restarted job cannot reuse this output identity.
        self.output.mkdir(parents=True, exist_ok=False)
        prepared = self.frozen_json(
            Path(self.config["prepared_report"]), self.config["prepared_report_sha256"]
        )
        if (
            prepared["status"] != "passed"
            or prepared["test_opened"] is not False
            or prepared["training_updates"] != 0
            or prepared["coverage"] not in {"partial", "complete"}
        ):
            raise ValueError("Require completed development patch preparation")
        queue = self.frozen_json(
            Path(prepared["config"]["candidate_queue_config"]),
            prepared["config"]["candidate_queue_config_sha256"],
        )
        plan = self.frozen_json(Path(queue["reference_plan"]), queue["reference_plan_sha256"])
        source = self.frozen_json(Path(plan["manifest"]), plan["manifest_sha256"])
        order = {
            split: {
                self.asset_key(row["path"]): index
                for index, row in enumerate(source["splits"][split])
            }
            for split in ["train", "validation"]
        }
        if any(len(order[s]) != len(source["splits"][s]) for s in order):
            raise ValueError("Source split contains duplicate canonical asset paths")
        if order["train"].keys() & order["validation"].keys():
            raise ValueError("Source training and validation paths overlap")
        held_out = {
            self.asset_key(row["path"])
            for split, rows in source["splits"].items()
            if split not in order
            for row in rows
        }
        if held_out & (order["train"].keys() | order["validation"].keys()):
            raise ValueError("Source development paths overlap a held-out split")
        config = {
            "schema": "unity-rgba-channel-sse-v1",
            "patch_size": 240,
            "assembly": self.config,
            "reference_plan_sha256": queue["reference_plan_sha256"],
            "source_manifest_sha256": plan["manifest_sha256"],
            "assembler_sha256": ArtifactStore.sha256_file(Path(__file__)),
            "dataset_validator_sha256": ArtifactStore.sha256_file(
                Path(__file__).parents[2] / "src/adaptive_astc/data/unity_patch_dataset.py"
            ),
        }
        binding = ArtifactStore.fingerprint(config)
        splits: dict[str, list[JsonDict]] = {"train": [], "validation": []}
        seen: set[str] = set()
        run_ids: set[str] = set()
        sources = []
        for shard in prepared["shards"]:
            if shard["run_id"] in run_ids:
                raise ValueError("Patch preparation repeats a shard identity")
            run_ids.add(shard["run_id"])
            corpus = Path(shard["corpus"])
            document = self.frozen_json(corpus, shard["corpus_sha256"])
            if (
                document["config"]["patch_size"] != 240
                or document["config"]["source_sha256"] != prepared["config"]["patch_source_sha256"]
                or document["counts"] != shard["counts"]
                or document["patch_counts"] != shard["patch_counts"]
            ):
                raise ValueError("Shard protocol or coverage differs from its prepared receipt")
            for split in splits:
                if not document["counts"][split]:
                    continue
                dataset = UnityPatchDataset(
                    corpus.parent, split, expected_sha256=shard["corpus_sha256"]
                )
                for row in dataset.rows:
                    key = self.asset_key(row["path"])
                    if key not in order[split] or key in seen:
                        raise ValueError("Unknown, duplicate or wrong-split asset in patch shards")
                    seen.add(key)
                    splits[split].append(
                        {
                            **row,
                            "binding": binding,
                            "source_shard": {
                                "corpus": str(corpus),
                                "sha256": shard["corpus_sha256"],
                                "binding": row["binding"],
                                "index": row["index"],
                            },
                        }
                    )
            sources.append(
                {"run_id": shard["run_id"], "corpus": str(corpus), "sha256": shard["corpus_sha256"]}
            )
        if run_ids != set(prepared["config"]["run_ids"]):
            raise ValueError("Prepared shard identities differ from the requested batch set")
        counts = {split: len(rows) for split, rows in splits.items()}
        patch_counts = {
            split: sum(row["patch_count"] for row in rows) for split, rows in splits.items()
        }
        if (
            counts != prepared["counts"]
            or patch_counts != prepared["patch_counts"]
            or not all(counts.values())
        ):
            raise ValueError("Assembled counts differ or a development split is empty")
        full_counts = {split: len(rows) for split, rows in order.items()}
        complete = prepared["coverage"] == "complete" and counts == full_counts
        if prepared["coverage"] == "complete" and not complete:
            raise ValueError("Reported complete coverage omits source development assets")
        for split, rows in splits.items():
            rows.sort(key=lambda row: order[split][self.asset_key(row["path"])])
            for index, row in enumerate(rows):
                row["index"] = index
        result = {
            "status": "passed",
            "config": config,
            "binding": binding,
            "counts": counts,
            "patch_counts": patch_counts,
            "expected_full_counts": full_counts,
            "coverage": "complete" if complete else "partial",
            "splits": splits,
            "sources": sources,
            "candidate_count": sum(counts.values()) * 20,
            "max_psnr_reconstruction_error_db": max(
                row["max_psnr_error_db"] for rows in splits.values() for row in rows
            ),
            "test_opened": False,
            "training_updates": 0,
            "scope": "Native development corpus assembly; shared frozen targets, no model training",
        }
        result["fingerprint"] = ArtifactStore.fingerprint({"binding": binding, "splits": splits})
        staging = self.output / ".validation"
        ArtifactStore.write_json(staging / "corpus.json", result)
        corpus_sha = ArtifactStore.sha256_file(staging / "corpus.json")
        for split in splits:
            UnityPatchDataset(staging, split, expected_sha256=corpus_sha)
        # Same-volume hard-link publication is atomic and refuses an existing destination.
        (self.output / "corpus.json").hardlink_to(staging / "corpus.json")
        (staging / "corpus.json").unlink()
        result = {key: value for key, value in result.items() if key != "splits"}
        result.update(
            corpus=str(self.output / "corpus.json"),
            corpus_sha256=corpus_sha,
            wall_seconds=time.perf_counter() - started,
        )
        report.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".assembly-report-", dir=report.parent) as directory:
            staged_report = Path(directory) / "report.json"
            ArtifactStore.write_json(staged_report, result)
            report.hardlink_to(staged_report)
        return result
