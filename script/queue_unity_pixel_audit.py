"""Audit native development and confirmation pixels after their capture jobs pass."""

from __future__ import annotations

import argparse
from pathlib import Path

from reproductions.unity_search_baseline.pixel_audit_pipeline import UnityPixelAuditPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = UnityPixelAuditPipeline(Path(__file__).resolve().parents[1], args.config).run()
    print({key: result[key] for key in ["status", "counts", "wall_seconds", "test_opened"]})


if __name__ == "__main__":
    main()
