"""Run an auditable reproduction command independently of the chat tool session."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reproductions.common.jobs import ReproductionJob  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = ReproductionJob(ROOT, args.config).run()
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
