"""Audit raw-capture inference inputs against completed Unity development tensors."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.capture_input_audit import UnityCaptureInputAudit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityCaptureInputAudit(Path(__file__).resolve().parents[1], args.config).run()
    print({key: result[key] for key in ["status", "splits", "test_opened", "wall_seconds"]})


if __name__ == "__main__":
    main()
