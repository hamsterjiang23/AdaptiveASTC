"""Compatibility exports for existing experiment scripts."""

from adaptive_astc.config import (
    CLASSES as CLASSES,
)
from adaptive_astc.config import (
    DEFAULT_REPORT as DEFAULT_REPORT,
)
from adaptive_astc.config import (
    DEFAULT_RUN as DEFAULT_RUN,
)
from adaptive_astc.config import (
    REPORT_ROOT as REPORT_ROOT,
)
from adaptive_astc.config import (
    RUN_ID as RUN_ID,
)
from adaptive_astc.config import (
    SEED as SEED,
)
from adaptive_astc.config import (
    SNAPSHOT_SHA256 as SNAPSHOT_SHA256,
)
from adaptive_astc.config import (
    JsonDict as JsonDict,
)
from adaptive_astc.utils.artifacts import ArtifactStore
from adaptive_astc.utils.environment import RunEnvironment

read_json = ArtifactStore.read_json
write_json = ArtifactStore.write_json
sha256_file = ArtifactStore.sha256_file
fingerprint = ArtifactStore.fingerprint
environment = RunEnvironment.capture
