"""Check rule replay against frozen original decisions, without encoding or training."""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.benchmark import UnitySearchBaseline
from reproductions.unity_search_baseline.candidate_completion import UnityCandidateCompletion
from reproductions.unity_search_baseline.patch_targets import UnityPatchCorpus
from reproductions.unity_search_baseline.policy import UnitySearchPolicy


class UnityPolicyAudit:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path.resolve()
        self.config = ArtifactStore.read_json(config_path)

    def run(self) -> JsonDict:
        started = time.perf_counter()
        config = self.config
        manifest_path = Path(config["candidate_manifest"])
        if ArtifactStore.sha256_file(manifest_path) != config["candidate_manifest_sha256"]:
            raise ValueError("Frozen candidate manifest changed")
        source = Path(config["engine_source"])
        if ArtifactStore.sha256_file(source) != config["engine_source_sha256"]:
            raise ValueError("Engine source changed since policy audit was frozen")
        manifest = ArtifactStore.read_json(manifest_path)
        if (
            manifest["status"] != "passed"
            or manifest["test_opened"] is not False
            or manifest["original_search_labels_preserved"] is not True
            or set(manifest["splits"]) != {"train", "validation"}
        ):
            raise ValueError("A completed development candidate manifest is required")
        verifier = UnityPatchCorpus(self.config_path)
        policies: dict[Path, UnitySearchPolicy] = {}
        cached_choices: dict[Path, dict[str, JsonDict]] = {}
        representatives = {
            Path(row["capture_directory"]).resolve(): row
            for rows in manifest["splits"].values()
            for row in rows
        }
        policy_provenance = []
        for binding in config["policy_caches"]:
            path = Path(binding["file"])
            if ArtifactStore.sha256_file(path) != binding["sha256"]:
                raise ValueError("Original native policy cache changed")
            entries = [
                json.loads(line) for line in path.read_text("utf-8-sig").splitlines() if line
            ]
            tables = [
                row["tableConfig"]
                for row in entries
                if row.get("_kind") == "astc_cache_table_config"
            ]
            if len(tables) != 1:
                raise ValueError("Expected exactly one native policy table")
            capture = Path(binding["capture_directory"]).resolve()
            if capture in policies:
                raise ValueError("Duplicate capture policy binding")
            if capture not in representatives:
                raise ValueError("Policy cache is outside the frozen captured corpus")
            row = representatives[capture]
            verifier.measured_image(row)
            policy_provenance.append(self.verify_policy_origin(binding, row))
            policies[capture] = UnitySearchPolicy(tables[0])
            records = [row for row in entries if "filePath" in row]
            indexed = {UnitySearchBaseline._asset_key(row["filePath"]): row for row in records}
            if len(indexed) != len(records):
                raise ValueError("Duplicate cached asset identity")
            cached_choices[capture] = indexed
        if set(policies) != set(representatives):
            raise ValueError("Every original capture requires its own policy binding")
        rows = []
        seen: set[str] = set()
        for split, sources in manifest["splits"].items():
            if len(sources) != manifest["counts"][split]:
                raise ValueError("Candidate split count changed")
            for row in sources:
                if row["source_split"] != split or row["path"] in seen:
                    raise ValueError("Candidate split or asset identity changed")
                seen.add(row["path"])
                capture = Path(row["capture_directory"]).resolve()
                cached = cached_choices[capture][UnitySearchBaseline._asset_key(row["path"])]
                expected = row["selection"]
                if (
                    cached["fileHash"].lower() != row["source_md4"].lower()
                    or cached["blockSize"] != expected["block_size"]
                    or cached["qualityLevel"] != expected["preset"]
                    or cached.get("rdo") is not False
                    or not expected["search_executed"]
                    or expected["cache_hit"]
                ):
                    raise ValueError("Original search choice differs from native cache")
                measured = verifier.measured_image(row)
                metadata = measured["metadata"]
                profile = row["actual_options"]["profile"]
                if profile not in {0, 1}:
                    raise ValueError("This replay audit covers captured LDR inputs")
                if (
                    metadata["is_normal"]
                    != (row["actual_options"]["texture_type_importer"] == "NormalMap")
                    or (profile == 0) != row["import_metadata"]["srgb"]
                    or (row["width"], row["height"])
                    != (row["actual_options"]["width"], row["actual_options"]["height"])
                ):
                    raise ValueError(
                        "Policy input metadata disagrees with captured encoder options"
                    )
                decision = asdict(
                    policies[capture].select(
                        measured["candidates"],
                        width=row["width"],
                        height=row["height"],
                        srgb=profile == 0,
                        normal=metadata["is_normal"],
                    )
                )
                compared = ["block_size", "preset", "selection_reason", "candidates_measured"]
                differences = {
                    key: {"original": expected[key], "replay": decision[key]}
                    for key in compared
                    if expected[key] != decision[key]
                }
                # Diagnostic only: exact PSNR observations, with all non-PSNR gates removed.
                psnr_only = asdict(
                    policies[capture].select(
                        measured["candidates"],
                        width=row["width"],
                        height=row["height"],
                        srgb=False,
                        normal=False,
                    )
                )
                rows.append(
                    {
                        "path": row["path"],
                        "split": split,
                        "width": row["width"],
                        "height": row["height"],
                        "normal": metadata["is_normal"],
                        "srgb": profile == 0,
                        "original_selection": expected,
                        "replay": decision,
                        "differences": differences,
                        "psnr_only_diagnostic": psnr_only,
                        "psnr_only_footprint_matches": psnr_only["block_size"]
                        == expected["block_size"],
                        "psnr_only_full_choice_matches": (
                            psnr_only["block_size"],
                            psnr_only["preset"],
                        )
                        == (expected["block_size"], expected["preset"]),
                        "candidate_receipt_sha256": row["candidate_receipt_sha256"],
                    }
                )
        if not rows:
            raise ValueError("No development decisions to audit")
        mismatches = [row for row in rows if row["differences"]]
        result = {
            "status": "failed" if mismatches else "passed",
            "config": config,
            "config_sha256": ArtifactStore.sha256_file(self.config_path),
            "implementation_sha256": ArtifactStore.sha256_file(Path(__file__)),
            "policy_source_sha256": ArtifactStore.sha256_file(
                Path(__file__).with_name("policy.py")
            ),
            "policy_origin": policy_provenance,
            "counts": manifest["counts"],
            "images": len(rows),
            "mismatches": len(mismatches),
            "matching_fields": ["block_size", "preset", "selection_reason", "candidates_measured"],
            "branch_counts": dict(Counter(row["replay"]["selection_reason"] for row in rows)),
            "normal_images": sum(row["normal"] for row in rows),
            "strict_quality_passing_images": sum(
                row["replay"]["strict_quality_met"] for row in rows
            ),
            "psnr_only_footprint_matches": sum(row["psnr_only_footprint_matches"] for row in rows),
            "psnr_only_full_choice_matches": sum(
                row["psnr_only_full_choice_matches"] for row in rows
            ),
            "rows": rows,
            "coverage": manifest["coverage"],
            "test_opened": False,
            "wall_seconds": time.perf_counter() - started,
            "scope": (
                "Measured-quality rule replay, not model prediction accuracy; "
                "PSNR-only ablation removes other gates and is diagnostic only"
            ),
        }
        raw = Path(config["output"]) / "receipt.json"
        if raw.exists():
            raise FileExistsError("Use a new audit identity; prior measurements are immutable")
        ArtifactStore.write_json(raw, result)
        summary = {key: value for key, value in result.items() if key != "rows"}
        summary.update(
            raw_receipt=str(raw),
            raw_receipt_sha256=ArtifactStore.sha256_file(raw),
            failed_rows=mismatches,
        )
        ArtifactStore.write_json(Path(config["report"]), summary)
        if mismatches:
            raise ValueError(
                f"Native policy replay mismatched {len(mismatches)} original decisions"
            )
        return summary

    @staticmethod
    def verify_policy_origin(binding: JsonDict, row: JsonDict) -> JsonDict:
        capture = Path(row["capture_directory"]).resolve()
        raw = ArtifactStore.read_json(Path(row["candidate_directory"]).parent / "receipt.json")
        config = raw["config"]
        if Path(config["capture"]).resolve() != capture:
            raise ValueError("Candidate producer is bound to another reference capture")
        reference_path = capture / "receipt.json"
        if ArtifactStore.sha256_file(reference_path) != config["capture_receipt_sha256"]:
            raise ValueError("Original reference capture receipt changed")
        reference = ArtifactStore.read_json(reference_path)
        UnityCandidateCompletion.verify_capture_provenance(config, reference)
        run = Path(config["capture_run"]).resolve()
        phase = config["capture_phase"]
        if capture != run / "references" / f"normalized-{phase}":
            raise ValueError("Reference capture location disagrees with frozen phase")
        identity = ArtifactStore.read_json(run / "identity.json")
        phase_config = ArtifactStore.read_json(run / f"{phase}-config.json")
        project = Path(identity["project"])
        expected = (
            project / phase_config["cacheDirectory"] / "parameter_cache_detail.jsonl"
        ).resolve()
        if Path(binding["file"]).resolve() != expected or not expected.is_relative_to(
            (project / "ASTC_Cache").resolve()
        ):
            raise ValueError("Policy cache differs from the frozen original capture phase")
        baseline = UnitySearchBaseline(
            run.parents[2],
            project,
            Path(identity["editor"]),
            Path(identity["manifest"]),
            run_id=run.name,
            capture_references=True,
            source_split=identity.get("source_split", "train"),
            capture_paths=identity.get("capture_paths"),
        )
        if baseline.run_dir != run:
            raise ValueError("Original baseline run location changed")
        # Reuse the original LITE verifier, including its complete tableConfig comparison.
        verified = baseline.audit(phase)
        if verified != reference["capture_provenance"]:
            raise ValueError("Current native audit disagrees with original capture provenance")
        return {"capture_directory": str(capture), "cache_sha256": binding["sha256"], **verified}
