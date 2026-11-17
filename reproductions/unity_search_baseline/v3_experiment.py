"""V3 development controls, configuration and frozen-prediction candidate ablations."""

from __future__ import annotations

import gzip
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.v3_evidence import UnityV3Evidence
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy
from script.diagnose_unity_rules import UnityRuleDiagnostics


class UnityV3Experiment:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.evidence_tool = UnityV3Evidence(root)
        self.evidence = self.evidence_tool.prepare()
        self.output = self.evidence_tool.output
        self.private = self.evidence_tool.private

    def entries(self, *, smoke: bool = False) -> tuple[list[JsonDict], list[int]]:
        path = Path(self.evidence["corpus"])
        if A.sha256_file(path) != self.evidence["corpus_sha256"]:
            raise ValueError("Development corpus changed")
        corpus = A.read_json(path)
        rows = corpus["splits"]["validation"]
        indices = self.evidence_tool.smoke_indices(rows, 8) if smoke else list(range(1000))
        selected = [rows[i] for i in indices]
        diagnostic = UnityRuleDiagnostics(self.evidence_tool.plan / "evidence.json")
        return diagnostic.prepare(selected), indices

    @staticmethod
    def summary(entries: list[JsonDict], rows: list[JsonDict]) -> JsonDict:
        result = UnityRuleDiagnostics.summarize(entries, [r["selected_index"] for r in rows])
        counts = [len(row["measured_indices"]) for row in rows]
        result.update(
            mean_encoding_count=float(np.mean(counts)),
            p95_encoding_count=float(np.percentile(counts, 95)),
            max_encoding_count=max(counts),
            exhaustive_outputs=sum(row["selected_index"] % 5 == 4 for row in rows),
        )
        result["groups"] = {}
        for group in ["normal", "linear", "srgb_small", "srgb_large"]:
            indices = []
            for i, entry in enumerate(entries):
                texture = entry["texture"]
                name = (
                    "normal"
                    if texture.normal
                    else "linear"
                    if not texture.srgb
                    else "srgb_large"
                    if texture.width * texture.height >= 512**2
                    else "srgb_small"
                )
                if name == group:
                    indices.append(i)
            if indices:
                result["groups"][group] = UnityRuleDiagnostics.summarize(
                    [entries[i] for i in indices], [rows[i]["selected_index"] for i in indices]
                )
        return result

    def offline(self) -> JsonDict:
        started = time.perf_counter()
        report_path = self.output / "candidate-ablation.json"
        if report_path.exists():
            raise FileExistsError("Preserve the existing offline ablation")
        entries, _ = self.entries()
        with np.load(self.evidence["artifacts"]["best-validation.npz"], allow_pickle=False) as data:
            predictions = {key: data[key].copy() for key in data.files}
        if any(
            len(predictions[name]) != 1000
            for name in ["channel_mse", "channel_zero", "image_quality"]
        ):
            raise ValueError("Frozen prediction coverage changed")
        outputs: JsonDict = {}
        traces: JsonDict = {}
        for candidate_set in [NativeCandidateSet.full20(), NativeCandidateSet.no_exhaustive16()]:
            controls: dict[str, list[JsonDict]] = {"oracle": [], "pure": [], "forward": []}
            for index, entry in enumerate(entries):
                policy = UnityV3Policy(entry["policy"], candidate_set)
                predicted_candidates = UnityQualityPrediction.candidates(
                    entry["texture"],
                    predictions["channel_mse"][index],
                    predictions["channel_zero"][index],
                    predictions["image_quality"][index],
                )
                pure = policy.select(predicted_candidates, entry["texture"])
                oracle = policy.search(
                    lambda i: entry["candidates"][i]["metrics"], entry["texture"]
                )
                forward = policy.search(
                    lambda i: entry["candidates"][i]["metrics"],
                    entry["texture"],
                    pure.selected_index,
                )
                if candidate_set.name == "full20":
                    for field in [
                        "block_size",
                        "preset",
                        "selection_reason",
                        "candidates_measured",
                    ]:
                        if getattr(oracle.decision, field) != getattr(entry["decision"], field):
                            raise ValueError(f"Canonical20 native replay changed: {field}")
                controls["pure"].append({**asdict(pure), "measured_indices": [pure.selected_index]})
                for name, outcome in [("oracle", oracle), ("forward", forward)]:
                    controls[name].append(
                        {
                            **asdict(outcome.decision),
                            "measured_indices": list(outcome.measured_indices),
                        }
                    )
            outputs[candidate_set.name] = {
                name: self.summary(entries, rows) for name, rows in controls.items()
            }
            traces[candidate_set.name] = controls
        if (
            outputs["full20"]["pure"]["accuracy"] != 0.869
            or outputs["full20"]["forward"]["accuracy"] != 0.936
        ):
            raise ValueError("V2 frozen prediction/control system no longer reproduces")
        archive = self.private / "candidate-ablation-traces.json.gz"
        with gzip.open(archive, "xt", encoding="utf-8") as stream:
            json.dump(traces, stream)
        result = {
            "status": "passed",
            "images": 1000,
            "results": outputs,
            "original_labels": "original_unity_canonical20",
            "trace_archive": str(archive),
            "trace_sha256": A.sha256_file(archive),
            "parent_binding": str(self.evidence_tool.plan / "evidence.json"),
            "model_forward_calls": 0,
            "training_updates": 0,
            "actual_encoding_calls": 0,
            "test_opened": False,
            "wall_seconds": time.perf_counter() - started,
        }
        A.write_json(report_path, result)
        return result

    def prepare_smoke_corpus(self) -> Path:
        destination = self.private / "smoke-corpus" / "corpus.json"
        if destination.exists():
            return destination.parent
        original = A.read_json(Path(self.evidence["corpus"]))
        for split, count in [("train", 32), ("validation", 8)]:
            indices = self.evidence_tool.smoke_indices(original["splits"][split], count)
            original["splits"][split] = [original["splits"][split][i] for i in indices]
            original["counts"][split] = count
            original["patch_counts"][split] = sum(
                r["patch_count"] for r in original["splits"][split]
            )
        original["coverage"] = "partial"
        original["candidate_count"] = 40 * 20
        original["fingerprint"] = A.fingerprint(
            {"binding": original["binding"], "splits": original["splits"]}
        )
        destination.parent.mkdir(parents=True, exist_ok=False)
        A.write_json(destination, original)
        return destination.parent
