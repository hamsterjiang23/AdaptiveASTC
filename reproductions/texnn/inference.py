"""Cascaded P-NN and DEM-NN inference for the real historical ASTC backend."""

from __future__ import annotations

import itertools
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch

from adaptive_astc.utils.artifacts import ArtifactStore
from reproductions.texnn.corpus import TexNNBlockCorpus
from reproductions.texnn.models import TexNNClassifier
from reproductions.texnn.runtime import TexNNConfiguration, TexNNNativeBackend


class TexNNPredictor:
    def __init__(
        self, root: Path, run_dir: Path, size: int, *, device: str = "cpu", batch_size: int = 256
    ) -> None:
        if batch_size < 1:
            raise ValueError("Inference batch size must be positive")
        started = time.perf_counter()
        self.backend = TexNNNativeBackend(root)
        self.size = size
        self.manifest = TexNNBlockCorpus.validate(run_dir / "prepared" / f"{size}x{size}")
        collection = ArtifactStore.read_json(run_dir / "collection.json")
        if (
            self.manifest["collection_sha256"]
            != ArtifactStore.sha256_file(run_dir / "collection.json")
            or collection["protocol_sha256"] != ArtifactStore.sha256_file(run_dir / "protocol.json")
            or collection["status"] != "passed"
        ):
            raise ValueError("Model corpus protocol differs from its collected training features")
        self.device = torch.device(device)
        self.batch_size = batch_size
        torch.set_num_threads(1)
        self.model_hashes: dict[str, str] = {}
        self.models = {
            network: self._load(run_dir / "models" / f"{size}x{size}" / network, network)
            for network in ["pnn", "demnn"]
        }
        self.setup_seconds = time.perf_counter() - started

    def _load(self, directory: Path, network: str) -> TexNNClassifier:
        complete = ArtifactStore.read_json(directory / "training_complete.json")
        checkpoint = directory / "best.pt"
        digest = ArtifactStore.sha256_file(checkpoint)
        if complete["status"] != "passed" or digest != complete["best_sha256"]:
            raise ValueError("TexNN checkpoint failed its training receipt hash check")
        packet = torch.load(checkpoint, map_location="cpu", weights_only=True)
        if (
            packet["network"] != network
            or packet["size"] != self.size
            or packet["data_fingerprint"] != self.manifest["fingerprint"]
            or packet["feature_protocol"] != self.manifest["feature_protocol"]
            or packet["optimization_config"]["architecture_sha256"]
            != ArtifactStore.sha256_file(Path(__file__).with_name("architectures.json"))
        ):
            raise ValueError("TexNN checkpoint is incompatible with its data or architecture")
        if network not in {"pnn", "demnn"}:
            raise ValueError("Unknown TexNN classifier")
        kind: Literal["pnn", "demnn"] = "pnn" if network == "pnn" else "demnn"
        model = TexNNClassifier((self.size, self.size), kind, **packet["model_config"]).to(
            self.device
        )
        model.load_state_dict(packet["model"], strict=True)
        model.eval()
        self.model_hashes[network] = digest
        return model

    def _top(self, network: str, features: np.ndarray, valid: int, topk: int) -> np.ndarray:
        # Appendix widths remain exact; padded unused outputs have no configuration identity.
        with torch.inference_mode():
            logits = self.models[network](torch.from_numpy(features).to(self.device))
            return logits[:, :valid].topk(topk, dim=1).indices.cpu().numpy()

    def predict(
        self,
        pixels: Path,
        destination: Path,
        *,
        partition_topk: int = 1,
        joint_topk: int = 1,
        preset: str = "exhaustive",
    ) -> dict[str, Any]:
        if (
            not 1 <= partition_topk <= len(self.manifest["partitions"])
            or not 1 <= joint_topk <= len(self.manifest["joint_labels"])
            or partition_topk * joint_topk > 1024
        ):
            raise ValueError("Top-k exceeds the available configuration vocabulary")
        started = time.perf_counter()
        destination.mkdir(parents=True, exist_ok=False)
        blocks, constant = self.backend.blocks(pixels, (self.size, self.size))
        partition_choices: list[list[TexNNConfiguration]] = [[] for _ in blocks]
        prepared_seconds = time.perf_counter() - started
        started_pnn = time.perf_counter()
        active = np.flatnonzero(~constant)
        for start in range(0, len(active), self.batch_size):
            indices = active[start : start + self.batch_size]
            selected = self._top(
                "pnn", blocks[indices], len(self.manifest["partitions"]), partition_topk
            )
            for index, labels in zip(indices, selected, strict=True):
                partition_choices[index] = [
                    TexNNConfiguration(*self.manifest["partitions"][label]) for label in labels
                ]
        pnn_seconds = time.perf_counter() - started_pnn
        footprint = (self.size, self.size)
        partition_file = destination / "partitions.bin"
        self.backend.write_predictions(partition_file, pixels, footprint, partition_choices)
        feature_file = destination / "features.jsonl"
        feature_seconds = self.backend.features(
            pixels, partition_file, feature_file, footprint, preset
        )
        configurations: list[list[TexNNConfiguration]] = [[] for _ in blocks]
        seen = np.zeros((len(blocks), partition_topk), dtype=np.bool_)
        started_dem = time.perf_counter()
        iterator = self.backend.iter_features(feature_file)
        for batch in iter(lambda: list(itertools.islice(iterator, self.batch_size)), []):
            features = []
            for row in batch:
                if (
                    row.block_index >= len(blocks)
                    or constant[row.block_index]
                    or row.candidate_index >= partition_topk
                    or seen[row.block_index, row.candidate_index]
                ):
                    raise ValueError("Duplicate or unexpected partition feature row")
                seen[row.block_index, row.candidate_index] = True
                features.append(np.concatenate((blocks[row.block_index], row.endpoints)))
            selected = self._top(
                "demnn",
                np.asarray(features, dtype=np.float32),
                len(self.manifest["joint_labels"]),
                joint_topk,
            )
            for row, labels in zip(batch, selected, strict=True):
                partition = partition_choices[row.block_index][row.candidate_index]
                for label in labels:
                    mode, dual, *endpoints = self.manifest["joint_labels"][label]
                    configurations[row.block_index].append(
                        TexNNConfiguration(
                            partition.partition_count,
                            partition.partition_index,
                            mode,
                            dual,
                            (endpoints[0], endpoints[1], endpoints[2], endpoints[3]),
                        )
                    )
        if not seen[~constant].all() or seen[constant].any():
            raise ValueError("Native feature pass missed a predicted partition")
        dem_seconds = time.perf_counter() - started_dem
        prediction_file = destination / "configurations.bin"
        self.backend.write_predictions(prediction_file, pixels, footprint, configurations)
        return {
            "predictions": str(prediction_file),
            "partition_topk": partition_topk,
            "joint_topk": joint_topk,
            "blocks": len(blocks),
            "constant_blocks": int(constant.sum()),
            "feature_rows": int(seen.sum()),
            "device": str(self.device),
            "torch_threads": torch.get_num_threads(),
            "batch_size": self.batch_size,
            "model_sha256": self.model_hashes,
            "data_fingerprint": self.manifest["fingerprint"],
            "model_setup_seconds": self.setup_seconds,
            "timings": {
                "pixel_preparation_seconds": prepared_seconds,
                "pnn_seconds": pnn_seconds,
                "native_feature_seconds": feature_seconds,
                "demnn_with_feature_io_seconds": dem_seconds,
                "prediction_pipeline_seconds": time.perf_counter() - started,
            },
        }
