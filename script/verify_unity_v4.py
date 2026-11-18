"""Independently check completed V4 cells, native files, policy events and repeat identity."""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from adaptive_astc.config import JsonDict
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction, UnityTextureInput
from adaptive_astc.utils.artifacts import ArtifactStore as A
from reproductions.unity_search_baseline.v3_policy import UnityV3Policy
from reproductions.unity_search_baseline.v4_experiment import UnityV4Experiment
from reproductions.unity_search_baseline.v4_policy import UnityV4Policy, V4Options


def verify(root: Path, attempt: str, *, partial: bool, smoke: bool = False) -> JsonDict:
    experiment = UnityV4Experiment(root)
    directory = experiment.public / f"{'smoke32' if smoke else 'benchmark1000'}-{attempt}"
    if not directory.exists():
        raise FileNotFoundError("No formal V4 measurement directory exists")
    experiment.prepare()
    binding = A.read_json(directory / "execution-binding.json")
    validation_indices = binding["validation_indices"]
    image_count = 32 if smoke else 1000
    cell_count = 36 if smoke else 108
    if len(validation_indices) != image_count or len(set(validation_indices)) != image_count:
        raise ValueError("The bound image scope is incomplete or duplicated")
    for name, digest in binding["files_sha256"].items():
        if A.sha256_file(Path(name)) != digest:
            raise ValueError(f"Bound V4 file changed: {name}")
    parent_config_path = (
        root / "experiment report/unity-v3-20261113/benchmark-trained-unity-full1000-v1-config.json"
    )
    parent_config = A.read_json(parent_config_path)
    parent_sources = parent_config["execution_sources_sha256"]
    for name, digest in parent_sources.items():
        if A.sha256_file(root / name) != digest:
            raise ValueError(f"Inherited V3 execution source changed: {name}")
    offline = A.read_json(experiment.public / "offline.json")
    if A.sha256_file(Path(offline["trace_archive"])) != offline["trace_sha256"]:
        raise ValueError("Frozen offline traces changed")
    with gzip.open(offline["trace_archive"], "rt", encoding="utf-8") as stream:
        expected = json.load(stream)
    cells = []
    for file in sorted(directory.glob("*.json")):
        if file.name in {"execution-binding.json", "result.json"} or file.name.startswith(
            "failure-"
        ):
            continue
        row = A.read_json(file)
        if all(key in row for key in ["case", "scope", "mode", "repeat", "trace"]):
            cells.append(row)
    if not partial and len(cells) != cell_count:
        raise ValueError("The full declared V4 measurement grid must pass before verification")
    identities = [(c["case"]["name"], c["scope"], c["mode"], c["repeat"]) for c in cells]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate formal measurement identity")
    declared = {case["name"]: case for case in offline["controls"]}
    required_identities = set(
        itertools.product(
            declared, ("files", "pixels_ready"), ("batch", "single"), range(1 if smoke else 3)
        )
    )
    if not set(identities).issubset(required_identities):
        raise ValueError("A measured cell is outside the declared experiment matrix")
    if not partial and set(identities) != required_identities:
        raise ValueError("The complete timing matrix is missing required identities")
    hashes: dict[tuple[str, str, str], list[str]] = {}
    representative: dict[tuple[str, str, str], list[JsonDict]] = {}
    counts: dict[str, int] = defaultdict(int)
    for cell in cells:
        if cell["status"] != "passed":
            raise ValueError("Cell failed")
        for key in ["trace", "predictions"]:
            if A.sha256_file(Path(cell[key])) != cell[f"{key}_sha256"]:
                raise ValueError(f"Cell archive changed: {key}")
        with np.load(cell["predictions"], allow_pickle=False) as predictions:
            arrays = {key: predictions[key].copy() for key in predictions.files}
            for key in ["channel_mse", "channel_zero", "zero_probability"]:
                if predictions[key].shape != (image_count, 20, 4):
                    raise ValueError(f"Prediction coverage differs: {key}")
            if predictions["image_quality"].shape != (image_count, 20, 3):
                raise ValueError("Whole-image quality predictions have incorrect coverage")
        with gzip.open(cell["trace"], "rt", encoding="utf-8") as stream:
            trace = json.load(stream)
        name = cell["case"]["name"]
        if cell["case"]["options"] != declared[name]["options"]:
            raise ValueError("The measured configuration differs from selected offline parameters")
        if len(trace["choices"]) != image_count or trace["astc_sha256"] != cell["astc_sha256"]:
            raise ValueError("Native cell coverage or hash record differs")
        mode_key = (name, cell["scope"], cell["mode"])
        if hashes.setdefault(mode_key, cell["astc_sha256"]) != cell["astc_sha256"]:
            raise ValueError("Native ASTC bytes changed across repeats or timing modes")
        representative.setdefault(mode_key, trace["choices"])
        actual_queries = sum(len(choice["measured_indices"]) for choice in trace["choices"])
        if cell["timings"]["encoding_calls"] != actual_queries:
            raise ValueError("Recorded encoding count differs from actual query records")
        if cell["mode"] == "single":
            latencies = np.asarray(cell["timings"]["single_image_latencies_seconds"])
            if (
                latencies.shape != (image_count,)
                or not np.isfinite(latencies).all()
                or np.any(latencies <= 0)
            ):
                raise ValueError("Single-image latency measurements are incomplete or invalid")
            if not np.isclose(
                latencies.sum(), cell["timings"]["end_to_end_seconds"], rtol=0, atol=1e-7
            ):
                raise ValueError("Single-image latency sum differs from dataset timing")
        for position, (index, choice) in enumerate(
            zip(validation_indices, trace["choices"], strict=True)
        ):
            entry = experiment.entries[index]
            base = UnityV3Policy(entry["policy"])
            texture = UnityTextureInput(**choice["gate_context"])
            context = UnityTextureInput(**choice["prediction_context"])
            candidates = UnityQualityPrediction.candidates(
                context,
                arrays["channel_mse"][position],
                arrays["channel_zero"][position],
                arrays["image_quality"][position],
            )
            archived = (
                UnityV4Policy(base, V4Options(**cell["case"]["options"]))
                .search(
                    lambda candidate: entry["candidates"][candidate]["metrics"],
                    texture,
                    candidates,
                    prediction_texture=context,
                )
                .record()
            )
            for key in [
                "source_index",
                "selected_index",
                "measured_indices",
                "selection_reason",
                "strict_quality_met",
            ]:
                desired = index if key == "source_index" else archived[key]
                if choice[key] != desired:
                    raise ValueError(f"Frozen replay mismatch: {name} image {index} {key}")
            indices = choice["measured_indices"]
            if len(indices) != len(set(indices)):
                raise ValueError("A candidate was encoded more than once")
            if [q["selected_index"] for q in choice["queries"]] != indices:
                raise ValueError("Query records and measured candidate order differ")
            selected = choice["selected_index"]
            if selected not in indices:
                raise ValueError("The selected result was never encoded")
            counts["frozen_prediction_trace_difference_images"] += any(
                choice[key] != expected[name][index][key]
                for key in [
                    "original_start",
                    "adjusted_start",
                    "measured_indices",
                    "selected_index",
                ]
            )
            if (
                base.strict_quality(choice["selected_metrics"], texture)
                != choice["strict_quality_met"]
            ):
                raise ValueError("Final actual strict quality flag differs from metrics")
            event = choice["unlock_event"]
            if event is not None:
                block = base.candidate_set.candidate(event["before_index"])[0]
                payload = UnityV4Policy.payload(texture, block)
                if payload != event["before_payload_bytes"]:
                    raise ValueError("Unlock payload reference is incorrect")
                next_block = {12: 10, 10: 8, 8: 6}.get(block)
                if next_block != event["next_block"]:
                    raise ValueError("Unlock must inspect only the adjacent smaller block")
                if next_block is None:
                    if (
                        event["proposed_payload_bytes"] is not None
                        or event["budget_permitted"]
                        or event["replaced"]
                        or event["rescue_queries"]
                    ):
                        raise ValueError("The 6x6 terminal branch must retain its original output")
                    counts["unlock_terminal_events"] += 1
                else:
                    proposed = UnityV4Policy.payload(texture, next_block)
                    permitted = 2 * proposed <= 3 * payload
                    if (
                        proposed != event["proposed_payload_bytes"]
                        or permitted != event["budget_permitted"]
                    ):
                        raise ValueError("Unlock budget admission differs from exact payload bytes")
                    if not permitted:
                        if event["rescue_queries"] or event["replaced"]:
                            raise ValueError("A budget-blocked unlock issued a rescue query")
                        counts["unlock_budget_blocked_events"] += 1
                    if any(
                        base.candidate_set.candidate(candidate)[0] != next_block
                        for candidate in event["rescue_queries"]
                    ):
                        raise ValueError("Unlock queried a block outside its one-step rescue")
                if event["replaced"]:
                    selected_block = base.candidate_set.candidate(selected)[0]
                    if selected_block != next_block:
                        raise ValueError("Unlock selected a block outside its one-step rescue")
                    if 2 * UnityV4Policy.payload(texture, selected_block) > 3 * payload:
                        raise ValueError("Unlock violates the 50 percent payload budget")
                    if not choice["strict_quality_met"]:
                        raise ValueError("Unlock replaced an output with a failing candidate")
                    counts["unlock_replacements"] += 1
                elif selected != event["before_index"] or choice["strict_quality_met"]:
                    raise ValueError("An unsuccessful unlock did not preserve its failing output")
            counts["queries"] += len(indices)
            counts["gate_events"] += len(choice["gate_events"])
        audit = cell["output_audit"]
        manifest = Path(audit["manifest"])
        if A.sha256_file(manifest) != audit["manifest_sha256"]:
            raise ValueError("Native output manifest changed")
        outputs = A.read_json(manifest)["outputs"]
        if len(outputs) != image_count:
            raise ValueError("Native output files do not cover the complete validation set")
        for position, (index, output) in enumerate(zip(validation_indices, outputs, strict=True)):
            if output["index"] != index:
                raise ValueError("Saved native output order differs")
            for key in ["astc", "decoded_png"]:
                path = Path(output[key])
                if A.sha256_file(path) != output[f"{key}_sha256"]:
                    raise ValueError(f"Saved native output changed: {path}")
                counts["native_files"] += 1
            if output["astc_sha256"] != cell["astc_sha256"][position]:
                raise ValueError("Saved ASTC differs from the selected runtime output")
            entry = experiment.entries[index]
            candidate_set = UnityV3Policy(entry["policy"]).candidate_set
            selected_block = candidate_set.candidate(trace["choices"][position]["selected_index"])[
                0
            ]
            payload_bytes = UnityV4Policy.payload(entry["texture"], selected_block)
            if Path(output["astc"]).stat().st_size != payload_bytes + 16:
                raise ValueError("The native ASTC file size differs from its actual block geometry")
            counts["native_payload_sizes_checked"] += 1
    equivalence = None
    for scope, mode in itertools.product(("files", "pixels_ready"), ("batch", "single")):
        baseline_key = ("v3_baseline", scope, mode)
        optimized_key = ("remove_lookahead", scope, mode)
        if baseline_key not in hashes or optimized_key not in hashes:
            continue
        if hashes[baseline_key] != hashes[optimized_key]:
            raise ValueError("Removing lookahead changed ASTC bytes in the same input mode")
        for before, after in zip(
            representative[baseline_key], representative[optimized_key], strict=True
        ):
            if before["measured_indices"] != after["measured_indices"]:
                if before["measured_indices"][:-1] != after["measured_indices"]:
                    raise ValueError("Lookahead removal changed more than the terminal query")
                selected_block = before["selected_index"] // 5
                if before["measured_indices"][-1] // 5 == selected_block:
                    raise ValueError("Removed query was inside the selected block")
            counts["lookahead_equivalence_images"] += 1
        equivalence = True
    if not partial:
        result = A.read_json(directory / "result.json")
        if result["status"] != "passed" or not result["model_parameters_and_buffers_unchanged"]:
            raise ValueError("Native benchmark is incomplete or the model changed")
    report = {
        "status": "passed_partial_audit" if partial else "passed",
        "scope": "completed_cells_only"
        if partial
        else f"complete_{image_count}images_{cell_count}cells",
        "cells": len(cells),
        "control_count": len({key[0] for key in hashes}),
        "replay_prediction_source": "per_cell_actual_predictions",
        "counts": dict(counts),
        "lookahead_astc_equivalence": equivalence,
        "training_updates": 0,
        "new_encoder_calls": 0,
        "new_model_forward_calls": 0,
        "inherited_v3_execution_sources_checked": len(parent_sources),
        "inherited_v3_config_sha256": A.sha256_file(parent_config_path),
        "source_binding_sha256": A.sha256_file(directory / "execution-binding.json"),
    }
    destination = experiment.public / (
        f"smoke32-{attempt}-artifact-audit.json"
        if smoke
        else "partial-artifact-audit.json"
        if partial
        else "complete-artifact-audit.json"
    )
    A.write_json(destination, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="v3")
    parser.add_argument("--partial", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                Path(__file__).resolve().parents[1],
                args.attempt,
                partial=args.partial,
                smoke=args.smoke,
            )
        )
    )


if __name__ == "__main__":
    main()
