"""Prepare data through the shared class-based command entry point."""

import sys
from pathlib import Path

from adaptive_astc.cli import ExperimentCLI

if __name__ == "__main__":
    configuration = Path(__file__).with_name("train_config.toml")
    ExperimentCLI.main(command="prepare", arguments=["--config", str(configuration), *sys.argv[1:]])
