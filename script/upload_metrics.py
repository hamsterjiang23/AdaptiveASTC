"""Upload existing results with their historical source fingerprints."""

import sys
from pathlib import Path

from adaptive_astc.tracking.upload import MetricsUploader

if __name__ == "__main__":
    configuration = Path(__file__).with_name("train_config.toml")
    MetricsUploader.main(["--config", str(configuration), *sys.argv[1:]])
