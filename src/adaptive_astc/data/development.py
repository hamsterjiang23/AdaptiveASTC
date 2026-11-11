"""Verified train/validation views of an existing measured GDC corpus."""

from pathlib import Path

import numpy as np

from adaptive_astc.config import CLASSES, JsonDict
from adaptive_astc.utils.artifacts import ArtifactStore


class MeasuredDevelopmentData:
    def __init__(self, source: Path) -> None:
        self.source = source.resolve()

    def load(self, train_limit: int = 0, validation_limit: int = 0) -> JsonDict:
        if min(train_limit, validation_limit) < 0:
            raise ValueError("Development limits must be nonnegative")
        manifest_path = self.source / "manifest.json"
        manifest = ArtifactStore.read_json(manifest_path)
        if manifest["classes"] != list(CLASSES):
            raise ValueError("Unexpected class ordering")
        protocol = ArtifactStore.read_json(self.source / "protocol.json")
        if (
            ArtifactStore.sha256_file(self.source / "protocol.json")
            != manifest["label_protocol_sha256"]
        ):
            raise ValueError("Measured GDC protocol changed")
        indexes = {item["path"]: index for index, item in enumerate(protocol["inputs"])}
        splits: dict[str, list[JsonDict]] = {}
        for split, limit in [("train", train_limit), ("validation", validation_limit)]:
            rows = manifest["splits"][split]
            if limit and limit < len(rows):
                rows = [rows[int(i)] for i in np.linspace(0, len(rows) - 1, limit, dtype=int)]
            for row in rows:
                receipt_path = (
                    self.source / "labels" / f"{indexes[row['path']]:05d}" / "receipt.json"
                )
                if ArtifactStore.sha256_file(receipt_path) != row["label_receipt_sha256"]:
                    raise ValueError("GDC label receipt changed")
                receipt = ArtifactStore.read_json(receipt_path)
                if (
                    receipt["status"] != "passed"
                    or receipt["path"] != row["path"]
                    or receipt["split"] != split
                    or receipt["selected"]["name"] != CLASSES[row["class_id"]]
                ):
                    raise ValueError("GDC label identity changed")
                cache = self.source / row["cache"]
                if ArtifactStore.sha256_file(cache) != row["cache_sha256"]:
                    raise ValueError("Frozen RGB224 cache changed")
                pixels = np.load(cache, allow_pickle=False)
                if pixels.shape != (224, 224, 3) or pixels.dtype != np.uint8:
                    raise ValueError("Expected frozen RGB224 uint8 pixels")
            splits[split] = rows
        if {row["group"] for row in splits["train"]} & {
            row["group"] for row in splits["validation"]
        }:
            raise ValueError("Train and validation asset groups overlap")
        result = {
            "source_manifest_sha256": ArtifactStore.sha256_file(manifest_path),
            "source_root": str(self.source),
            "classes": list(CLASSES),
            "splits": splits,
            "counts": {split: len(rows) for split, rows in splits.items()},
            "test_opened": False,
        }
        result["fingerprint"] = ArtifactStore.fingerprint(result)
        return result
