"""Prepare measured GDC-style PSNR labels while preserving frozen source splits."""

from __future__ import annotations

import math
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.config import CLASSES
from adaptive_astc.data.splitting import DatasetSplitter
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.environment import RunEnvironment
from reproductions.common.encoder import ASTCEncoder, ASTCFile
from reproductions.common.upstream import BaselineGate, EncoderSource


class GDCLabelSelection:
    @staticmethod
    def choose(candidates: list[dict[str, Any]], target: float) -> tuple[dict[str, Any], bool]:
        if not candidates or not math.isfinite(target):
            raise ValueError("Finite PSNR target and measured candidates are required")
        for row in candidates:
            quality = row["rgb_psnr"]
            if (
                row["payload_bytes"] < 1
                or (quality is None and not row["lossless"])
                or (quality is not None and not math.isfinite(quality))
            ):
                raise ValueError("Invalid measured GDC candidate")
        valid = [row for row in candidates if row["lossless"] or row["rgb_psnr"] > target]

        # Rounded payload is the objective. Equal payload keeps the larger footprint.
        def size_key(row: dict[str, Any]) -> tuple[int, int]:
            return row["payload_bytes"], -math.prod(row["footprint"])

        if valid:
            return min(valid, key=size_key), True
        # The talk does not specify this case: preserve the best measured quality and flag it.
        return min(candidates, key=lambda row: (-row["rgb_psnr"], *size_key(row))), False


class GDCMeasuredDataset:
    def __init__(self, root: Path, project: Path, source_manifest: Path, output: Path) -> None:
        self.root, self.project = root.resolve(), project.resolve()
        self.source_manifest, self.output = source_manifest.resolve(), output.resolve()

    @staticmethod
    def validate_receipt(
        folder: Path,
        receipt: dict[str, Any],
        index: int,
        expected: dict[str, Any],
        protocol: dict[str, Any],
        protocol_fingerprint: str,
    ) -> None:
        if (
            receipt["status"] != "passed"
            or receipt["index"] != index
            or receipt["protocol_fingerprint"] != protocol_fingerprint
            or any(receipt[key] != expected[key] for key in ["split", "path", "fileHash"])
        ):
            raise ValueError("GDC receipt differs from its frozen source identity")
        candidates = receipt["candidates"]
        if sorted(row["name"] for row in candidates) != sorted(CLASSES):
            raise ValueError("GDC receipt must cover every candidate exactly once")
        required = {"input.png"} | {
            f"{name}.{suffix}" for name in CLASSES for suffix in ["astc", "png", "txt"]
        }
        if set(receipt["artifacts_sha256"]) != required:
            raise ValueError("GDC receipt lacks the complete required artifact set")
        for name, digest in receipt["artifacts_sha256"].items():
            if Path(name).name != name or ArtifactStore.sha256_file(folder / name) != digest:
                raise ValueError("Measured GDC candidate changed")
        with Image.open(folder / "input.png") as image:
            width, height = image.size
        for row in candidates:
            astc = ASTCFile.read(folder / f"{row['name']}.astc")
            if (
                astc.footprint != tuple(row["footprint"])
                or row["name"] != f"{astc.footprint[0]}x{astc.footprint[1]}"
                or astc.width != width
                or astc.height != height
                or astc.depth != 1
                or astc.payload_bytes != row["payload_bytes"]
                or astc.container_bytes != row["container_bytes"]
            ):
                raise ValueError("GDC candidate dimensions or bytes differ from actual ASTC")
            psnr = ASTCEncoder.psnr_rgb(folder / "input.png", folder / f"{row['name']}.png")
            if not (
                (row["lossless"] and row["rgb_psnr"] is None and math.isinf(psnr))
                or (
                    not row["lossless"]
                    and row["rgb_psnr"] is not None
                    and abs(psnr - row["rgb_psnr"]) < 1e-8
                )
            ):
                raise ValueError("GDC candidate PSNR differs from its saved reconstruction")
        chosen, passed = GDCLabelSelection.choose(candidates, protocol["target_psnr"])
        if (
            receipt["selected"] != chosen
            or receipt["target_met"] != passed
            or receipt["fallback"] != (None if passed else "no_feasible_candidate")
        ):
            raise ValueError("GDC selected label contradicts the measured selection rule")

    def collect(
        self, sizes: dict[str, int], *, target: float = 35.0, workers: int = 4
    ) -> dict[str, Any]:
        if workers < 1 or not math.isfinite(target):
            raise ValueError("Positive worker count and finite target are required")
        BaselineGate.require(
            self.root
            / "experiment report/.local/unity-search-baseline-lite-rdo-off/full-receipt.json"
        )
        source = EncoderSource(
            self.root / "reproductions/nah2022_psnr_search",
            self.root / "experiment report/.local/reproduction-binaries/nah2022_psnr_search",
        )
        commit = source.verify()
        build = ArtifactStore.read_json(source.artifact_dir / "build-receipt.json")
        if (
            build["commit"] != commit
            or ArtifactStore.sha256_file(Path(build["executable"])) != build["sha256"]
        ):
            raise ValueError("GDC reference encoder differs from the pinned source/build")
        manifest = ArtifactStore.read_json(self.source_manifest)
        inputs = []
        for split in ["train", "validation", "calibration", "test"]:
            count = sizes[split]
            if count < 1 or count > len(manifest["splits"][split]):
                raise ValueError("Requested split size is outside the frozen source split")
            for row in manifest["splits"][split][:count]:
                inputs.append({"split": split, "row": row})
        protocol = {
            "implementation": "talk_reimplementation_project_four_square",
            "manifest_sha256": ArtifactStore.sha256_file(self.source_manifest),
            "encoder_commit": commit,
            "encoder_sha256": build["sha256"],
            "footprints": list(CLASSES),
            "preset": "medium",
            "threads_per_encoder": 1,
            "decode_threads": "astcenc CLI default",
            "target_psnr": target,
            "comparison": ">",
            "metric": "full-image byte-domain RGB MSE PSNR",
            "input": "source RGB8, original dimensions, Linear LDR, no mip, no RDO",
            "sizes": sizes,
            "fallback": "highest measured RGB PSNR, then smallest payload",
            "equal_payload": "largest footprint area",
            "candidate_coverage": "all four candidates",
            "missing_original_settings": [
                "full footprint set",
                "encoder version/preset",
                "original corpus",
            ],
            "inputs": [
                {
                    "split": item["split"],
                    "path": item["row"]["path"],
                    "fileHash": item["row"]["fileHash"],
                }
                for item in inputs
            ],
        }
        self.output.mkdir(parents=True, exist_ok=True)
        protocol_path = self.output / "protocol.json"
        if protocol_path.exists() and ArtifactStore.read_json(protocol_path) != protocol:
            raise ValueError("Existing GDC label recipe differs; use a new run identity")
        ArtifactStore.write_json(protocol_path, protocol)
        protocol_fingerprint = ArtifactStore.fingerprint(protocol)
        started = time.perf_counter()
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            pending = {
                executor.submit(
                    self._collect_one, index, item, protocol, build, protocol_fingerprint
                ): index
                for index, item in enumerate(inputs)
            }
            for future in as_completed(pending):
                index = pending[future]
                try:
                    row = future.result()
                except Exception as error:
                    row = {"index": index, "status": "failed", "error": repr(error)}
                results.append(row)
                print(f"GDC labels {len(results)}/{len(inputs)} {row['status']}", flush=True)
        results.sort(key=lambda row: row["index"])
        receipt = {
            "status": "passed" if all(row["status"] == "passed" for row in results) else "failed",
            "protocol_sha256": ArtifactStore.sha256_file(protocol_path),
            "results": results,
            "workers": workers,
            "wall_seconds": time.perf_counter() - started,
            "environment": RunEnvironment.capture(),
        }
        attempts = self.output / "attempts"
        attempts.mkdir(exist_ok=True)
        ArtifactStore.write_json(attempts / f"collection-{uuid.uuid4().hex}.json", receipt)
        previous = self.output / "collection.json"
        if previous.exists():
            cached = ArtifactStore.read_json(previous)
            if cached["status"] == "passed" and cached["results"] == results:
                return cached
        ArtifactStore.write_json(previous, receipt)
        return receipt

    def _collect_one(
        self,
        index: int,
        item: dict[str, Any],
        protocol: dict[str, Any],
        build: dict[str, Any],
        protocol_fingerprint: str,
    ) -> dict[str, Any]:
        folder = self.output / "labels" / f"{index:05d}"
        receipt_path = folder / "receipt.json"
        if receipt_path.exists():
            try:
                receipt = ArtifactStore.read_json(receipt_path)
                expected = {
                    "split": item["split"],
                    "path": item["row"]["path"],
                    "fileHash": item["row"]["fileHash"],
                }
                self.validate_receipt(
                    folder, receipt, index, expected, protocol, protocol_fingerprint
                )
            except (ValueError, KeyError, TypeError, OSError):
                pass
            else:
                return {
                    "index": index,
                    "status": "passed",
                    "receipt_sha256": ArtifactStore.sha256_file(receipt_path),
                }
        if folder.exists():
            archive = self.output / "attempts" / f"partial-{index}-{uuid.uuid4().hex}"
            archive.parent.mkdir(exist_ok=True)
            if not folder.resolve().is_relative_to(
                self.output
            ) or not archive.resolve().is_relative_to(self.output):
                raise ValueError("GDC partial output archive escaped the run directory")
            folder.rename(archive)
        folder.mkdir(parents=True)
        row = item["row"]
        source = (self.project / row["path"]).resolve()
        if not source.is_relative_to(self.project / "Assets"):
            raise ValueError("GDC source escaped project Assets")
        if MD4.new(source.read_bytes()).hexdigest() != row["fileHash"].lower():
            raise ValueError("GDC source hash differs from frozen manifest")
        preparation_started = time.perf_counter()
        pixels = folder / "input.png"
        with Image.open(source) as image:
            image.convert("RGB").save(pixels)
        preparation_seconds = time.perf_counter() - preparation_started
        encoder = ASTCEncoder(Path(build["executable"]), threads=1)
        candidates = []
        for name in CLASSES:
            x, y = (int(value) for value in name.split("x"))
            encoded, seconds, stdout = encoder.encode(
                pixels, folder / f"{name}.astc", (x, y), "medium"
            )
            (folder / f"{name}.txt").write_text(stdout, encoding="utf-8")
            decoded_seconds = encoder.decode(folder / f"{name}.astc", folder / f"{name}.png")
            metric_started = time.perf_counter()
            psnr = encoder.psnr_rgb(pixels, folder / f"{name}.png")
            candidates.append(
                {
                    "name": name,
                    "footprint": [x, y],
                    "payload_bytes": encoded.payload_bytes,
                    "container_bytes": encoded.container_bytes,
                    "rgb_psnr": psnr if math.isfinite(psnr) else None,
                    "lossless": math.isinf(psnr),
                    "timings": {
                        "encode_seconds": seconds,
                        "decode_seconds": decoded_seconds,
                        "metric_seconds": time.perf_counter() - metric_started,
                    },
                }
            )
        selected, passed = GDCLabelSelection.choose(candidates, protocol["target_psnr"])
        if MD4.new(source.read_bytes()).hexdigest() != row["fileHash"].lower():
            raise ValueError("GDC source changed while generating candidate labels")
        if ArtifactStore.sha256_file(encoder.executable) != build["sha256"]:
            raise ValueError("GDC encoder changed during label generation")
        receipt = {
            "status": "passed",
            "index": index,
            "split": item["split"],
            "path": row["path"],
            "fileHash": row["fileHash"],
            "protocol_fingerprint": protocol_fingerprint,
            "preparation_seconds": preparation_seconds,
            "candidates": candidates,
            "selected": selected,
            "target_met": passed,
            "fallback": None if passed else "no_feasible_candidate",
            "artifacts_sha256": {
                path.name: ArtifactStore.sha256_file(path)
                for path in sorted(folder.iterdir())
                if path.is_file()
            },
        }
        ArtifactStore.write_json(receipt_path, receipt)
        return {
            "index": index,
            "status": "passed",
            "receipt_sha256": ArtifactStore.sha256_file(receipt_path),
        }

    def assemble(self) -> dict[str, Any]:
        collection = ArtifactStore.read_json(self.output / "collection.json")
        protocol = ArtifactStore.read_json(self.output / "protocol.json")
        protocol_fingerprint = ArtifactStore.fingerprint(protocol)
        if collection["status"] != "passed" or collection[
            "protocol_sha256"
        ] != ArtifactStore.sha256_file(self.output / "protocol.json"):
            raise ValueError("Complete all GDC labels before assembling the classifier dataset")
        original = ArtifactStore.read_json(self.source_manifest)
        if protocol["manifest_sha256"] != ArtifactStore.sha256_file(self.source_manifest):
            raise ValueError("Frozen GDC source manifest changed")
        lookup = {row["path"]: row for rows in original["splits"].values() for row in rows}
        splits: dict[str, list[dict[str, Any]]] = {name: [] for name in protocol["sizes"]}
        for entry in collection["results"]:
            folder = self.output / "labels" / f"{entry['index']:05d}"
            if entry["receipt_sha256"] != ArtifactStore.sha256_file(folder / "receipt.json"):
                raise ValueError("Measured GDC label receipt changed")
            measured = ArtifactStore.read_json(folder / "receipt.json")
            expected = protocol["inputs"][entry["index"]]
            self.validate_receipt(
                folder, measured, entry["index"], expected, protocol, protocol_fingerprint
            )
            row = dict(lookup[measured["path"]])
            source_cache = (self.source_manifest.parent / row["cache"]).resolve()
            cache = (self.output / row["cache"]).resolve()
            if not source_cache.is_relative_to(
                self.source_manifest.parent
            ) or not cache.is_relative_to(self.output):
                raise ValueError("Classifier cache path escaped its dataset root")
            if ArtifactStore.sha256_file(source_cache) != row["cache_sha256"]:
                raise ValueError("Frozen RGB224 classifier input cache changed")
            cache.parent.mkdir(parents=True, exist_ok=True)
            if not cache.exists():
                shutil.copy2(source_cache, cache)
            if ArtifactStore.sha256_file(cache) != row["cache_sha256"]:
                raise ValueError("Copied GDC classifier cache differs from frozen input")
            selected = measured["selected"]
            for key in [
                "psnr",
                "msSsimDb",
                "fileSize",
                "timestamp",
                "qualityLevel",
                "rdo",
                "blockSize",
            ]:
                row.pop(key, None)
            row.update(
                blockSize=selected["name"],
                class_id=CLASSES.index(selected["name"]),
                psnr=selected["rgb_psnr"],
                lossless=selected["lossless"],
                fileSize=selected["payload_bytes"],
                qualityLevel="medium",
                rdo=False,
                label_target_met=measured["target_met"],
                label_fallback=measured["fallback"],
                label_receipt_sha256=entry["receipt_sha256"],
            )
            splits[measured["split"]].append(row)
        if {name: len(rows) for name, rows in splits.items()} != protocol["sizes"]:
            raise ValueError("Measured GDC dataset split coverage is incomplete")
        audit = DatasetSplitter.audit_manifests(splits)
        manifest = {
            "seed": original["seed"],
            "classes": list(CLASSES),
            "image_root": str(self.project),
            "sizes": protocol["sizes"],
            "smoke": protocol["sizes"]["train"] != 10000,
            "source_manifest_sha256": protocol["manifest_sha256"],
            "label_protocol_sha256": collection["protocol_sha256"],
            "label_collection_sha256": ArtifactStore.sha256_file(self.output / "collection.json"),
            "protocol": protocol,
            "audit": audit,
            "splits": splits,
        }
        manifest["fingerprint"] = ArtifactStore.fingerprint(manifest)
        target = self.output / "manifest.json"
        if target.exists() and ArtifactStore.read_json(target) != manifest:
            raise ValueError("Existing classifier manifest differs; use a new run identity")
        ArtifactStore.write_json(target, manifest)
        return {
            "status": "passed",
            "fingerprint": manifest["fingerprint"],
            "sizes": protocol["sizes"],
        }
