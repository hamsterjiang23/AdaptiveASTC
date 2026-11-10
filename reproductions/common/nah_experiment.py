"""Run native Nah encoders with explicit reconstructed settings and per-image evidence."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

from Crypto.Hash import MD4
from PIL import Image

from reproductions.common.encoder import ASTCEncoder
from reproductions.common.upstream import BaselineGate, EncoderSource
from reproductions.nah2022_psnr_search.search import FOOTPRINTS, PSNRBlockSearch


class NahExperiment:
    def __init__(
        self,
        root: Path,
        method: Literal["nah2022_psnr_search", "nah2023_adaptive_astcenc"],
        project: Path,
        manifest: Path,
        run_id: str,
        *,
        input_set: Literal["probe", "smoke"] = "probe",
        target: float | None = None,
        initial: tuple[int, int] = (6, 6),
        category: str = "game",
        threads: int = 1,
    ) -> None:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be one directory name")
        self.root = root.resolve()
        self.method = method
        self.project = project.resolve()
        self.manifest = manifest.resolve()
        self.method_dir = self.root / "reproductions" / method
        self.run_dir = self.root / "experiment report/.local/reproduction-runs" / method / run_id
        self.report_dir = self.root / "experiment report" / method / run_id
        self.input_set = input_set
        if initial not in FOOTPRINTS:
            raise ValueError(f"Unsupported initial footprint: {initial}")
        self.initial = initial
        self.threads = threads
        source = json.loads((self.method_dir / "source.json").read_text(encoding="utf-8"))
        default_target = source["class_target_psnr"][category] if "2022" in method else 40.0
        self.target = float(default_target if target is None else target)
        if not math.isfinite(self.target) or self.target <= 0:
            raise ValueError("PSNR target must be positive and finite")
        self.category = category

    def run(self) -> dict[str, object]:
        baseline_dir = self.root / "experiment report/.local/unity-search-baseline-lite-rdo-off"
        BaselineGate.require(baseline_dir / "full-receipt.json")
        artifact_dir = self.root / "experiment report/.local/reproduction-binaries" / self.method
        commit = EncoderSource(self.method_dir, artifact_dir).verify()
        build = json.loads((artifact_dir / "build-receipt.json").read_text(encoding="utf-8"))
        if build["commit"] != commit:
            raise ValueError("Encoder build receipt belongs to a different upstream revision")
        executable = Path(build["executable"])
        if hashlib.sha256(executable.read_bytes()).hexdigest() != build["sha256"]:
            raise ValueError("Encoder binary differs from the build receipt")
        encoder = ASTCEncoder(executable, self.threads)
        config = json.loads((baseline_dir / "smoke1-config.json").read_text(encoding="utf-8"))
        known = {
            row["path"].casefold(): row
            for row in json.loads(self.manifest.read_text(encoding="utf-8"))["splits"]["train"]
        }
        paths = config["assets"][:2] if self.input_set == "probe" else config["assets"]
        rows = [known[row["path"].casefold()] for row in paths]
        protocol = {
            "method": self.method,
            "implementation_kind": "paper_reimplementation"
            if "2022" in self.method
            else "author_code",
            "commit": commit,
            "executable_sha256": build["sha256"],
            "baseline_receipt_sha256": hashlib.sha256(
                (baseline_dir / "full-receipt.json").read_bytes()
            ).hexdigest(),
            "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "inputs": [{"path": row["path"], "fileHash": row["fileHash"]} for row in rows],
            "reference_pixels": "source image converted to RGB8, original resolution",
            "color_profile": "linear LDR byte-domain RGB",
            "mipmaps": False,
            "alpha": "discarded by explicit RGB adaptation",
            "target_psnr": self.target,
            "initial_footprint": self.initial,
            "initial_provenance": "reconstructed 6x6 default from the Nah 2023 author example"
            if self.initial == (6, 6)
            else "explicit command-line reconstruction choice",
            "category": self.category,
            "threads": self.threads,
            "final_preset": "thorough" if "2022" in self.method else "medium",
            "author_2023_randomness": "unmodified upstream srand(time(NULL)) sampling",
            "comparison_scope": "source-RGB project adaptation, separate from Unity import timing",
        }
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self._write(self.run_dir / "protocol.json", protocol)
        records: list[dict[str, Any]] = []
        started = time.perf_counter()
        with (self.run_dir / "images.jsonl").open("w", encoding="utf-8") as stream:
            for index, row in enumerate(rows):
                folder = self.run_dir / f"{index:05d}"
                folder.mkdir()
                try:
                    record = self._measure(row, folder, encoder)
                    record["success"] = True
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    record = {"asset": row["path"], "success": False, "error": str(error)}
                records.append(record)
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                print(
                    f"{self.method} {index + 1}/{len(rows)} success={record['success']}", flush=True
                )
        successful = [row for row in records if row["success"]]
        summary = {
            "status": "passed" if len(successful) == len(rows) else "failed",
            "expected": len(rows),
            "succeeded": len(successful),
            "failed": len(rows) - len(successful),
            "target_met": sum(row["target_met"] for row in successful),
            "wall_seconds": time.perf_counter() - started,
            "selected_payload_bytes": sum(row["payload_bytes"] for row in successful),
            "fixed8_payload_bytes": sum(row["fixed8_payload_bytes"] for row in successful),
            "preprocess_seconds": sum(row["preprocess_seconds"] for row in successful),
            "search_and_final_encode_seconds": sum(
                row["decision_encode_seconds"] for row in successful
            ),
            "fixed8_encode_seconds": sum(row["fixed8_encode_seconds"] for row in successful),
            "protocol": protocol,
        }
        self._write(self.run_dir / "receipt.json", summary)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._write(self.report_dir / "summary.json", summary)
        return summary

    @staticmethod
    def _write(path: Path, document: object) -> None:
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    def _measure(self, row: dict[str, Any], folder: Path, encoder: ASTCEncoder) -> dict[str, Any]:
        started = time.perf_counter()
        source = (self.project / row["path"]).resolve()
        if not source.is_relative_to(self.project / "Assets"):
            raise ValueError("Source path escaped project Assets")
        if MD4.new(source.read_bytes()).hexdigest() != row["fileHash"].lower():
            raise ValueError("Source MD4 differs from the training manifest")
        reference = folder / "input.png"
        with Image.open(source) as image:
            image.convert("RGB").save(reference)
        preprocessing = time.perf_counter() - started
        probes: list[dict[str, object]] = []

        def probe(footprint: tuple[int, int]) -> float:
            name = f"probe-{footprint[0]}x{footprint[1]}"
            _, encode_seconds, stdout = encoder.encode(
                reference, folder / f"{name}.astc", footprint, "fastest"
            )
            (folder / f"{name}.txt").write_text(stdout, encoding="utf-8")
            decode_seconds = encoder.decode(folder / f"{name}.astc", folder / f"{name}.png")
            quality = encoder.psnr_rgb(reference, folder / f"{name}.png")
            probes.append(
                {
                    "footprint": footprint,
                    "psnr": quality if math.isfinite(quality) else None,
                    "lossless": math.isinf(quality),
                    "encode_seconds": encode_seconds,
                    "decode_seconds": decode_seconds,
                }
            )
            return quality

        started = time.perf_counter()
        preset = "medium"
        target = self.target
        chosen = self.initial
        if "2022" in self.method:
            chosen = PSNRBlockSearch().select(probe, self.initial, self.target).footprint
            preset = "thorough"
            target = None
        final, encode_seconds, stdout = encoder.encode(
            reference, folder / "selected.astc", chosen, preset, target_psnr=target
        )
        decision_seconds = time.perf_counter() - started
        (folder / "selected.txt").write_text(stdout, encoding="utf-8")
        decode_seconds = encoder.decode(folder / "selected.astc", folder / "selected.png")
        quality = encoder.psnr_rgb(reference, folder / "selected.png")
        fixed, fixed_seconds, fixed_stdout = encoder.encode(
            reference, folder / "fixed8.astc", (8, 8), preset
        )
        (folder / "fixed8.txt").write_text(fixed_stdout, encoding="utf-8")
        encoder.decode(folder / "fixed8.astc", folder / "fixed8.png")
        fixed_quality = encoder.psnr_rgb(reference, folder / "fixed8.png")
        return {
            "asset": row["path"],
            "source_md4": row["fileHash"],
            "width": final.width,
            "height": final.height,
            "footprint": final.footprint,
            "preset": preset,
            "payload_bytes": final.payload_bytes,
            "container_bytes": final.container_bytes,
            "psnr_rgb": quality if math.isfinite(quality) else None,
            "lossless": math.isinf(quality),
            "target_met": quality >= self.target,
            "preprocess_seconds": preprocessing,
            "decision_encode_seconds": decision_seconds,
            "final_encode_seconds": encode_seconds if probes else None,
            "verification_decode_seconds": decode_seconds,
            "search_probes": probes,
            "fixed8_payload_bytes": fixed.payload_bytes,
            "fixed8_psnr_rgb": fixed_quality if math.isfinite(fixed_quality) else None,
            "fixed8_lossless": math.isinf(fixed_quality),
            "fixed8_encode_seconds": fixed_seconds,
        }
