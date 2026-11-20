"""Evaluate the frozen V5 rule only after the new cohort passes native pixel isolation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image

from adaptive_astc.config import JsonDict
from adaptive_astc.data.unity_capture_input import UnityCaptureInputAdapter
from adaptive_astc.data.unity_tile_errors import UnityTileGrid, UnityTileViews
from adaptive_astc.evaluation.unity_dense_tile_inference import UnityDenseTileInference
from adaptive_astc.evaluation.unity_inference import UnityQualityInference
from adaptive_astc.evaluation.unity_quality import UnityQualityPrediction
from adaptive_astc.models.unity_dense_tile import UnityDenseTileRegressor
from adaptive_astc.models.unity_quality import UnityQualityRegressor
from adaptive_astc.training.unity_dense_tile_trainer import UnityDenseTileTrainer
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.runtime import ExperimentRuntime
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal
from reproductions.unity_search_baseline.capture_policy import UnityCapturePolicyBinding
from reproductions.unity_search_baseline.confirmation_capture import (
    ConfirmationSearchBaseline,
    UnityConfirmationCapture,
)
from reproductions.unity_search_baseline.quality import UnityQuality
from reproductions.unity_search_baseline.supplement import UnityASTCBackend
from reproductions.unity_search_baseline.v3_deployment import V3NativeQueries
from reproductions.unity_search_baseline.v3_policy import NativeCandidateSet, UnityV3Policy
from script.audit_unity_v5_confirmation_pixels import REPORT as PIXEL_GATE
from script.audit_unity_v5_confirmation_pixels import NativeReference
from script.prepare_unity_v5_confirmation_capture import EXECUTION, PUBLIC, ROOT, checked, record
from script.prepare_unity_v5_pixel_revision import REVISED_AUDIT

OUTPUT = EXECUTION / "formal-evaluation-v1"
REPORT = PUBLIC / "confirmation-evaluation-v1.json"
RULE = {"view": "display", "region": "content", "y_db": 28, "x_share": 0.1}
STABLE = NativeCandidateSet.full20()
CANDIDATE = STABLE.GRID.index((8, "fastest"))
BATCH_IMAGES = 16


def exact_count(
    original: NDArray[np.uint8], decoded: NDArray[np.uint8], content: NDArray[np.bool_]
) -> int:
    grid = UnityTileGrid(*original.shape[:2])
    sse = grid.squared_errors(original, decoded).sum(axis=2)
    cutoff = grid.counts() * (3 * 255**2 * 10 ** (-RULE["y_db"] / 10))
    return int(np.count_nonzero((sse > cutoff) & content))


def summarize(rows: list[JsonDict]) -> JsonDict:
    covered = [row for row in rows if row["content_tiles"]]
    tp = sum(row["predicted_flag"] and row["exact_flag"] for row in covered)
    positives = sum(row["exact_flag"] for row in covered)
    predicted = sum(row["predicted_flag"] for row in covered)
    return {
        "images": len(rows),
        "images_with_content": len(covered),
        "predicted_flags": predicted,
        "exact_flags": positives,
        "true_positive_against_exact_rule": tp,
        "precision_against_exact_rule": tp / predicted if predicted else None,
        "recall_against_exact_rule": tp / positives if positives else None,
        "mean_absolute_bad_share_error": (
            float(np.mean([abs(row["predicted_share"] - row["exact_share"]) for row in covered]))
            if covered
            else None
        ),
    }


def load_policy_batches(
    series: JsonDict, rows: list[JsonDict]
) -> tuple[
    list[UnityCapturePolicyBinding],
    list[UnityV3Policy],
]:
    result = []
    by_directory: dict[Path, tuple[UnityV3Policy, list[JsonDict]]] = {}
    for batch in series["batches"]:
        path = checked({"path": batch["config"], "sha256": batch["config_sha256"]})
        capture = UnityConfirmationCapture(ROOT, path)
        binding = UnityCapturePolicyBinding(
            capture.baseline,
            "batch",
            reference_sha256=batch["reference_receipt_sha256"],
            phase_sha256=batch["phase_receipt_sha256"],
        )
        result.append(binding)
        archive = (capture.baseline.run_dir / "references/normalized-batch").resolve()
        if archive in by_directory:
            raise ValueError("Ambiguous native policy source")
        by_directory[archive] = (UnityV3Policy(binding.policy, STABLE), capture.rows)
    policies = []
    for row in rows:
        policy, source = by_directory[Path(row["capture_directory"]).resolve()]
        original = source[row["capture_index"]]
        if row["path"] != original["path"] or row["source_sha256"] != original["source_sha256"]:
            raise ValueError("Native rule binding differs from the audited texture identity")
        policies.append(policy)
    return result, policies


def score(
    rows: list[JsonDict],
    adapter: UnityCaptureInputAdapter,
    policies: list[UnityV3Policy],
    detector: UnityDenseTileInference,
    predictors: dict[str, UnityQualityInference],
    backend: UnityASTCBackend,
    quality: UnityQuality,
) -> JsonDict:
    pair_root = OUTPUT / "blind-review"
    folder = pair_root / "confirmation" / "pairs"
    folder.mkdir(parents=True, exist_ok=False)
    metrics, pairs = [], []
    for offset in range(0, len(rows), BATCH_IMAGES):
        cohort = UnityCaptureInputAdapter(rows[offset : offset + BATCH_IMAGES], "confirmation")
        predictions = {
            name: inference.run(cohort.dataset())[0] for name, inference in predictors.items()
        }
        for pos, row in enumerate(rows[offset : offset + BATCH_IMAGES]):
            index = offset + pos
            spec, texture = adapter.textures[index], adapter.decision_inputs[index]
            policy = policies[index]
            original = NativeReference.from_row(row, "reference_png").pixels()
            dense = detector.predict(original, spec)
            screened, masks = detector.screen(original, spec, dense, [28.0], 0.1)
            selection = screened["predicted_bad"]["display"]["28.0"]["content"]
            native = np.ascontiguousarray(original[::-1])
            payload, decoded, timings = backend.encode_decode(
                native,
                8,
                "fastest",
                srgb=spec.srgb,
                need_alpha=spec.need_alpha,
            )
            reference_display = UnityTileViews.display(original, spec.need_alpha)
            decoded_display = UnityTileViews.display(decoded[::-1], spec.need_alpha)
            exact = exact_count(reference_display, decoded_display, masks["content"])
            denominator = screened["region_tiles"]["content"]
            image_id = f"{index:04d}"
            pair = {"index": index, "id": image_id, "display_sha256": {}}
            for kind, display in (("reference", reference_display), ("decoded", decoded_display)):
                path = folder / f"{image_id}-{kind}.png"
                Image.fromarray(display).save(path)
                pair["display_sha256"][path.name] = A.sha256_file(path)
            pairs.append(pair)
            queries = V3NativeQueries(native, spec, texture, policy, backend, quality)
            arms = {}
            for name, pred in predictions.items():
                candidates = UnityQualityPrediction.candidates(
                    texture,
                    pred["channel_mse"][pos],
                    pred["channel_zero"][pos],
                    pred["image_quality"][pos],
                )
                start = policy.select(candidates, texture).selected_index
                outcome = policy.search(queries.measure, texture, start)
                selected = outcome.decision.selected_index
                measured = queries.metrics[selected]
                block, preset = STABLE.candidate(selected)
                arms[name] = {
                    "prediction_start": start,
                    "selected": selected,
                    "block_size": f"{block}x{block}",
                    "preset": preset,
                    "matched_native_block": f"{block}x{block}" == row["selection"]["block_size"],
                    "strict_quality": policy.strict_quality(measured, texture),
                    "measured_indices": list(outcome.measured_indices),
                }
            metrics.append(
                {
                    "index": index,
                    "asset": row["path"],
                    "srgb_color": spec.srgb and not spec.normal,
                    "content_tiles": denominator,
                    "predicted_bad_tiles": selection["predicted_bad_tiles"][CANDIDATE],
                    "predicted_share": selection["predicted_bad_share"][CANDIDATE],
                    "predicted_flag": selection["flagged"][CANDIDATE] if denominator else None,
                    "exact_bad_tiles": exact,
                    "exact_share": exact / denominator if denominator else None,
                    "exact_flag": 10 * exact >= denominator if denominator else None,
                    "oracle_payload_bytes": len(payload),
                    "oracle_timings": timings,
                    "native_searches": arms,
                    "candidate_queries": queries.records,
                    "native_encoding_calls": 1 + queries.encode_attempts,
                }
            )
        A.write_json(OUTPUT / "progress.json", {"status": "running", "evaluated": len(metrics)})
        A.write_json(OUTPUT / "measurements.json", {"rows": metrics})
    with (folder.parent / "ratings.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("id", "visible_gradient_banding", "comment"))
        writer.writerows((row["id"], "", "") for row in pairs)
    packet = pair_root / "manifest.json"
    A.write_json(packet, {"strata": {"confirmation": {"rows": pairs}}, "human_ratings": 0})
    return {
        "screening_all": summarize(metrics),
        "screening_srgb_color": summarize([row for row in metrics if row["srgb_color"]]),
        "native_policy": {
            name: {
                "block_size_match_rate": sum(
                    row["native_searches"][name]["matched_native_block"] for row in metrics
                )
                / len(metrics),
                "strict_quality_pass_rate": sum(
                    row["native_searches"][name]["strict_quality"] for row in metrics
                )
                / len(metrics),
            }
            for name in predictors
        },
        "native_strict_regressions_from_v3": [
            row["index"]
            for row in metrics
            if row["native_searches"]["v3"]["strict_quality"]
            and not row["native_searches"]["v5"]["strict_quality"]
        ],
        "native_encoding_calls": sum(row["native_encoding_calls"] for row in metrics),
        "blind_review_packet": record(packet),
        "human_precision_and_recall": None,
        "measurements": record(OUTPUT / "measurements.json"),
    }


def main() -> None:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixel-gate-sha256", required=True)
    parser.add_argument("--revised-cohort", action="store_true")
    args = parser.parse_args()
    gate_path = REVISED_AUDIT if args.revised_cohort else PIXEL_GATE
    if not gate_path.is_file():
        raise ValueError("Wait for the complete V5 pixel isolation receipt before evaluation")
    gate_bytes = gate_path.read_bytes()
    if hashlib.sha256(gate_bytes).hexdigest() != args.pixel_gate_sha256:
        raise ValueError("V5 pixel isolation receipt differs from the approved execution binding")
    gate = json.loads(gate_bytes)
    if (
        gate["status"] != "passed"
        or bool(gate.get("revised_cohort")) != args.revised_cohort
        or gate["full_scoped_pixel_isolation_passed"] is not True
        or gate["counts"] != {"train": 10000, "validation": 1000, "confirmation": 1000}
        or gate["exact_cross_cohort_groups"]
        or gate["near_cross_cohort_groups"]
    ):
        raise ValueError("The complete 1,000-image V5 pixel isolation gate must pass first")
    preflight = A.read_json(checked(gate["execution_preflight"]))
    protocol = A.read_json(checked(preflight["protocol"]))
    if (
        preflight["confirmation_authorized_by_user"] is not True
        or protocol["screening_rule"] != RULE
    ):
        raise ValueError("Expected the authorized frozen V5 screening rule")
    series_report = A.read_json(checked(gate["series_report"]))
    rows = A.read_json(checked(gate["capture_manifest"]))["splits"]["confirmation"]
    adapter = UnityCaptureInputAdapter(rows, "confirmation")
    if len(rows) != 1000 or adapter.fingerprint != gate["input_fingerprint"]:
        raise ValueError("Formal V5 inputs differ from the pixel isolation gate")
    policy_bindings, policies = load_policy_batches(series_report, rows)

    old_contract = ROOT / "experiment report/unity-v3-20261113/confirmation-contract.json"
    if A.sha256_file(old_contract) != (
        "1ea704f218586298679af4a1bfcb2ca016cf6c38d19ce74fe47945c091a89ebc"
    ):
        raise ValueError("The historical V3 confirmation contract changed")
    historical = A.read_json(old_contract)
    parent = Path(historical["selected_system"]["checkpoint"])
    if A.sha256_file(parent) != protocol["native_v3_parent_sha256"]:
        raise ValueError("Frozen V3 control checkpoint changed")
    binaries = historical["native_binaries"]
    dll = Path(binaries["astcenc-avx2-shared.dll"])
    baseline = policy_bindings[0].baseline
    if not isinstance(baseline, ConfirmationSearchBaseline):
        raise ValueError("Expected the bound native confirmation capture backend")
    environment = baseline.capture.environment
    backend = UnityASTCBackend(dll, environment["encoder_dlls"][dll.name])
    for name, digest in {
        "build-receipt.json": "870ad425363c6e415a9504020f7e72424ed03b5aac5401a615c240d5bfb902f9",
        "unity_astc_quality.dll": (
            "445e037d1aa598527e38b0fa0ae3418a1926fe47339ddd2888a196960f6e41f3"
        ),
    }.items():
        checked({"path": binaries[name], "sha256": digest})
    quality = UnityQuality(Path(binaries["build-receipt.json"]))
    device = ExperimentRuntime.configure(20261112)
    if device.type != "cuda":
        raise RuntimeError("V5 formal confirmation requires CUDA")
    cpu = torch.device("cpu")
    v3 = UnityQualityRegressor.from_checkpoint(
        torch.load(parent, map_location=cpu, weights_only=True), cpu
    )
    dense = UnityDenseTileRegressor(
        UnityQualityRegressor.from_checkpoint(
            torch.load(parent, map_location=cpu, weights_only=True), cpu
        )
    )
    dense.load_state_dict(
        torch.load(checked(protocol["model"]), map_location=cpu, weights_only=True)["model"],
        strict=True,
    )
    if UnityDenseTileTrainer.model_hash(dense) != protocol["model_state_sha256"]:
        raise ValueError("Frozen V5 model state changed")
    v5 = UnityQualityRegressor.from_checkpoint(
        torch.load(checked(protocol["native_policy_model"]), map_location=cpu, weights_only=True),
        cpu,
    )
    if UnityDenseTileTrainer.model_hash(v5) != UnityDenseTileTrainer.model_hash(dense.native):
        raise ValueError("Frozen V5 dense and native encoders differ")
    model_hashes = {
        "v3": UnityDenseTileTrainer.model_hash(v3),
        "v5": UnityDenseTileTrainer.model_hash(v5),
    }
    paths = [
        gate_path,
        old_contract,
        parent,
        Path(__file__),
        *(Path(path) for path in binaries.values()),
    ]
    for key in ("execution_preflight", "capture_manifest", "series_report", "inputs"):
        paths.append(checked(gate[key]))
    paths.append(checked(preflight["protocol"]))
    for key in ("model", "native_policy_model", "training_report"):
        paths.append(checked(protocol[key]))
    for name, digest in protocol["source_sha256"].items():
        paths.append(checked({"path": name, "sha256": digest}))
    for binding in policy_bindings:
        binding.verify()
    inputs: dict[str, str | None] = {str(path.resolve()): A.sha256_file(path) for path in paths}
    inputs[str(gate_path.resolve())] = args.pixel_gate_sha256
    for binding in policy_bindings:
        inputs.update(binding.inputs)
    inputs.update(
        {
            str(spec.reference): row["reference_sha256"]
            for spec, row in zip(adapter.textures, rows, strict=True)
        }
    )
    seal = UnityEvaluationSeal(
        ROOT / "experiment report/.local/unity-confirmation-seals",
        {
            "schema": "unity_native_inference_v1",
            "split": "confirmation",
            "cohort_fingerprint": A.fingerprint(sorted(row["source_sha256"] for row in rows)),
            "model": {**model_hashes, "dense": protocol["model_state_sha256"]},
            "inputs_fingerprint": adapter.fingerprint,
            "policies_fingerprint": A.fingerprint(
                [binding.effective_fingerprint for binding in policy_bindings]
            ),
            "decision": {
                "rule": RULE,
                "candidate": [8, "fastest"],
                "candidate_set": "full20",
                "patch_size": 240,
                "batch": 16,
            },
            "runtime": {
                "platform": platform.platform(),
                "torch": torch.__version__,
                "device": torch.cuda.get_device_name(),
            },
            "files_sha256": inputs,
        },
    )
    if REPORT.exists():
        raise FileExistsError("Preserve the existing V5 confirmation result")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    seal.acquire()
    detector = UnityDenseTileInference(dense, device, 240, 16)
    predictors = {
        name: UnityQualityInference(model.to(device), device, 16, 0.5)
        for name, model in (("v3", v3), ("v5", v5))
    }
    result = seal.forward(
        lambda: score(rows, adapter, policies, detector, predictors, backend, quality)
    )
    if UnityDenseTileTrainer.model_hash(dense) != protocol["model_state_sha256"] or any(
        UnityDenseTileTrainer.model_hash(model) != model_hashes[name]
        for name, model in (("v3", v3), ("v5", v5))
    ):
        raise ValueError("A frozen model changed during evaluation")
    A.write_json(
        REPORT,
        {
            "status": "machine_evaluation_complete_awaiting_independent_human_ratings",
            "test_opened": True,
            "images": len(rows),
            "training_updates": 0,
            "pixel_gate": record(gate_path),
            "seal": record(seal.path),
            "screening_rule": RULE,
            "wall_seconds": time.perf_counter() - started,
            **result,
        },
    )
    print(f"V5 confirmation machine evaluation: {REPORT}")


if __name__ == "__main__":
    main()
