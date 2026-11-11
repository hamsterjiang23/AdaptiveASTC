"""Audit and report classifier compression on the captured Unity reference cohort."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from adaptive_astc.config import CLASSES
from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.gdc2023.reporting import GDCReport


class GDCReferenceReport(GDCReport):
    def write(self) -> dict[str, Any]:
        batch_path = self.evaluation / "receipt.json"
        batch = ArtifactStore.read_json(batch_path)
        binding = batch["binding"]
        initialization = binding["initialization"]
        manifest = ArtifactStore.read_json(self.run / "manifest.json")
        protocol = ArtifactStore.read_json(self.run / "protocol.json")
        content = dict(manifest)
        fingerprint = content.pop("fingerprint")
        capture = Path(binding["capture_directory"])
        descriptor = ArtifactStore.read_json(capture / "receipt.json")
        if (
            batch["schema"] != "gdc_unity_reference_v1"
            or batch["status"] != "passed"
            or batch["images"] != len(batch["per_image"])
            or not 1 <= batch["images"] <= descriptor["images"]
            or ArtifactStore.fingerprint(content) != fingerprint
            or binding["data_fingerprint"] != fingerprint
            or ArtifactStore.sha256_file(self.run / "protocol.json")
            != manifest["label_protocol_sha256"]
            or binding["encoder_sha256"] != protocol["encoder_sha256"]
            or ArtifactStore.sha256_file(capture / "receipt.json") != binding["capture_sha256"]
            or ArtifactStore.sha256_file(self.run / initialization / "best.pt")
            != binding["checkpoint_sha256"]
        ):
            raise ValueError("Unity-reference result identity or coverage changed")
        for name, digest in binding["training_files_sha256"].items():
            if (
                Path(name).name != name
                or ArtifactStore.sha256_file(self.run / initialization / name) != digest
            ):
                raise ValueError("Reference classifier training state changed")
        rows = []
        target = batch["evaluation_target_psnr"]
        for index, row in enumerate(batch["per_image"]):
            folder = self.evaluation / f"{index:05d}"
            expected = descriptor["rows"][index]
            if (
                row["path"] != expected["path"]
                or row["source_md4"] != expected["source_md4"]
                or ArtifactStore.sha256_file(folder / "receipt.json") != row["receipt_sha256"]
                or ArtifactStore.read_json(folder / "receipt.json")
                != {key: value for key, value in row.items() if key != "receipt_sha256"}
            ):
                raise ValueError("Reference result differs from its native per-image receipt")
            for name, digest in row["artifacts_sha256"].items():
                if Path(name).name != name or ArtifactStore.sha256_file(folder / name) != digest:
                    raise ValueError("Reference compression artifact changed")
            if row["artifacts_sha256"]["input.png"] != expected["artifacts_sha256"]["input.png"]:
                raise ValueError("Reference classifier input differs from Unity pixels")
            for kind, key, footprint in [
                (
                    "selected",
                    "payload_bytes",
                    tuple(int(v) for v in CLASSES[row["predicted_class"]].split("x")),
                ),
                ("fixed8", "fixed8_payload_bytes", (8, 8)),
            ]:
                actual = ASTCFile.read(folder / f"{kind}.astc")
                quality = ASTCEncoder.psnr_rgb(folder / "input.png", folder / f"{kind}.png")
                metric = row["quality"][kind]
                recorded = math.inf if metric["lossless"] else metric["rgb_psnr"]
                if (
                    actual.footprint != footprint
                    or actual.payload_bytes != row[key]
                    or not math.isclose(quality, recorded, abs_tol=1e-8)
                    or (quality > target) != metric["target_met"]
                ):
                    raise ValueError("Reference quality, footprint or actual ASTC bytes changed")
            for name in ["input.png", "unity.png", "unity.astc"]:
                if (
                    ArtifactStore.sha256_file(capture / f"{index:05d}" / name)
                    != expected["artifacts_sha256"][name]
                ):
                    raise ValueError("Captured Unity comparison pixels changed")
            unity = ASTCEncoder.psnr_rgb(
                capture / f"{index:05d}/input.png", capture / f"{index:05d}/unity.png"
            )
            rows.append(
                {
                    **row,
                    "unity_rgb_psnr": unity if math.isfinite(unity) else None,
                    "unity_lossless": math.isinf(unity),
                    "unity_target_met": unity > target,
                    "unity_payload_bytes": ASTCFile.read(
                        capture / f"{index:05d}/unity.astc"
                    ).payload_bytes,
                }
            )
        quality = {
            "target_psnr": target,
            "comparison": ">",
            "model_target_met": sum(row["quality"]["selected"]["target_met"] for row in rows),
            "fixed8_target_met": sum(row["quality"]["fixed8"]["target_met"] for row in rows),
            "unity_target_met": sum(row["unity_target_met"] for row in rows),
        }
        payload = {
            "model_bytes": sum(row["payload_bytes"] for row in rows),
            "fixed8_bytes": sum(row["fixed8_payload_bytes"] for row in rows),
            "unity_bytes": sum(row["unity_payload_bytes"] for row in rows),
        }
        costs = {
            name: sum(row["timings"][name] for row in rows)
            for name in [
                "source_rgb_seconds",
                "preprocessing_seconds",
                "inference_seconds",
                "final_encode_seconds",
                "model_pipeline_seconds",
                "fixed8_pipeline_seconds",
                "verification_seconds",
            ]
        }
        costs.update(setup_seconds=batch["setup_seconds"], wall_seconds=batch["wall_seconds"])
        summary = {
            **batch,
            "quality": quality,
            "payload": payload,
            "costs": costs,
            "protocol": {key: value for key, value in protocol.items() if key != "inputs"},
            "protocol_sha256": manifest["label_protocol_sha256"],
            "per_image": rows,
            "evaluation_receipt_sha256": ArtifactStore.sha256_file(batch_path),
        }
        self.report.mkdir(parents=True, exist_ok=True)
        ArtifactStore.write_json(self.report / f"{initialization}-unity-reference.json", summary)
        text = (
            "# GDC on Unity reference pixels\n\n"
            f"Measured {len(rows)} captured mip0 RGB inputs from the training cohort. "
            f"The frozen classifier passed strict RGB {target} dB on "
            f"{quality['model_target_met']} images, fixed8 passed on "
            f"{quality['fixed8_target_met']}, "
            "and Unity's selected payload passed on "
            f"{quality['unity_target_met']}. `[verified: accompanying JSON quality and scope]`\n\n"
            "Deployment time includes RGB input preparation, classifier preparation, inference and "
            "one final encode. The paired fixed8 time includes RGB preparation and fixed encoding. "
            "`[verified: accompanying JSON costs and per_image.timings]`\n\n"
            f"[Full measured results]({initialization}-unity-reference.json) retain "
            "per-image quality, "
            "payload, source hashes and model identity. `[verified: accompanying JSON]`\n"
        )
        (self.report / "README.md").write_text(text, encoding="utf-8")
        return {
            "status": "passed",
            "report": str(self.report),
            "quality": quality,
            "payload": payload,
            "costs": costs,
        }
