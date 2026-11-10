"""Audit native files and publish method results with both RGB and reference RGBA metrics."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from reproductions.common.encoder import ASTCEncoder, ASTCFile


class NahReport:
    def __init__(self, root: Path, method: str, run_id: str) -> None:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be one directory name")
        self.run_dir = root / "experiment report/.local/reproduction-runs" / method / run_id
        self.report_dir = root / "experiment report" / method / run_id
        self.build_receipt = (
            root / "experiment report/.local/reproduction-binaries" / method / "build-receipt.json"
        )

    def write(self) -> dict[str, Any]:
        started = time.perf_counter()
        summary = json.loads((self.run_dir / "receipt.json").read_text(encoding="utf-8"))
        protocol = summary["protocol"]
        protocol_path = self.run_dir / "protocol.json"
        if protocol != json.loads(protocol_path.read_text(encoding="utf-8")):
            raise ValueError("Measured receipt differs from the stored protocol")
        images_path = self.run_dir / "images.jsonl"
        rows = [json.loads(line) for line in images_path.read_text(encoding="utf-8").splitlines()]
        if len(rows) != summary["expected"] or [row["asset"] for row in rows] != [
            entry["path"] for entry in protocol["inputs"]
        ]:
            raise ValueError("Measured images differ from the frozen input order")
        build = json.loads(self.build_receipt.read_text(encoding="utf-8"))
        executable = Path(build["executable"])
        if (
            build["commit"] != protocol["commit"]
            or build["sha256"] != protocol["executable_sha256"]
            or hashlib.sha256(executable.read_bytes()).hexdigest() != protocol["executable_sha256"]
        ):
            raise ValueError("Report decoder differs from the measured encoder identity")
        encoder = ASTCEncoder(executable, protocol["threads"])
        audit = []
        for index, row in enumerate(rows):
            if not row["success"]:
                continue
            folder = self.run_dir / f"{index:05d}"
            selected = ASTCFile.read(folder / "selected.astc")
            fixed = ASTCFile.read(folder / "fixed8.astc")
            if (
                selected.payload_bytes != row["payload_bytes"]
                or fixed.payload_bytes != row["fixed8_payload_bytes"]
                or selected.footprint != tuple(row["footprint"])
                or fixed.footprint != (8, 8)
                or (selected.width, selected.height) != (row["width"], row["height"])
                or (fixed.width, fixed.height) != (row["width"], row["height"])
            ):
                raise ValueError("Stored ASTC header differs from the measured image record")
            artifacts = {
                name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                for name in [
                    "input.png",
                    "selected.astc",
                    "selected.png",
                    "fixed8.astc",
                    "fixed8.png",
                ]
            }
            if row.get("artifacts_sha256", artifacts) != artifacts:
                raise ValueError("Stored image artifacts changed since measurement")
            with tempfile.TemporaryDirectory(
                prefix="quality-audit-", dir=self.run_dir
            ) as temporary:
                for name in ["selected", "fixed8"]:
                    decoded = Path(temporary) / f"{name}.png"
                    encoder.decode(folder / f"{name}.astc", decoded)
                    if hashlib.sha256(decoded.read_bytes()).hexdigest() != artifacts[f"{name}.png"]:
                        raise ValueError("Saved PNG differs from a fresh native ASTC decode")
            quality_rgb = ASTCEncoder.psnr_rgb(folder / "input.png", folder / "selected.png")
            quality_rgba = ASTCEncoder.psnr_rgba(folder / "input.png", folder / "selected.png")
            fixed_rgb = ASTCEncoder.psnr_rgb(folder / "input.png", folder / "fixed8.png")
            fixed_rgba = ASTCEncoder.psnr_rgba(folder / "input.png", folder / "fixed8.png")
            recorded = float("inf") if row["lossless"] else row["psnr_rgb"]
            if not math.isclose(quality_rgb, recorded, abs_tol=1e-10):
                raise ValueError("Decoded RGB quality changed since timing")
            audit.append(
                {
                    "asset": row["asset"],
                    "psnr_rgb": quality_rgb if math.isfinite(quality_rgb) else None,
                    "psnr_rgba": quality_rgba if math.isfinite(quality_rgba) else None,
                    "lossless": math.isinf(quality_rgb),
                    "rgb_target_met": quality_rgb >= protocol["target_psnr"],
                    "reference_rgba_target_met": quality_rgba >= protocol["target_psnr"],
                    "fixed8_rgb_target_met": fixed_rgb >= protocol["target_psnr"],
                    "fixed8_rgba_target_met": fixed_rgba >= protocol["target_psnr"],
                    "artifacts_sha256": artifacts,
                }
            )
        (self.run_dir / "quality-audit.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audit), encoding="utf-8"
        )
        summary["quality_audit"] = {
            "verified_outputs": len(audit),
            "rgb_target_met": sum(row["rgb_target_met"] for row in audit),
            "reference_rgba_target_met": sum(row["reference_rgba_target_met"] for row in audit),
            "fixed8_rgb_target_met": sum(row["fixed8_rgb_target_met"] for row in audit),
            "fixed8_rgba_target_met": sum(row["fixed8_rgba_target_met"] for row in audit),
            "lossless_outputs": sum(row["lossless"] for row in audit),
            "images_log_sha256": hashlib.sha256(images_path.read_bytes()).hexdigest(),
            "receipt_sha256": hashlib.sha256(
                (self.run_dir / "receipt.json").read_bytes()
            ).hexdigest(),
            "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
            "decode_verification": "fresh pinned native decode with exact PNG SHA-256 matches",
            "seconds": time.perf_counter() - started,
        }
        self.report_dir.mkdir(parents=True, exist_ok=True)
        (self.report_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        target = protocol["target_psnr"]
        checks = summary["quality_audit"]
        timing = [row["decision_encode_seconds"] for row in rows if row["success"]]
        size_change = (
            f"{summary['selected_payload_bytes'] / summary['fixed8_payload_bytes'] - 1:+.2%}"
            if summary["fixed8_payload_bytes"]
            else "n/a"
        )
        median = f"{statistics.median(timing):.6f}" if timing else "n/a"
        lines = [
            f"# {protocol['method']} 原生复现测量",
            "",
            f"固定提交 `{protocol['commit']}`，"
            f"编码器 SHA-256 为 `{protocol['executable_sha256']}`。"
            f"本次为 {summary['expected']} 张项目源图 RGB8 适配，原始分辨率、Linear LDR、无 mip，"
            f"编码线程数为 {protocol['threads']}，初始块 {protocol['initial_footprint']}，"
            f"目标 {target} dB，"
            f"最终 preset 为 {protocol['final_preset']}。`[verified: summary.json protocol]`",
            "",
            "| 项目 | 结果 |",
            "|---|---|",
            f"| 编码及解码完成 | {summary['succeeded']}/{summary['expected']}，"
            f"失败 {summary['failed']}"
            " `[verified: summary.json succeeded/failed]` |",
            f"| 搜索及最终编码 | {summary['search_and_final_encode_seconds']:.3f} s，"
            f"逐图中位数 {median} s `[verified: receipt.json；images.jsonl]` |",
            f"| 参考像素准备 | {summary['preprocess_seconds']:.3f} s"
            " `[verified: summary.json preprocess_seconds]` |",
            f"| 固定 8×8 编码 | {summary['fixed8_encode_seconds']:.3f} s"
            " `[verified: summary.json fixed8_encode_seconds]` |",
            f"| 实验总墙钟 | {summary['wall_seconds']:.3f} s，含两种结果的解码与质量检查"
            " `[verified: summary.json wall_seconds；common/nah_experiment.py run]` |",
            f"| 选择结果 payload | {summary['selected_payload_bytes']:,} B"
            " `[verified: summary.json selected_payload_bytes]` |",
            f"| 固定 8×8 payload | {summary['fixed8_payload_bytes']:,} B，"
            f"选择结果相对变化 {size_change} `[verified: summary.json payload fields]` |",
            f"| 全图 RGBA 达标 | {checks['reference_rgba_target_met']}/{len(audit)}"
            " `[verified: summary.json quality_audit]` |",
            f"| 全图 RGB 达标 | {checks['rgb_target_met']}/{len(audit)}"
            " `[verified: summary.json quality_audit]` |",
            f"| 固定 8×8 RGBA／RGB 达标 | {checks['fixed8_rgba_target_met']}／"
            f"{checks['fixed8_rgb_target_met']}，分母 {len(audit)}"
            " `[verified: summary.json quality_audit]` |",
            "",
            "## 评价口径与补全设置",
            "",
            "参考编码器 PNG 加载器扩展为 4 通道，原生目标评价使用 RGBA。"
            "本次另保存全图 RGB 指标，两个口径的达标率分开统计。"
            "原始 Alpha 在源图 RGB8 适配中去除，编码器读取时为不透明 Alpha。"
            "`[verified: astcenccli_image_load_store.cpp load_image_with_stb；"
            "astcenccli_error_metrics.cpp compute_error_metrics/componentmasks；"
            "common/nah_experiment.py _measure]`",
            "",
        ]
        if "2023" in protocol["method"]:
            lines.append(
                "作者版本保留基于当前时间的随机块抽样，搜索中约跳过 90% 的块，"
                "误差分母使用全图像素数的十分之一。零误差返回 999 dB。"
                "本报告的达标率通过最终完整 ASTC 文件解码后重新计算。"
                "`[verified: upstream astcenc_entry.cpp L833–836、L862–879；"
                "astcenccli_error_metrics.cpp L250–265、L333–392；quality-audit.jsonl]`"
            )
        else:
            lines.append(
                f"本次类别记录为 {protocol['category']}，目标 {target} dB。"
                f"初始块为 {protocol['initial_footprint']}，其来源记录为 "
                f"`{protocol['initial_provenance']}`。"
                "论文类别目标保存在 source.json，目标覆盖以本次 protocol 的数值为准。"
                "搜索使用 fastest 和完整 RGBA 质量测量，最终重新编码为 thorough。"
                "逐候选 CLI 启动、解码及质量计算包含在本实现的搜索计时中。"
                "`[verified: source.json class_target_psnr；common/nah_experiment.py；"
                "summary.json protocol；Nah 2022 Table 1；2023 upstream README L1–9]`"
            )
        lines.extend(
            [
                "",
                "本次使用项目图片及明确补全的协议，原文发表数据集和结果另行保留。"
                "Unity 基线使用实际导入像素及项目插件，本次采用源图 RGB8 和参考编码器。"
                "解码验证使用 CLI 默认设置。"
                "可比控制为同方法、同输入、同 preset 的固定 8×8。"
                "`[verified: summary.json protocol；Unity 基线 identity.json；"
                "common/encoder.py encode/decode 启动参数]`",
                "",
                "逐图测量、候选日志、ASTC、解码图片与质量复查保存在同方法同运行名的 "
                "`.local/reproduction-runs/` 目录。公共 summary 通过 SHA-256 绑定原始记录与协议。"
                "报告使用同一固定二进制重新解码，核对 PNG SHA-256 后重算质量，"
                "原始 receipt 和计时保持其测量值。"
                "`[verified: summary.json quality_audit；common/reporting.py write]`",
                "",
            ]
        )
        (self.report_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
        return {"report": str(self.report_dir / "README.md"), "quality": checks}
