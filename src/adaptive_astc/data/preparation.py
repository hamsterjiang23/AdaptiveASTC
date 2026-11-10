"""End-to-end deterministic preparation orchestration."""

import json
import random
import time
from collections import Counter
from pathlib import Path
from typing import cast

import numpy as np
from PIL import Image, UnidentifiedImageError

from adaptive_astc.config import CLASSES, FORMAL_SIZES, SEED, SMOKE_SIZES, SNAPSHOT_SHA256, JsonDict
from adaptive_astc.data.catalog import TextureCatalog
from adaptive_astc.data.deduplication import NearDuplicateIndex
from adaptive_astc.data.images import ImagePreprocessor
from adaptive_astc.data.splitting import DatasetSplitter
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.environment import RunEnvironment


class DataPreparer:
    """Own input locations and coordinate catalog, decoding, split, and audit."""

    def __init__(
        self,
        snapshot: Path,
        image_root: Path,
        run_dir: Path,
        report_dir: Path,
        smoke: bool = False,
        exclude_manifests: list[Path] | None = None,
        expected_sha256: str = SNAPSHOT_SHA256,
    ) -> None:
        self.snapshot = snapshot
        self.image_root = image_root
        self.run_dir = run_dir
        self.report_dir = report_dir
        self.smoke = smoke
        self.exclude_manifests = exclude_manifests
        self.catalog = TextureCatalog(snapshot, image_root, expected_sha256)
        self.preprocessor = ImagePreprocessor(image_root, run_dir)

    def run(self) -> JsonDict:
        started = time.perf_counter()
        sizes = SMOKE_SIZES if self.smoke else FORMAL_SIZES
        self.run_dir.mkdir(parents=True, exist_ok=True)
        rows, counts, config = self.catalog.build()
        rows = DatasetSplitter.assign_folds(rows)
        references: dict[str, JsonDict] = {}
        excluded_manifest_hashes: list[str] = []
        for path in self.exclude_manifests or []:
            prior = ArtifactStore.read_json(path)
            if prior["snapshot_sha256"] != self.catalog.expected_sha256:
                raise ValueError("Excluded manifest uses a different label snapshot")
            excluded_manifest_hashes.append(ArtifactStore.sha256_file(path))
            for prior_rows in prior["splits"].values():
                for row in prior_rows:
                    references[row["fileHash"]] = row
        counts["excluded_smoke_hashes"] = sum(row["fileHash"] in references for row in rows)
        rows = [row for row in rows if row["fileHash"] not in references]
        minimum_groups = 1 if self.smoke else 50
        split_folds = DatasetSplitter.select_split_folds(rows, sizes, minimum_groups)
        class_counts = [sum(row["class_id"] == label for row in rows) for label in range(4)]
        ArtifactStore.write_json(self.run_dir / "mother_pools.json", {"rows": rows})
        near_index = NearDuplicateIndex()
        for row in references.values():
            verified, preview = self.preprocessor.decode(row)
            near_index.add(verified, preview)
        manifests: dict[str, list[JsonDict]] = {}
        rejection_path = self.run_dir / "rejections.jsonl"
        with rejection_path.open("w", encoding="utf-8") as rejected:
            for split, size in sizes.items():
                selected: list[JsonDict] = []
                previews: list[np.ndarray] = []
                targets = DatasetSplitter.quotas(class_counts, size)
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
                            decoded, preview = self.preprocessor.decode(candidate)
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
                                str(error)
                                if isinstance(error, ValueError)
                                else type(error).__name__
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
                        ArtifactStore.write_json(
                            self.report_dir / "data_failure.json",
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
        audit = DatasetSplitter.audit_manifests(manifests)
        if any(
            len({row["group"] for row in manifests[split]}) < minimum_groups
            for split in split_folds
        ):
            raise ValueError("Selected holdouts have insufficient asset group coverage")
        audit["cross_split_near_duplicates"] = 0
        if references:
            if any(row["fileHash"] in references for items in manifests.values() for row in items):
                raise ValueError("Smoke image entered a formal split")
            audit["smoke_hashes_and_near_duplicates_excluded"] = True
        metadata = {
            "snapshot_sha256": self.catalog.expected_sha256,
            "seed": SEED,
            "classes": CLASSES,
            "image_root": str(self.image_root.resolve()),
            "sizes": sizes,
            "smoke": self.smoke,
        }
        if excluded_manifest_hashes:
            metadata["excluded_manifest_sha256"] = sorted(excluded_manifest_hashes)
        if not self.smoke:
            metadata["split_folds"] = split_folds
            metadata["minimum_holdout_groups"] = minimum_groups
        data_fingerprint = ArtifactStore.fingerprint({"metadata": metadata, "splits": manifests})
        previous = self.run_dir / "manifest.json"
        if (
            previous.exists()
            and ArtifactStore.read_json(previous)["fingerprint"] != data_fingerprint
        ):
            raise ValueError(
                "Re-preparation differs from the sealed manifest; use a new run directory"
            )
        ArtifactStore.write_json(
            previous, {**metadata, "fingerprint": data_fingerprint, "splits": manifests}
        )
        summary = {
            **metadata,
            "fingerprint": data_fingerprint,
            "source_records": 183051,
            "eligible_unique_hashes": len(rows),
            "eligible_class_counts": dict(zip(CLASSES, class_counts)),
            "asset_groups": len({row["group"] for row in rows}),
            "filter_counts": dict(counts),
            "mother_pool_sha256": ArtifactStore.sha256_file(self.run_dir / "mother_pools.json"),
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
            "environment": RunEnvironment.capture(),
        }
        ArtifactStore.write_json(self.report_dir / "data_summary.json", summary)
        table = "\n".join(
            f"| {split} | {info['count']} | {info['class_counts']} | {info['asset_groups']} | "
            "`[verified: data_summary.json /splits]` |"
            for split, info in summary["splits"].items()
        )
        self.report_dir.mkdir(parents=True, exist_ok=True)
        (self.report_dir / "data_report.md").write_text(
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
