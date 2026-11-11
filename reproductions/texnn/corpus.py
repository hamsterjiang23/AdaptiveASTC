"""Prepare reproducible source patches and memory-mapped TexNN block datasets."""

from __future__ import annotations

import json
import math
import random
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
from Crypto.Hash import MD4
from PIL import Image

from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.environment import RunEnvironment
from reproductions.texnn.data import TexNNLabelCollector
from reproductions.texnn.reference import TexNNReference
from reproductions.texnn.runtime import TexNNConfiguration


class TexNNCorpusBuilder:
    def __init__(self, root: Path, project: Path, manifest: Path, run_dir: Path) -> None:
        self.root = root.resolve()
        self.project = project.resolve()
        self.manifest = manifest.resolve()
        self.run_dir = run_dir.resolve()
        self.collector = TexNNLabelCollector(self.root)

    def collect(
        self, images: int = 64, patch_size: int = 64, workers: int = 4, seed: int = 20261111
    ) -> dict[str, Any]:
        if images < 1 or patch_size < 8 or workers < 1:
            raise ValueError("Corpus size, patch extent and worker count must be positive")
        manifest = ArtifactStore.read_json(self.manifest)
        train = manifest["splits"]["train"]
        if images > len(train):
            raise ValueError("Requested more images than the frozen training split")
        known = {row["path"].casefold(): row for row in train}
        baseline = self.root / "experiment report/.local/unity-search-baseline-lite-rdo-off"
        smoke = ArtifactStore.read_json(baseline / "smoke1-config.json")["assets"]
        ordered = [known[row["path"].casefold()] for row in smoke]
        used = {row["path"].casefold() for row in ordered}
        ordered += sorted(
            (row for row in train if row["path"].casefold() not in used),
            key=lambda row: row["path"],
        )
        inputs = [{"path": row["path"], "fileHash": row["fileHash"]} for row in ordered[:images]]
        reference = TexNNReference(self.root)
        commit = reference.verify()
        build = ArtifactStore.read_json(reference.artifact_dir / "build-receipt.json")
        protocol = {
            "manifest_sha256": ArtifactStore.sha256_file(self.manifest),
            "inputs": inputs,
            "patch_size": patch_size,
            "seed": seed,
            "footprints": [4, 6, 8],
            "preset": "exhaustive",
            "commit": commit,
            "binaries": {"reference": build["sha256"], "labels": build["labels_sha256"]},
            "feature_protocol": "partition_single_plane_rgb24_v2",
            "source_scope": "training split, one block-aligned source crop per image/footprint",
        }
        if protocol["feature_protocol"] != build.get("feature_protocol"):
            raise ValueError("Corpus requires the current partition-only feature build")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        protocol_path = self.run_dir / "protocol.json"
        if protocol_path.exists():
            if ArtifactStore.read_json(protocol_path) != protocol:
                raise ValueError(
                    "Existing corpus recipe differs from the requested source/protocol"
                )
        else:
            ArtifactStore.write_json(protocol_path, protocol)
        started = time.perf_counter()
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            pending = {
                executor.submit(self._collect_asset, index, row, protocol): index
                for index, row in enumerate(inputs)
            }
            for future in as_completed(pending):
                index = pending[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = {"index": index, "status": "failed", "error": repr(error)}
                results.append(result)
                print(f"TexNN corpus {len(results)}/{images} status={result['status']}", flush=True)
        results.sort(key=lambda row: row["index"])
        receipt = {
            "status": "passed" if all(row["status"] == "passed" for row in results) else "failed",
            "protocol_sha256": ArtifactStore.sha256_file(protocol_path),
            "expected_assets": images,
            "workers": workers,
            "wall_seconds": time.perf_counter() - started,
            "environment": RunEnvironment.capture(),
            "assets": results,
        }
        attempts = self.run_dir / "attempts"
        attempts.mkdir(exist_ok=True)
        ArtifactStore.write_json(attempts / f"collection-{uuid.uuid4().hex}.json", receipt)
        complete_path = self.run_dir / "collection.json"
        if complete_path.exists():
            complete = ArtifactStore.read_json(complete_path)
            if complete["status"] == "passed" and complete["assets"] == results:
                return complete
        ArtifactStore.write_json(self.run_dir / "collection.json", receipt)
        return receipt

    def _collect_asset(
        self, index: int, row: dict[str, str], protocol: dict[str, Any]
    ) -> dict[str, Any]:
        asset_dir = self.run_dir / "assets" / f"{index:05d}"
        asset_dir.mkdir(parents=True, exist_ok=True)
        asset_path = asset_dir / "asset.json"
        asset: dict[str, Any]
        if asset_path.exists():
            asset = ArtifactStore.read_json(asset_path)
            if asset["path"] != row["path"] or asset["fileHash"] != row["fileHash"]:
                raise ValueError("Cached crop belongs to a different asset version")
        else:
            source = (self.project / row["path"]).resolve()
            if not source.is_relative_to(self.project / "Assets"):
                raise ValueError("Corpus source escaped the project Assets directory")
            data = source.read_bytes()
            if MD4.new(data).hexdigest() != row["fileHash"].lower():
                raise ValueError("Source MD4 differs from the frozen training manifest")
            asset = dict(row)
            asset["source_sha256"] = ArtifactStore.sha256_file(source)
            asset["crops"] = {}
            del data
            with Image.open(source) as image:
                rgb = image.convert("RGB")
                for size in protocol["footprints"]:
                    columns = max(1, image.width // size)
                    rows = max(1, image.height // size)
                    crop_columns = min(columns, max(1, protocol["patch_size"] // size))
                    crop_rows = min(rows, max(1, protocol["patch_size"] // size))
                    rng = random.Random(f"{protocol['seed']}:{row['path']}:{size}")
                    left = rng.randrange(columns - crop_columns + 1) * size
                    native_y = rng.randrange(rows - crop_rows + 1) * size
                    width = min(image.width, crop_columns * size)
                    height = min(image.height, crop_rows * size)
                    top = image.height - native_y - height
                    box = (left, top, left + width, top + height)
                    crop = asset_dir / f"crop-{size}x{size}.png"
                    rgb.crop(box).save(crop)
                    asset["crops"][str(size)] = {
                        "box": box,
                        "source_size": image.size,
                        "sha256": ArtifactStore.sha256_file(crop),
                    }
            if MD4.new(source.read_bytes()).hexdigest() != row["fileHash"].lower():
                raise ValueError("Original texture changed while preparing its crops")
            ArtifactStore.write_json(asset_path, asset)
        receipts = {}
        for size in protocol["footprints"]:
            crop = asset_dir / f"crop-{size}x{size}.png"
            if ArtifactStore.sha256_file(crop) != asset["crops"][str(size)]["sha256"]:
                raise ValueError("Cached source crop changed")
            target = asset_dir / f"{size}x{size}"
            previous = target / "receipt.json"
            valid = False
            if previous.exists():
                cached = ArtifactStore.read_json(previous)
                valid = (
                    cached.get("status") == "passed"
                    and cached.get("feature_protocol") == protocol["feature_protocol"]
                    and cached.get("binaries") == protocol["binaries"]
                    and all(
                        (target / name).is_file()
                        and ArtifactStore.sha256_file(target / name) == expected
                        for name, expected in cached["artifacts_sha256"].items()
                    )
                )
            if not valid:
                if target.exists():
                    archive = (
                        self.run_dir / "attempts" / f"partial-{index}-{size}-{uuid.uuid4().hex}"
                    )
                    archive.parent.mkdir(exist_ok=True)
                    if not target.resolve().is_relative_to(
                        self.run_dir
                    ) or not archive.resolve().is_relative_to(self.run_dir):
                        raise ValueError("Partial collection archive escaped the corpus directory")
                    target.rename(archive)
                collected = self.collector.collect(crop, target, (size, size))
                if collected["binaries"] != protocol["binaries"]:
                    raise ValueError("Native binaries changed during corpus collection")
            receipts[str(size)] = ArtifactStore.sha256_file(previous)
        return {"index": index, "status": "passed", "receipts_sha256": receipts}


class TexNNBlockCorpus:
    @staticmethod
    def rows(collection: Path, size: int) -> Iterator[dict[str, Any]]:
        receipt = ArtifactStore.read_json(collection / "collection.json")
        for asset in receipt["assets"]:
            folder = collection / "assets" / f"{asset['index']:05d}" / f"{size}x{size}"
            with (folder / "labels.jsonl").open(encoding="utf-8") as stream:
                for line in stream:
                    row = json.loads(line)
                    if row.get("feature_protocol") != 2:
                        raise ValueError("Recollect legacy labels using partition-only endpoints")
                    if not row["constant"] and not row["error"]:
                        yield row

    @classmethod
    def prepare(cls, collection: Path, size: int, seed: int = 20261111) -> dict[str, Any]:
        collection = collection.resolve()
        receipt = ArtifactStore.read_json(collection / "collection.json")
        protocol = ArtifactStore.read_json(collection / "protocol.json")
        if receipt["status"] != "passed":
            raise ValueError("Complete successful corpus collection before packing training data")
        if receipt["protocol_sha256"] != ArtifactStore.sha256_file(collection / "protocol.json"):
            raise ValueError("Corpus protocol changed since collection")
        if size not in protocol["footprints"]:
            raise ValueError("Footprint is absent from the collection recipe")
        for asset in receipt["assets"]:
            folder = collection / "assets" / f"{asset['index']:05d}" / f"{size}x{size}"
            if (
                ArtifactStore.sha256_file(folder / "receipt.json")
                != asset["receipts_sha256"][str(size)]
            ):
                raise ValueError("Native collection receipt changed")
            sample = ArtifactStore.read_json(folder / "receipt.json")
            for name, expected in sample["artifacts_sha256"].items():
                if ArtifactStore.sha256_file(folder / name) != expected:
                    raise ValueError("Native collection artifact changed before training")
        first = collection / "assets/00000" / f"{size}x{size}" / "catalog.json"
        partitions = ArtifactStore.read_json(first)["partitions"]
        partition_ids = {tuple(pair): index for index, pair in enumerate(partitions)}
        joints = set()
        count = 0
        for row in cls.rows(collection, size):
            joints.add(TexNNConfiguration.from_teacher(row).joint_label)
            count += 1
        if count < 2:
            raise ValueError("TexNN training requires at least two nonconstant blocks")
        joint_labels = sorted(joints)
        architecture = ArtifactStore.read_json(Path(__file__).with_name("architectures.json"))
        if len(joint_labels) > architecture["demnn"][f"{size}x{size}"][-1]:
            raise ValueError("Observed joint labels exceed the Appendix DEM-NN output width")
        joint_ids = {label: index for index, label in enumerate(joint_labels)}
        final = collection / "prepared" / f"{size}x{size}"
        if (final / "manifest.json").exists():
            cached = cls.validate(final)
            if cached["seed"] != seed:
                raise ValueError("Prepared data uses a different train/validation split seed")
            if cached["collection_sha256"] == ArtifactStore.sha256_file(
                collection / "collection.json"
            ):
                return cached
            raise ValueError("Prepared data belongs to an earlier collection receipt")
        destination = final.with_name(f"partial-{size}x{size}-{uuid.uuid4().hex}")
        destination.mkdir(parents=True, exist_ok=False)
        arrays = {
            "rgb": np.lib.format.open_memmap(
                destination / "rgb.npy", mode="w+", dtype="float32", shape=(count, size * size * 3)
            ),
            "endpoints": np.lib.format.open_memmap(
                destination / "endpoints.npy", mode="w+", dtype="float32", shape=(count, 24)
            ),
            "pnn": np.lib.format.open_memmap(
                destination / "pnn.npy", mode="w+", dtype="int64", shape=(count,)
            ),
            "demnn": np.lib.format.open_memmap(
                destination / "demnn.npy", mode="w+", dtype="int64", shape=(count,)
            ),
        }
        for index, row in enumerate(cls.rows(collection, size)):
            configuration = TexNNConfiguration.from_teacher(row)
            arrays["rgb"][index] = row["rgb"]
            arrays["endpoints"][index] = row["ideal_endpoints"]
            arrays["pnn"][index] = partition_ids[
                (configuration.partition_count, configuration.partition_index)
            ]
            arrays["demnn"][index] = joint_ids[configuration.joint_label]
        for array in arrays.values():
            array.flush()
        del array
        arrays.clear()
        permutation = np.random.default_rng(seed).permutation(count)
        validation_count = max(1, math.floor(count * 0.15))
        np.save(destination / "validation.npy", permutation[:validation_count])
        np.save(destination / "train.npy", permutation[validation_count:])
        manifest = {
            "feature_protocol": protocol["feature_protocol"],
            "size": size,
            "samples": count,
            "train_samples": count - validation_count,
            "validation_samples": validation_count,
            "seed": seed,
            "partitions": partitions,
            "joint_labels": joint_labels,
            "joint_fields": ["block_mode", "dual_component", "cem0", "cem1", "cem2", "cem3"],
            "endpoint_mode_padding": "repeat last active mode",
            "collection_sha256": ArtifactStore.sha256_file(collection / "collection.json"),
            "files_sha256": {
                path.name: ArtifactStore.sha256_file(path)
                for path in sorted(destination.glob("*.npy"))
            },
        }
        manifest["fingerprint"] = ArtifactStore.fingerprint(manifest)
        ArtifactStore.write_json(destination / "manifest.json", manifest)
        if not destination.resolve().is_relative_to(
            collection
        ) or not final.resolve().is_relative_to(collection):
            raise ValueError("Prepared corpus path escaped its collection")
        destination.rename(final)
        return manifest

    @staticmethod
    def validate(directory: Path) -> dict[str, Any]:
        manifest = ArtifactStore.read_json(directory / "manifest.json")
        payload = dict(manifest)
        fingerprint = payload.pop("fingerprint")
        if ArtifactStore.fingerprint(payload) != fingerprint:
            raise ValueError("Prepared TexNN corpus manifest changed")
        for name, expected in manifest["files_sha256"].items():
            if Path(name).name != name or ArtifactStore.sha256_file(directory / name) != expected:
                raise ValueError("Prepared TexNN corpus array changed")
        return manifest
