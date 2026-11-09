"""Deterministic, asset-isolated source-image preparation."""

import json
import math
import random
import time
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import cast

import imagehash
import numpy as np
from Crypto.Hash import MD4
from PIL import Image, UnidentifiedImageError
from sklearn.model_selection import StratifiedGroupKFold

from adaptive_astc.common import (
    CLASSES,
    SEED,
    SNAPSHOT_SHA256,
    JsonDict,
    environment,
    fingerprint,
    read_json,
    sha256_file,
    write_json,
)

FORMAL_SIZES = {"test": 2000, "calibration": 1000, "validation": 1000, "train": 10000}
SMOKE_SIZES = {"test": 16, "calibration": 8, "validation": 8, "train": 32}
SUFFIXES = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff"}
EXCLUDED = (
    "Assets/Editor/",
    "Assets/Editor Default Resources/",
    "Assets/Plugins/",
    "Assets/Tools/",
    "Packages/",
)


def asset_group(path: str) -> str:
    parts = PurePosixPath(path).parts
    if parts[:3] in (
        ("Assets", "Art", "Characters"),
        ("Assets", "Art", "Monster"),
        ("Assets", "Art", "Environment"),
    ):
        return "/".join(parts[:4])
    parent = list(parts[:-1])
    if parent and parent[-1].upper() in {"SD", "HD", "FHD"}:
        parent.pop()
    return "/".join(parent)


def quotas(counts: list[int], total: int) -> list[int]:
    shares = [count * total / sum(counts) for count in counts]
    result = [math.floor(share) for share in shares]
    order = sorted(range(len(counts)), key=lambda index: (-(shares[index] - result[index]), index))
    for index in order[: total - sum(result)]:
        result[index] += 1
    return result


def catalog(snapshot: Path, image_root: Path) -> tuple[list[JsonDict], Counter[str], JsonDict]:
    if sha256_file(snapshot) != SNAPSHOT_SHA256:
        raise ValueError("The source snapshot SHA-256 does not match the frozen protocol")
    document = read_json(snapshot)
    entries: dict[str, JsonDict] = document["entries"]
    hashes: dict[str, list[str]] = defaultdict(list)
    for path, entry in entries.items():
        hashes[str(entry["fileHash"])].append(path)
    counts: Counter[str] = Counter()
    rows: list[JsonDict] = []
    root = image_root.resolve()
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
                "group": asset_group(path),
                "alternatives": candidates[1:],
            }
        )
        counts["deduplicated_records"] += len(candidates) - 1
    return sorted(rows, key=lambda row: row["path"]), counts, document["tableConfig"]


def assign_folds(rows: list[JsonDict]) -> list[JsonDict]:
    labels = [row["class_id"] for row in rows]
    groups = [row["group"] for row in rows]
    splitter = StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=SEED)
    for fold, (_, indices) in enumerate(splitter.split(np.zeros(len(rows)), labels, groups)):
        for index in indices:
            rows[index]["fold"] = fold
    return rows


def select_split_folds(
    rows: list[JsonDict], sizes: dict[str, int], min_groups: int
) -> dict[str, int]:
    counts = [sum(row["class_id"] == label for row in rows) for label in range(4)]
    required = quotas(counts, max(sizes.values()) if min_groups == 1 else sizes["test"])
    eligible: list[int] = []
    for fold in range(10):
        members = [row for row in rows if row["fold"] == fold]
        group_count = len({row["group"] for row in members})
        labels = Counter(row["class_id"] for row in members)
        if group_count >= min_groups and all(
            labels[label] >= required[label] for label in range(4)
        ):
            eligible.append(fold)
    if len(eligible) < 3:
        raise ValueError("Three class-supported, multi-asset holdout folds are required")
    return dict(zip(("test", "calibration", "validation"), eligible[:3], strict=True))


def decode_candidate(
    row: JsonDict, image_root: Path, cache_root: Path
) -> tuple[JsonDict, np.ndarray]:
    source = image_root / str(row["path"])
    digest = MD4.new()
    with source.open("rb") as stream:
        header = stream.read(32)
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            if len(header) < 25:
                raise ValueError("truncated_png_header")
            if header[24] > 8:
                raise ValueError("unsupported_png_bit_depth")
        stream.seek(0)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != str(row["fileHash"]).lower():
        raise ValueError("md4_mismatch")
    with Image.open(source) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("multiframe")
        if image.format == "TIFF":
            bits = getattr(image, "tag_v2", {}).get(258, (8,))
            samples = (bits,) if isinstance(bits, int) else bits
            if any(value > 8 for value in samples):
                raise ValueError("unsupported_tiff_bit_depth")
        if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK"}:
            raise ValueError("unsupported_pixel_mode")
        image.load()
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        alpha_nonopaque = False
        if has_alpha:
            alpha_range = cast(tuple[int, int], image.convert("RGBA").getchannel("A").getextrema())
            alpha_nonopaque = alpha_range[0] < 255
        rgb = image.convert("RGB")
        preview = np.asarray(rgb.resize((32, 32), Image.Resampling.BILINEAR), dtype=np.uint8)
        phash = int(str(imagehash.phash(rgb, hash_size=8)), 16)
        pixels = np.asarray(rgb.resize((224, 224), Image.Resampling.BILINEAR), dtype=np.uint8)
        width, height = image.size
    relative_cache = Path("cache") / str(row["fileHash"])[:2] / f"{row['fileHash']}.npy"
    target = cache_root / relative_cache
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, pixels, allow_pickle=False)
    if target.exists():
        if sha256_file(target) != sha256_file(temporary):
            raise RuntimeError("Existing image cache differs; prepare a new run directory")
        temporary.unlink()
    else:
        temporary.replace(target)
    result = dict(row)
    result.update(
        {
            "width": width,
            "height": height,
            "has_alpha": has_alpha,
            "alpha_nonopaque": alpha_nonopaque,
            "phash": phash,
            "cache": relative_cache.as_posix(),
            "cache_sha256": sha256_file(target),
        }
    )
    result.pop("alternatives", None)
    return result, preview


class NearDuplicateIndex:
    """Five bands retrieve every Hamming-distance-at-most-four candidate."""

    def __init__(self) -> None:
        self.bands: dict[tuple[int, int], set[int]] = defaultdict(set)
        self.items: list[tuple[JsonDict, np.ndarray]] = []

    @staticmethod
    def keys(value: int) -> list[tuple[int, int]]:
        return [(band, (value >> (13 * band)) & 8191) for band in range(5)]

    def match(self, row: JsonDict, preview: np.ndarray) -> str | None:
        candidates: set[int] = set()
        for key in self.keys(int(row["phash"])):
            candidates.update(self.bands.get(key, set()))
        aspect = row["width"] / row["height"]
        for index in sorted(candidates):
            other, other_preview = self.items[index]
            if (int(row["phash"]) ^ int(other["phash"])).bit_count() > 4:
                continue
            if abs(aspect / (other["width"] / other["height"]) - 1) > 0.01:
                continue
            difference = preview.astype(np.float32) - other_preview.astype(np.float32)
            if float(np.mean(difference**2)) <= 9:
                return str(other["path"])
        return None

    def add(self, row: JsonDict, preview: np.ndarray) -> None:
        index = len(self.items)
        self.items.append((row, preview))
        for key in self.keys(int(row["phash"])):
            self.bands[key].add(index)


def audit_manifests(manifests: dict[str, list[JsonDict]]) -> JsonDict:
    seen_hashes: set[str] = set()
    seen_groups: set[str] = set()
    for split in FORMAL_SIZES:
        rows = manifests[split]
        hashes = {str(row["fileHash"]) for row in rows}
        groups = {str(row["group"]) for row in rows}
        if len(hashes) != len(rows) or seen_hashes & hashes or seen_groups & groups:
            raise ValueError(f"Cross-split hash/group isolation failed for {split}")
        seen_hashes.update(hashes)
        seen_groups.update(groups)
    return {"content_hash_disjoint": True, "asset_group_disjoint": True}


def prepare(
    snapshot: Path,
    image_root: Path,
    run_dir: Path,
    report_dir: Path,
    smoke: bool = False,
    exclude_manifests: list[Path] | None = None,
) -> JsonDict:
    started = time.perf_counter()
    sizes = SMOKE_SIZES if smoke else FORMAL_SIZES
    run_dir.mkdir(parents=True, exist_ok=True)
    rows, counts, config = catalog(snapshot, image_root)
    rows = assign_folds(rows)
    references: dict[str, JsonDict] = {}
    excluded_manifest_hashes: list[str] = []
    for path in exclude_manifests or []:
        prior = read_json(path)
        if prior["snapshot_sha256"] != SNAPSHOT_SHA256:
            raise ValueError("Excluded manifest uses a different label snapshot")
        excluded_manifest_hashes.append(sha256_file(path))
        for prior_rows in prior["splits"].values():
            for row in prior_rows:
                references[row["fileHash"]] = row
    counts["excluded_smoke_hashes"] = sum(row["fileHash"] in references for row in rows)
    rows = [row for row in rows if row["fileHash"] not in references]
    minimum_groups = 1 if smoke else 50
    split_folds = select_split_folds(rows, sizes, minimum_groups)
    class_counts = [sum(row["class_id"] == label for row in rows) for label in range(4)]
    write_json(run_dir / "mother_pools.json", {"rows": rows})
    near_index = NearDuplicateIndex()
    for row in references.values():
        verified, preview = decode_candidate(row, image_root, run_dir)
        near_index.add(verified, preview)
    manifests: dict[str, list[JsonDict]] = {}
    rejection_path = run_dir / "rejections.jsonl"
    with rejection_path.open("w", encoding="utf-8") as rejected:
        for split, size in sizes.items():
            selected: list[JsonDict] = []
            previews: list[np.ndarray] = []
            targets = quotas(class_counts, size)
            for label, required in enumerate(targets):
                fold = split_folds.get(split)
                pool = [
                    row
                    for row in rows
                    if row["class_id"] == label
                    and (
                        row["fold"] == fold
                        if fold is not None
                        else row["fold"] not in split_folds.values()
                    )
                ]
                random.Random(SEED + label + list(sizes).index(split) * 100).shuffle(pool)
                accepted = 0
                for candidate in pool:
                    if accepted == required:
                        break
                    try:
                        decoded, preview = decode_candidate(candidate, image_root, run_dir)
                        match = near_index.match(decoded, preview)
                        if match is not None:
                            raise ValueError("cross_split_near_duplicate")
                    except (
                        ValueError,
                        OSError,
                        UnidentifiedImageError,
                        Image.DecompressionBombError,
                    ) as error:
                        reason = (
                            str(error) if isinstance(error, ValueError) else type(error).__name__
                        )
                        counts[f"rejected_{reason}"] += 1
                        rejected.write(
                            json.dumps({"path": candidate["path"], "reason": reason}) + "\n"
                        )
                        continue
                    selected.append(decoded)
                    previews.append(preview)
                    accepted += 1
                if accepted != required:
                    write_json(
                        report_dir / "data_failure.json",
                        {
                            "split": split,
                            "class": CLASSES[label],
                            "required": required,
                            "accepted": accepted,
                            "counts": dict(counts),
                        },
                    )
                    raise ValueError(
                        f"Insufficient {split} {CLASSES[label]}: {accepted}/{required}"
                    )
            for selected_row, preview in zip(selected, previews, strict=True):
                near_index.add(selected_row, preview)
            selected.sort(key=lambda row: row["path"])
            manifests[split] = selected
            print(f"prepared {split}={len(selected)}", flush=True)
    audit = audit_manifests(manifests)
    if any(
        len({row["group"] for row in manifests[split]}) < minimum_groups for split in split_folds
    ):
        raise ValueError("Selected holdouts have insufficient asset group coverage")
    audit["cross_split_near_duplicates"] = 0
    if references:
        if any(row["fileHash"] in references for items in manifests.values() for row in items):
            raise ValueError("Smoke image entered a formal split")
        audit["smoke_hashes_and_near_duplicates_excluded"] = True
    metadata = {
        "snapshot_sha256": SNAPSHOT_SHA256,
        "seed": SEED,
        "classes": CLASSES,
        "image_root": str(image_root.resolve()),
        "sizes": sizes,
        "smoke": smoke,
    }
    if excluded_manifest_hashes:
        metadata["excluded_manifest_sha256"] = sorted(excluded_manifest_hashes)
    if not smoke:
        metadata["split_folds"] = split_folds
        metadata["minimum_holdout_groups"] = minimum_groups
    data_fingerprint = fingerprint({"metadata": metadata, "splits": manifests})
    previous = run_dir / "manifest.json"
    if previous.exists() and read_json(previous)["fingerprint"] != data_fingerprint:
        raise ValueError("Re-preparation differs from the sealed manifest; use a new run directory")
    write_json(previous, {**metadata, "fingerprint": data_fingerprint, "splits": manifests})
    summary = {
        **metadata,
        "fingerprint": data_fingerprint,
        "source_records": 183051,
        "eligible_unique_hashes": len(rows),
        "eligible_class_counts": dict(zip(CLASSES, class_counts)),
        "asset_groups": len({row["group"] for row in rows}),
        "filter_counts": dict(counts),
        "mother_pool_sha256": sha256_file(run_dir / "mother_pools.json"),
        "split_folds": split_folds,
        "table_config": config,
        "audit": audit,
        "splits": {
            split: {
                "count": len(items),
                "class_counts": dict(Counter(row["blockSize"] for row in items)),
                "asset_groups": len({row["group"] for row in items}),
                "alpha_nonopaque": sum(row["alpha_nonopaque"] for row in items),
                "presets": dict(Counter(row["qualityLevel"] for row in items)),
                "rdo": dict(Counter(str(row["rdo"]) for row in items)),
            }
            for split, items in manifests.items()
        },
        "elapsed_seconds": time.perf_counter() - started,
        "environment": environment(),
    }
    write_json(report_dir / "data_summary.json", summary)
    table = "\n".join(
        f"| {split} | {info['count']} | {info['class_counts']} | {info['asset_groups']} | "
        "`[verified: data_summary.json /splits]` |"
        for split, info in summary["splits"].items()
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "data_report.md").write_text(
        "# 数据准备报告\n\n"
        f"清单指纹为`{data_fingerprint}`。`[verified: data_summary.json /fingerprint]`\n\n"
        "| 集合 | 数量 | 类别数量 | 资产组数 | 证据 |\n|---|---|---|---|---|\n" + table + "\n\n"
        "入选图片逐张MD4和解码检查通过，跨集合内容哈希、资产组及协议近重复检查通过。"
        "`[verified: data_summary.json /audit；prepare完成路径]`\n\n"
        "近重复审计使用协议中的pHash、宽高比和RGB缩略图阈值；清洗、Alpha、preset和RDO分布"
        "见配套统计。训练输入为RGB源图，标签为LITE历史策略。"
        "`[verified: data_summary.json /splits、/table_config]`\n",
        encoding="utf-8",
    )
    return cast(JsonDict, summary)
