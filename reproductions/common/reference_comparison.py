"""Compare method-native decisions using byte-identical captured Unity mip0 RGB inputs."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.common.cohort import EvaluationCohort
from reproductions.common.comparison import ReproductionComparison
from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.common.upstream import BaselineGate
from reproductions.gdc2023.reference_reporting import GDCReferenceReport


class ReferenceComparison(ReproductionComparison):
    def write(self, gdc_report: Path, destination: Path) -> dict[str, Any]:
        baseline = self.local / "unity-search-baseline-lite-rdo-off"
        BaselineGate.require(baseline / "full-receipt.json")
        paths, cohort = EvaluationCohort.unity64(baseline)
        relative = gdc_report.resolve().relative_to(self.root / "experiment report/gdc2023")
        if len(relative.parts) != 3:
            raise ValueError("Expected a GDC run/evaluation report")
        gdc = ArtifactStore.read_json(gdc_report)
        run = self.local / "reproduction-runs/gdc2023" / relative.parts[0]
        evaluation = run / "evaluations" / relative.parts[1] / gdc["binding"]["initialization"]
        original_sha = ArtifactStore.sha256_file(gdc_report)
        with TemporaryDirectory(prefix="reference-audit-", dir=self.local) as temporary:
            audited = Path(temporary)
            GDCReferenceReport(self.root, run, evaluation, audited).write()
            if original_sha != ArtifactStore.sha256_file(audited / gdc_report.name):
                raise ValueError("Reference report differed from a fresh artifact audit")
        capture = Path(gdc["binding"]["capture_directory"])
        descriptor = ArtifactStore.read_json(capture / "receipt.json")
        manifest = ArtifactStore.read_json(capture / "manifest.json")
        if (
            gdc["images"] != 64
            or gdc["binding"]["cohort"] != cohort
            or descriptor["status"] != "passed"
            or descriptor["images"] != 64
            or [row["path"] for row in descriptor["rows"]] != paths
            or ArtifactStore.sha256_file(capture / "manifest.json") != descriptor["manifest_sha256"]
        ):
            raise ValueError("Reference comparison requires the complete frozen Unity64 cohort")
        inputs = [
            {"path": row["path"], "fileHash": row["fileHash"]}
            for row in manifest["splits"]["train"]
        ]
        if [row["path"] for row in inputs] != paths:
            raise ValueError("Reference RGB manifest order differs from the frozen cohort")
        methods = {}
        for method, run_id in [
            ("nah2022_psnr_search", "unity-reference64-game"),
            ("nah2023_adaptive_astcenc", "unity-reference64-target40"),
        ]:
            rows, provenance = self.nah(method, run_id, inputs)
            methods[method] = {**self.summarize(rows), **provenance, "per_image": rows}
        gdc_rows = []
        unity_rows = []
        fixed_rows = []
        native = {
            row["asset"].casefold(): row for row in self.json_lines(baseline / "full-native.jsonl")
        }
        for index, (captured, measured) in enumerate(
            zip(descriptor["rows"], gdc["per_image"], strict=True)
        ):
            folder = capture / f"{index:05d}"
            for name, digest in captured["artifacts_sha256"].items():
                if Path(name).name != name or ArtifactStore.sha256_file(folder / name) != digest:
                    raise ValueError("Captured Unity artifact changed")
            input_sha = captured["artifacts_sha256"]["input.png"]
            hashes = {item["per_image"][index]["input_png_sha256"] for item in methods.values()}
            hashes.add(measured["artifacts_sha256"]["input.png"])
            if hashes != {input_sha}:
                raise ValueError("Methods received different reference RGB PNG bytes")
            selected = native[captured["path"].casefold()]
            if any(selected[key] != captured["selection"][key] for key in ["block_size", "preset"]):
                raise ValueError("Captured Unity choice differs from the original baseline")
            quality = ASTCEncoder.psnr_rgb(folder / "input.png", folder / "unity.png")
            actual = ASTCFile.read(folder / "unity.astc")
            if actual.footprint != tuple(int(value) for value in selected["block_size"].split("x")):
                raise ValueError("Unity captured payload differs from its selected footprint")
            unity_rows.append(
                {
                    "path": captured["path"],
                    "input_png_sha256": input_sha,
                    "payload_bytes": actual.payload_bytes,
                    "psnr_rgb": None if captured["unity_lossless"] else quality,
                    "lossless": captured["unity_lossless"],
                    "pipeline_seconds": selected["search_ms"] / 1000,
                    "native_selection": selected,
                }
            )
            for rows, kind, size, timing in [
                (gdc_rows, "selected", "payload_bytes", "model_pipeline_seconds"),
                (fixed_rows, "fixed8", "fixed8_payload_bytes", "fixed8_pipeline_seconds"),
            ]:
                metric = measured["quality"][kind]
                rows.append(
                    {
                        "path": captured["path"],
                        "input_png_sha256": input_sha,
                        "payload_bytes": measured[size],
                        "psnr_rgb": metric["rgb_psnr"],
                        "lossless": metric["lossless"],
                        "pipeline_seconds": measured["timings"][timing],
                    }
                )
        methods["gdc2023"] = {
            **self.summarize(gdc_rows),
            "per_image": gdc_rows,
            "protocol": gdc["protocol"],
            "public_report_sha256": original_sha,
        }
        methods["gdc_fixed8"] = {**self.summarize(fixed_rows), "per_image": fixed_rows}
        methods["unity_lite"] = {
            **self.summarize(unity_rows),
            "per_image": unity_rows,
            "time_scope": "original baseline mip0 search including selected payload",
        }
        result = {
            "status": "passed",
            "schema": "unity_reference_comparison_v1",
            "images": 64,
            "scope": "training-cohort diagnostic on identical Unity mip0 RGB PNG bytes",
            "common_rgb_strict_target": 35.0,
            "all_input_png_hashes_equal": True,
            "capture_sha256": ArtifactStore.sha256_file(capture / "receipt.json"),
            "capture_manifest_sha256": descriptor["manifest_sha256"],
            "cohort": cohort,
            "original_source_rgb_equal": descriptor["source_rgb_equal"],
            "baseline_receipt_sha256": ArtifactStore.sha256_file(baseline / "full-receipt.json"),
            "methods": methods,
            "limits": [
                "Unity retains RGBA, sRGB/normal interpretation and LITE30 search policy. "
                "Common evaluation is RGB35",
                "Nah2022 uses full RGBA target search and thorough final encoding. "
                "Nah2023 uses sampled RGBA search. Targets and presets are saved in each protocol",
                "Unity search time comes from the original measured baseline with identical "
                "selected configurations",
                "Native objectives, presets, candidates and alpha treatment differ. "
                "Assess quality and bytes alongside time",
                "GDC training diagnostic uses the frozen source-trained model. "
                "Held-out test2000 evaluates generalization",
                "TexNN fixed-footprint internal encoder measurements are reported separately",
            ],
        }
        destination.mkdir(parents=True, exist_ok=True)
        ArtifactStore.write_json(destination / "comparison.json", result)
        lines = [
            "# Unity / Nah / GDC captured-reference comparison",
            "",
            "All methods received identical captured mip0 RGB PNG bytes on the frozen64 "
            "training cohort. "
            "Common evaluation uses full-image RGB PSNR >35 dB and actual ASTC payload. "
            "`[verified: comparison.json all_input_png_hashes_equal, "
            "common_rgb_strict_target and scope]`",
            "",
            "| Method | RGB >35 dB | Payload bytes | Measured pipeline seconds |",
            "|---|---|---|---|",
        ]
        for name, values in methods.items():
            lines.append(
                f"| {name} | {values['source_rgb_strict35_met']}/64 | "
                f"{values['payload_bytes']:,} | "
                f"{values['preprocessing_decision_and_final_encode_seconds']:.3f} "
                "`[verified: comparison.json methods]` |"
            )
        lines.extend(
            [
                "",
                "Unity timing covers the original native mip0 search and selected payload. "
                "Other rows include preprocessing, decision and final encoding. "
                "Native quality objectives, "
                "presets, alpha and color treatment remain method-specific. "
                "`[verified: comparison.json methods.unity_lite.time_scope and limits]`",
                "",
                "[Per-image results, protocols and provenance](comparison.json). "
                "`[verified: accompanying JSON]`",
                "",
            ]
        )
        (destination / "README.md").write_text("\n".join(lines), encoding="utf-8")
        return {"status": "passed", "report": str(destination), "images": 64}
