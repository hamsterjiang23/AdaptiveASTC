"""CPU-only preparation API and compatibility exports."""

from collections import Counter
from pathlib import Path

import numpy as np

from adaptive_astc.config import (
    EXCLUDED as EXCLUDED,
)
from adaptive_astc.config import (
    FORMAL_SIZES as FORMAL_SIZES,
)
from adaptive_astc.config import (
    SMOKE_SIZES as SMOKE_SIZES,
)
from adaptive_astc.config import (
    SNAPSHOT_SHA256,
    JsonDict,
)
from adaptive_astc.config import (
    SUFFIXES as SUFFIXES,
)
from adaptive_astc.data.catalog import TextureCatalog as TextureCatalog
from adaptive_astc.data.deduplication import NearDuplicateIndex as NearDuplicateIndex
from adaptive_astc.data.images import ImagePreprocessor as ImagePreprocessor
from adaptive_astc.data.preparation import DataPreparer as DataPreparer
from adaptive_astc.data.splitting import DatasetSplitter as DatasetSplitter

asset_group = DatasetSplitter.asset_group
quotas = DatasetSplitter.quotas
assign_folds = DatasetSplitter.assign_folds
select_split_folds = DatasetSplitter.select_split_folds
audit_manifests = DatasetSplitter.audit_manifests


def catalog(snapshot: Path, image_root: Path) -> tuple[list[JsonDict], Counter[str], JsonDict]:
    return TextureCatalog(snapshot, image_root, SNAPSHOT_SHA256).build()


def decode_candidate(
    row: JsonDict, image_root: Path, cache_root: Path
) -> tuple[JsonDict, np.ndarray]:
    return ImagePreprocessor(image_root, cache_root).decode(row)


def prepare(
    snapshot: Path,
    image_root: Path,
    run_dir: Path,
    report_dir: Path,
    smoke: bool = False,
    exclude_manifests: list[Path] | None = None,
) -> JsonDict:
    return DataPreparer(
        snapshot, image_root, run_dir, report_dir, smoke, exclude_manifests, SNAPSHOT_SHA256
    ).run()
