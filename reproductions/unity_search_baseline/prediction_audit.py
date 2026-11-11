"""Audit native prediction interfaces with exact targets and a zero-channel ablation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_patch_dataset import UnityPatchDataset
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.unity_search_baseline.policy import UnitySearchPolicy
from reproductions.unity_search_baseline.policy_audit import UnityPolicyAudit


class UnityPredictionAudit:
    def __init__(self, root: Path, config_path: Path) -> None:
        self.root = root.resolve()
        self.config_path = config_path.resolve()
        self.config = ArtifactStore.read_json(config_path)
        self.policies: dict[Path, UnitySearchPolicy] = {}
        self.origins: list[JsonDict] = []
        self.sources: dict[Path, JsonDict] = {}

    def policy_for(self, row: JsonDict) -> UnitySearchPolicy:
        source = row["source_shard"]
        path = Path(source["corpus"]).resolve()
        if path not in self.sources:
            if ArtifactStore.sha256_file(path) != source["sha256"]:
                raise ValueError("Original native patch shard changed")
            shard = ArtifactStore.read_json(path)
            config = shard["config"]
            manifest_path = Path(config["candidate_manifest"])
            if ArtifactStore.sha256_file(manifest_path) != config["candidate_manifest_sha256"]:
                raise ValueError("Native candidate manifest changed")
            self.sources[path] = ArtifactStore.read_json(manifest_path)
        original = self.sources[path]["splits"][row["split"]][source["index"]]
        if (
            original["path"] != row["path"]
            or original["selection"] != row["original_selection"]
            or original["reference_sha256"] != row["reference_sha256"]
        ):
            raise ValueError("Merged native row differs from its original candidate identity")
        capture = Path(original["capture_directory"]).resolve()
        if capture not in self.policies:
            raw = ArtifactStore.read_json(
                Path(original["candidate_directory"]).parent / "receipt.json"
            )
            run = Path(raw["config"]["capture_run"])
            phase = raw["config"]["capture_phase"]
            identity = ArtifactStore.read_json(run / "identity.json")
            phase_config = ArtifactStore.read_json(run / f"{phase}-config.json")
            cache = (
                Path(identity["project"])
                / phase_config["cacheDirectory"]
                / "parameter_cache_detail.jsonl"
            )
            binding = {
                "capture_directory": str(capture),
                "file": str(cache),
                "sha256": ArtifactStore.sha256_file(cache),
            }
            self.origins.append(UnityPolicyAudit.verify_policy_origin(binding, original))
            rows = [json.loads(line) for line in cache.read_text("utf-8-sig").splitlines() if line]
            tables = [
                entry["tableConfig"]
                for entry in rows
                if entry.get("_kind") == "astc_cache_table_config"
            ]
            if len(tables) != 1:
                raise ValueError("Original phase requires exactly one native policy table")
            self.policies[capture] = UnitySearchPolicy(tables[0])
        return self.policies[capture]

    def run(self) -> JsonDict:
        started = time.perf_counter()
        output = Path(self.config["output"]).resolve()
        report = Path(self.config["report"]).resolve()
        if not output.is_relative_to(self.root / "experiment report/.local"):
            raise ValueError(
                "Raw prediction-interface audit belongs under experiment report/.local"
            )
        if report == output or report.is_relative_to(output) or report.exists():
            raise FileExistsError("Use a fresh, separate public audit report")
        output.mkdir(parents=True, exist_ok=False)
        observations = {}
        raw_rows = {}
        for split in ["train", "validation"]:
            dataset = UnityPatchDataset(
                Path(self.config["corpus"]), split, expected_sha256=self.config["corpus_sha256"]
            )
            policies = [self.policy_for(row) for row in dataset.rows]
            mse = UnityQualityPrediction.aggregate_mse(
                np.log10(dataset.mse + 1e-10),
                dataset.pixel_counts,
                dataset.image_ids,
                len(dataset.rows),
            )
            exact = np.array(
                [row["full_channel_squared_errors"] for row in dataset.rows], dtype=np.float64
            )
            exact /= np.array([row["pixel_count"] for row in dataset.rows])[:, None, None] * 255**2
            np.testing.assert_allclose(mse, exact, rtol=1e-12, atol=1e-16)
            zero = exact == 0
            quality = np.array(
                [
                    [
                        [
                            q[name] if q[name] is not None else np.nan
                            for name in UnityQualityPrediction.QUALITY_NAMES
                        ]
                        for q in row["image_quality"]
                    ]
                    for row in dataset.rows
                ],
                dtype=np.float64,
            )
            oracle, oracle_rows = UnityQualityPrediction.score(
                dataset.rows, policies, mse, zero, quality
            )
            if oracle["accuracy"] != 1 or oracle["full_choice_accuracy"] != 1:
                raise ValueError("Exact native targets did not reconstruct original decisions")
            # Tiny positive residuals make truly lossless channels participate in native PSNR.
            ablation, ablation_rows = UnityQualityPrediction.score(
                dataset.rows, policies, np.maximum(mse, 1e-9), np.zeros_like(zero), quality
            )
            observations[split] = {
                "exact_targets": oracle,
                "positive_floor_without_zero_mask": ablation,
                "max_channel_mse_aggregation_difference": float(np.max(np.abs(mse - exact))),
                "patches": len(dataset),
                "zero_full_image_channels": int(zero.sum()),
            }
            raw_rows[split] = {
                "exact_targets": oracle_rows,
                "positive_floor_without_zero_mask": ablation_rows,
            }
        result = {
            "status": "passed",
            "config": self.config,
            "config_sha256": ArtifactStore.sha256_file(self.config_path),
            "results": observations,
            "policy_origins": self.origins,
            "sources_sha256": {
                str(path): ArtifactStore.sha256_file(path)
                for path in [
                    Path(__file__),
                    self.root / "src/adaptive_astc/evaluation/unity_quality.py",
                    self.root / "src/adaptive_astc/data/unity_patch_dataset.py",
                    Path(__file__).with_name("policy.py"),
                    Path(__file__).with_name("policy_audit.py"),
                ]
            },
            "model_accuracy": None,
            "training_updates": 0,
            "test_opened": False,
            "scope": (
                "Exact-target interface verification and numeric diagnostic only; "
                "no learned predictions"
            ),
            "wall_seconds": time.perf_counter() - started,
        }
        raw_path = output / "receipt.json"
        ArtifactStore.write_json(raw_path, {**result, "rows": raw_rows})
        result.update(
            raw_receipt=str(raw_path), raw_receipt_sha256=ArtifactStore.sha256_file(raw_path)
        )
        report.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=report.parent, prefix=".prediction-audit-") as staging:
            path = Path(staging) / "report.json"
            ArtifactStore.write_json(path, result)
            report.hardlink_to(path)
        return result
