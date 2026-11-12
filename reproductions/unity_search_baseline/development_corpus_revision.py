"""Replace approved development rows while preserving immutable candidate and patch targets."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.development_revision import UnityDevelopmentRevision as R


class UnityDevelopmentCorpusRevision:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root, self.path = root.resolve(), config_path.resolve()
        self.config = A.read_json(self.path)
        self.sha = A.sha256_file(self.path)
        self.output = Path(self.config["output"]).resolve()
        self.report = Path(self.config["report"]).resolve()
        self.provenance_inputs: dict[str, str] = {}
        self.provenance_documents: dict[str, JsonDict] = {}
        local = self.root / "experiment report/.local"
        if (
            not self.output.is_relative_to(local)
            or not self.report.is_relative_to(self.root / "experiment report")
            or self.report.is_relative_to(local)
        ):
            raise ValueError("Revised corpus needs distinct local data and public report paths")
        self.verify_sources()

    def verify_sources(self) -> None:
        baseline = self.frozen("source_baseline")
        required = set(baseline["sources_unchanged"]) | {
            "reproductions/unity_search_baseline/development_corpus_revision.py",
            "script/revise_unity_corpus.py",
            "reproductions/unity_search_baseline/development_revision.py",
            "src/adaptive_astc/data/unity_capture_input.py",
            "src/adaptive_astc/data/unity_inference.py",
        }
        sources = self.config["sources_sha256"]
        if set(sources) != required:
            raise ValueError("Corpus revision execution source bindings are incomplete")
        for name, digest in sources.items():
            if A.sha256_file(self.root / name) != digest:
                raise ValueError(f"Corpus revision execution source changed: {name}")
        if any(sources[name] != digest for name, digest in baseline["sources_unchanged"].items()):
            raise ValueError("Original corpus execution source differs")

    def frozen(self, key: str) -> JsonDict:
        binding = self.config[key]
        if A.sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"Frozen corpus revision input changed: {key}")
        return A.read_json(Path(binding["path"]))

    def evidence(self, path: Path, expected: str | None = None) -> JsonDict:
        key = str(path.resolve())
        if key not in self.provenance_documents:
            raw = path.read_bytes()
            self.provenance_inputs[key] = hashlib.sha256(raw).hexdigest()
            self.provenance_documents[key] = json.loads(raw)
        if expected is not None and self.provenance_inputs[key] != expected:
            raise ValueError(f"Native origin evidence changed: {path}")
        return self.provenance_documents[key]

    def origin(self, row: JsonDict) -> JsonDict:
        source = row["source_shard"]
        shard = self.evidence(Path(source["corpus"]), source["sha256"])
        original_patch = shard["splits"][row["split"]][source["index"]]
        if original_patch["binding"] != source["binding"] or any(
            row.get(key) != value
            for key, value in original_patch.items()
            if key not in {"binding", "index"}
        ):
            raise ValueError("Revised row differs from its immutable native patch origin")
        config = shard["config"]
        manifest = self.evidence(
            Path(config["candidate_manifest"]), config["candidate_manifest_sha256"]
        )
        original = manifest["splits"][row["split"]][source["index"]]
        if any(
            original[key] != row[target]
            for key, target in [
                ("path", "path"),
                ("reference_sha256", "reference_sha256"),
                ("selection", "original_selection"),
                ("actual_options", "actual_options"),
                ("import_metadata", "import_metadata"),
            ]
        ):
            raise ValueError("Patch origin differs from native candidate/capture identities")
        return original

    def verify_new_identity(self, row: JsonDict, expected: JsonDict, manifest: JsonDict) -> None:
        original = self.origin(row)
        if original["source_md4"].lower() != expected["fileHash"].lower():
            raise ValueError("Replacement source MD4 differs from the approved source")
        receipt_path = Path(original["candidate_directory"]).parent / "receipt.json"
        receipt = self.evidence(receipt_path)
        summary = self.evidence(
            Path(receipt["config"]["report"]), original["candidate_report_sha256"]
        )
        if Path(summary["raw_receipt"]).resolve() != receipt_path.resolve():
            raise ValueError("Candidate summary points to a different raw origin")
        self.evidence(receipt_path, summary["raw_receipt_sha256"])
        if receipt["status"] != "passed" or receipt["test_opened"] is not False:
            raise ValueError("Replacement candidate measurement did not pass")
        run, phase = Path(receipt["config"]["capture_run"]), receipt["config"]["capture_phase"]
        identity = self.evidence(
            run / "identity.json", receipt["capture_binding"]["identity_sha256"]
        )
        if Path(identity["manifest"]).resolve() != Path(manifest["path"]).resolve() or (
            identity["manifest_sha256"] != manifest["sha256"]
        ):
            raise ValueError("Replacement capture used another source manifest")
        captured_sources = self.evidence(Path(manifest["path"]), manifest["sha256"])
        sources = [
            item
            for item in captured_sources["splits"][row["split"]]
            if R.key(item["path"]) == R.key(row["path"])
        ]
        if len(sources) != 1 or any(
            sources[0][key] != expected[key]
            for key in ["fileHash", "source_sha256", "source_bytes", "meta_sha256"]
        ):
            raise ValueError("Approved source bytes or metadata differ from the capture source")
        phase_config = self.evidence(
            run / f"{phase}-config.json", receipt["capture_binding"]["phase_config_sha256"]
        )
        backups = Path(phase_config["backupDirectory"])
        index_path = backups / "index.jsonl"
        raw = index_path.read_bytes()
        self.provenance_inputs[str(index_path.resolve())] = hashlib.sha256(raw).hexdigest()
        backups_for_asset = {
            entry["backup"]
            for line in raw.splitlines()
            if line.strip()
            for entry in [json.loads(line)]
            if R.key(entry["asset"]) == R.key(row["path"])
        }
        if len(backups_for_asset) != 1:
            raise ValueError("Replacement original importer metadata backup is ambiguous")
        filename = backups_for_asset.pop()
        if Path(filename).name != filename:
            raise ValueError("Metadata backup path escapes the capture archive")
        backup = backups / filename
        digest = A.sha256_file(backup)
        if digest != expected["meta_sha256"]:
            raise ValueError("Replacement was imported with different original metadata")
        self.provenance_inputs[str(backup.resolve())] = digest

    def run(self) -> JsonDict:
        started = time.perf_counter()
        old, added, reservation = [
            self.frozen(key) for key in ["original_corpus", "replacement_corpus", "reservation"]
        ]
        reservation_config = self.frozen("reservation_config")
        if reservation["config_sha256"] != self.config["reservation_config"]["sha256"] or (
            reservation_config["development_corpus"] != self.config["original_corpus"]
        ):
            raise ValueError("Original corpus differs from the approved reservation's corpus")
        if (
            reservation["status"] != "reserved"
            or reservation["counts"] != self.config["expected_counts"]
        ):
            raise ValueError("Reservation does not match the requested new development coverage")
        manifest_binding = reservation["files"]["manifest"]
        if A.sha256_file(Path(manifest_binding["path"])) != manifest_binding["sha256"]:
            raise ValueError("Revised source manifest changed")
        source = A.read_json(Path(manifest_binding["path"]))
        replacement_binding = reservation["files"]["replacements"]
        replacement_sources = self.evidence(
            Path(replacement_binding["path"]), replacement_binding["sha256"]
        )
        for corpus in [old, added]:
            if (
                corpus["status"] != "passed"
                or corpus["test_opened"] is not False
                or (
                    corpus["config"]["schema"] != "unity-rgba-channel-sse-v1"
                    or corpus["config"]["patch_size"] != 240
                    or A.fingerprint(corpus["config"]) != corpus["binding"]
                    or A.fingerprint({"binding": corpus["binding"], "splits": corpus["splits"]})
                    != corpus["fingerprint"]
                )
            ):
                raise ValueError("Require intact original and replacement native corpora")
        if old["counts"] != self.config["expected_counts"] or (
            added["counts"] != reservation["replacement_counts"]
        ):
            raise ValueError("Original or replacement corpus coverage differs")
        removed: dict[str, set[str]] = {"train": set(), "validation": set()}
        replacements: dict[str, list[JsonDict]] = {"train": [], "validation": []}
        for split in removed:
            available = {R.key(row["path"]): row for row in added["splits"][split]}
            if len(available) != added["counts"][split]:
                raise ValueError("Duplicate replacement corpus identities")
            for mapping in reservation["replacements"]:
                if mapping["split"] != split:
                    continue
                original = old["splits"][split][mapping["index"]]
                if original["path"] != mapping["old_path"] or (
                    original["import_metadata"]["texture_dimension"] != "Cube"
                ):
                    raise ValueError("Original row is not the approved Cube at its frozen position")
                removed[split].add(R.key(mapping["old_path"]))
                replacements[split].append(available.pop(R.key(mapping["new_path"])))
            if available:
                raise ValueError("Replacement corpus contains unapproved extra identities")
        splits, mappings = R.replace_rows(old["splits"], removed, replacements)
        if mappings != reservation["replacements"]:
            raise ValueError("Corpus replacements differ from the approved source mapping")
        for split, rows in splits.items():
            if [row["path"] for row in rows] != [row["path"] for row in source["splits"][split]]:
                raise ValueError("Revised corpus order differs from the revised source manifest")
        for split, rows in replacements.items():
            expected_sources = {
                R.key(row["path"]): row for row in replacement_sources["splits"][split]
            }
            if len(expected_sources) != len(rows):
                raise ValueError(
                    "Replacement source list differs from the measured replacement count"
                )
            for row in rows:
                self.verify_new_identity(
                    row, expected_sources[R.key(row["path"])], replacement_binding
                )
        self.report.parent.mkdir(parents=True, exist_ok=True)
        with self.report.open("x", encoding="utf-8") as stream:
            json.dump({"status": "assembling", "config_sha256": self.sha}, stream)
        try:
            self.output.mkdir(parents=True, exist_ok=False)
            configuration = {
                "schema": "unity-rgba-channel-sse-v1",
                "patch_size": 240,
                "revision": self.config,
                "source_sha256": A.sha256_file(Path(__file__)),
            }
            binding = A.fingerprint(configuration)
            added_keys = {R.key(row["path"]) for rows in replacements.values() for row in rows}
            inputs: list[JsonDict] = []
            for split, rows in splits.items():
                for index, row in enumerate(rows):
                    self.origin(row)
                    parent = (
                        "replacement_corpus"
                        if R.key(row["path"]) in added_keys
                        else "original_corpus"
                    )
                    projected = {**row, "reference_png": row["reference"], "source_split": split}
                    _, _, native_input = UnityCaptureInputAdapter.project(projected)
                    inputs.append(native_input)
                    rows[index] = {
                        **row,
                        "index": index,
                        "binding": binding,
                        "revision_parent": {
                            **self.config[parent],
                            "index": row["index"],
                            "binding": row["binding"],
                        },
                    }
            counts = {split: len(rows) for split, rows in splits.items()}
            patch_counts = {
                split: sum(row["patch_count"] for row in rows) for split, rows in splits.items()
            }
            result = {
                "status": "passed",
                "config": configuration,
                "binding": binding,
                "splits": splits,
                "counts": counts,
                "expected_full_counts": counts,
                "patch_counts": patch_counts,
                "coverage": "complete",
                "candidate_count": sum(counts.values()) * 20,
                "max_psnr_reconstruction_error_db": max(
                    row["max_psnr_error_db"] for rows in splits.values() for row in rows
                ),
                "training_updates": 0,
                "test_opened": False,
                "scope": "Approved native development revision; prior target artifacts reused",
                "fingerprint": A.fingerprint({"binding": binding, "splits": splits}),
            }
            staging = self.output / ".validation"
            A.write_json(staging / "corpus.json", result)
            corpus_sha = A.sha256_file(staging / "corpus.json")
            for split in splits:
                UnityPatchDataset(staging, split, expected_sha256=corpus_sha)
            for key in [
                "original_corpus",
                "replacement_corpus",
                "reservation",
                "reservation_config",
            ]:
                self.frozen(key)
            self.verify_sources()
            if A.sha256_file(Path(manifest_binding["path"])) != manifest_binding["sha256"]:
                raise ValueError("Revised source manifest changed during assembly")
            if A.sha256_file(self.path) != self.sha:
                raise ValueError("Corpus revision configuration changed")
            for name, digest in self.provenance_inputs.items():
                if A.sha256_file(Path(name)) != digest:
                    raise ValueError(f"Native origin changed before publication: {name}")
            destination = self.output / "corpus.json"
            destination.hardlink_to(staging / "corpus.json")
            (staging / "corpus.json").unlink()
            inputs_path = self.output / "input-bindings.json"
            A.write_json(inputs_path, {"inputs": inputs})
            report = {key: value for key, value in result.items() if key != "splits"}
            report.update(
                corpus=str(destination),
                corpus_sha256=corpus_sha,
                input_bindings=str(inputs_path),
                input_bindings_sha256=A.sha256_file(inputs_path),
                input_eligibility_images=len(inputs),
                config_sha256=self.sha,
                retained_images=sum(counts.values()) - len(added_keys),
                replaced_images=len(added_keys),
                original_data_modified=False,
                native_origin_inputs_sha256=self.provenance_inputs,
                wall_seconds=time.perf_counter() - started,
            )
            A.write_json(self.report, report)
            return report
        except BaseException as error:
            A.write_json(
                self.report,
                {
                    "status": "failed",
                    "config_sha256": self.sha,
                    "error": repr(error),
                    "training_updates": 0,
                    "test_opened": False,
                },
            )
            raise
