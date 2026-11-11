"""Compare existing methods on the frozen Unity64 assets with explicit protocol boundaries."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.cohort import EvaluationCohort
from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.common.upstream import BaselineGate


class ReproductionComparison:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.local = self.root / "experiment report/.local"

    @staticmethod
    def json_lines(path: Path) -> list[dict[str, Any]]:
        import json

        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "images": len(rows),
            "payload_bytes": sum(row["payload_bytes"] for row in rows),
            "source_rgb_strict35_met": sum(
                row["lossless"] or row["psnr_rgb"] > 35.0 for row in rows
            ),
            "source_rgb_at_least30_met": sum(
                row["lossless"] or row["psnr_rgb"] >= 30.0 for row in rows
            ),
            "preprocessing_decision_and_final_encode_seconds": sum(
                row["pipeline_seconds"] for row in rows
            ),
        }

    def nah(
        self, method: str, run_id: str, inputs: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        run = self.local / "reproduction-runs" / method / run_id
        public = self.root / "experiment report" / method / run_id / "summary.json"
        summary = ArtifactStore.read_json(public)
        for name, field in [
            ("images.jsonl", "images_log_sha256"),
            ("receipt.json", "receipt_sha256"),
            ("protocol.json", "protocol_sha256"),
        ]:
            if ArtifactStore.sha256_file(run / name) != summary["quality_audit"][field]:
                raise ValueError("Nah comparison artifacts differ from the audited run")
        protocol = ArtifactStore.read_json(run / "protocol.json")
        if protocol != summary["protocol"] or protocol["inputs"] != inputs:
            raise ValueError("Nah comparison input cohort or protocol differs")
        measured = self.json_lines(run / "images.jsonl")
        audited = self.json_lines(run / "quality-audit.jsonl")
        if len(measured) != len(inputs) or len(audited) != len(inputs):
            raise ValueError("Nah comparison coverage is incomplete")
        build = ArtifactStore.read_json(
            self.local / "reproduction-binaries" / method / "build-receipt.json"
        )
        executable = Path(build["executable"])
        if (
            build["commit"] != protocol["commit"]
            or ArtifactStore.sha256_file(executable) != protocol["executable_sha256"]
        ):
            raise ValueError("Nah comparison decoder differs from the frozen encoder")
        decoder = ASTCEncoder(executable, protocol["threads"])
        rows = []
        for index, (identity, row, audit) in enumerate(zip(inputs, measured, audited, strict=True)):
            if (
                not row["success"]
                or row["asset"] != identity["path"]
                or row["source_md4"] != identity["fileHash"]
                or audit["asset"] != row["asset"]
            ):
                raise ValueError("Nah comparison source identity changed")
            folder = run / f"{index:05d}"
            for name, digest in audit["artifacts_sha256"].items():
                if ArtifactStore.sha256_file(folder / name) != digest:
                    raise ValueError("Nah comparison output changed after the native decode audit")
            with tempfile.TemporaryDirectory(prefix="comparison-decode-", dir=run) as temporary:
                decoded = Path(temporary) / "selected.png"
                decoder.decode(folder / "selected.astc", decoded)
                if ArtifactStore.sha256_file(decoded) != ArtifactStore.sha256_file(
                    folder / "selected.png"
                ):
                    raise ValueError("Nah comparison ASTC differs from its fresh native decode")
            quality = ASTCEncoder.psnr_rgb(folder / "input.png", folder / "selected.png")
            expected = math.inf if row["lossless"] else row["psnr_rgb"]
            if not math.isclose(quality, expected, abs_tol=1e-8):
                raise ValueError("Nah RGB quality differs under common measurement")
            actual = ASTCFile.read(folder / "selected.astc")
            if actual.payload_bytes != row["payload_bytes"]:
                raise ValueError("Nah payload differs from its actual ASTC")
            rows.append(
                {
                    "path": row["asset"],
                    "fileHash": row["source_md4"],
                    "input_png_sha256": audit["artifacts_sha256"]["input.png"],
                    "payload_bytes": actual.payload_bytes,
                    "psnr_rgb": None if math.isinf(quality) else quality,
                    "lossless": math.isinf(quality),
                    "pipeline_seconds": row["preprocess_seconds"] + row["decision_encode_seconds"],
                    "footprint": row["footprint"],
                }
            )
        if ArtifactStore.sha256_file(executable) != protocol["executable_sha256"]:
            raise ValueError("Nah comparison decoder changed during verification")
        return rows, {
            "protocol": protocol,
            "public_summary_sha256": ArtifactStore.sha256_file(public),
            "quality_audit_sha256": ArtifactStore.sha256_file(run / "quality-audit.jsonl"),
        }

    def write(self, gdc_report: Path, destination: Path) -> dict[str, Any]:
        baseline = self.local / "unity-search-baseline-lite-rdo-off"
        BaselineGate.require(baseline / "full-receipt.json")
        paths, cohort_identity = EvaluationCohort.unity64(baseline)
        parameters = {
            row["filePath"].casefold(): row
            for row in self.json_lines(baseline / "full-parameters.jsonl")
            if "filePath" in row
        }
        inputs = [
            {"path": path, "fileHash": parameters[path.casefold()]["fileHash"]} for path in paths
        ]
        methods = {}
        for name, run_id in [
            ("nah2022_psnr_search", "source-rgb64-game"),
            ("nah2023_adaptive_astcenc", "source-rgb64-target40"),
        ]:
            rows, provenance = self.nah(name, run_id, inputs)
            methods[name] = {**self.summarize(rows), **provenance, "per_image": rows}
        gdc = ArtifactStore.read_json(gdc_report)
        relative = gdc_report.resolve().relative_to(self.root / "experiment report/gdc2023")
        if len(relative.parts) != 3:
            raise ValueError("GDC comparison requires a method/run evaluation report")
        gdc_run = self.local / "reproduction-runs/gdc2023" / relative.parts[0]
        evaluation = gdc_run / "evaluations" / relative.parts[1] / gdc["initialization"]
        raw_batch = ArtifactStore.read_json(evaluation / "receipt.json")
        if (
            gdc["status"] != "passed"
            or gdc["smoke"]
            or gdc["images"] != 64
            or gdc["split"] != "train"
            or gdc["data_use"] != "training diagnostic"
            or gdc["binding"].get("cohort_paths") != paths
            or gdc["binding"].get("cohort_identity") != cohort_identity
            or ArtifactStore.sha256_file(evaluation / "receipt.json")
            != gdc["evaluation_receipt_sha256"]
            or raw_batch["binding"] != gdc["binding"]
            or raw_batch["status"] != "passed"
            or raw_batch["images"] != 64
            or raw_batch["results"] != [
                {"index": index, "receipt_sha256": row["receipt_sha256"]}
                for index, row in enumerate(gdc["per_image"])
            ]
        ):
            raise ValueError(
                "GDC comparison requires the formal model's measured Unity64 diagnostic"
            )
        gdc_rows = []
        for index, (identity, row) in enumerate(zip(inputs, gdc["per_image"], strict=True)):
            if any(row[key] != identity[key] for key in ["path", "fileHash"]):
                raise ValueError("GDC comparison source identity differs")
            folder = evaluation / f"{index:05d}"
            if ArtifactStore.sha256_file(folder / "receipt.json") != row[
                "receipt_sha256"
            ] or ArtifactStore.read_json(folder / "receipt.json") != {
                key: value
                for key, value in row.items()
                if key not in {"receipt_sha256", "label_receipt_sha256", "offline_candidates"}
            }:
                raise ValueError("GDC comparison differs from its raw native evaluation")
            for name, digest in row["artifacts_sha256"].items():
                if ArtifactStore.sha256_file(folder / name) != digest:
                    raise ValueError("GDC comparison artifact changed")
            quality = ASTCEncoder.psnr_rgb(folder / "input.png", folder / "selected.png")
            expected = math.inf if row["lossless"] else row["rgb_psnr"]
            if not math.isclose(quality, expected, abs_tol=1e-8):
                raise ValueError("GDC RGB quality differs under common measurement")
            gdc_rows.append(
                {
                    **identity,
                    "input_png_sha256": row["artifacts_sha256"]["input.png"],
                    "payload_bytes": row["payload_bytes"],
                    "psnr_rgb": row["rgb_psnr"],
                    "lossless": row["lossless"],
                    "pipeline_seconds": row["timings"]["model_pipeline_seconds"],
                    "footprint": row["predicted_footprint"],
                }
            )
        for index in range(64):
            hashes = {item["per_image"][index]["input_png_sha256"] for item in methods.values()}
            hashes.add(gdc_rows[index]["input_png_sha256"])
            if len(hashes) != 1:
                raise ValueError("Shared Nah/GDC source RGB pixels differ")
        methods["gdc2023"] = {
            **self.summarize(gdc_rows),
            "protocol": gdc["protocol"],
            "public_report_sha256": ArtifactStore.sha256_file(gdc_report),
            "per_image": gdc_rows,
        }
        native = {
            row["asset"].casefold(): row for row in self.json_lines(baseline / "full-native.jsonl")
        }
        imported = {
            row["asset"].casefold(): row for row in self.json_lines(baseline / "full-imports.jsonl")
        }
        unity_rows = [
            {
                "path": path,
                "native": native[path.casefold()],
                "import": imported[path.casefold()],
                "parameters": parameters[path.casefold()],
            }
            for path in paths
        ]
        result = {
            "status": "passed",
            "scope": "shared source identities with method-native search protocols",
            "images": 64,
            "inputs": inputs,
            "source_rgb_png_hashes_equal": True,
            "unity_reference_pixel_equivalence": (
                "not measured; imported pixels and mip scope differ"
            ),
            "unity": {
                "search_seconds": sum(row["native"]["search_ms"] for row in unity_rows) / 1000,
                "select_and_complete_encode_seconds": sum(
                    row["native"]["select_and_encode_ms"] for row in unity_rows
                )
                / 1000,
                "import_seconds": sum(row["import"]["import_wall_ms"] for row in unity_rows) / 1000,
                "mip0_reference_payload_bytes": sum(
                    row["parameters"]["fileSize"] for row in unity_rows
                ),
                "per_image": unity_rows,
                "sources_sha256": {
                    name: ArtifactStore.sha256_file(baseline / name)
                    for name in [
                        "full-receipt.json",
                        "full-native.jsonl",
                        "full-imports.jsonl",
                        "full-parameters.jsonl",
                    ]
                },
            },
            "source_rgb_methods": methods,
            "limits": [
                "GDC shared64 is training-set resubstitution; the independent test2000 report "
                "measures generalization",
                "Unity uses imported RGBA reference pixels, LITE quality policy and full "
                "mip/face encoding",
                "Nah/GDC preserve different candidate sets, targets, encoders and presets; "
                "common RGB35 is evaluation only",
                "Common pixels and quality evaluation do not make native search "
                "objectives equivalent",
                "Do not rank these native times as equal-quality speedups; use each method's "
                "paired fixed8 control",
                "TexNN predicts internal block configurations and is evaluated separately "
                "at fixed footprints",
            ],
        }
        destination.mkdir(parents=True, exist_ok=True)
        ArtifactStore.write_json(destination / "comparison.json", result)
        lines = [
            "# Unity / Nah / GDC shared64 comparison",
            "",
            "The same 64 source-file identities are verified against the frozen Unity cohort. "
            "Nah and GDC use byte-identical full-resolution RGB PNG inputs and the same full-image "
            "RGB PSNR evaluator. Unity retains imported pixels and its native LITE policy. "
            "`[verified: comparison.json inputs, source_rgb_png_hashes_equal and "
            "unity_reference_pixel_equivalence]`",
            "",
            "| Method | Source RGB >35 dB | Payload bytes | Preprocessing, decision "
            "and final encode s |",
            "|---|---|---|---|",
        ]
        for name, measured in methods.items():
            lines.append(
                f"| {name} | {measured['source_rgb_strict35_met']}/64 | "
                f"{measured['payload_bytes']:,} | "
                f"{measured['preprocessing_decision_and_final_encode_seconds']:.3f} "
                "`[verified: comparison.json source_rgb_methods]` |"
            )
        lines += [
            "",
            "GDC shared64 is a training diagnostic. Quality targets, presets and search scope "
            "differ between methods, and Unity reference pixels are not verified equal. "
            "These times do not "
            "establish equal-quality speedup. TexNN remains in its fixed-footprint report. "
            "`[verified: comparison.json limits]`",
            "",
            "Full source identities, Unity native timings, protocols and per-image values "
            "are retained "
            "in [comparison.json](comparison.json). `[verified: accompanying JSON]`",
            "",
        ]
        (destination / "README.md").write_text("\n".join(lines), encoding="utf-8")
        return {"status": "passed", "report": str(destination), "images": 64}
