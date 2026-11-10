"""Frozen source snapshot filtering and content deduplication."""

from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from adaptive_astc.config import CLASSES, EXCLUDED, SNAPSHOT_SHA256, SUFFIXES, JsonDict
from adaptive_astc.data.splitting import DatasetSplitter
from adaptive_astc.utils.artifacts import ArtifactStore


class TextureCatalog:
    """Resolve eligible images against one explicitly pinned label snapshot."""

    def __init__(
        self, snapshot: Path, image_root: Path, expected_sha256: str = SNAPSHOT_SHA256
    ) -> None:
        self.snapshot = snapshot
        self.image_root = image_root
        self.expected_sha256 = expected_sha256

    def build(self) -> tuple[list[JsonDict], Counter[str], JsonDict]:
        if ArtifactStore.sha256_file(self.snapshot) != self.expected_sha256:
            raise ValueError("The source snapshot SHA-256 does not match the frozen protocol")
        document = ArtifactStore.read_json(self.snapshot)
        entries: dict[str, JsonDict] = document["entries"]
        hashes: dict[str, list[str]] = defaultdict(list)
        for path, entry in entries.items():
            hashes[str(entry["fileHash"])].append(path)
        counts: Counter[str] = Counter()
        rows: list[JsonDict] = []
        root = self.image_root.resolve()
        for content_hash, paths in sorted(hashes.items()):
            if len({entries[path]["blockSize"] for path in paths}) != 1:
                counts["conflicting_hash_groups"] += 1
                counts["conflicting_records"] += len(paths)
                continue
            candidates: list[str] = []
            for path in sorted(paths):
                relative = PurePosixPath(path)
                if path.startswith(EXCLUDED):
                    counts["excluded_resource_records"] += 1
                elif relative.suffix.lower() not in SUFFIXES:
                    counts["unsupported_extension_records"] += 1
                elif relative.is_absolute() or ".." in relative.parts or ":" in path:
                    counts["unsafe_path_records"] += 1
                elif not (root / path).is_file():
                    counts["missing_records"] += 1
                else:
                    candidates.append(path)
            if not candidates:
                continue
            path = candidates[0]
            entry = entries[path]
            rows.append(
                {
                    "path": path,
                    "fileHash": content_hash,
                    "blockSize": entry["blockSize"],
                    "class_id": CLASSES.index(entry["blockSize"]),
                    "qualityLevel": entry["qualityLevel"],
                    "rdo": entry["rdo"],
                    "psnr": entry["psnr"],
                    "msSsimDb": entry["msSsimDb"],
                    "fileSize": entry["fileSize"],
                    "group": DatasetSplitter.asset_group(path),
                    "alternatives": candidates[1:],
                }
            )
            counts["deduplicated_records"] += len(candidates) - 1
        return sorted(rows, key=lambda row: row["path"]), counts, document["tableConfig"]
