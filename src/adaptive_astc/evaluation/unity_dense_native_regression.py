"""Compare V5's native branch with the measured V3 production policy."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import torch

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_inference import UnityInferenceInput, UnityInferenceTexture
from adaptive_astc.data.unity_tile_archive import UnityTileArchive
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.v3_experiment import UnityV3Experiment
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy
from script.diagnose_unity_rules import UnityRuleDiagnostics


class UnityDenseNativeRegression:
    """Replay the real V3 policy with verified archived native candidate measurements."""

    def __init__(self, root: Path, archive: UnityTileArchive, indices: list[int]) -> None:
        if (
            not indices
            or sorted(set(indices)) != indices
            or not all(0 <= i < 1000 for i in indices)
        ):
            raise ValueError("Expected unique, sorted V5 validation indices")
        self.indices = indices
        self.archive = archive
        rows = [archive.splits["validation"][i] for i in indices]
        self.references = {Path(row["reference"]): row["reference_sha256"] for row in rows}
        self.verify_references()
        self.entries = UnityRuleDiagnostics(root / "experiment plan/V3/evidence.json").prepare(rows)
        self.dataset = UnityInferenceInput(
            [
                UnityInferenceTexture(
                    Path(row["reference"]),
                    row["import_metadata"]["srgb"],
                    row["metadata"]["is_normal"],
                    row["metadata"]["need_alpha"],
                    row["metadata"]["mip_count"],
                )
                for row in rows
            ],
            patch_size=240,
        )
        progress = A.read_json(root / "experiment report/unity-v3-20261113/progress.json")
        parent = progress["stages"]["benchmark-trained-unity-full1000-v1"]
        report = archive.read_bound_json(Path(parent["report"]), parent["report_sha256"], dict)
        if (
            report["status"] != "passed"
            or report["test_opened"] is not False
            or report["validation_indices"] != list(range(1000))
        ):
            raise ValueError(
                "Legacy V3 measured comparison is not the full ordered development set"
            )
        case = report["results"]["forward-unity-full20"]
        measurement = next(
            m
            for m in case["measurements"]
            if (m["scope"], m["mode"], m["repeat"]) == ("files", "batch", 0)
        )
        trace_path = Path(measurement["trace_archive"])
        self.trace_sha256 = measurement["trace_sha256"]
        if A.sha256_file(trace_path) != self.trace_sha256:
            raise ValueError("Legacy V3 trace digest changed")
        with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
            trace = json.load(stream)
        self.historical = [
            self.historical_row(trace, i, entry)
            for i, entry in zip(indices, self.entries, strict=True)
        ]

    def verify_references(self) -> None:
        for path, digest in self.references.items():
            if A.sha256_file(path) != digest:
                raise ValueError(f"V3 replay reference changed: {path}")

    def historical_row(self, trace: JsonDict, index: int, entry: JsonDict) -> JsonDict:
        row = trace["choices"][index]
        image = self.archive.image("validation", index)
        selected = row["selected_index"]
        candidate = image.candidates[selected]
        expected_choice = (int(row["block_size"].split("x")[0]), row["preset"])
        if (
            row["source_index"] != index
            or row["post_audit_strict_quality_met"] != entry["strict"][selected]
            or [c["metrics"] for c in image.candidates] != image.row["image_quality"]
            or [c["payload_bytes"] for c in image.candidates] != image.row["payload_bytes"]
            or (candidate["block"], candidate["preset"]) != expected_choice
            or candidate["astc_sha256"] != trace["astc_sha256"][index]
        ):
            raise ValueError(
                f"Historical V3 ASTC identity differs from candidate archive at {index}"
            )
        return {
            "index": index,
            "asset": image.row["path"],
            "start_index": row["starting_decision"]["selected_index"],
            "selected_index": selected,
            "measured_indices": row["measured_indices"],
            "strict_pass": row["post_audit_strict_quality_met"],
        }

    def run(self, model: UnityQualityRegressor, device: torch.device) -> JsonDict:
        self.verify_references()
        predictions, timing = UnityQualityInference(model, device, 16, 0.5).run(self.dataset)
        self.verify_references()
        choices: list[JsonDict] = []
        for i, (index, entry) in enumerate(zip(self.indices, self.entries, strict=True)):
            texture, measured = entry["texture"], entry["candidates"]
            policy = UnityV3Policy(entry["policy"], NativeCandidateSet.full20())
            candidates = UnityQualityPrediction.candidates(
                texture,
                predictions["channel_mse"][i],
                predictions["channel_zero"][i],
                predictions["image_quality"][i],
            )
            start = policy.select(candidates, texture).selected_index
            result = policy.search(lambda candidate: measured[candidate]["metrics"], texture, start)
            selected = result.decision.selected_index
            choices.append(
                {
                    "index": index,
                    "asset": entry["row"]["path"],
                    "start_index": start,
                    "selected_index": selected,
                    "measured_indices": list(result.measured_indices),
                    "strict_pass": bool(entry["strict"][selected]),
                }
            )
        legacy = UnityV3Experiment.summary(self.entries, self.historical)
        measured_legacy = sum(r["strict_pass"] for r in self.historical) / len(self.historical)
        if measured_legacy != legacy["actual_strict_quality_pass_rate"]:
            raise ValueError("Archived V3 strict labels disagree with real V3 measured results")
        current = UnityV3Experiment.summary(self.entries, choices)
        by_field = {
            field: [
                new["index"]
                for new, old in zip(choices, self.historical, strict=True)
                if new[field] != old[field]
            ]
            for field in ("start_index", "selected_index", "measured_indices", "strict_pass")
        }
        return {
            "status": "passed",
            "candidate_set": "full20",
            "control": "V3 files/batch/repeat0",
            "scope": "V3 native patch inference using archived native quality measurements",
            "images": len(choices),
            "validation_indices": self.indices,
            "test_opened": False,
            "control_trace_sha256": self.trace_sha256,
            "timing": timing,
            "control_metrics": legacy,
            "metrics": current,
            "changes_from_v3": by_field,
            "new_strict_regressions": [
                new["index"]
                for new, old in zip(choices, self.historical, strict=True)
                if old["strict_pass"] and not new["strict_pass"]
            ],
            "no_aggregate_regression": (
                current["accuracy"] >= legacy["accuracy"]
                and current["actual_strict_quality_pass_rate"] >= measured_legacy
            ),
            "choices": choices,
        }
