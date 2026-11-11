"""Publish per-image quality, bytes and full pipeline costs for a measured GDC run."""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

from adaptive_astc.config import CLASSES
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.cohort import EvaluationCohort
from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.gdc2023.costs import PreparationCost
from reproductions.gdc2023.dataset import GDCMeasuredDataset


class GDCReport:
    def __init__(self, root: Path, run: Path, evaluation: Path, report: Path) -> None:
        self.root, self.run = root.resolve(), run.resolve()
        self.evaluation, self.report = evaluation.resolve(), report.resolve()

    def write(self) -> dict[str, Any]:
        batch_path = self.evaluation / "receipt.json"
        batch = ArtifactStore.read_json(batch_path)
        manifest = ArtifactStore.read_json(self.run / "manifest.json")
        protocol = ArtifactStore.read_json(self.run / "protocol.json")
        collection = ArtifactStore.read_json(self.run / "collection.json")
        binding = batch["binding"]
        initialization, split = binding["initialization"], binding["split"]
        selected_rows = EvaluationCohort.rows(manifest, split, binding.get("cohort_paths"))
        if "cohort_identity" in binding:
            frozen_paths, identity = EvaluationCohort.unity64(
                self.root / "experiment report/.local/unity-search-baseline-lite-rdo-off"
            )
            if (
                split != "train"
                or binding["cohort_identity"] != identity
                or binding.get("cohort_paths") != frozen_paths
            ):
                raise ValueError("GDC shared diagnostic differs from the frozen Unity64 cohort")
        manifest_content = dict(manifest)
        fingerprint = manifest_content.pop("fingerprint")
        protocol_sha256 = ArtifactStore.sha256_file(self.run / "protocol.json")
        if (
            batch["status"] != "passed"
            or ArtifactStore.fingerprint(manifest_content) != fingerprint
            or binding["data_fingerprint"] != manifest["fingerprint"]
            or batch["protocol_sha256"] != protocol_sha256
            or manifest["label_protocol_sha256"] != protocol_sha256
            or manifest["label_collection_sha256"]
            != ArtifactStore.sha256_file(self.run / "collection.json")
            or collection["status"] != "passed"
            or collection["protocol_sha256"] != protocol_sha256
            or batch["images"] != len(selected_rows)
            or len(batch["results"]) != batch["images"]
            or ArtifactStore.sha256_file(self.run / initialization / "best.pt")
            != binding["checkpoint_sha256"]
        ):
            raise ValueError("GDC compression result coverage, protocol or model changed")
        for name, digest in binding["training_files_sha256"].items():
            if (
                Path(name).name != name
                or ArtifactStore.sha256_file(self.run / initialization / name) != digest
            ):
                raise ValueError("GDC completed training state changed after evaluation")
        seen = set()
        rows = []
        native_indices = {
            (item["split"], item["path"]): index for index, item in enumerate(protocol["inputs"])
        }
        protocol_fingerprint = ArtifactStore.fingerprint(protocol)
        for entry in batch["results"]:
            index = entry["index"]
            if index in seen or not 0 <= index < batch["images"]:
                raise ValueError("Duplicate or unexpected GDC compression sample")
            seen.add(index)
            folder = self.evaluation / f"{index:05d}"
            path = folder / "receipt.json"
            if ArtifactStore.sha256_file(path) != entry["receipt_sha256"]:
                raise ValueError("GDC measured compression receipt changed")
            measured = ArtifactStore.read_json(path)
            expected = selected_rows[index]
            if measured["status"] != "passed" or any(
                measured[key] != expected[key] for key in ["path", "fileHash"]
            ):
                raise ValueError("GDC compression sample differs from frozen evaluation input")
            required = {
                "input.png",
                "selected.astc",
                "selected.png",
                "selected.txt",
                "fixed8.astc",
                "fixed8.png",
                "fixed8.txt",
            }
            if set(measured["artifacts_sha256"]) != required:
                raise ValueError("GDC compression result is missing required artifacts")
            for name, digest in measured["artifacts_sha256"].items():
                if ArtifactStore.sha256_file(folder / name) != digest:
                    raise ValueError("GDC measured compression artifact changed")
            for kind, metric, lossless, size_key in [
                ("selected", "rgb_psnr", "lossless", "payload_bytes"),
                ("fixed8", "fixed8_rgb_psnr", "fixed8_lossless", "fixed8_payload_bytes"),
            ]:
                astc = ASTCFile.read(folder / f"{kind}.astc")
                quality = ASTCEncoder.psnr_rgb(folder / "input.png", folder / f"{kind}.png")
                if astc.payload_bytes != measured[size_key] or not (
                    (measured[lossless] and measured[metric] is None and math.isinf(quality))
                    or (
                        not measured[lossless]
                        and measured[metric] is not None
                        and abs(quality - measured[metric]) < 1e-8
                    )
                ):
                    raise ValueError("GDC saved quality or actual payload differs from its receipt")
                if (quality > protocol["target_psnr"]) != measured[
                    "target_met" if kind == "selected" else "fixed8_target_met"
                ]:
                    raise ValueError("GDC quality pass flag contradicts the strict target")
            native_index = native_indices[(split, expected["path"])]
            label_folder = self.run / "labels" / f"{native_index:05d}"
            if (
                ArtifactStore.sha256_file(label_folder / "receipt.json")
                != expected["label_receipt_sha256"]
            ):
                raise ValueError("GDC offline control receipt changed after dataset assembly")
            label = ArtifactStore.read_json(label_folder / "receipt.json")
            GDCMeasuredDataset.validate_receipt(
                label_folder,
                label,
                native_index,
                protocol["inputs"][native_index],
                protocol,
                protocol_fingerprint,
            )
            if (
                measured["label_class"] != expected["class_id"]
                or CLASSES[expected["class_id"]] != label["selected"]["name"]
                or measured["label_target_met"] != label["target_met"]
                or measured["label_payload_bytes"] != label["selected"]["payload_bytes"]
            ):
                raise ValueError("GDC evaluation label differs from its offline measurements")
            for measured_name, native_name in [
                ("input.png", "input.png"),
                ("selected.astc", f"{CLASSES[measured['predicted_class']]}.astc"),
                ("selected.png", f"{CLASSES[measured['predicted_class']]}.png"),
                ("fixed8.astc", "8x8.astc"),
                ("fixed8.png", "8x8.png"),
            ]:
                if (
                    measured["artifacts_sha256"][measured_name]
                    != label["artifacts_sha256"][native_name]
                ):
                    raise ValueError("GDC final output differs from the offline control pixels")
            rows.append(
                {
                    **measured,
                    "receipt_sha256": entry["receipt_sha256"],
                    "label_receipt_sha256": expected["label_receipt_sha256"],
                    "offline_candidates": label["candidates"],
                }
            )
        finite = [row["rgb_psnr"] for row in rows if row["rgb_psnr"] is not None]
        fixed_finite = [
            row["fixed8_rgb_psnr"] for row in rows if row["fixed8_rgb_psnr"] is not None
        ]
        pipeline = sum(row["timings"]["model_pipeline_seconds"] for row in rows)
        fixed_pipeline = sum(row["timings"]["fixed8_pipeline_seconds"] for row in rows)
        model_bytes = sum(row["payload_bytes"] for row in rows)
        fixed_bytes = sum(row["fixed8_payload_bytes"] for row in rows)
        controls = {}
        for name in CLASSES:
            candidates = [
                next(item for item in row["offline_candidates"] if item["name"] == name)
                for row in rows
            ]
            qualities = [item["rgb_psnr"] for item in candidates if not item["lossless"]]
            controls[name] = {
                "images": len(candidates),
                "target_met": sum(
                    item["lossless"] or item["rgb_psnr"] > protocol["target_psnr"]
                    for item in candidates
                ),
                "payload_bytes": sum(item["payload_bytes"] for item in candidates),
                "finite_mean_psnr": statistics.mean(qualities) if qualities else None,
                "lossless": sum(item["lossless"] for item in candidates),
                "offline_encode_seconds": sum(
                    item["timings"]["encode_seconds"] for item in candidates
                ),
                "timing_scope": "candidate encoding during parallel offline label collection",
            }
        cost_digest = binding["training_files_sha256"].get("wall-clock.json")
        if cost_digest is None:
            costs = {
                "status": "unknown_unrecorded_training",
                "all_attempts_wall_seconds": None,
                "data_fingerprint": fingerprint,
                "initialization": initialization,
                "source_sha256": None,
            }
        else:
            costs = ArtifactStore.read_json(self.run / initialization / "wall-clock.json")
            if (
                costs["status"] != "passed"
                or costs["data_fingerprint"] != fingerprint
                or costs["initialization"] != initialization
                or costs["model_sha256"] != binding["checkpoint_sha256"]
                or costs["training_complete_sha256"]
                != binding["training_files_sha256"]["training_complete.json"]
                or costs["checkpoint_last_sha256"] != binding["training_files_sha256"]["last.pt"]
            ):
                raise ValueError(
                    "GDC training cost does not belong to the evaluated training/model"
                )
            costs["source_sha256"] = cost_digest
        preparation_digest = binding.get("preparation_process_sha256")
        preparation: dict[str, Any] = {
            "status": "unknown_unrecorded_process_wall",
            "wall_seconds": None,
            "source_sha256": None,
        }
        if preparation_digest is not None:
            preparation_path = self.run / "preparation-process.json"
            if ArtifactStore.sha256_file(preparation_path) != preparation_digest:
                raise ValueError("Data preparation timing changed after evaluation")
            recorded = PreparationCost.load_optional(preparation_path)
            if recorded is None:
                preparation = {
                    "status": "unknown_incomplete_process_record",
                    "wall_seconds": None,
                    "source_sha256": preparation_digest,
                }
            else:
                if (
                    recorded["protocol_sha256"] != protocol_sha256
                    or recorded["collection_sha256"]
                    != ArtifactStore.sha256_file(self.run / "collection.json")
                    or recorded["manifest_sha256"]
                    != ArtifactStore.sha256_file(self.run / "manifest.json")
                ):
                    raise ValueError("Data preparation timing differs from the evaluated dataset")
                preparation = {**recorded, "source_sha256": preparation_digest}
        summary = {
            "status": "passed",
            "scope": batch["scope"],
            "data_use": "training diagnostic" if split == "train" else "held-out " + split,
            "smoke": manifest["smoke"],
            "initialization": initialization,
            "split": split,
            "images": len(rows),
            "data_fingerprint": manifest["fingerprint"],
            "binding": binding,
            "protocol": protocol,
            "evaluation_receipt_sha256": ArtifactStore.sha256_file(batch_path),
            "quality": {
                "target_psnr": protocol["target_psnr"],
                "comparison": ">",
                "model_target_met": sum(row["target_met"] for row in rows),
                "model_violation_rate": sum(not row["target_met"] for row in rows) / len(rows),
                "fixed8_target_met": sum(row["fixed8_target_met"] for row in rows),
                "label_target_met": sum(row["label_target_met"] for row in rows),
                "model_finite_mean_psnr": statistics.mean(finite) if finite else None,
                "model_finite_std_psnr": statistics.pstdev(finite) if finite else None,
                "fixed8_finite_mean_psnr": statistics.mean(fixed_finite) if fixed_finite else None,
                "model_lossless": sum(row["lossless"] for row in rows),
                "fixed8_lossless": sum(row["fixed8_lossless"] for row in rows),
                "classification_accuracy": sum(
                    row["predicted_class"] == row["label_class"] for row in rows
                )
                / len(rows),
            },
            "payload": {
                "model_bytes": model_bytes,
                "fixed8_bytes": fixed_bytes,
                "label_best_bytes": sum(row["label_payload_bytes"] for row in rows),
                "model_to_fixed8_ratio": model_bytes / fixed_bytes,
            },
            "offline_fixed_footprints": controls,
            "costs": {
                "data_preparation_process": preparation,
                "label_collection_wall_seconds": collection["wall_seconds"],
                "label_collection_workers": collection["workers"],
                "training": costs,
                "evaluation_setup_seconds": batch["setup_seconds"],
                "evaluation_wall_seconds": batch["wall_seconds"],
                "source_rgb_seconds": sum(row["timings"]["source_rgb_seconds"] for row in rows),
                "classifier_preprocessing_seconds": sum(
                    row["timings"]["classifier_preprocessing_seconds"] for row in rows
                ),
                "inference_seconds": sum(row["timings"]["inference_seconds"] for row in rows),
                "final_encode_seconds": sum(row["timings"]["final_encode_seconds"] for row in rows),
                "model_pipeline_seconds": pipeline,
                "fixed8_pipeline_seconds": fixed_pipeline,
                "model_to_fixed8_time_ratio": pipeline / fixed_pipeline,
                "verification_seconds": sum(row["timings"]["verification_seconds"] for row in rows),
            },
            "per_image": rows,
            "limits": [
                "Four square footprints, astcenc3.3 medium, source RGB8 and ResNet18 "
                "are project reconstructions",
                "Original talk candidate set, hyperparameters, corpus and published performance "
                "are not reproduced",
                "Single final encoding retains quality violations without re-encoding",
                "Model is uncalibrated; probability calibration is a separate experiment",
                "Input profile, metric, encoder and timing differ from the Unity LITE baseline",
                "Preprocessing, inference and final encoding are timed; setup and verification "
                "are separate",
                "Classification and bytes do not establish equal-quality production acceptance",
                "Fixed-footprint offline candidate times include concurrent label workers and "
                "are not paired deployment latency controls",
                "A train-split shared cohort is a resubstitution diagnostic, not generalization",
            ],
        }
        self.report.mkdir(parents=True, exist_ok=True)
        ArtifactStore.write_json(self.report / f"{initialization}-{split}.json", summary)
        text = (
            "# GDC measured compression loop\n\n"
            f"Measured {len(rows)} {split} images with the {initialization} model. "
            f"The strict target passed for {summary['quality']['model_target_met']} images. "
            f"Actual payload / fixed8 is {model_bytes / fixed_bytes:.4f}; "
            f"complete model pipeline / fixed8 time is {pipeline / fixed_pipeline:.4f}. "
            "`[verified: accompanying JSON quality, payload and costs]`\n\n"
            "Quality violations are retained. This is a source-RGB four-square reconstruction; "
            "the original published results and a direct Unity speedup are unverified. "
            "`[verified: accompanying JSON protocol and limits]`\n\n"
            "| Offline fixed footprint | Strict target passed | Actual payload bytes |\n"
            "|---|---|---|\n"
            + "".join(
                f"| {name} | {control['target_met']}/{control['images']} | "
                f"{control['payload_bytes']:,} "
                "`[verified: accompanying JSON offline_fixed_footprints]` |\n"
                for name, control in controls.items()
            )
            + "\nAll controls use the same full-resolution RGB inputs. Offline encoding times "
            "come from parallel label collection; the separately measured fixed8 pipeline "
            "remains the deployment latency control. "
            "`[verified: accompanying JSON protocol, offline_fixed_footprints and costs]`\n\n"
            f"Full per-image results and costs: [{initialization}-{split}.json]"
            f"({initialization}-{split}.json). `[verified: accompanying JSON]`\n"
        )
        (self.report / "README.md").write_text(text, encoding="utf-8")
        return {
            "status": "passed",
            "report": str(self.report),
            "quality": summary["quality"],
            "payload": summary["payload"],
            "costs": summary["costs"],
        }
