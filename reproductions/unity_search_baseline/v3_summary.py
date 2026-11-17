"""Select one V3 development system and freeze its validation identity for review."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import time
from pathlib import Path

import numpy as np
import torch
from torch.version import cuda as cuda_runtime

from adaptive_astc.config import JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore as A
from adaptive_astc.utils.unity_evaluation_seal import UnityEvaluationSeal
from reproductions.unity_search_baseline.deployment import UnityDeploymentResult
from reproductions.unity_search_baseline.v3_benchmark import UnityV3Benchmark
from reproductions.unity_search_baseline.v3_experiment import UnityV3Experiment
from reproductions.unity_search_baseline.v3_input_diagnostics import UnityV3InputDiagnostics


class UnityV3Summary:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.experiment = UnityV3Experiment(root)
        self.public = self.experiment.output

    def audit_selected_output(self, selected: JsonDict) -> JsonDict:
        """Independently measure selected-output auditing and ASTC/PNG file writing."""
        benchmark = A.read_json(Path(selected["report"]))
        case = benchmark["results"][selected["name"]]
        first = next(
            m for m in case["measurements"] if m["scope"] == "files" and m["mode"] == "batch"
        )
        trace_path = Path(first["trace_archive"])
        if A.sha256_file(trace_path) != first["trace_sha256"]:
            raise ValueError("Selected-output audit needs the original benchmark trace")
        with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
            trace = json.load(stream)
        config = A.read_json(Path(selected["config"]))
        inputs = Path(config["output"]) / selected["name"] / "files-batch-0"
        containers = [(inputs / f"{index:04}.astc").read_bytes() for index in range(1000)]
        if [hashlib.sha256(value).hexdigest() for value in containers] != trace["astc_sha256"]:
            raise ValueError("Selected ASTC files changed after the real benchmark")
        worker = UnityV3Benchmark(self.root, Path(selected["config"]))
        started = time.perf_counter()
        worker.prepare()
        preparation_seconds = time.perf_counter() - started
        output = self.experiment.private / "selected-output-audit"
        result = UnityDeploymentResult(containers, trace["choices"], None, {})
        started = time.perf_counter()
        metrics = worker.audit(result, case["case"], output)
        audit_and_write_seconds = time.perf_counter() - started
        worker.verify()
        if metrics != selected["metrics"]:
            raise ValueError("Selected-output audit changed the final validation metrics")
        files = {
            str(path): A.sha256_file(path)
            for index in range(1000)
            for extension in ["astc", "png"]
            for path in [output / f"{index:04}.{extension}"]
        }
        record = {
            "status": "passed",
            "images": 1000,
            "source_trace": str(trace_path),
            "source_trace_sha256": first["trace_sha256"],
            "prepare_seconds": preparation_seconds,
            "audit_and_astc_png_write_seconds": audit_and_write_seconds,
            "scope": "Separate post-selection measurement, excluded from system timing",
            "files_sha256": files,
            "metrics": metrics,
            "test_opened": False,
        }
        A.write_json(self.public / "selected-output-audit.json", record)
        return record

    def confirmation_registry_status(self, readiness: JsonDict) -> JsonDict:
        cohort = A.fingerprint(
            {
                "reservation": readiness["registry_parent_manifest_sha256"],
                "split": "confirmation",
            }
        )
        registry = self.root / "experiment report/.local/unity-confirmation-seals"
        path = registry / cohort / "seal.json"
        return {
            "registry": str(registry),
            "cohort_fingerprint": cohort,
            "seal_path": str(path),
            "existing_seal": path.exists(),
            "existing_seal_sha256": A.sha256_file(path) if path.exists() else None,
            "available_for_new_contract": not path.exists(),
        }

    def run(self) -> JsonDict:
        destination = self.public / "summary.json"
        if destination.exists():
            raise FileExistsError("Keep the original V3 selection result")
        reports = [
            self.public / f"{name}.json"
            for name in [
                "benchmark-v2-full1000-v1",
                "benchmark-trained-unity-full1000-v1",
                "benchmark-trained-source_aligned-full1000-v1",
            ]
        ]
        systems: list[JsonDict] = []
        controls: list[JsonDict] = []
        parents: dict[str, str] = {}
        training: JsonDict = {}
        for mode in ["unity", "source_aligned"]:
            training[mode] = {}
            for stage in ["full", "head"]:
                name = f"train-{mode}-{stage}-full-v1"
                path = self.public / f"{name}.json"
                record = A.read_json(path)
                receipt_path = self.experiment.private / "jobs" / name / "receipt.json"
                receipt = A.read_json(receipt_path)
                if (
                    record["status"] != "completed"
                    or record["test_opened"]
                    or len(record["history"]) != 30
                    or record["training_updates"] <= 0
                    or record["checkpoint_audit"]["status"] != "passed"
                    or receipt["status"] != "passed"
                ):
                    raise ValueError("Require the completed paired full30 and head30 runs")
                training[mode][stage] = {
                    "process_seconds": receipt["wall_seconds"],
                    "trainer_seconds": record["wall_seconds"],
                    "training_updates": record["training_updates"],
                    "report": str(path),
                }
                parents[str(path)] = A.sha256_file(path)
                parents[str(receipt_path)] = A.sha256_file(receipt_path)
        unity_head = A.read_json(self.public / "train-unity-head-full-v1.json")
        repeated_predictions = Path(unity_head["config"]["output"]) / "best-validation.npz"
        frozen_predictions = Path(self.experiment.evidence["artifacts"]["best-validation.npz"])
        repeated_sha = A.sha256_file(repeated_predictions)
        if repeated_sha != unity_head["checkpoint_audit"]["predictions_sha256"]:
            raise ValueError("Unity paired-control predictions changed after checkpoint replay")
        frozen_sha = A.sha256_file(frozen_predictions)
        reproduction = {
            "images": 1000,
            "frozen_predictions": str(frozen_predictions),
            "frozen_predictions_sha256": frozen_sha,
            "retrained_predictions": str(repeated_predictions),
            "retrained_predictions_sha256": repeated_sha,
            "validation_predictions_bit_identical": repeated_sha == frozen_sha,
        }
        parents[str(repeated_predictions)] = repeated_sha
        parents[str(frozen_predictions)] = frozen_sha
        for report_path in reports:
            report = A.read_json(report_path)
            if report["status"] != "passed" or report["images"] != 1000 or report["test_opened"]:
                raise ValueError("Every formal comparison must cover the frozen validation1000")
            parents[str(report_path)] = A.sha256_file(report_path)
            config_path = report_path.with_name(report_path.stem + "-config.json")
            config = A.read_json(config_path)
            model_label = {
                "benchmark-v2-full1000-v1": "V2冻结权重",
                "benchmark-trained-unity-full1000-v1": "Unity输入配对训练权重",
                "benchmark-trained-source_aligned-full1000-v1": "原图输入配对训练权重",
            }[report_path.stem]
            for name, case in report["results"].items():
                measurements = [
                    r
                    for r in case["measurements"]
                    if r["scope"] == "files" and r["mode"] == "batch"
                ]
                if len(measurements) != 3:
                    raise ValueError("Each candidate needs three real primary timing repeats")
                metrics = measurements[0]["metrics"]
                latency: JsonDict = {}
                for timing_scope in ["files", "pixels_ready"]:
                    repeats = [
                        m
                        for m in case["measurements"]
                        if m["scope"] == timing_scope and m["mode"] == "single"
                    ]
                    if len(repeats) != 3:
                        raise ValueError("Require three independent sequential latency repeats")
                    summaries = []
                    for measured in repeats:
                        values = np.asarray(measured["timings"]["single_image_latencies_seconds"])
                        if values.shape != (1000,):
                            raise ValueError("Single-image latency must cover validation1000")
                        summaries.append(
                            {
                                "mean_ms": float(values.mean() * 1000),
                                "median_ms": float(np.median(values) * 1000),
                                "p95_ms": float(np.percentile(values, 95) * 1000),
                            }
                        )
                    latency[timing_scope] = summaries
                controls.append(
                    {
                        "name": name,
                        "model_label": model_label,
                        "arm": case["case"]["arm"],
                        "report": str(report_path),
                        "config": str(config_path),
                        "checkpoint": config.get(
                            "checkpoint", self.experiment.evidence["artifacts"]["best.pt"]
                        ),
                        "checkpoint_sha256": config.get(
                            "checkpoint_sha256",
                            self.experiment.evidence["files_sha256"][
                                self.experiment.evidence["artifacts"]["best.pt"]
                            ],
                        ),
                        "input_mode": case["case"]["input_mode"],
                        "candidate_set": case["case"]["candidate_set"],
                        "metrics": metrics,
                        "single_image_latency_ms": latency,
                        "median_file_batch_seconds": case["files_batch_median_seconds"],
                        "change_count": int("trained" in report_path.stem)
                        + int(case["case"]["input_mode"] != "unity")
                        + int(case["case"]["candidate_set"] != "full20"),
                    }
                )
                if case["case"]["arm"] == "forward":
                    systems.append(controls[-1])
        selected = min(
            systems,
            key=lambda r: (
                -r["metrics"]["accuracy"],
                r["median_file_batch_seconds"],
                r["metrics"]["payload_bytes"],
                r["change_count"],
            ),
        )
        config = A.read_json(Path(selected["config"]))
        benchmark = A.read_json(Path(selected["report"]))
        files = dict(benchmark["files_sha256"]) | parents
        files[str(Path(__file__).resolve())] = A.sha256_file(Path(__file__))
        entries, _ = self.experiment.entries()
        historical_capture: JsonDict = {
            "images": len(entries),
            "cache_hits": sum(e["row"]["original_selection"]["cache_hit"] for e in entries),
            "search_executed": sum(
                e["row"]["original_selection"]["search_executed"] for e in entries
            ),
            "source": self.experiment.evidence["corpus"],
            "scope": "Historical Unity capture timings in original_selection, in milliseconds",
        }
        for field in ["search_ms", "format_ms", "select_and_encode_ms"]:
            values = np.array([e["row"]["original_selection"][field] for e in entries])
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError("Historical Unity capture timing is incomplete")
            historical_capture[field] = {
                "count": len(values),
                "total_seconds": float(values.sum() / 1000),
                "mean_ms": float(values.mean()),
                "median_ms": float(np.median(values)),
                "p95_ms": float(np.percentile(values, 95)),
            }
        diagnostics = UnityV3InputDiagnostics(self.root).run(entries, controls)
        diagnostic_path = self.public / "input-diagnostics.json"
        files[str(diagnostic_path)] = A.sha256_file(diagnostic_path)
        benchmark_reports = {str(path): A.read_json(path) for path in reports}
        for control in controls:
            record = benchmark_reports[control["report"]]["results"][control["name"]]
            measured = next(
                m for m in record["measurements"] if m["scope"] == "files" and m["mode"] == "batch"
            )
            trace = Path(measured["trace_archive"])
            if A.sha256_file(trace) != measured["trace_sha256"]:
                raise ValueError("A completed real-encoding query trace changed")
            with gzip.open(trace, "rt", encoding="utf-8") as stream:
                choices = json.load(stream)["choices"]
            if len(choices) != len(entries):
                raise ValueError("Input-change group comparisons must cover every validation asset")
            control["input_change_groups"] = {
                name: self.experiment.summary(
                    [entries[i] for i in indices], [choices[i] for i in indices]
                )
                for name, indices in diagnostics["group_indices"].items()
            }
        diagnostic_source = Path(__file__).with_name("v3_input_diagnostics.py")
        files[str(diagnostic_source)] = A.sha256_file(diagnostic_source)
        for diagnostic in diagnostics["controls"]:
            files[diagnostic["predictions"]] = diagnostic["predictions_sha256"]
            files[diagnostic["checkpoint"]] = diagnostic["checkpoint_sha256"]
        output_audit = self.audit_selected_output(selected)
        output_audit_path = self.public / "selected-output-audit.json"
        files[str(output_audit_path)] = A.sha256_file(output_audit_path)
        identity: JsonDict = {
            "schema": "unity_native_inference_v1",
            "split": "validation",
            "cohort_fingerprint": A.fingerprint([e["row"]["path"] for e in entries]),
            "model": {
                "checkpoint": selected["checkpoint"],
                "sha256": A.sha256_file(Path(selected["checkpoint"])),
            },
            "inputs_fingerprint": A.fingerprint(
                {
                    "input_mode": selected["input_mode"],
                    "source_manifest": config["source_manifest"],
                    "references": [e["row"]["reference_sha256"] for e in entries],
                }
            ),
            "policies_fingerprint": A.fingerprint([e["policy"].table for e in entries]),
            "decision": {
                "arm": "forward",
                "start": "predicted_candidate_index",
                "candidate_set": selected["candidate_set"],
                "zero_threshold": 0.5,
                "margin_psnr_db": 0,
                "margin_ssim_db": 0,
                "margin_angle_deg": 0,
            },
            "runtime": {
                "python": platform.python_version(),
                "torch": torch.__version__,
                "cuda": cuda_runtime,
                "cudnn": torch.backends.cudnn.version(),
                "gpu": torch.cuda.get_device_name(),
                "cpu_logical_count": os.cpu_count(),
                "torch_intraop_threads": torch.get_num_threads(),
                "torch_interop_threads": torch.get_num_interop_threads(),
                "encoder_settings": "Bound UnityASTCBackend call defaults and encoder DLL SHA",
                "inference_batch_size": 16,
                "benchmark_config": selected["config"],
                "benchmark_config_sha256": A.sha256_file(Path(selected["config"])),
                "encoding_scope": "mip0",
                "primary_timing": "files_batch",
            },
            "files_sha256": files,
        }
        seal = UnityEvaluationSeal(self.experiment.private / "selected-validation-seal", identity)
        seal.acquire()
        readiness_path = (
            self.experiment.evidence_tool.v2 / "forward-system-protocol-readiness-v4.json"
        )
        readiness = A.read_json(readiness_path)
        if readiness["test_opened"] or readiness["formal_confirmation_executed"]:
            raise ValueError("Held-out cohort was opened during V3 development")
        registry_status = self.confirmation_registry_status(readiness)
        contract = {
            "schema": "unity-v3-confirmation-contract-v1",
            "status": (
                "prepared_for_execution_review"
                if registry_status["available_for_new_contract"]
                else "existing_cohort_contract_requires_review"
            ),
            "confirmation_registry": registry_status,
            "confirmation_execution_authorized": False,
            "selected_system": selected,
            "validation_seal": str(seal.path),
            "validation_seal_fingerprint": seal.fingerprint,
            "cohort": {
                "images": 2000,
                "readiness": str(readiness_path),
                "readiness_sha256": A.sha256_file(readiness_path),
                "native_input_fingerprint": readiness["native_input_fingerprint"],
                "registry_parent_manifest_sha256": readiness["registry_parent_manifest_sha256"],
                "native_rule_contexts": readiness["native_policy_contexts"],
            },
            "reference_labels": "original_unity_canonical20",
            "primary_acceptance": {"system_block_top1_min": 0.90},
            "source_input": {
                "mode": selected["input_mode"],
                "pixel_format": "RGBA8",
                "target_size": "explicit captured target dimensions",
                "resize": "Pillow BICUBIC when source_aligned",
                "prediction_metadata": "source-derived black/alpha plus explicit importer flags",
            },
            "quality_gate": "actual Unity reference pixels and original native thresholds",
            "native_binaries": self.experiment.evidence["binaries"],
            "timing": {
                "warmups": 1,
                "repetitions": 3,
                "scopes": config["scopes"],
                "measurement_modes": config["measurement_modes"],
            },
            "test_opened": False,
        }
        A.write_json(self.public / "confirmation-contract.json", contract)
        result = {
            "status": "completed_development",
            "controls": controls,
            "training_costs": training,
            "unity_input_retraining_reproduction": reproduction,
            "input_diagnostics": diagnostics,
            "selected_output_audit": output_audit,
            "historical_unity_capture_timings": historical_capture,
            "systems": systems,
            "recommendation": selected,
            "development_admission_passed": selected["metrics"]["accuracy"] >= 0.90,
            "parents_sha256": parents,
            "validation_seal_fingerprint": seal.fingerprint,
            "confirmation_execution_authorized": False,
            "test_opened": False,
        }
        A.write_json(destination, result)
        self.write_markdown(result)
        verification_path = self.public / "verification.json"
        verification = A.read_json(verification_path) if verification_path.exists() else {}
        source_paths = {Path(path) for path in verification.get("source_sha256", {})}
        source_paths.update([Path(__file__).resolve(), diagnostic_source.resolve()])
        sources = {str(path): A.sha256_file(path) for path in sorted(source_paths)}
        verification.update(
            status="passed_development_execution",
            summary_sha256=A.sha256_file(destination),
            full_validation_images=1000,
            paired_training_complete=True,
            confirmation_execution_authorized=False,
            source_sha256=sources,
            new_python_files=len(sources),
            selected_output_audit="passed",
        )
        A.write_json(verification_path, verification)
        return result

    def write_markdown(self, result: JsonDict) -> None:
        selected = result["recommendation"]
        source = A.read_json(self.public / "source-input-audit.json")
        ablation = A.read_json(self.public / "candidate-ablation.json")["results"]
        source_native = next(
            row for row in result["systems"] if row["name"] == "forward-source_native-full20"
        )
        source_trained = next(
            row
            for row in result["systems"]
            if row["model_label"] == "原图输入配对训练权重"
            and row["candidate_set"] == "full20"
        )
        cut = next(
            row
            for row in result["systems"]
            if row["model_label"] == "V2冻结权重"
            and row["name"] == "forward-unity-no_exhaustive16"
        )
        lines = [
            "# V3 开发实验结果",
            "",
            f"推荐系统使用**{selected['model_label']}**，"
            f"输入为`{selected['input_mode']}`，候选集合为`{selected['candidate_set']}`，"
            f"1000张开发验证图的块大小准确率为 **{selected['metrics']['accuracy']:.1%}**，"
            "文件到mip0 ASTC的批量中位耗时为 "
            f"**{selected['median_file_batch_seconds']:.2f} ms／图**。"
            "`[verified: summary.json recommendation]`",
            "",
            "计时期间观察到并发Blender CPU负载。各轮原始计时及逐图延迟均已保存，"
            "运行时负载观测见resource-observations.jsonl。"
            "`[verified: resource-observations.jsonl；benchmark报告各轮measurements]`",
            "",
            "| 系统 | 原Unity标签Top-1 | 严格质量通过 | 平均编码次数 | 批量摊销ms／图 |",
            "|---|---|---|---|---|",
        ]
        for row in result["systems"]:
            metrics = row["metrics"]
            lines.append(
                f"| {row['model_label']}／{row['name']} | {metrics['accuracy']:.1%} | "
                f"{metrics['actual_strict_quality_pass_rate']:.1%} | "
                f"{metrics['mean_encoding_count']:.3f} | {row['median_file_batch_seconds']:.2f} "
                f"`[verified: {Path(row['report']).name} results.{row['name']}]` |"
            )
        lines += [
            "",
            "冻结V2权重使用原尺寸源图时，"
            f"续搜准确率为{source_native['metrics']['accuracy']:.1%}，"
            f"平均编码{source_native['metrics']['mean_encoding_count']:.3f}次；"
            "尺寸对齐原图经过配对训练后，"
            f"续搜准确率为{source_trained['metrics']['accuracy']:.1%}，"
            f"平均编码{source_trained['metrics']['mean_encoding_count']:.3f}次，"
            f"批量摊销耗时为{source_trained['median_file_batch_seconds']:.2f}ms／图。"
            "`[verified: summary.json systems 对应原图输入条目]`",
            "",
            "冻结V2权重删除exhaustive后，"
            f"续搜准确率为{cut['metrics']['accuracy']:.1%}，"
            f"批量摊销耗时为{cut['median_file_batch_seconds']:.2f}ms／图，"
            f"相对原标签有{cut['metrics']['quality_regression_images']}张严格质量回退。"
            "16候选规则标签与原20候选的块大小变化率为"
            f"{1 - ablation['no_exhaustive16']['oracle']['accuracy']:.1%}。"
            "`[verified: summary.json systems 对应冻结V2的16候选条目；"
            "candidate-ablation.json results.no_exhaustive16.oracle]`",
            "",
            "## 原图训练与预测",
            "",
            "| 模型／输入 | 纯预测Top-1 | 近阈值PSNR RMSE dB | 黑像素比例变化图数 |",
            "|---|---|---|---|",
        ]
        for index, row in enumerate(result["input_diagnostics"]["controls"]):
            metrics = row["metrics"]
            rmse = metrics["color_near_threshold_rmse_db"]
            value = "未覆盖" if rmse is None else f"{rmse:.4f}"
            lines.append(
                f"| {Path(row['checkpoint']).parent.name}／{row['input_mode']} | "
                f"{metrics['accuracy']:.1%} | {value} | "
                f"{row['input_context_differences']['black_pixel_ratio_changed']} "
                f"`[verified: input-diagnostics.json controls[{index}]]` |"
            )
        lines += [
            "",
            "原图路线的纯预测、后续编码次数和完整耗时分别由本表与系统表提供。"
            "训练与模型输入准备的成本见对应训练报告，"
            "最终系统按原Unity标签准确率优先的既定规则选择。"
            "`[verified: input-diagnostics.json；summary.json systems、recommendation]`",
            "",
            "原图路线的训练监督、最终编码和实际质量门控使用Unity参考像素及真实导入属性，"
            "调用方提供目标尺寸、sRGB、法线用途、Alpha需求和法线评价mip范围。"
            "`[verified: unity_v3_input.py SourceTextureSpec；"
            "v3_deployment.py UnityV3DeploymentTrial.run、V3NativeQueries.measure；"
            "unity_v3_dataset.py UnityV3PatchDataset]`",
            "",
            "源尺寸变化、对齐后RGB变化、Alpha变化、法线和Linear等分组的纯预测效果，"
            "见input-diagnostics.json的groups；对应真实续搜、质量与编码次数，"
            "见summary.json的input_change_groups。"
            "`[verified: input-diagnostics.json controls[*].groups；"
            "summary.json controls[*].input_change_groups]`",
        ]
        lines += [
            "",
            "## 配对训练成本",
            "",
            "| 输入 | 全模型30轮进程秒 | 整图头30轮进程秒 |",
            "|---|---|---|",
        ]
        for mode, stages in result["training_costs"].items():
            lines.append(
                f"| {mode} | {stages['full']['process_seconds']:.2f} | "
                f"{stages['head']['process_seconds']:.2f} "
                f"`[verified: summary.json training_costs.{mode}]` |"
            )
        prediction_parity = result["unity_input_retraining_reproduction"][
            "validation_predictions_bit_identical"
        ]
        parity_text = "相同" if prediction_parity else "不同"
        lines += [
            "",
            f"Unity输入配对训练与冻结V2的1000图完整质量预测存档SHA为{parity_text}，"
            "两个模型条目的计时分别来自对应的实测过程。"
            "`[verified: summary.json unity_input_retraining_reproduction]`",
            "",
            f"源图核验覆盖10000张训练图和1000张验证图，失败{len(source['failures'])}张，"
            f"源尺寸与Unity目标尺寸不同的数量为{source['counts']['train:size_changed']}／"
            f"{source['counts']['validation:size_changed']}。"
            "`[verified: source-input-audit.json counts、failures]`",
            "",
            "冻结V2模型删除exhaustive后，"
            f"纯预测Top-1为{ablation['no_exhaustive16']['pure']['accuracy']:.1%}，"
            f"续搜Top-1为{ablation['no_exhaustive16']['forward']['accuracy']:.1%}，"
            "对应20候选为86.9%／93.6%。`[verified: candidate-ablation.json results]`",
            "",
            "完整时间分段、逐图延迟序列及P95见各benchmark报告的measurements。"
            "模型和DLL加载成本见input-diagnostics.json的model_setup_seconds和"
            "binary_setup_seconds，所选输出审计及ASTC／PNG写盘成本见"
            "selected-output-audit.json。这些成本在最终诊断进程独立测量。"
            "`[verified: benchmark报告 results.*.measurements；input-diagnostics.json；"
            "selected-output-audit.json]`",
            "",
            "## 历史Unity采集时间",
            "",
            "以下数值来自原始采集记录，保留原记录的计时范围。"
            "本轮真实编码计时见上文系统表。"
            "`[verified: summary.json historical_unity_capture_timings]`",
            "",
            "| 原记录字段 | 平均ms／图 | 中位ms／图 | P95 ms／图 |",
            "|---|---|---|---|",
        ]
        for field in ["search_ms", "format_ms", "select_and_encode_ms"]:
            timing = result["historical_unity_capture_timings"][field]
            lines.append(
                f"| {field} | {timing['mean_ms']:.2f} | {timing['median_ms']:.2f} | "
                f"{timing['p95_ms']:.2f} "
                f"`[verified: summary.json historical_unity_capture_timings.{field}]` |"
            )
        lines += [
            "",
            "最终开发合同已保存，2000张独立确认集仍等待正式执行授权。"
            "`[verified: confirmation-contract.json "
            "confirmation_execution_authorized、test_opened]`",
            "",
            "## 执行入口",
            "",
            "```powershell",
            "uv run --no-sync python script/execute_unity_v3.py --status",
            "```",
            "",
            "计划与矩阵见[V3计划](<../../experiment plan/V3/README.md>)，"
            "回归检查见[verification.json](verification.json)，"
            "阶段记录见[progress.json](progress.json)。"
            "`[verified: 对应文件]`",
        ]
        (self.public / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
