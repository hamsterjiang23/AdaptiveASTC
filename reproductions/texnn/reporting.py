"""Audit actual ASTC payloads and publish a bounded TexNN reproduction report."""

from __future__ import annotations

import math
import statistics
import uuid
from pathlib import Path
from typing import Any

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.texnn.reference import TexNNReference


class TexNNReport:
    def __init__(self, root: Path, run_id: str, evaluation_id: str) -> None:
        for name in [run_id, evaluation_id]:
            if not name or Path(name).name != name or name in {".", ".."}:
                raise ValueError("TexNN report identities must be single directory names")
        self.root = root.resolve()
        self.run_id, self.evaluation_id = run_id, evaluation_id
        self.run = self.root / "experiment report/.local/reproduction-runs/texnn" / run_id
        self.raw = self.run / "evaluations" / evaluation_id

    def write(self) -> dict[str, Any]:
        batch = ArtifactStore.read_json(self.raw / "receipt.json")
        protocol = ArtifactStore.read_json(self.raw / "protocol.json")
        if (
            batch["status"] != "passed"
            or batch["protocol_sha256"] != ArtifactStore.sha256_file(self.raw / "protocol.json")
            or batch["inputs_sha256"] != ArtifactStore.sha256_file(self.raw / "inputs.json")
        ):
            raise ValueError("TexNN batch evaluation or provenance failed")
        expected = protocol["images"] * len(protocol["footprints"]) * len(protocol["topk_settings"])
        if len(batch["results"]) != expected:
            raise ValueError("TexNN batch coverage is incomplete")
        inputs = ArtifactStore.read_json(self.raw / "inputs.json")["assets"]
        build = ArtifactStore.read_json(
            TexNNReference(self.root).artifact_dir / "build-receipt.json"
        )
        decoder = ASTCEncoder(Path(build["executable"]), threads=1)
        if ArtifactStore.sha256_file(decoder.executable) != build["sha256"]:
            raise ValueError("Report decoder differs from its recorded build")
        audit_dir = self.raw / "audits" / uuid.uuid4().hex
        audit_dir.mkdir(parents=True)
        groups: dict[str, list[dict[str, Any]]] = {}
        public_rows = []
        seen = set()
        for row in batch["results"]:
            identity = (row["size"], row["partition_topk"], row["joint_topk"], row["index"])
            path = Path(row["receipt"]).resolve()
            if (
                row["status"] != "passed"
                or identity in seen
                or row["size"] not in protocol["footprints"]
                or [row["partition_topk"], row["joint_topk"]] not in protocol["topk_settings"]
                or not 0 <= row["index"] < protocol["images"]
                or not path.is_relative_to(self.raw.resolve())
                or ArtifactStore.sha256_file(path) != row["receipt_sha256"]
            ):
                raise ValueError("TexNN per-image result or identity changed")
            seen.add(identity)
            receipt = ArtifactStore.read_json(path)
            for name, digest in receipt["artifacts_sha256"].items():
                artifact = (path.parent / name).resolve()
                if (
                    not artifact.is_relative_to(path.parent)
                    or ArtifactStore.sha256_file(artifact) != digest
                ):
                    raise ValueError("TexNN measured artifact changed")
            if (
                receipt["binaries"]["reference"] != build["sha256"]
                or receipt["binaries"]["prediction"] != build["prediction_sha256"]
                or receipt["source_sha256"] != inputs[row["index"]]["pixels_sha256"]
                or row["asset"] != inputs[row["index"]]["asset"]
                or receipt["footprint"] != [row["size"], row["size"]]
            ):
                raise ValueError("TexNN measured input or decoder differs from its protocol")
            selected = ASTCFile.read(path.parent / "selected.astc")
            control = ASTCFile.read(path.parent / "reference.astc")
            if selected != control or selected.payload_bytes != receipt["payload_bytes"]:
                raise ValueError("TexNN actual payload disagrees with its recorded dimensions")
            for kind in ["selected", "reference"]:
                decoded = audit_dir / ("-".join(str(value) for value in identity) + f"-{kind}.tga")
                decoder.decode(path.parent / f"{kind}.astc", decoded)
                if ArtifactStore.sha256_file(decoded) != receipt["artifacts_sha256"][f"{kind}.tga"]:
                    raise ValueError("Fresh TexNN decode differs from the saved reconstruction")
                quality = decoder.psnr_rgb(path.parent / "input.png", decoded)
                metric = receipt["rgb_psnr" if kind == "selected" else "reference_rgb_psnr"]
                if not (
                    (metric is None and math.isinf(quality))
                    or (metric is not None and abs(metric - quality) < 1e-8)
                ):
                    raise ValueError("Fresh TexNN PSNR disagrees with measured PSNR")
            key = f"{row['size']}x{row['size']}-top{row['partition_topk']}x{row['joint_topk']}"
            groups.setdefault(key, []).append(receipt)
            public_rows.append(
                {
                    "index": row["index"],
                    "asset": row["asset"],
                    "group": key,
                    "source_md4": inputs[row["index"]]["fileHash"],
                    "crop_box": inputs[row["index"]]["crop_box"],
                    "receipt": str(path.relative_to(self.root)).replace("\\", "/"),
                    "receipt_sha256": row["receipt_sha256"],
                    "rgb_psnr": receipt["rgb_psnr"],
                    "reference_rgb_psnr": receipt["reference_rgb_psnr"],
                    "psnr_delta_db": receipt["psnr_delta_db"],
                    "payload_bytes": receipt["payload_bytes"],
                    "native_decisions": receipt["native_decisions"],
                    "timings": receipt["timings"],
                }
            )
        summaries = {}
        for key, rows in groups.items():
            learned = sum(row["timings"]["learned_pipeline_seconds"] for row in rows)
            reference = sum(row["timings"]["reference_pipeline_seconds"] for row in rows)
            counts = {
                name: sum(row["native_decisions"][name] for row in rows)
                for name in ["blocks", "constant", "predicted", "fallback"]
            }
            deltas = [row["psnr_delta_db"] for row in rows if row["psnr_delta_db"] is not None]
            summaries[key] = {
                "images": len(rows),
                "counts": counts,
                "fallback_rate_nonconstant": counts["fallback"]
                / max(1, counts["blocks"] - counts["constant"]),
                "learned_pipeline_seconds": learned,
                "reference_pipeline_seconds": reference,
                "aggregate_relative_time": learned / reference,
                "mean_psnr_delta_db": statistics.mean(deltas) if deltas else None,
                "finite_psnr_pairs": len(deltas),
                "lossless": sum(row["lossless"] for row in rows),
                "payload_bytes": sum(row["payload_bytes"] for row in rows),
            }
        training = []
        for size in [4, 6, 8]:
            prepared = self.run / "prepared" / f"{size}x{size}" / "manifest.json"
            manifest = ArtifactStore.read_json(prepared)
            for network in ["pnn", "demnn"]:
                folder = self.run / "models" / f"{size}x{size}" / network
                packet = ArtifactStore.read_json(folder / "training_complete.json")
                if (
                    packet["status"] != "passed"
                    or ArtifactStore.sha256_file(folder / "best.pt") != packet["best_sha256"]
                ):
                    raise ValueError("TexNN completed model checkpoint changed")
                if any(
                    item["predictions"]["model_sha256"][network] != packet["best_sha256"]
                    for key, items in groups.items()
                    if key.startswith(f"{size}x{size}-")
                    for item in items
                ):
                    raise ValueError("Reported training model differs from evaluated model")
                history = ArtifactStore.read_json(folder / "history.json")["epochs"]
                best = next(item for item in history if item["epoch"] == packet["best_epoch"])
                training.append(
                    {
                        "size": size,
                        "network": network,
                        "samples": manifest["samples"],
                        "train_samples": manifest["train_samples"],
                        "validation_samples": manifest["validation_samples"],
                        "observed_joint_labels": len(manifest["joint_labels"]),
                        "partition_catalog_labels": len(manifest["partitions"]),
                        "data_fingerprint": manifest["fingerprint"],
                        "completed_epochs": packet["completed_epochs"],
                        "best_epoch": packet["best_epoch"],
                        "validation": best["validation"],
                        "attempt_training_seconds": packet["wall_seconds"],
                        "total_training_seconds": packet.get("total_training_seconds"),
                        "cumulative_training_seconds_known": packet.get("total_training_seconds")
                        is not None,
                        "total_attempt_seconds": packet["attempt_total_seconds"],
                        "best_sha256": packet["best_sha256"],
                        "receipt_sha256": ArtifactStore.sha256_file(
                            folder / "training_complete.json"
                        ),
                        "config": packet["config"],
                    }
                )
        if ArtifactStore.sha256_file(decoder.executable) != build["sha256"]:
            raise ValueError("Decoder changed during report audit")
        collection = ArtifactStore.read_json(self.run / "collection.json")
        collection_protocol = ArtifactStore.read_json(self.run / "protocol.json")
        if collection["protocol_sha256"] != ArtifactStore.sha256_file(self.run / "protocol.json"):
            raise ValueError("Collected training source protocol changed")
        summary = {
            "status": "passed",
            "run_id": self.run_id,
            "evaluation_id": self.evaluation_id,
            "scope": "paper_reimplementation_project_adaptation",
            "protocol": protocol,
            "raw_receipt_sha256": ArtifactStore.sha256_file(self.raw / "receipt.json"),
            "groups": summaries,
            "training": training,
            "data_collection": {
                "protocol": collection_protocol,
                "receipt_sha256": ArtifactStore.sha256_file(self.run / "collection.json"),
                "expected_assets": collection["expected_assets"],
                "wall_seconds": collection["wall_seconds"],
            },
            "reference_commit": build["commit"],
            "native_sources_sha256": build["native_sources_sha256"],
            "per_image": public_rows,
            "audit": {
                "fresh_decodes": expected * 2,
                "exact_reconstruction_hash_match": True,
                "source": str(audit_dir.relative_to(self.root)).replace("\\", "/"),
            },
            "costs": {
                "crop_preparation_seconds": batch["crop_preparation_seconds"],
                "model_setup_seconds": batch["model_setup_seconds"],
                "batch_wall_seconds": batch["wall_seconds"],
            },
            "limits": [
                "Bounded project training patches differ from the original 2050-texture corpus",
                "Training uses an 85/15 block split; evaluation uses separate validation images",
                "Snapshot, class mapping, endpoint padding, Gaussian scale, Adam and patience "
                "are reconstructed",
                "CLI, file exchange and debug decision logging remain timed overheads",
                "Model loading is separate from inference; Unity/Nah times are not comparable",
                "Published performance and million-block training scale are not reproduced",
            ],
        }
        destination = self.root / "experiment report/texnn" / self.run_id
        destination.mkdir(parents=True, exist_ok=True)
        ArtifactStore.write_json(destination / f"{self.evaluation_id}.json", summary)
        lines = [
            "# TexNN project adaptation",
            "",
            "The measured chain includes native labels, six Appendix-sized networks, "
            "cascaded prediction, actual ASTC encoding and decoding. This is a bounded project "
            "adaptation. Original published performance remains unverified. "
            "`[verified: accompanying JSON scope, training, audit and limits]`",
            "",
            "| Footprint / top-k | Images | Predicted / fallback blocks | Mean PSNR delta "
            "| Pipeline / reference time |",
            "|---|---|---|---|---|",
        ]
        for key, group in summaries.items():
            delta = (
                "lossless pairs"
                if group["mean_psnr_delta_db"] is None
                else f"{group['mean_psnr_delta_db']:.3f} dB"
            )
            lines.append(
                f"| {key} | {group['images']} | {group['counts']['predicted']} / "
                f"{group['counts']['fallback']} | {delta} | "
                f"{group['aggregate_relative_time']:.3f}x "
                f"`[verified: {self.evaluation_id}.json groups.{key}]` |"
            )
        lines.extend(
            [
                "",
                "The ratio includes RGB preparation, P-NN inference, native ideal-endpoint "
                "features, DEM-NN inference, prediction-file I/O, CLI starts and final encoding. "
                "Source-crop preparation, model loading, label generation, training and "
                "verification are recorded separately. Lower ratios mean less elapsed time. "
                "`[verified: accompanying JSON per_image.timings, costs and training; "
                "evaluation.py evaluate]`",
                "",
                "Fallback uses the unchanged historical full search when predicted candidates "
                "are invalid. Its time is included. Lossless pairs are excluded from finite "
                "PSNR deltas and retained per image. `[verified: native/prediction.cpp "
                "texnn_process_block; accompanying JSON groups and per_image]`",
                "",
                "## Reproduction limits",
                "",
            ]
        )
        lines += [
            f"- {limit}. `[verified: accompanying JSON limits]`" for limit in summary["limits"]
        ]
        lines.extend(
            [
                "",
                "Full per-image records, model/data fingerprints and audit results: "
                f"[{self.evaluation_id}.json]({self.evaluation_id}.json). "
                "`[verified: accompanying JSON]`",
                "",
            ]
        )
        (destination / "README.md").write_text("\n".join(lines), encoding="utf-8")
        ArtifactStore.write_json(audit_dir / "audit.json", summary["audit"])
        return {"status": "passed", "report": str(destination), "groups": summaries}
